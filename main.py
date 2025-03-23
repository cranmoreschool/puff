#!/usr/bin/env python3
from flask import Flask, jsonify, request
import os
import json
import time
import logging
import sqlite3
import threading
import random
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Global Configuration
DB_FILENAME = "sensor_data.db"
SENSOR_READ_INTERVAL = 5  # seconds between readings

# Initialize logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('air_quality.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def init_db():
    """Initialize the SQLite database."""
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
                pm10_calibration REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

def sensor_loop():
    """Main loop for simulated sensor data."""
    while True:
        try:
            # Generate simulated data with some variation
            pm25 = 10 + random.uniform(0, 30)  # Values between 10-40
            pm10 = pm25 + 5 + random.uniform(0, 20)  # Values between 15-65
            
            # Apply calibration factors
            settings = get_settings()
            if settings:
                pm25 *= settings['pm25_calibration']
                pm10 *= settings['pm10_calibration']
            
            insert_reading(pm25, pm10)
            logger.debug(f"Recorded reading - PM2.5: {pm25}, PM10: {pm10}")
            time.sleep(SENSOR_READ_INTERVAL)
            
        except Exception as e:
            logger.error(f"Sensor loop error: {str(e)}")
            time.sleep(5)  # Wait before retrying

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
    """Get current settings from the database."""
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
        logger.error(f"Error getting settings: {str(e)}")
        raise

def update_settings(settings):
    """Update settings in the database."""
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
            settings['pm25_warning'],
            settings['pm25_critical'],
            settings['pm10_warning'],
            settings['pm10_critical'],
            settings['pm25_calibration'],
            settings['pm10_calibration']
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        raise

# HTML Templates
INDEX_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
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
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in {
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
                    <a href="/help" class="nav-link text-gray-600 hover:text-gray-900 transition-all">Help</a>
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
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Air Quality Status</h2>
                        <div id="airQualityStatus" class="text-lg font-medium transition-all duration-300">
                            Checking air quality...
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        // Initialize gauge chart with smooth animations
        const ctx = document.getElementById('gaugeChart').getContext('2d');
        
        // Create initial gradient
        const createGradient = (color1, color2) => {
            const gradient = ctx.createLinearGradient(0, 0, 200, 0);
            gradient.addColorStop(0, color1);
            gradient.addColorStop(1, color2);
            return gradient;
        };

        // Initial gradient (green)
        const initialGradient = createGradient('#10B981', '#34D399');

        const gaugeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [33, 67],
                    backgroundColor: [initialGradient, '#E5E7EB'],
                    circumference: 180,
                    rotation: 270,
                    borderWidth: 0,
                    borderRadius: 15,
                    spacing: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                animation: {
                    duration: 1500,
                    easing: 'easeInOutQuart'
                }
            }
        });

        function getAirQualityStatus(pm25) {
            if (pm25 <= 12) {
                return {
                    text: "Good",
                    color: "text-green-600"
                };
            } else if (pm25 <= 35) {
                return {
                    text: "Moderate",
                    color: "text-yellow-600"
                };
            } else {
                return {
                    text: "Poor",
                    color: "text-red-600"
                };
            }
        }

        // Update readings with smooth animations
        function updateReadings() {
            fetch('/api/current')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        return;
                    }
                    
                    // Update numerical displays with fade
                    const pm25Display = document.getElementById('pm25');
                    const pm10Display = document.getElementById('pm10');
                    const statusDisplay = document.getElementById('airQualityStatus');
                    
                    // Fade out
                    pm25Display.style.opacity = '0';
                    pm10Display.style.opacity = '0';
                    statusDisplay.style.opacity = '0';
                    
                    setTimeout(() => {
                        // Update values
                        pm25Display.textContent = data.pm25.toFixed(1);
                        pm10Display.textContent = data.pm10.toFixed(1);
                        
                        // Update air quality status
                        const status = getAirQualityStatus(data.pm25);
                        statusDisplay.textContent = status.text;
                        statusDisplay.className = `text-lg font-medium ${status.color} transition-all duration-300`;
                        
                        // Fade in
                        pm25Display.style.opacity = '1';
                        pm10Display.style.opacity = '1';
                        statusDisplay.style.opacity = '1';
                    }, 200);
                    
                    // Update gauge with enhanced scaling
                    const pm25 = data.pm25;
                    let percentage;
                    
                    // Linear scaling with adjusted ranges for better visibility
                    if (pm25 <= 12) {
                        percentage = (pm25 / 12) * 33;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#10B981', '#34D399'); // Green
                    } else if (pm25 <= 35) {
                        percentage = 33 + ((pm25 - 12) / (35 - 12)) * 33;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#FBBF24', '#F59E0B'); // Yellow
                    } else {
                        percentage = 66 + ((pm25 - 35) / 15) * 34;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#EF4444', '#DC2626'); // Red
                    }
                    
                    gaugeChart.data.datasets[0].data = [percentage, 100 - percentage];
                    gaugeChart.update();
                })
                .catch(error => console.error('Error:', error));
        }

        // Update readings every 5 seconds
        updateReadings();
        setInterval(updateReadings, 5000);
    </script>
</body>
</html>
'''

HISTORY_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality History</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
        .button {
            transition: all 0.3s ease;
        }
        .button:hover {
            transform: translateY(-2px);
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in {
            animation: fadeIn 0.5s ease forwards;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Air Quality History</div>
                <div class="space-x-8">
                    <a href="/" class="nav-link text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="nav-link text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="nav-link text-gray-600 hover:text-gray-900">Settings</a>
                    <a href="/help" class="nav-link text-gray-600 hover:text-gray-900">Help</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg fade-in">
            <div class="flex justify-between items-center mb-6">
                <h1 class="text-2xl font-semibold text-gray-800">Historical Data</h1>
                <div class="space-x-4">
                    <button onclick="loadData('24h')" class="button px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">24 Hours</button>
                    <button onclick="loadData('7d')" class="button px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">7 Days</button>
                    <button onclick="loadData('30d')" class="button px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">30 Days</button>
                </div>
            </div>
            
            <!-- Chart Container -->
            <div class="h-96 mb-8">
                <canvas id="historyChart"></canvas>
            </div>

            <!-- Statistics Cards -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
                <div class="glass rounded-xl p-6 transition-all duration-300 hover:shadow-lg">
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Average PM2.5</h3>
                    <div id="avgPM25" class="text-2xl font-semibold text-blue-600">--</div>
                </div>
                <div class="glass rounded-xl p-6 transition-all duration-300 hover:shadow-lg">
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Maximum PM2.5</h3>
                    <div id="maxPM25" class="text-2xl font-semibold text-red-600">--</div>
                </div>
                <div class="glass rounded-xl p-6 transition-all duration-300 hover:shadow-lg">
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Minimum PM2.5</h3>
                    <div id="minPM25" class="text-2xl font-semibold text-green-600">--</div>
                </div>
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
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 5
                    },
                    {
                        label: 'PM10',
                        data: [],
                        borderColor: '#10B981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 5
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: {
                                family: 'Inter'
                            }
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(255, 255, 255, 0.9)',
                        titleColor: '#1F2937',
                        bodyColor: '#1F2937',
                        borderColor: '#E5E7EB',
                        borderWidth: 1,
                        padding: 12,
                        bodyFont: {
                            family: 'Inter'
                        },
                        titleFont: {
                            family: 'Inter',
                            weight: '600'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(156, 163, 175, 0.1)'
                        },
                        ticks: {
                            font: {
                                family: 'Inter'
                            }
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(156, 163, 175, 0.1)'
                        },
                        ticks: {
                            font: {
                                family: 'Inter'
                            },
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                animation: {
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }
            }
        });

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
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
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in {
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
                    <a href="/help" class="nav-link text-gray-600 hover:text-gray-900 transition-all">Help</a>
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
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Air Quality Status</h2>
                        <div id="airQualityStatus" class="text-lg font-medium transition-all duration-300">
                            Checking air quality...
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        // Initialize gauge chart with smooth animations
        const ctx = document.getElementById('gaugeChart').getContext('2d');
        
        // Create initial gradient
        const createGradient = (color1, color2) => {
            const gradient = ctx.createLinearGradient(0, 0, 200, 0);
            gradient.addColorStop(0, color1);
            gradient.addColorStop(1, color2);
            return gradient;
        };

        // Initial gradient (green)
        const initialGradient = createGradient('#10B981', '#34D399');

        const gaugeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [33, 67],
                    backgroundColor: [initialGradient, '#E5E7EB'],
                    circumference: 180,
                    rotation: 270,
                    borderWidth: 0,
                    borderRadius: 15,
                    spacing: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                animation: {
                    duration: 1500,
                    easing: 'easeInOutQuart'
                }
            }
        });

        function getAirQualityStatus(pm25) {
            if (pm25 <= 12) {
                return {
                    text: "Good",
                    color: "text-green-600"
                };
            } else if (pm25 <= 35) {
                return {
                    text: "Moderate",
                    color: "text-yellow-600"
                };
            } else {
                return {
                    text: "Poor",
                    color: "text-red-600"
                };
            }
        }

        // Update readings with smooth animations
        function updateReadings() {
            fetch('/api/current')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        return;
                    }
                    
                    // Update numerical displays with fade
                    const pm25Display = document.getElementById('pm25');
                    const pm10Display = document.getElementById('pm10');
                    const statusDisplay = document.getElementById('airQualityStatus');
                    
                    // Fade out
                    pm25Display.style.opacity = '0';
                    pm10Display.style.opacity = '0';
                    statusDisplay.style.opacity = '0';
                    
                    setTimeout(() => {
                        // Update values
                        pm25Display.textContent = data.pm25.toFixed(1);
                        pm10Display.textContent = data.pm10.toFixed(1);
                        
                        // Update air quality status
                        const status = getAirQualityStatus(data.pm25);
                        statusDisplay.textContent = status.text;
                        statusDisplay.className = `text-lg font-medium ${status.color} transition-all duration-300`;
                        
                        // Fade in
                        pm25Display.style.opacity = '1';
                        pm10Display.style.opacity = '1';
                        statusDisplay.style.opacity = '1';
                    }, 200);
                    
                    // Update gauge with enhanced scaling
                    const pm25 = data.pm25;
                    let percentage;
                    
                    // Linear scaling with adjusted ranges for better visibility
                    if (pm25 <= 12) {
                        percentage = (pm25 / 12) * 33;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#10B981', '#34D399'); // Green
                    } else if (pm25 <= 35) {
                        percentage = 33 + ((pm25 - 12) / (35 - 12)) * 33;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#FBBF24', '#F59E0B'); // Yellow
                    } else {
                        percentage = 66 + ((pm25 - 35) / 15) * 34;
                        gaugeChart.data.datasets[0].backgroundColor[0] = createGradient('#EF4444', '#DC2626'); // Red
                    }
                    
                    gaugeChart.data.datasets[0].data = [percentage, 100 - percentage];
                    gaugeChart.update();
                })
                .catch(error => console.error('Error:', error));
        }

        // Update readings every 5 seconds
        updateReadings();
        setInterval(updateReadings, 5000);
    </script>
</body>
</html>
'''

# Flask Routes
@app.route('/')
def index():
    """Serve the main dashboard page."""
    return INDEX_HTML

@app.route('/history')
def history():
    """Serve the history page."""
    return HISTORY_HTML

@app.route('/settings')
def settings():
    """Serve the settings page."""
    return SETTINGS_HTML

@app.route('/help')
def help():
    """Serve the help page."""
    return HELP_HTML

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

def main():
    """Initialize the application and start the required threads."""
    try:
        # Initialize database
        init_db()
        
        # Start sensor reading thread
        sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
        sensor_thread.start()
        
        # Start Flask server
        app.run(host='0.0.0.0', port=8000)
        
    except Exception as e:
        logger.error(f"Application startup error: {str(e)}")
        raise

if __name__ == '__main__':
    main()
