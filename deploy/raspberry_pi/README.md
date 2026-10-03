# Raspberry Pi Zero 2 W Deployment

This directory contains the complete deployment package for running the Home Automation system on a Raspberry Pi Zero 2 W.

## Target Platform

- **Hardware**: Raspberry Pi Zero 2 W (aarch64)
- **OS**: Raspberry Pi OS 64-bit (Debian 13 "Trixie")
- **Python**: 3.13+
- **RAM**: ~415 MB available
- **Storage**: ~8.4 GB free

## Architecture

```
Voice → USB Mic → Vosk STT → Grammar → Parser → Controller → GPIO/Relay
                                                            → SQLite
                                                            → FastAPI (port 8000)
```

## Devices Supported

| Room | Devices |
|------|---------|
| Living Room | Light, Fan, TV, Plug |
| Bedroom | Light, Fan, AC |
| Kitchen | Light, Fan, Exhaust |
| Bathroom/Toilet | Light, Exhaust |
| Garden/Balcony | Garden Light |

## Hardware Connections

| Device | GPIO Pin | Relay Logic |
|--------|----------|-------------|
| Light | GPIO 17 | Active High |
| Fan | GPIO 27 | Active High |

## Directory Structure

```
deploy/raspberry_pi/
├── app/                    # Application code (copied to Pi)
│   ├── backend/           # Python backend
│   ├── frontend/          # Web UI (static files)
│   └── models/
│       └── vosk-model/    # Vosk offline STT model (~56 MB)
├── install.sh             # Installation script (run on Pi)
├── start.sh               # Start application
├── stop.sh                # Stop application
├── status.sh              # Check status
├── diagnose.py            # Deployment verification
├── requirements-pi.txt    # Python dependencies
├── home-automation.service # Systemd service file
└── README.md              # This file
```

## Quick Start (on Raspberry Pi)

### 1. Copy deployment package to Pi

From Windows (PowerShell):
```powershell
scp -r B:\Home_auto\deploy\raspberry_pi pi@<PI_IP>:/home/amogh/home_auto/
```

Or using rsync:
```powershell
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' B:\Home_auto\deploy\raspberry_pi\ pi@<PI_IP>:/home/amogh/home_auto/
```

### 2. Run installer on Pi

```bash
cd /home/amogh/home_auto/deploy/raspberry_pi
chmod +x install.sh
./install.sh
```

### 3. Configure (optional)

```bash
export PORCUPINE_ACCESS_KEY="your-porcupine-key"  # For wake word
export GPIO_ENABLED="true"
export RELAY_ACTIVE_HIGH="true"
```

### 4. Verify deployment

```bash
cd /home/amogh/home_auto/deploy/raspberry_pi
source app/venv/bin/activate
python diagnose.py
```

### 5. Start the system

```bash
./start.sh
```

### 6. Enable auto-start (optional)

```bash
sudo cp home-automation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable home-automation
sudo systemctl start home-automation
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORCUPINE_ACCESS_KEY` | "" | Picovoice access key for wake word |
| `GPIO_ENABLED` | "true" | Enable GPIO control (false = mock mode) |
| `RELAY_ACTIVE_HIGH` | "true" | Relay logic (true = active high) |
| `LIGHT_RELAY_PIN` | "17" | GPIO pin for light relay |
| `FAN_RELAY_PIN` | "27" | GPIO pin for fan relay |
| `DATABASE_PATH` | "./data/home_automation.db" | SQLite database path |
| `VOSK_MODEL_PATH` | "./models/vosk-model" | Vosk model directory |
| `VOSK_USE_GRAMMAR` | "true" | Use constrained grammar |
| `VOSK_VOCAB_FILE` | "./models/vosk-model/vocab.json" | Vocabulary file |

## Voice Commands

The system uses constrained grammar for reliable recognition:

- "Switch on bedroom fan"
- "Turn off kitchen exhaust"
- "Switch on living room TV"
- "Switch off garden lights"
- "Turn on bathroom light"
- "Switch on geyser"
- "Turn off plug"

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /status | System status |
| GET | /appliances | List all appliances |
| POST | /appliance | Control appliance |
| GET | /history | Command history |
| GET | /schedules | Pending scheduled commands |
| DELETE | /schedules/{id} | Cancel scheduled command |
| GET/POST | /mode | Get/set input mode |

## Troubleshooting

### Microphone not detected
```bash
arecord -l
# Ensure USB mic appears in the list
```

### GPIO permission denied
```bash
sudo usermod -a -G gpio amogh
# Reboot required
```

### Vosk model not found
```bash
ls -la /home/amogh/home_auto/deploy/raspberry_pi/app/models/vosk-model/
# Should contain: am/, conf/, graph/, ivector/, vocab.json
```

### Port 8000 already in use
```bash
sudo lsof -i :8000
# Kill existing process or change port in start.sh
```

### Service won't start
```bash
sudo journalctl -u home-automation -f
# Check logs for errors
```

## Development vs Production

| Aspect | Development (Windows) | Production (Pi) |
|--------|----------------------|-----------------|
| Python | 3.11.9 | 3.13+ |
| GPIO | Mock | Real (RPi.GPIO/gpiozero) |
| Mic | Default | USB (ALSA) |
| Wake Word | Porcupine | Porcupine (optional) |
| Database | Local file | Persistent file |
| Frontend | Served by FastAPI | Served by FastAPI |

## File Exclusions (Not Deployed)

The following are intentionally excluded from the deployment package:
- `venv/` - Windows virtual environment (Pi creates its own)
- `.git/` - Git history
- `__pycache__/` - Python bytecode cache
- `.pytest_cache/` - Test cache
- `backend/tests/` - Test files
- `models/sherpa/` - Experimental Sherpa model (~136 MB)
- `data/voice_benchmark/` - Benchmark data
- IDE files (`.vscode/`, `.idea/`)
- `requirements.txt` - Development dependencies (includes mediapipe, opencv, sherpa-onnx)

## License

Internal use only.