#!/bin/bash
set -e

echo "========================================="
echo "Home Automation - Raspberry Pi Installer"
echo "Target: Raspberry Pi Zero 2 W (aarch64)"
echo "OS: Raspberry Pi OS 64-bit (Debian 13 Trixie)"
echo "Python: 3.13+"
echo "========================================="

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "WARNING: This script is designed for Raspberry Pi hardware."
    echo "Continuing anyway..."
fi

echo ""
echo "[1/6] Updating package list..."
sudo apt-get update

echo ""
echo "[2/6] Installing system dependencies..."
sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-dev \
    portaudio19-dev \
    libsndfile1 \
    git \
    curl

echo ""
echo "[3/6] Checking Python version..."
python3 --version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_VERSION="3.13"
if [[ $(echo "$PYTHON_VERSION $REQUIRED_VERSION" | awk '{print ($1 >= $2)}') -eq 0 ]]; then
    echo "WARNING: Python $PYTHON_VERSION detected, but Python 3.13+ is recommended."
    echo "Some packages may not have pre-built wheels for this version."
fi

echo ""
echo "[4/6] Creating virtual environment..."
cd "$(dirname "$0")/app"
python3 -m venv venv
source venv/bin/activate

echo ""
echo "[5/6] Upgrading pip and installing Python dependencies..."
pip install --upgrade pip setuptools wheel
pip install -r ../requirements-pi.txt

echo ""
echo "[6/6] Verifying installation..."
python -c "
import sys
print(f'Python: {sys.version}')
import vosk
print(f'Vosk: {vosk.__version__}')
import pyaudio
print('PyAudio: OK')
import pvporcupine
print(f'Porcupine: {pvporcupine.__version__}')
import fastapi
print(f'FastAPI: {fastapi.__version__}')
import uvicorn
print(f'Uvicorn: {uvicorn.__version__}')
import numpy
print(f'NumPy: {numpy.__version__}')
import apscheduler
print(f'APScheduler: {apscheduler.__version__}')
# Verify GPIO library
try:
    import gpiozero
    print(f'gpiozero: {gpiozero.__version__}')
except ImportError:
    print('WARNING: No GPIO library available (mock mode will be used)')
"

echo ""
echo "========================================="
echo "Installation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Configure environment variables (optional):"
echo "     export PORCUPINE_ACCESS_KEY='your-key'"
echo "     export GPIO_ENABLED='true'"
echo "     export RELAY_ACTIVE_HIGH='true'"
echo "     export LIGHT_RELAY_PIN='17'"
echo "     export FAN_RELAY_PIN='27'"
echo "     export DATABASE_PATH='./data/home_automation.db'"
echo "     export VOSK_MODEL_PATH='./models/vosk-model'"
echo "     export VOICE_ENABLED='true'"
echo "     export AUDIO_INPUT_DEVICE_INDEX='0'"
echo ""
echo "  2. Test the system:"
echo "     cd $(dirname "$0")/app && source venv/bin/activate && python ../diagnose.py"
echo ""
echo "  3. Start the application:"
echo "     ./start.sh"
echo ""
echo "  4. Enable systemd service (optional):"
echo "     sudo cp ../home-automation.service /etc/systemd/system/"
echo "     sudo systemctl daemon-reload"
echo "     sudo systemctl enable home-automation"
echo "     sudo systemctl start home-automation"