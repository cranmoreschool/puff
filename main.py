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

# HTML Templates as Multi-line Strings
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Response Overlay HTML -->
    <template id="overlayTemplate">
        <div id="responseOverlay">
            <div id="responseText"></div>
        </div>
    </template>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor</title>
    <!-- Font Awesome for icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        #responseOverlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(5px);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
        }
        #responseOverlay.active {
            display: flex;
            opacity: 1;
        }
        #responseText {
            background: rgba(255, 255, 255, 0.95);
            padding: 2rem;
            border-radius: 1rem;
            max-width: 80%;
            text-align: center;
            font-size: 1.5rem;
            color: #1F2937;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            transform: translateY(20px);
            transition: transform 0.3s ease-out;
        }
        #responseOverlay.active #responseText {
            transform: translateY(0);
        }
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
                <div class="text-xl font-semibold text-gray-800">Air Quality Monitor</div>
                <div class="space-x-6 flex items-center">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                    <a href="/onboarding" class="text-gray-600 hover:text-gray-900">Help</a>
                    <button onclick="toggleFullscreen()" class="ml-4 bg-blue-500 text-white px-3 py-1 rounded-lg hover:bg-blue-600 transition-colors">
                        <i class="fas fa-expand"></i>
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <h1 class="text-2xl font-semibold text-gray-800 mb-6">Real-time Air Quality</h1>
            
            <!-- Add listening indicator -->
            <div class="listening-indicator">
                <i class="fas fa-microphone"></i>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                    <canvas id="gaugeChart" class="w-full"></canvas>
                </div>
                <div class="space-y-6">
                    <div class="glass rounded-xl p-6">
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Current Readings</h2>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <div class="text-sm text-gray-600">PM2.5</div>
                                <div id="pm25" class="text-2xl font-semibold text-gray-800">--</div>
                            </div>
                            <div>
                                <div class="text-sm text-gray-600">PM10</div>
                                <div id="pm10" class="text-2xl font-semibold text-gray-800">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="glass rounded-xl p-6">
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Voice Assistant</h2>
                        <button onclick="activatePuff()" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg transition-colors w-full">
                            Activate Puff
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <style>
        /* Add styles for the listening indicator */
        @keyframes pulse {
            0% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(1); opacity: 0.5; }
        }
        .listening-indicator {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            width: 50px;
            height: 50px;
            border-radius: 25px;
            background: #3B82F6;
            display: none;
            justify-content: center;
            align-items: center;
            color: white;
            font-size: 24px;
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        }
        .listening-indicator.active {
            display: flex;
            animation: pulse 1.5s infinite;
        }
    </style>
    <script>
        // Initialize response overlay
        document.body.insertAdjacentHTML('afterbegin', `
            <div id="responseOverlay" class="fixed inset-0 hidden z-[9999]">
                <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>
                <div class="relative w-full h-full flex items-center justify-center">
                    <div id="responseText" class="bg-white/90 p-8 rounded-xl max-w-2xl mx-4 text-2xl text-gray-800 font-medium shadow-lg transform transition-all"></div>
                </div>
            </div>
        `);

        // Fullscreen toggle function
        function toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                }
            }
        }

        // WebSocket connection for listening status
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        const indicator = document.querySelector('.listening-indicator');
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            const overlay = document.getElementById('responseOverlay');
            
            if (data.type === 'status') {
                if (data.data.status === 'listening') {
                    indicator.classList.add('active');
                    indicator.style.background = '#3B82F6';  // Blue
                } else if (data.data.status === 'processing') {
                    indicator.classList.add('active');
                    indicator.style.background = '#10B981';  // Green
                } else {
                    indicator.classList.remove('active');
                }
            } else if (data.type === 'response') {
                // Show response overlay
                const responseText = document.getElementById('responseText');
                responseText.textContent = data.data.text;
                overlay.classList.add('active');
                
                // Hide after 5 seconds
                setTimeout(() => {
                    overlay.classList.remove('active');
                }, 5000);
            }
        };

        // Initialize gauge chart
        const ctx = document.getElementById('gaugeChart').getContext('2d');
        const gaugeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [0, 100],
                    backgroundColor: ['#10B981', '#E5E7EB'],
                    circumference: 180,
                    rotation: 270,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '80%',
                plugins: {
                    legend: { display: false }
                }
            }
        });

        // Function to update the gauge and readings
        function updateReadings() {
            fetch('/api/current')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('pm25').textContent = data.pm25.toFixed(1);
                    document.getElementById('pm10').textContent = data.pm10.toFixed(1);
                    
                    // Update gauge based on PM2.5 (adjust scale as needed)
                    const pm25 = data.pm25;
                    const percentage = Math.min(pm25 / 100 * 100, 100);
                    gaugeChart.data.datasets[0].data = [percentage, 100 - percentage];
                    
                    // Update color based on value
                    let color;
                    if (pm25 < 12) color = '#10B981';      // Green
                    else if (pm25 < 35) color = '#FBBF24';  // Yellow
                    else color = '#EF4444';                 // Red
                    
                    gaugeChart.data.datasets[0].backgroundColor[0] = color;
                    gaugeChart.update();
                })
                .catch(error => console.error('Error fetching data:', error));
        }

        // Update readings every 5 seconds
        updateReadings();
        setInterval(updateReadings, 5000);

        // Show response overlay
        function showResponse(text, duration = 5000) {
            const overlay = document.getElementById('responseOverlay');
            const responseText = document.getElementById('responseText');
            
            responseText.textContent = text;
            overlay.classList.remove('hidden');
            overlay.classList.add('flex');
            
            setTimeout(() => {
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
            }, duration);
        }

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
                showResponse(data.response);
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
                .catch(error => console.error('Error loading data:', error));
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
        // Load current settings when page loads
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
            .catch(error => console.error('Error loading settings:', error));

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
                console.error('Error saving settings:', error);
                alert('Error saving settings. Please try again.');
            });
        });
    </script>
</body>
</html>
"""

onboarding_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor - Onboarding</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .step {
            display: none;
        }
        .step.active {
            display: block;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Onboarding</div>
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
            <div class="max-w-2xl mx-auto">
                <div class="step active" data-step="1">
                    <h2 class="text-2xl font-semibold text-gray-800 mb-4">Welcome to Your Air Quality Monitor!</h2>
                    <p class="text-gray-600 mb-6">Let's get you set up with your new air quality monitoring system. This quick guide will walk you through the basics.</p>
                    <img src="https://placehold.co/600x300" alt="Welcome" class="rounded-lg mb-6">
                    <button onclick="nextStep()" class="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors">Get Started</button>
                </div>

                <div class="step" data-step="2">
                    <h2 class="text-2xl font-semibold text-gray-800 mb-4">Connecting Your Sensor</h2>
                    <p class="text-gray-600 mb-6">The SDS011 sensor should be connected to your Raspberry Pi via USB. Make sure it's properly plugged in and recognized by the system.</p>
                    <div class="space-y-4 mb-6">
                        <div class="flex items-start">
                            <div class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center">1</div>
                            <div class="ml-3">
                                <p class="text-gray-700">Plug the sensor into any available USB port</p>
                            </div>
                        </div>
                        <div class="flex items-start">
                            <div class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center">2</div>
                            <div class="ml-3">
                                <p class="text-gray-700">Wait for the green LED to light up</p>
                            </div>
                        </div>
                        <div class="flex items-start">
                            <div class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center">3</div>
                            <div class="ml-3">
                                <p class="text-gray-700">The system will automatically detect the sensor</p>
                            </div>
                        </div>
                    </div>
                    <div class="flex space-x-4">
                        <button onclick="prevStep()" class="bg-gray-500 text-white px-6 py-2 rounded-lg hover:bg-gray-600 transition-colors">Back</button>
                        <button onclick="nextStep()" class="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors">Next</button>
                    </div>
                </div>

                <div class="step" data-step="3">
                    <h2 class="text-2xl font-semibold text-gray-800 mb-4">Understanding the Dashboard</h2>
                    <p class="text-gray-600 mb-6">The main dashboard shows real-time air quality data through an easy-to-read gauge and numerical displays.</p>
                    <div class="space-y-4 mb-6">
                        <div class="glass rounded-xl p-4">
                            <h3 class="font-medium text-gray-800 mb-2">Gauge Chart</h3>
                            <p class="text-gray-600">Shows current PM2.5 levels with color-coding:</p>
                            <ul class="list-disc list-inside text-gray-600 ml-4">
                                <li>Green: Good air quality</li>
                                <li>Yellow: Moderate levels</li>
                                <li>Red: Poor air quality</li>
                            </ul>
                        </div>
                        <div class="glass rounded-xl p-4">
                            <h3 class="font-medium text-gray-800 mb-2">Numerical Readings</h3>
                            <p class="text-gray-600">Display exact PM2.5 and PM10 values in μg/m³</p>
                        </div>
                    </div>
                    <div class="flex space-x-4">
                        <button onclick="prevStep()" class="bg-gray-500 text-white px-6 py-2 rounded-lg hover:bg-gray-600 transition-colors">Back</button>
                        <button onclick="nextStep()" class="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors">Next</button>
                    </div>
                </div>

                <div class="step" data-step="4">
                    <h2 class="text-2xl font-semibold text-gray-800 mb-4">Meet Puff - Your AI Assistant</h2>
                    <p class="text-gray-600 mb-6">Puff is your voice-activated AI assistant. Just say "Puff" followed by your question about air quality.</p>
                    <div class="space-y-4 mb-6">
                        <div class="glass rounded-xl p-4">
                            <h3 class="font-medium text-gray-800 mb-2">Example Commands</h3>
                            <ul class="list-disc list-inside text-gray-600 ml-4">
                                <li>"Puff, what's the current air quality?"</li>
                                <li>"Puff, show me today's highest reading"</li>
                                <li>"Puff, when did PM levels spike last?"</li>
                            </ul>
                        </div>
                    </div>
                    <div class="flex space-x-4">
                        <button onclick="prevStep()" class="bg-gray-500 text-white px-6 py-2 rounded-lg hover:bg-gray-600 transition-colors">Back</button>
                        <button onclick="nextStep()" class="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors">Finish</button>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        let currentStep = 1;
        const totalSteps = 4;

        function showStep(step) {
            document.querySelectorAll('.step').forEach(el => el.classList.remove('active'));
            document.querySelector(`[data-step="${step}"]`).classList.add('active');
        }

        function nextStep() {
            if (currentStep < totalSteps) {
                currentStep++;
                showStep(currentStep);
            } else {
                window.location.href = '/';  // Redirect to dashboard when finished
            }
        }

        function prevStep() {
            if (currentStep > 1) {
                currentStep--;
                showStep(currentStep);
            }
        }
    </script>
</body>
</html>
"""

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

def get_settings():
    """Retrieve current settings from the database."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'pm25_warning': result[1],
                'pm25_critical': result[2],
                'pm10_warning': result[3],
                'pm10_critical': result[4],
                'pm25_calibration': result[5],
                'pm10_calibration': result[6]
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving settings: {str(e)}")
        raise

def update_settings(settings_data):
    """Update sensor settings in the database."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO settings (
                pm25_warning, pm25_critical,
                pm10_warning, pm10_critical,
                pm25_calibration, pm10_calibration
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            settings_data['pm25_warning'],
            settings_data['pm25_critical'],
            settings_data['pm10_warning'],
            settings_data['pm10_critical'],
            settings_data['pm25_calibration'],
            settings_data['pm10_calibration']
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        raise

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

def voice_listener_loop():
    """Continuously listen for voice commands in the background."""
    recognizer = sr.Recognizer()
    
    while True:
        try:
            with sr.Microphone() as source:
                logger.info("Listening for commands...")
                broadcast_listening_status('listening')
                recognizer.adjust_for_ambient_noise(source)
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
    url = f"javascript:(function(){{window.location='http://localhost:8000';setTimeout(function(){{document.documentElement.requestFullscreen()}},1000)}})();"
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
