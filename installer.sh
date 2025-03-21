#!/bin/bash

echo "Installing Air Quality Monitor dependencies..."

# Check for Python3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed"
    exit 1
fi

# Check for pip
if ! command -v pip &> /dev/null; then
    echo "Error: pip is not installed"
    exit 1
fi

# Install system dependencies for audio
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    sudo apt-get update
    sudo apt-get install -y python3-pyaudio mpg123 portaudio19-dev
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    sudo yum install -y python3-pyaudio mpg123 portaudio-devel
elif command -v pacman &> /dev/null; then
    # Arch Linux
    sudo pacman -S --noconfirm python-pyaudio mpg123 portaudio
elif command -v brew &> /dev/null; then
    # macOS
    brew install portaudio mpg123
else
    echo "Warning: Could not install system dependencies automatically."
    echo "Please install PyAudio and mpg123 manually for your system."
fi

# Install Python dependencies
echo "Installing Python packages..."
pip install --break-system-packages -r requirements.txt

if [ $? -eq 0 ]; then
    echo "Installation completed successfully!"
    echo "You can now run the application with: python3 main.py"
    echo "The voice assistant 'Puff' will be listening for commands."
    echo "Try saying: 'Puff, what's the current air quality?'"
else
    echo "Error: Failed to install dependencies"
    exit 1
fi
