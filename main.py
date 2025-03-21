    #!/usr/bin/env python3
"""
SDS011 Air Quality Monitoring System with AI Assistant "Puff"
A comprehensive system for monitoring air quality using the SDS011 sensor,
featuring a modern web interface and voice-activated AI assistant.
"""

import os
import json
import time
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, jsonify, request
import serial
import speech_recognition as sr
from gtts import gTTS
import pyaudio
from flask_sock import Sock

# Global Configuration
DB_FILENAME = "sensor_data.db"
SENSOR_PORT = "/dev/ttyUSB0"  # Adjust based on your system
BAUD_RATE = 9600
READ_TIMEOUT = 2
SENSOR_READ_INTERVAL = 5  # seconds between readings

# Initialize Flask app and WebSocket
app = Flask(__name__)
sock = Sock(app)

# Global WebSocket clients list
ws_clients = set()

# HTML Templates
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { 
            font-family: 'Inter', sans-serif;
            transition: background-color 0.3s ease;
        }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }
        .glass:hover {
            background: rgba(255, 255, 255, 0.8);
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
        }
        .nav-link {
            position: relative;
            transition: color 0.3s ease;
        }
        .nav-link::after {
            content: '';
            position: absolute;
            width: 0;
            height: 2px;
            bottom: -4px;
            left: 0;
            background-color: #3B82F6;
            transition: width 0.3s ease;
        }
        .nav-link:hover::after {
            width: 100%;
        }
        .card {
            transform: translateY(0);
            transition: all 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .button {
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .button::after {
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            top: 0;
            left: -100%;
            background: linear-gradient(
                90deg,
                rgba(255,255,255,0) 0%,
                rgba(255,255,255,0.2) 50%,
                rgba(255,255,255,0) 100%
            );
            transition: left 0.5s ease;
        }
        .button:hover::after {
            left: 100%;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in {
            animation: fadeIn 0.5s ease forwards;
        }
        .page-transition {
            opacity: 0;
            transform: translateY(20px);
            animation: fadeIn 0.5s ease forwards;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800 fade-in">Air Quality Monitor</div>
                <div class="space-x-8">
                    <a href="/" class="nav-link text-gray-600 hover:text-gray-900 transition-all">Dashboard</a>
                    <a href="/history" class="nav-link text-gray-600 hover:text-gray-900 transition-all">History</a>
                    <a href="/settings" class="nav-link text-gray-600 hover:text-gray-900 transition-all">Settings</a>
                    <a href="/onboarding" class="nav-link text-gray-600 hover:text-gray-900 transition-all">Help</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg backdrop-blur-lg transition-all duration-300 hover:shadow-xl page-transition">
            <h1 class="text-2xl font-semibold text-gray-800 mb-6 fade-in">Real-time Air Quality</h1>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div class="card transition-transform duration-300">
                    <canvas id="gaugeChart" class="w-full"></canvas>
                </div>
                <div class="space-y-6">
                    <div class="glass rounded-xl p-6 card hover:shadow-lg transition-all duration-300">
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Current Readings</h2>
                        <div class="grid grid-cols-2 gap-4">
                            <div class="transition-all duration-300">
                                <div class="text-sm text-gray-600">PM2.5</div>
                                <div id="pm25" class="text-2xl font-semibold text-gray-800 transition-opacity duration-200">--</div>
                            </div>
                            <div class="transition-all duration-300">
                                <div class="text-sm text-gray-600">PM10</div>
                                <div id="pm10" class="text-2xl font-semibold text-gray-800 transition-opacity duration-200">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="glass rounded-xl p-6 card hover:shadow-lg transition-all duration-300">
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Voice Assistant</h2>
                        <button onclick="activatePuff()" class="button bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg transition-all duration-300 w-full transform hover:scale-[1.02]">
                            <i class="fas fa-microphone mr-2"></i>Ask Puff
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <div id="responseOverlay" class="fixed inset-0 hidden z-[9999] transition-all duration-300">
        <div class="absolute inset-0 bg-black/70 backdrop-blur-md transition-all duration-300"></div>
        <div class="relative w-full h-full flex items-center justify-center">
            <div id="responseText" class="glass bg-white/90 p-8 rounded-xl max-w-2xl mx-4 text-2xl text-gray-800 font-medium shadow-xl transform transition-all duration-300 scale-95 opacity-0">
                <div class="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer"></div>
            </div>
        </div>
    </div>

    <style>
        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        .animate-shimmer {
            animation: shimmer 2s infinite;
        }
        #responseOverlay.active #responseText {
            opacity: 1;
            transform: scale(100%);
        }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
        }
    </style>

    <script>
        // WebSocket connection
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            const overlay = document.getElementById('responseOverlay');
            
            if (data.type === 'response') {
                const responseText = document.getElementById('responseText');
                responseText.textContent = data.data.text;
                overlay.classList.remove('hidden');
                overlay.classList.add('flex');
                
                setTimeout(() => {
                    overlay.classList.add('hidden');
                    overlay.classList.remove('flex');
                }, 5000);
            }
        };

        // Initialize gauge chart with smooth animations
        const ctx = document.getElementById('gaugeChart').getContext('2d');
        const gaugeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [0, 100],
                    backgroundColor: ['#10B981', '#E5E7EB'],
                    circumference: 180,
                    rotation: 270,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                animation: {
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }
            }
        });

        // Add gradient to gauge
        const gradient = ctx.createLinearGradient(0, 0, 200, 0);
        gradient.addColorStop(0, '#10B981');    // Green
        gradient.addColorStop(0.5, '#3B82F6');  // Blue
        gradient.addColorStop(1, '#6366F1');    // Indigo

        // Update readings with smooth animations
        function updateReadings() {
            fetch('/api/current')
                .then(response => response.json())
                .then(data => {
                    // Update numerical displays with fade
                    const pm25Display = document.getElementById('pm25');
                    const pm10Display = document.getElementById('pm10');
                    
                    pm25Display.style.opacity = '0';
                    pm10Display.style.opacity = '0';
                    
                    setTimeout(() => {
                        pm25Display.textContent = data.pm25.toFixed(1);
                        pm10Display.textContent = data.pm10.toFixed(1);
                        pm25Display.style.opacity = '1';
                        pm10Display.style.opacity = '1';
                    }, 200);
                    
                    // Update gauge with enhanced scaling
                    const pm25 = data.pm25;
                    // Use logarithmic scaling for better visualization
                    const percentage = Math.min(
                        (Math.log(pm25 + 1) / Math.log(100)) * 100,
                        100
                    );
                    
                    gaugeChart.data.datasets[0].data = [percentage, 100 - percentage];
                    
                    // Dynamic gradient based on value
                    let gradientColors;
                    if (pm25 < 12) {
                        gradientColors = [
                            { stop: 0, color: '#10B981' },    // Green
                            { stop: 1, color: '#34D399' }     // Light green
                        ];
                    } else if (pm25 < 35) {
                        gradientColors = [
                            { stop: 0, color: '#FBBF24' },    // Yellow
                            { stop: 1, color: '#F59E0B' }     // Dark yellow
                        ];
                    } else {
                        gradientColors = [
                            { stop: 0, color: '#EF4444' },    // Red
                            { stop: 1, color: '#DC2626' }     // Dark red
                        ];
                    }
                    
                    const gradient = ctx.createLinearGradient(0, 0, 200, 0);
                    gradientColors.forEach(({stop, color}) => {
                        gradient.addColorStop(stop, color);
                    });
                    
                    gaugeChart.data.datasets[0].backgroundColor[0] = gradient;
                    gaugeChart.update('none'); // Update without animation for smoother transitions
                })
                .catch(error => console.error('Error:', error));
        }

        updateReadings();
        setInterval(updateReadings, 5000);

        // Voice assistant activation
        function activatePuff() {
            fetch('/api/puff', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: "What's the current air quality?"
                })
            })
            .then(response => response.json())
            .then(data => {
                const overlay = document.getElementById('responseOverlay');
                const responseText = document.getElementById('responseText');
                responseText.textContent = data.response;
                overlay.classList.remove('hidden');
                overlay.classList.add('flex');
                
                setTimeout(() => {
                    overlay.classList.add('hidden');
                    overlay.classList.remove('flex');
                }, 5000);
            })
            .catch(error => console.error('Error:', error));
        }
    </script>
</body>
</html>
"""

history_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality History</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Air Quality History</div>
                <div class="space-x-6">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                    <a href="/onboarding" class="text-gray-600 hover:text-gray-900">Help</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <div class="flex justify-between items-center mb-6">
                <h1 class="text-2xl font-semibold text-gray-800">Historical Data</h1>
                <div class="space-x-4">
                    <button onclick="loadData('24h')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors">24 Hours</button>
                    <button onclick="loadData('7d')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors">7 Days</button>
                    <button onclick="loadData('30d')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors">30 Days</button>
                </div>
            </div>
            <div class="h-96">
                <canvas id="historyChart"></canvas>
            </div>
        </div>
    </main>

    <script>
        const ctx = document.getElementById('historyChart').getContext('2d');
        let historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'PM2.5',
                        data: [],
                        borderColor: '#3B82F6',
                        tension: 0.1
                    },
                    {
                        label: 'PM10',
                        data: [],
                        borderColor: '#10B981',
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });

        function loadData(timeframe) {
            fetch(`/api/history?timeframe=${timeframe}`)
                .then(response => response.json())
                .then(data => {
                    historyChart.data.labels = data.timestamps;
                    historyChart.data.datasets[0].data = data.pm25_values;
                    historyChart.data.datasets[1].data = data.pm10_values;
                    historyChart.update();
                })
                .catch(error => console.error('Error:', error));
        }

        // Load last 24 hours by default
        loadData('24h');
    </script>
</body>
</html>
"""

settings_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Settings</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Settings</div>
                <div class="space-x-6">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                    <a href="/onboarding" class="text-gray-600 hover:text-gray-900">Help</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <h1 class="text-2xl font-semibold text-gray-800 mb-6">Sensor Settings</h1>
            <form id="settingsForm" class="space-y-6">
                <div class="space-y-4">
                    <h2 class="text-lg font-medium text-gray-800">PM2.5 Thresholds</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Warning Level</label>
                            <input type="number" name="pm25_warning" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" min="0" step="0.1">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Critical Level</label>
                            <input type="number" name="pm25_critical" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" min="0" step="0.1">
                        </div>
                    </div>
                </div>

                <div class="space-y-4">
                    <h2 class="text-lg font-medium text-gray-800">PM10 Thresholds</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Warning Level</label>
                            <input type="number" name="pm10_warning" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" min="0" step="0.1">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Critical Level</label>
                            <input type="number" name="pm10_critical" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" min="0" step="0.1">
                        </div>
                    </div>
                </div>

                <div class="space-y-4">
                    <h2 class="text-lg font-medium text-gray-800">Sensor Calibration</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700">PM2.5 Calibration Factor</label>
                            <input type="number" name="pm25_calibration" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" step="0.01">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700">PM10 Calibration Factor</label>
                            <input type="number" name="pm10_calibration" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500" step="0.01">
                        </div>
                    </div>
                </div>

                <div class="pt-4">
                    <button type="submit" class="w-full bg-blue-500 text-white px-4 py-2 rounded-lg hover:bg-blue-600 transition-colors">
                        Save Settings
                    </button>
                </div>
            </form>
        </div>
    </main>

    <script>
        // Load current settings
        fetch('/api/settings')
            .then(response => response.json())
            .then(data => {
                document.querySelector('[name="pm25_warning"]').value = data.pm25_warning;
                document.querySelector('[name="pm25_critical"]').value = data.pm25_critical;
                document.querySelector('[name="pm10_warning"]').value = data.pm10_warning;
                document.querySelector('[name="pm10_critical"]').value = data.pm10_critical;
                document.querySelector('[name="pm25_calibration"]').value = data.pm25_calibration;
                document.querySelector('[name="pm10_calibration"]').value = data.pm10_calibration;
            })
            .catch(error => console.error('Error:', error));

        // Handle form submission
        document.getElementById('settingsForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = {
                pm25_warning: parseFloat(document.querySelector('[name="pm25_warning"]').value),
                pm25_critical: parseFloat(document.querySelector('[name="pm25_critical"]').value),
                pm10_warning: parseFloat(document.querySelector('[name="pm10_warning"]').value),
                pm10_critical: parseFloat(document.querySelector('[name="pm10_critical"]').value),
                pm25_calibration: parseFloat(document.querySelector('[name="pm25_calibration"]').value),
                pm10_calibration: parseFloat(document.querySelector('[name="pm10_calibration"]').value)
            };

            fetch('/api/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                alert('Settings saved successfully!');
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error saving settings. Please try again.');
            });
        });
    </script>
</body>
</html>
"""

onboarding_html = """

<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor - Help</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Help & Guide</div>
                <div class="space-x-6">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                    <a href="/onboarding" class="text-gray-600 hover:text-gray-900">Help</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <div class="max-w-3xl mx-auto space-y-8">
                <section>
                    <h2 class="text-2xl font-semibold text-gray-800 mb-4">Welcome to Your Air Quality Monitor</h2>
                    <p class="text-gray-600">This system helps you monitor air quality in real-time using the SDS011 sensor.</p>
                </section>

                <section>
                    <h3 class="text-xl font-medium text-gray-800 mb-3">Dashboard Overview</h3>
                    <div class="space-y-4">
                        <div class="glass rounded-xl p-4">
                            <h4 class="font-medium text-gray-800 mb-2">Gauge Display</h4>
                            <p class="text-gray-600">Shows current PM2.5 levels with color indicators:</p>
                            <ul class="list-disc list-inside text-gray-600 ml-4 mt-2">
                                <li>Green: Good air quality (0-12 μg/m³)</li>
                                <li>Yellow: Moderate levels (12-35 μg/m³)</li>
                                <li>Red: Poor air quality (>35 μg/m³)</li>
                            </ul>
                        </div>

                        <div class="glass rounded-xl p-4">
                            <h4 class="font-medium text-gray-800 mb-2">Voice Assistant</h4>
                            <p class="text-gray-600">Meet Puff, your air quality assistant. Try these commands:</p>
                            <ul class="list-disc list-inside text-gray-600 ml-4 mt-2">
                                <li>"What's the current air quality?"</li>
                                <li>"Show me today's highest reading"</li>
                                <li>"When did PM levels spike last?"</li>
                            </ul>
                        </div>
                    </div>
                </section>

                <section>
                    <h3 class="text-xl font-medium text-gray-800 mb-3">History & Trends</h3>
                    <p class="text-gray-600 mb-4">View historical data and trends in the History page:</p>
                    <ul class="list-disc list-inside text-gray-600 ml-4">
                        <li>24-hour view for detailed daily patterns</li>
                        <li>7-day view for weekly trends</li>
                        <li>30-day view for monthly analysis</li>
                    </ul>
                </section>

                <section>
                    <h3 class="text-xl font-medium text-gray-800 mb-3">Customizing Settings</h3>
                    <p class="text-gray-600 mb-4">Adjust your monitoring preferences:</p>
                    <ul class="list-disc list-inside text-gray-600 ml-4">
                        <li>Set custom warning thresholds</li>
                        <li>Configure critical level alerts</li>
                        <li>Calibrate sensor readings</li>
                    </ul>
                </section>
            </div>
        </div>
    </main>
</body>
</html>
"""
@sock.route('/ws')
def ws_handler(ws):
    """Handle WebSocket connections."""
    ws_clients.add(ws)
    try:
        while True:
            # Keep connection alive
            ws.receive()
    except:
        ws_clients.remove(ws)

def broadcast_to_clients(message_type, data):
    """Broadcast messages to all connected clients."""
    message = json.dumps({
        'type': message_type,
        'data': data
    })
    dead_clients = set()
    
    for client in ws_clients:
        try:
            client.send(message)
        except:
            dead_clients.add(client)
    
    # Remove dead clients
    for client in dead_clients:
        ws_clients.remove(client)

def broadcast_listening_status(status):
    """Broadcast listening status to all connected clients."""
    broadcast_to_clients('status', {'status': status})

def broadcast_response(response_text):
    """Broadcast response text to all connected clients."""
    broadcast_to_clients('response', {'text': response_text})

def setup_logger():
    """Configure and return a logger instance."""
    logger = logging.getLogger('air_quality_monitor')
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

# Initialize logger
logger = setup_logger()

def init_db():
    """Initialize the SQLite database and create necessary tables."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        
        # Create sensor readings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pm25 REAL NOT NULL,
                pm10 REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pm25_warning REAL DEFAULT 12.0,
                pm25_critical REAL DEFAULT 35.0,
                pm10_warning REAL DEFAULT 54.0,
                pm10_critical REAL DEFAULT 154.0,
                pm25_calibration REAL DEFAULT 1.0,
                pm10_calibration REAL DEFAULT 1.0
            )
        ''')
        
        # Insert default settings if none exist
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (
                    pm25_warning, pm25_critical, 
                    pm10_warning, pm10_critical,
                    pm25_calibration, pm10_calibration
                ) VALUES (12.0, 35.0, 54.0, 154.0, 1.0, 1.0)
            ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

def query_current():
    """Get the most recent sensor reading."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pm25, pm10, timestamp 
            FROM sensor_readings 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'pm25': result[0],
                'pm10': result[1],
                'timestamp': result[2]
            }
        return None
    except Exception as e:
        logger.error(f"Error querying current reading: {str(e)}")
        raise

def query_history(timeframe='24h'):
    """Get historical sensor readings based on timeframe."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        
        if timeframe == '24h':
            time_filter = "datetime('now', '-1 day')"
        elif timeframe == '7d':
            time_filter = "datetime('now', '-7 days')"
        elif timeframe == '30d':
            time_filter = "datetime('now', '-30 days')"
        else:
            time_filter = "datetime('now', '-1 day')"
        
        cursor.execute(f'''
            SELECT pm25, pm10, timestamp 
            FROM sensor_readings 
            WHERE timestamp > {time_filter}
            ORDER BY timestamp ASC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return {
            'pm25_values': [r[0] for r in results],
            'pm10_values': [r[1] for r in results],
            'timestamps': [r[2] for r in results]
        }
    except Exception as e:
        logger.error(f"Error querying historical data: {str(e)}")
        raise

def get_highest_reading(timeframe='24h'):
    """Get the highest PM readings within the specified timeframe."""
    try:
        history = query_history(timeframe)
        if history and history['pm25_values']:
            max_pm25 = max(history['pm25_values'])
            max_pm10 = max(history['pm10_values'])
            max_pm25_idx = history['pm25_values'].index(max_pm25)
            max_pm10_idx = history['pm10_values'].index(max_pm10)
            return {
                'pm25': {'value': max_pm25, 'timestamp': history['timestamps'][max_pm25_idx]},
                'pm10': {'value': max_pm10, 'timestamp': history['timestamps'][max_pm10_idx]}
            }
        return None
    except Exception as e:
        logger.error(f"Error getting highest reading: {str(e)}")
        return None

def find_last_spike(threshold_factor=1.5):
    """Find the last time PM levels spiked significantly."""
    try:
        history = query_history('24h')
        if not history or not history['pm25_values']:
            return None

        # Calculate moving averages
        window = 5
        pm25_avg = []
        for i in range(len(history['pm25_values']) - window + 1):
            avg = sum(history['pm25_values'][i:i+window]) / window
            pm25_avg.append(avg)

        # Look for spikes
        for i in range(len(pm25_avg)-1, 0, -1):
            if pm25_avg[i] > pm25_avg[i-1] * threshold_factor:
                return {
                    'timestamp': history['timestamps'][i],
                    'value': history['pm25_values'][i],
                    'baseline': pm25_avg[i-1]
                }
        return None
    except Exception as e:
        logger.error(f"Error finding last spike: {str(e)}")
        return None

def setup_sensor():
    """Initialize and return a serial connection to the SDS011 sensor."""
    try:
        ser = serial.Serial(
            port=SENSOR_PORT,
            baudrate=BAUD_RATE,
            timeout=READ_TIMEOUT
        )
        logger.info(f"Sensor connected on {SENSOR_PORT}")
        return ser
    except Exception as e:
        logger.error(f"Error connecting to sensor: {str(e)}")
        raise

def read_sensor_data(ser):
    """Read and parse data from the SDS011 sensor."""
    try:
        # SDS011 data packet is 10 bytes long
        data = ser.read(10)
        
        if len(data) == 10 and data[0] == 0xAA and data[1] == 0xC0:
            pm25 = float(data[2] + data[3] * 256) / 10.0
            pm10 = float(data[4] + data[5] * 256) / 10.0
            return pm25, pm10
        return None, None
    except Exception as e:
        logger.error(f"Error reading sensor data: {str(e)}")
        return None, None

def sensor_loop():
    """Main loop for reading sensor data and storing it in the database."""
    try:
        ser = setup_sensor()
        while True:
            pm25, pm10 = read_sensor_data(ser)
            if pm25 is not None and pm10 is not None:
                insert_reading(pm25, pm10)
                logger.debug(f"Recorded reading - PM2.5: {pm25}, PM10: {pm10}")
            time.sleep(SENSOR_READ_INTERVAL)
    except Exception as e:
        logger.error(f"Sensor loop error: {str(e)}")
        time.sleep(5)  # Wait before retrying

def test_microphone(device_index):
    """Test if a microphone device is working."""
    try:
        recognizer = sr.Recognizer()
        with sr.Microphone(device_index=device_index) as source:
            logger.info(f"Testing microphone at index {device_index}")
            # Try to get audio from the microphone
            audio = recognizer.listen(source, timeout=1, phrase_time_limit=1)
            return True
    except Exception as e:
        logger.error(f"Microphone test failed for index {device_index}: {str(e)}")
        return False

def find_working_usb_microphone():
    """Scan for and find a working USB microphone."""
    try:
        # Get list of all audio devices
        mics = sr.Microphone.list_microphone_names()
        logger.info(f"Found {len(mics)} audio devices:")
        
        # First try devices that are explicitly labeled as USB
        for index, name in enumerate(mics):
            logger.info(f"Device {index}: {name}")
            if 'usb' in name.lower():
                if test_microphone(index):
                    logger.info(f"Found working USB microphone: {name} (index: {index})")
                    return index
        
        # If no USB device found, try other likely input devices
        for index, name in enumerate(mics):
            if any(keyword in name.lower() for keyword in ['input', 'mic', 'audio']):
                if test_microphone(index):
                    logger.info(f"Found working microphone: {name} (index: {index})")
                    return index
        
        logger.error("No working microphone found!")
        return None
    except Exception as e:
        logger.error(f"Error scanning for microphones: {str(e)}")
        return None

def voice_listener_loop():
    """Continuously listen for voice commands in the background."""
    recognizer = sr.Recognizer()
    
    # Find a working microphone
    device_index = find_working_usb_microphone()
    if device_index is None:
        logger.error("Could not find any working microphone. Voice commands will be disabled.")
        return
    
    while True:
        try:
            with sr.Microphone(device_index=device_index) as source:
                logger.info("Listening for commands...")
                broadcast_listening_status('listening')
                
                # Adjust for ambient noise with longer duration for better calibration
                logger.info("Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=2)
                audio = recognizer.listen(source)
                broadcast_listening_status('processing')
                
                try:
                    text = recognizer.recognize_google(audio).lower()
                    logger.info(f"Heard: {text}")
                    
                    if "puff" in text:
                        response = process_voice_command(text)
                        logger.info(f"Response: {response['response']}")
                        speak_response(response['response'])
                        broadcast_response(response['response'])
                        
                except sr.UnknownValueError:
                    pass  # Speech was unclear
                except sr.RequestError as e:
                    logger.error(f"Could not request results from speech recognition service: {str(e)}")
                    
                broadcast_listening_status('idle')
                    
        except Exception as e:
            logger.error(f"Error in voice listener loop: {str(e)}")
            broadcast_listening_status('idle')
            time.sleep(1)  # Wait before retrying

def process_voice_command(query):
    """Process a voice command and return a response."""
    try:
        query = query.lower()
        
        # Current air quality phrases
        current_phrases = ["what's the current", "what is the current", "how's the air", 
                         "how is the air", "current reading", "current air quality"]
        
        # Highest reading phrases
        highest_phrases = ["highest reading", "maximum level", "peak value", "worst reading",
                         "highest level", "maximum reading"]
        
        # Spike phrases
        spike_phrases = ["when did it spike", "last spike", "recent spike", "when was the spike",
                        "spike detection", "detect spike"]

        # Check for current air quality command
        if any(phrase in query for phrase in current_phrases):
            current_data = query_current()
            if current_data:
                response = f"Current PM2.5 level is {current_data['pm25']:.1f} and PM10 is {current_data['pm10']:.1f} micrograms per cubic meter."
                return {'response': response, 'data': current_data}
            return {'response': "I'm sorry, I couldn't get the current readings."}
            
        # Check for highest reading command
        elif any(phrase in query for phrase in highest_phrases):
            highest = get_highest_reading()
            if highest:
                response = f"Today's highest PM2.5 reading was {highest['pm25']['value']:.1f} at {highest['pm25']['timestamp']}, "
                response += f"and highest PM10 was {highest['pm10']['value']:.1f} at {highest['pm10']['timestamp']}."
                return {'response': response, 'data': highest}
            return {'response': "I'm sorry, I couldn't retrieve the highest readings."}
            
        # Check for spike detection command
        elif any(phrase in query for phrase in spike_phrases):
            spike = find_last_spike()
            if spike:
                response = f"I detected a spike in PM2.5 levels at {spike['timestamp']}, "
                response += f"reaching {spike['value']:.1f} from a baseline of {spike['baseline']:.1f}."
                return {'response': response, 'data': spike}
            return {'response': "I haven't detected any significant spikes in the recent readings."}
            
        else:
            return {'response': "I'm sorry, I didn't understand that command. You can ask about current readings, "
                              "highest readings, or when levels last spiked."}
                              
    except Exception as e:
        logger.error(f"Error processing voice command: {str(e)}")
        return {'response': "I'm sorry, I encountered an error processing your request."}

def speak_response(response_text):
    """Convert text to speech and play it."""
    try:
        tts = gTTS(text=response_text, lang='en')
        temp_file = "response.mp3"
        tts.save(temp_file)
        os.system(f"mpg123 {temp_file}")  # Using mpg123 to play the audio
        os.remove(temp_file)
    except Exception as e:
        logger.error(f"Error in text-to-speech: {str(e)}")

def insert_reading(pm25, pm10, timestamp=None):
    """Insert a new sensor reading into the database."""
    if timestamp is None:
        timestamp = datetime.now()
    
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO sensor_readings (pm25, pm10, timestamp) VALUES (?, ?, ?)',
            (pm25, pm10, timestamp)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting sensor reading: {str(e)}")
        raise

# Flask Routes
@app.route('/')
def index():
    """Serve the main dashboard page."""
    return index_html

@app.route('/history')
def history():
    """Serve the history page."""
    return history_html

@app.route('/settings')
def settings():
    """Serve the settings page."""
    return settings_html

@app.route('/onboarding')
def onboarding():
    """Serve the onboarding/tutorial page."""
    return onboarding_html

@app.route('/api/current')
def api_current():
    """Return the current sensor reading."""
    try:
        reading = query_current()
        if reading:
            return jsonify(reading)
        return jsonify({'error': 'No sensor data available'}), 404
    except Exception as e:
        logger.error(f"Error in /api/current: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/history')
def api_history():
    """Return historical sensor data."""
    try:
        timeframe = request.args.get('timeframe', '24h')
        data = query_history(timeframe)
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in /api/history: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Handle settings retrieval and updates."""
    try:
        if request.method == 'GET':
            settings = get_settings()
            if settings:
                return jsonify(settings)
            return jsonify({'error': 'No settings found'}), 404
            
        elif request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            required_fields = [
                'pm25_warning', 'pm25_critical',
                'pm10_warning', 'pm10_critical',
                'pm25_calibration', 'pm10_calibration'
            ]
            
            if not all(field in data for field in required_fields):
                return jsonify({'error': 'Missing required fields'}), 400
                
            update_settings(data)
            return jsonify({'message': 'Settings updated successfully'})
            
    except Exception as e:
        logger.error(f"Error in /api/settings: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/puff', methods=['POST'])
def api_puff():
    """Handle voice assistant queries."""
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No query provided'}), 400
            
        response = process_voice_command(data['query'])
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in /api/puff: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500

def open_browser():
    """Open the web browser in fullscreen."""
    import webbrowser
    from time import sleep
    # Wait for Flask to start
    sleep(1.5)
    
    # Add JavaScript to make it fullscreen
    url = f"http://localhost:8000"
    webbrowser.open(url)

def main():
    """Initialize the application and start the required threads."""
    try:
        # Initialize database
        init_db()
        
        # Start sensor reading thread
        sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
        sensor_thread.start()
        
        # Start voice listener thread
        voice_thread = threading.Thread(target=voice_listener_loop, daemon=True)
        voice_thread.start()
        
        # Start browser opener thread
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        logger.info("Voice assistant activated and listening for commands...")
        
        # Start Flask server
        app.run(host='0.0.0.0', port=8000)
        
    except Exception as e:
        logger.error(f"Application startup error: {str(e)}")
        raise

if __name__ == '__main__':
    main()
