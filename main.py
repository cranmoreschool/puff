#!/usr/bin/env python3
"""
Air Quality Monitor with SDS011 Sensor and Chatbot
All-in-one file with embedded installer and HTML templates
"""
# Import required packages
import os
import json
import time
import logging
import sqlite3
import threading
import serial
import glob
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from transformers import pipeline

# Initialize Flask app
app = Flask(__name__)

# Global Configuration
DB_FILENAME = "sensor_data.db"
SENSOR_READ_INTERVAL = 60  # Store readings every minute
DATA_RETENTION_DAYS = 60   # Keep 60 days of history
PORT = "/dev/ttyUSB0"      # Default port for Raspberry Pi

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

class SDS011:
    """SDS011 dust sensor class."""
    
    def __init__(self, port=PORT):
        self.port = port
        self.serial = None
        
    def open(self):
        """Open serial connection to the sensor."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2
            )
            logger.info(f"Connected to SDS011 on {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Error opening serial port: {str(e)}")
            return False
            
    def read(self):
        """Read a measurement from the sensor."""
        try:
            if not self.serial:
                return None
                
            # Read data packet
            data = self.serial.read(10)
            
            if len(data) == 10 and data[0] == 0xAA and data[1] == 0xC0:
                pm25 = float(data[2] + data[3] * 256) / 10.0
                pm10 = float(data[4] + data[5] * 256) / 10.0
                return pm25, pm10
                
            return None
            
        except Exception as e:
            logger.error(f"Error reading from sensor: {str(e)}")
            return None
            
    def close(self):
        """Close the serial connection."""
        if self.serial:
            self.serial.close()
            self.serial = None

class Chatbot:
    """Simple NLP-based chatbot for air quality inquiries."""
    
    def __init__(self):
        self.qa_pipeline = pipeline("question-answering")
        self.context = self._get_base_context()
        
    def _get_base_context(self):
        """Get base context for the chatbot."""
        return """
        Air quality is measured using PM2.5 and PM10 values.
        PM2.5 refers to particles smaller than 2.5 micrometers, which can penetrate deep into lungs.
        PM10 refers to particles smaller than 10 micrometers.
        
        Good air quality: PM2.5 < 12 μg/m³, PM10 < 54 μg/m³
        Moderate air quality: PM2.5 12-35 μg/m³, PM10 54-154 μg/m³
        Poor air quality: PM2.5 > 35 μg/m³, PM10 > 154 μg/m³
        
        To improve air quality:
        1. Use air purifiers with HEPA filters
        2. Ensure good ventilation
        3. Regular cleaning and dusting
        4. Control humidity levels
        5. Avoid indoor smoking
        6. Use natural cleaning products
        
        Example questions you can ask:
        - What are the current readings?
        - Show me the air quality history
        - When was the last air quality spike?
        - How can I improve my air quality?
        - What do these numbers mean?
        """
    
    def _update_context(self):
        """Update context with current readings and history."""
        try:
            current = query_current()
            if current:
                self.context += f"\nCurrent readings: PM2.5: {current['pm25']:.1f} μg/m³, PM10: {current['pm10']:.1f} μg/m³"
            
            history = query_history('24h')
            if history:
                max_pm25 = max(history['pm25_values'])
                max_pm10 = max(history['pm10_values'])
                self.context += f"\nHighest readings in last 24h: PM2.5: {max_pm25:.1f} μg/m³, PM10: {max_pm10:.1f} μg/m³"
        except:
            pass
    
    def get_response(self, question):
        """Get response for a question."""
        try:
            self._update_context()
            result = self.qa_pipeline(question=question, context=self.context)
            return result['answer']
        except Exception as e:
            logger.error(f"Chatbot error: {str(e)}")
            return "I'm sorry, I couldn't process that question. Please try asking something else."

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

def cleanup_old_data():
    """Remove data older than DATA_RETENTION_DAYS."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM sensor_readings WHERE timestamp < datetime("now", ?)',
            (f'-{DATA_RETENTION_DAYS} days',)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error cleaning up old data: {str(e)}")

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

def sensor_loop():
    """Main loop for reading from the SDS011 sensor."""
    sensor = SDS011()
    last_reading_time = None
    
    if not sensor.open():
        logger.error("Failed to open connection to SDS011 sensor")
        return
        
    while True:
        try:
            current_time = datetime.now()
            
            # Only store readings once per minute
            if last_reading_time is None or (current_time - last_reading_time).total_seconds() >= 60:
                # Read from sensor
                result = sensor.read()
                
                if result:
                    pm25, pm10 = result
                    
                    # Apply calibration factors
                    settings = get_settings()
                    if settings:
                        pm25 *= settings['pm25_calibration']
                        pm10 *= settings['pm10_calibration']
                    
                    insert_reading(pm25, pm10)
                    last_reading_time = current_time
                    logger.debug(f"Recorded reading - PM2.5: {pm25}, PM10: {pm10}")
                
                # Cleanup old data once per day
                if current_time.hour == 0 and current_time.minute == 0:
                    cleanup_old_data()
            
            time.sleep(SENSOR_READ_INTERVAL)
            
        except Exception as e:
            logger.error(f"Sensor loop error: {str(e)}")
            time.sleep(5)  # Wait before retrying

# Initialize chatbot
chatbot = Chatbot()

# Flask Routes
@app.route('/')
def index():
    """Serve the main dashboard page."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .glass {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .chat-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 350px;
            max-height: 500px;
            display: none;
            z-index: 1000;
        }
        .chat-container.open {
            display: flex;
        }
        .chat-messages {
            height: 300px;
            overflow-y: auto;
        }
        .chat-toggle {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 999;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <nav class="glass fixed w-full top-0 z-50 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Air Quality Monitor</div>
                <div class="space-x-8">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <h1 class="text-2xl font-semibold text-gray-800 mb-6">Real-time Air Quality</h1>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                    <canvas id="gaugeChart"></canvas>
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
                        <h2 class="text-lg font-medium text-gray-800 mb-2">Air Quality Status</h2>
                        <div id="status" class="text-lg font-medium">Checking...</div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- Chat Interface -->
    <button class="chat-toggle bg-blue-500 text-white p-4 rounded-full shadow-lg hover:bg-blue-600">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
        </svg>
    </button>

    <div class="chat-container glass rounded-lg flex flex-col">
        <div class="p-4 border-b border-gray-200">
            <h3 class="text-lg font-medium">Air Quality Assistant</h3>
        </div>
        <div class="chat-messages p-4 space-y-4"></div>
        <div class="p-4 border-t border-gray-200">
            <form id="chatForm" class="flex space-x-2">
                <input type="text" 
                       class="flex-1 px-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                       placeholder="Ask about air quality...">
                <button type="submit" 
                        class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                    Send
                </button>
            </form>
        </div>
    </div>

    <script>
        // Chat Interface
        const chatToggle = document.querySelector('.chat-toggle');
        const chatContainer = document.querySelector('.chat-container');
        const chatMessages = document.querySelector('.chat-messages');
        const chatForm = document.getElementById('chatForm');

        chatToggle.addEventListener('click', () => {
            chatContainer.classList.toggle('open');
        });

        function addMessage(message, isUser = false) {
            const div = document.createElement('div');
            div.className = `p-3 rounded-lg ${isUser ? 'bg-blue-500 text-white ml-8' : 'bg-gray-100 mr-8'}`;
            div.textContent = message;
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = chatForm.querySelector('input');
            const message = input.value.trim();
            if (!message) return;

            addMessage(message, true);
            input.value = '';

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message })
                });
                const data = await response.json();
                addMessage(data.response);
            } catch (error) {
                addMessage('Sorry, I encountered an error. Please try again.');
            }
        });

        // Gauge Chart
        const ctx = document.getElementById('gaugeChart').getContext('2d');
        const gaugeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [33, 67],
                    backgroundColor: ['#10B981', '#E5E7EB'],
                    circumference: 180,
                    rotation: 270
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });

        function updateReadings() {
            fetch('/api/current')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('pm25').textContent = data.pm25.toFixed(1);
                    document.getElementById('pm10').textContent = data.pm10.toFixed(1);
                    
                    let status = 'Good';
                    let color = 'text-green-600';
                    let chartColor = '#10B981';
                    let percentage = (data.pm25 / 12) * 33;
                    
                    if (data.pm25 > 35) {
                        status = 'Poor';
                        color = 'text-red-600';
                        chartColor = '#EF4444';
                        percentage = 66 + ((data.pm25 - 35) / 15) * 34;
                    } else if (data.pm25 > 12) {
                        status = 'Moderate';
                        color = 'text-yellow-600';
                        chartColor = '#F59E0B';
                        percentage = 33 + ((data.pm25 - 12) / 23) * 33;
                    }
                    
                    const statusElement = document.getElementById('status');
                    statusElement.textContent = status;
                    statusElement.className = `text-lg font-medium ${color}`;
                    
                    gaugeChart.data.datasets[0].data = [percentage, 100 - percentage];
                    gaugeChart.data.datasets[0].backgroundColor[0] = chartColor;
                    gaugeChart.update();
                })
                .catch(console.error);
        }
        
        updateReadings();
        setInterval(updateReadings, 5000);
    </script>
</body>
</html>'''

@app.route('/history')
def history():
    """Serve the history page."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air Quality History</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
                <div class="text-xl font-semibold text-gray-800">Air Quality History</div>
                <div class="space-x-8">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <div class="flex justify-between items-center mb-6">
                <h1 class="text-2xl font-semibold text-gray-800">Historical Data</h1>
                <div class="space-x-4">
                    <button onclick="loadData('24h')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">24 Hours</button>
                    <button onclick="loadData('7d')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">7 Days</button>
                    <button onclick="loadData('30d')" class="px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600">30 Days</button>
                </div>
            </div>
            
            <div class="h-96 mb-8">
                <canvas id="historyChart"></canvas>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="glass rounded-xl p-6">
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Average PM2.5</h3>
                    <div id="avgPM25" class="text-2xl font-semibold text-blue-600">--</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <h3 class="text-lg font-medium text-gray-800 mb-2">Maximum PM2.5</h3>
                    <div id="maxPM25" class="text-2xl font-semibold text-red-600">--</div>
                </div>
                <div class="glass rounded-xl p-6">
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
                        fill: true
                    },
                    {
                        label: 'PM10',
                        data: [],
                        borderColor: '#10B981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' }
                },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });

        function updateStatistics(data) {
            const pm25Values = data.pm25_values;
            const avgPM25 = pm25Values.reduce((a, b) => a + b, 0) / pm25Values.length;
            const maxPM25 = Math.max(...pm25Values);
            const minPM25 = Math.min(...pm25Values);

            document.getElementById('avgPM25').textContent = avgPM25.toFixed(1);
            document.getElementById('maxPM25').textContent = maxPM25.toFixed(1);
            document.getElementById('minPM25').textContent = minPM25.toFixed(1);
        }

        function formatTimestamp(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleString();
        }

        function loadData(timeframe) {
            fetch(`/api/history?timeframe=${timeframe}`)
                .then(response => response.json())
                .then(data => {
                    historyChart.data.labels = data.timestamps.map(formatTimestamp);
                    historyChart.data.datasets[0].data = data.pm25_values;
                    historyChart.data.datasets[1].data = data.pm10_values;
                    historyChart.update();
                    updateStatistics(data);
                })
                .catch(console.error);
        }

        loadData('24h');
    </script>
</body>
</html>'''

@app.route('/settings')
def settings():
    """Serve the settings page."""
    return '''<!DOCTYPE html>
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
        .notification {
            transform: translateY(-100%);
            opacity: 0;
            transition: all 0.3s ease;
        }
        .notification.show {
            transform: translateY(0);
            opacity: 1;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-purple-50 min-h-screen">
    <div id="notification" class="notification fixed top-4 right-4 max-w-sm bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50">
        Settings saved successfully!
    </div>

    <nav class="glass fixed w-full top-0 z-40 shadow-sm">
        <div class="container mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="text-xl font-semibold text-gray-800">Settings</div>
                <div class="space-x-8">
                    <a href="/" class="text-gray-600 hover:text-gray-900">Dashboard</a>
                    <a href="/history" class="text-gray-600 hover:text-gray-900">History</a>
                    <a href="/settings" class="text-gray-600 hover:text-gray-900">Settings</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-6 pt-24 pb-12">
        <div class="glass rounded-2xl p-8 shadow-lg">
            <h1 class="text-2xl font-semibold text-gray-800 mb-6">Sensor Settings</h1>
            
            <form id="settingsForm" class="space-y-8">
                <div class="space-y-6">
                    <h2 class="text-lg font-medium text-gray-800">PM2.5 Thresholds</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">Warning Level (μg/m³)</label>
                            <input type="number" name="pm25_warning" 
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0" step="0.1" required>
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">Critical Level (μg/m³)</label>
                            <input type="number" name="pm25_critical"
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0" step="0.1" required>
                        </div>
                    </div>
                </div>

                <div class="space-y-6">
                    <h2 class="text-lg font-medium text-gray-800">PM10 Thresholds</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">Warning Level (μg/m³)</label>
                            <input type="number" name="pm10_warning"
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0" step="0.1" required>
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">Critical Level (μg/m³)</label>
                            <input type="number" name="pm10_critical"
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0" step="0.1" required>
                        </div>
                    </div>
                </div>

                <div class="space-y-6">
                    <h2 class="text-lg font-medium text-gray-800">Sensor Calibration</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">PM2.5 Calibration Factor</label>
                            <input type="number" name="pm25_calibration"
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0.1" step="0.01" required>
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-700">PM10 Calibration Factor</label>
                            <input type="number" name="pm10_calibration"
                                   class="mt-1 block w-full px-4 py-2 rounded-lg border border-gray-300"
                                   min="0.1" step="0.01" required>
                        </div>
                    </div>
                </div>

                <div class="pt-6">
                    <button type="submit" 
                            class="w-full bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600">
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
            .catch(console.error);

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
                const notification = document.getElementById('notification');
                notification.classList.add('show');
                setTimeout(() => {
                    notification.classList.remove('show');
                }, 3000);
            })
            .catch(console.error);
        });
    </script>
</body>
</html>'''

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

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages."""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400
            
        response = chatbot.get_response(data['message'])
        return jsonify({'response': response})
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
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
