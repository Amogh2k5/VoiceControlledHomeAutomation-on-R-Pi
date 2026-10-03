#!/bin/bash
set -e

# Home Automation - Start Script
# Runs from deploy/raspberry_pi/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"

cd "$APP_DIR"

if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found. Run install.sh first."
    exit 1
fi

source venv/bin/activate

# Environment variables with defaults
export PORCUPINE_ACCESS_KEY="${PORCUPINE_ACCESS_KEY:-}"
export GPIO_ENABLED="${GPIO_ENABLED:-true}"
export RELAY_ACTIVE_HIGH="${RELAY_ACTIVE_HIGH:-true}"
export LIGHT_RELAY_PIN="${LIGHT_RELAY_PIN:-17}"
export FAN_RELAY_PIN="${FAN_RELAY_PIN:-27}"
export DATABASE_PATH="${DATABASE_PATH:-./data/home_automation.db}"
export VOSK_MODEL_PATH="${VOSK_MODEL_PATH:-./models/vosk-model}"
export VOSK_USE_GRAMMAR="${VOSK_USE_GRAMMAR:-true}"
export VOSK_VOCAB_FILE="${VOSK_VOCAB_FILE:-./models/vosk-model/vocab.json}"

# Ensure data directory exists
mkdir -p "$(dirname "$DATABASE_PATH")"

echo "Starting Home Automation System..."
echo "  GPIO_ENABLED=$GPIO_ENABLED"
echo "  LIGHT_RELAY_PIN=$LIGHT_RELAY_PIN"
echo "  FAN_RELAY_PIN=$FAN_RELAY_PIN"
echo "  RELAY_ACTIVE_HIGH=$RELAY_ACTIVE_HIGH"
echo "  DATABASE_PATH=$DATABASE_PATH"
echo "  VOSK_MODEL_PATH=$VOSK_MODEL_PATH"
echo "  VOSK_USE_GRAMMAR=$VOSK_USE_GRAMMAR"

# Check Vosk model exists
if [ ! -d "$VOSK_MODEL_PATH" ]; then
    echo "ERROR: Vosk model not found at $VOSK_MODEL_PATH"
    echo "Please ensure the model is present or set VOSK_MODEL_PATH correctly."
    exit 1
fi

# Start the application
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000