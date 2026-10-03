# Home Automation - Raspberry Pi Deployment Guide

## 1. Project Overview

This is a **voice-controlled home automation system** designed for **Raspberry Pi Zero 2 W**.

- **Offline speech recognition** using **Vosk** (no internet/cloud required)
- **ALSA/arecord** captures audio from a USB microphone (Jabra Evolve2 30 SE)
- **Constrained voice grammar** ensures reliable command recognition
- **Voice parser** converts recognized text into structured commands
- **Home Controller** executes commands and manages appliance state
- **GPIO** controls physical relays for lights and fans
- **FastAPI** provides REST API for status/control
- **Windows browser frontend** monitors and controls the system via the Pi backend

The system is **voice-first**: speak commands like "turn on the bedroom fan" and the Pi executes them locally.

---

## 2. System Architecture

```
Jabra USB Microphone
        ↓
ALSA / arecord
        ↓
Vosk (offline STT)
        ↓
Constrained Voice Grammar
        ↓
Voice Parser
        ↓
Home Controller
        ↓
GPIO
        ↓
Relay Module
        ↓
Physical Appliance (Light / Fan)

                    ┌─────────────────────────┐
                    │   Windows Browser       │
                    │   Frontend :3001        │
                    └───────────┬─────────────┘
                                ↓ HTTP/JSON
                    ┌─────────────────────────┐
                    │  Raspberry Pi FastAPI   │
                    │  Backend :8000          │
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │  Home Automation System │
                    └─────────────────────────┘
```

**Component roles:**

| Component | Role |
|-----------|------|
| Jabra USB Microphone | Audio input (16 kHz, mono, S16_LE) |
| ALSA / arecord | Low-level audio capture from USB device |
| Vosk | Offline speech-to-text with constrained grammar |
| Voice Parser | Normalizes ASR output → structured `InputCommand` |
| Home Controller | Validates & executes commands, updates state |
| GPIO | Drives relay module (Light=GPIO 17, Fan=GPIO 27) |
| Relay Module | Switches mains appliances (active HIGH) |
| FastAPI | REST API for status, control, history, scheduling |
| Windows Frontend | Browser UI served from Windows, polls Pi API |

---

## 3. Hardware Requirements

| Item | Specification |
|------|---------------|
| Raspberry Pi Zero 2 W | 4-core ARM Cortex-A53, 512 MB RAM |
| microSD card | 8 GB+ (Raspberry Pi OS 64-bit) |
| Power supply | 5 V / 2.5 A USB-C |
| USB microphone | Jabra Evolve2 30 SE (tested) |
| Relay module | 2-channel, 5 V logic, active HIGH |
| Appliances | Light, Fan (or other mains devices) |
| USB/OTG adapter | Micro-USB to USB-A for Jabra dongle |
| Windows laptop | Development & frontend access |

**GPIO wiring (must match configuration):**

| Appliance | GPIO Pin | Relay Logic |
|-----------|----------|-------------|
| Light | GPIO 17 | Active HIGH |
| Fan | GPIO 27 | Active HIGH |

---

## 4. Raspberry Pi OS Setup

1. Open **Raspberry Pi Imager** on Windows
2. Choose device: **Raspberry Pi Zero 2 W**
3. Choose OS: **Raspberry Pi OS (64-bit)**
4. Choose storage: your microSD card
5. Click **Next**, then **Edit Settings**:
   - **Hostname**: `pi-zero` (or your choice)
   - **Username**: `amogh`
   - **Password**: (set a secure password)
   - **Wireless LAN**: SSID = your phone hotspot name, Password = your hotspot password
   - **Wireless LAN Country**: your country code (e.g., `US`, `DE`, `IN`)
   - **SSH**: Enable → Use password authentication
   - **Raspberry Pi Connect**: Do NOT enable
6. Write image, insert SD card into Pi, power on

**Network requirement:** Pi and Windows laptop must be on the same network (phone hotspot in current setup).

---

## 5. First Boot and Finding the Raspberry Pi IP

After Pi boots (wait ~60 seconds), run this **Windows PowerShell** command to discover it on the phone hotspot subnet:

```powershell
1..254 | ForEach-Object {
    $ip = "10.36.186.$_"
    if (Test-Connection $ip -Count 1 -Quiet -ErrorAction SilentlyContinue) {
        "$ip is alive"
    }
}
```

> **Note:** `10.36.186.x` is specific to the **current phone hotspot**. If your network uses a different subnet (e.g., `192.168.1.x`), change the prefix accordingly.

**Expected output:**
```
10.36.186.119 is alive
```

That IP is your `<PI_IP>`.

---

## 6. SSH Into the Raspberry Pi

```powershell
ssh amogh@<PI_IP>
```

Example:
```powershell
ssh amogh@10.36.186.119
```

- Replace `<PI_IP>` with the IP discovered in Step 5
- First connection: type `yes` to accept host fingerprint
- Enter the password you set in Pi Imager

---

## 7. Verify Raspberry Pi Environment

Run these commands on the Pi:

```bash
uname -a
cat /etc/os-release
python3 --version
uname -m
df -h
free -h
hostname -I
```

**Expected:**

| Check | Expected |
|-------|----------|
| OS | Debian 13 (Trixie) |
| Architecture | aarch64 |
| Python | 3.13.x |
| RAM | ~415 MB available |
| Disk | ~8 GB free |

---

## 8. Install Raspberry Pi Dependencies

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git alsa-utils
```

- `alsa-utils` provides `arecord` (required for microphone capture)

---

## 9. Deploy the Project to the Raspberry Pi

From **Windows PowerShell**:

```powershell
scp -r B:\Home_auto\deploy\raspberry_pi amogh@<PI_IP>:/home/amogh/home_auto/
```

This copies the complete deployment package to `/home/amogh/home_auto/raspberry_pi/`.

On the Pi:

```bash
cd ~/home_auto/raspberry_pi
chmod +x install.sh start.sh stop.sh status.sh
```

**Deployment structure:**
```
raspberry_pi/
├── app/
│   ├── backend/          # FastAPI + voice + controller
│   ├── frontend/         # Static HTML/CSS/JS (served from Windows)
│   └── models/
│       └── vosk-model/   # Vosk offline model (~54 MB)
├── install.sh
├── start.sh
├── stop.sh
├── status.sh
├── diagnose.py
└── home-automation.service
```

---

## 10. Raspberry Pi Installation

```bash
cd ~/home_auto/raspberry_pi
./install.sh
```

The installer:
- Creates Python 3.13 virtual environment at `app/venv/`
- Installs Python dependencies from `requirements-pi.txt`
- Uses the bundled Vosk model at `app/models/vosk-model/`

**Verification note:** The installer's internal Vosk `__version__` check may show an error on some Python versions, but the model loads correctly. See Step 11 for the real verification.

---

## 11. Verify the Vosk Model

```bash
cd ~/home_auto/raspberry_pi/app
source venv/bin/activate
python -c "from backend.config import config; from vosk import Model; import os; p=os.path.abspath(config.vosk.model_path); print('Model path:', p); Model(p); print('Vosk model: OK')"
```

**Expected:**
```
Model path: /home/amogh/home_auto/raspberry_pi/app/models/vosk-model
Vosk model: OK
```

---

## 12. Verify the USB Microphone

```bash
arecord -l
```

The Jabra should appear as a capture device, e.g.:
```
card 1: Jabra [Jabra Evolve2 30 SE], device 0: USB Audio [USB Audio]
```

**Working microphone test:**
```bash
arecord -D plughw:1,0 -d 5 -f S16_LE -r 16000 -c 1 test.wav
ls -lh test.wav
```

**Expected:** `test.wav` created (~1.6 MB for 5 seconds).

> **Important:** PyAudio may report the Jabra as `maxInputChannels: 0` on this Pi environment even though ALSA capture works perfectly. The live voice implementation deliberately uses `arecord` (not PyAudio) for microphone capture. **Do not attempt to fix PyAudio if this test works.**

---

## 13. Voice System Configuration

| Variable | Value | Description |
|----------|-------|-------------|
| `VOICE_ENABLED` | `true` | Enables background voice listener |
| `AUDIO_ALSA_DEVICE` | `plughw:1,0` | ALSA capture device (Jabra) |

**Audio format:** 16 kHz, mono, S16_LE (matches Vosk model)

**Vosk grammar:** Constrained to supported commands (see Section 17)

**Porcupine:** NOT required for Raspberry Pi deployment

**Voice listening:** Continuous while backend runs

---

## 14. Start the Raspberry Pi Backend

**Primary method:**
```bash
cd ~/home_auto/raspberry_pi
./start.sh
```

**Expected startup logs:**
```
[VOICE] Starting ALSA capture: plughw:1,0
[VOICE] Live listener started
```

Backend runs on: `http://<PI_IP>:8000`

**Manual method (also works):**
```bash
cd ~/home_auto/raspberry_pi/app
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 15. Start the Windows Frontend

The frontend is **plain HTML/CSS/JS** served from Windows (no Node.js, no `npm`):

```powershell
cd B:\Home_auto\frontend
python -m http.server 3001
```

Open browser:
```
http://localhost:3001
```

**Frontend API base URL:**
```javascript
const API_BASE_URL = "http://10.36.186.119:8000";
```

> **Critical:** `10.36.186.119` is only the **current example IP**. When DHCP assigns a different address, update this constant in `frontend/app.js` to match the Pi's current IP.

---

## 16. Complete Daily Startup Procedure

**Windows:**
1. Connect laptop and Pi to same network (phone hotspot)
2. Find Pi IP (Step 5 command)
3. SSH into Pi: `ssh amogh@<PI_IP>`
4. Start backend: `cd ~/home_auto/raspberry_pi && ./start.sh`

**Windows (second terminal):**
```powershell
cd B:\Home_auto\frontend
python -m http.server 3001
```

**Browser:** `http://localhost:3001`

**Speak a command:** "turn on the bedroom fan"

---

## 17. Voice Commands

Supported examples (must match constrained grammar):

| Command | Action |
|---------|--------|
| "Turn on the bedroom fan" | Fan ON |
| "Turn off the bedroom fan" | Fan OFF |
| "Turn on the living room light" | Light ON |
| "Turn off the kitchen exhaust" | Exhaust OFF |
| "Switch on garden lights" | Garden lights ON |
| "Switch off the bathroom light" | Light OFF |

Commands pass through **constrained Vosk grammar** → **voice parser** → **HomeController**.

---

## 18. GPIO / Relay Configuration

| Setting | Value |
|---------|-------|
| `LIGHT_RELAY_PIN` | 17 |
| `FAN_RELAY_PIN` | 27 |
| `RELAY_ACTIVE_HIGH` | true |

> **Safety Warning:** Mains-voltage appliances require appropriate isolation, relay ratings, fusing, enclosure, and electrical safety practices. Do not connect mains directly without proper isolation and qualified electrical work.

---

## 19. FastAPI / API Verification

```powershell
curl.exe http://<PI_IP>:8000/api/status
```

**Swagger UI (if available):**
```
http://<PI_IP>:8000/docs
```

---

## 20. Frontend + Backend Troubleshooting

| # | Symptom | Diagnose | Likely Cause | Fix |
|---|---------|----------|--------------|-----|
| 1 | Cannot SSH | `ping <PI_IP>` | Wrong IP / network | Re-run Step 5 scan |
| 2 | Cannot find Pi IP | `arp -a` | Different subnet | Use correct subnet in Step 5 |
| 3 | Backend won't start | `./start.sh` logs | Missing deps / venv | Run `./install.sh` |
| 4 | Port 8000 in use | `sudo lsof -i :8000` | Old process | `./stop.sh` or `pkill -f uvicorn` |
| 5 | Frontend 404 on `/api/status` | Browser dev tools Network tab | Wrong API base URL | Update `API_BASE_URL` in `frontend/app.js` |
| 6 | Frontend can't connect | Browser console | CORS / wrong IP | Verify `API_BASE_URL` matches Pi IP |
| 7 | Mic not in `arecord -l` | `arecord -l` | USB not seated / driver | Replug Jabra, check `dmesg` |
| 8 | `arecord` capture fails | `arecord -D plughw:1,0 ...` | Wrong device string | Use `plughw:1,0` or correct card |
| 9 | Vosk model fails to load | Step 11 command | Path wrong / corrupt | Verify `app/models/vosk-model/` exists |
| 10 | Voice listener doesn't start | `sudo journalctl -u home-automation -f` | `VOICE_ENABLED=false` | Set `VOICE_ENABLED=true` |
| 11 | Voice recognized but relay unchanged | Logs show `[VOICE] Executed` | GPIO wiring / relay | Check GPIO 17/27 wiring, relay ratings |
| 12 | GPIO unavailable | `groups amogh` | User not in gpio group | `sudo usermod -a -G gpio amogh` then reboot |
| 13 | Pi IP changed | `hostname -I` | DHCP lease expired | Update frontend `API_BASE_URL` |
| 14 | ALSA warnings | `arecord` stderr | Buffer underrun | Usually harmless; increase buffer if persistent |
| 15 | PyAudio reports 0 input devices | `python -c "import pyaudio; p=pyaudio.PyAudio(); [print(p.get_device_info_by_index(i)) for i in range(p.get_device_count())]"` | Known limitation | Use ALSA/arecord (current design) |

---

## 21. systemd Auto-Start

```bash
sudo cp ~/home_auto/raspberry_pi/home-automation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable home-automation.service
sudo systemctl start home-automation.service
```

Verify:
```bash
sudo systemctl status home-automation.service
sudo journalctl -u home-automation.service -f
```

---

## 22. Stop / Restart / Status

**Project scripts:**
```bash
cd ~/home_auto/raspberry_pi
./start.sh
./stop.sh
./status.sh
```

**systemd (if enabled):**
```bash
sudo systemctl start home-automation.service
sudo systemctl stop home-automation.service
sudo systemctl restart home-automation.service
sudo systemctl status home-automation.service
```

---

## 23. Updating the Deployment

From Windows after code changes:
```powershell
scp -r B:\Home_auto\deploy\raspberry_pi\app amogh@<PI_IP>:/home/amogh/home_auto/raspberry_pi/
```

If service/config files changed:
```bash
sudo systemctl daemon-reload
sudo systemctl restart home-automation.service
```

---

## 24. Testing

| Test Suite | Result |
|------------|--------|
| Unit/Integration tests | **166 passed, 4 failed** |
| Deployment verification | **PASSED** |

**4 pre-existing failures (unrelated to voice implementation):**
- Delayed schedule `scheduled_time` assertions
- Schedule test isolation
- Cancel executed schedule status expectation

These existed before the Raspberry Pi voice integration.

---

## 25. Project Directory Structure

```
raspberry_pi/
├── app/
│   ├── backend/
│   ├── frontend/
│   └── models/
│       └── vosk-model/
├── install.sh
├── start.sh
├── stop.sh
├── status.sh
├── diagnose.py
└── home-automation.service
```

---

## 26. Quick Start (Copy-Paste)

**Windows (PowerShell):**
```powershell
# 1. Find Pi IP
1..254 | ForEach-Object { $ip="10.36.186.$_"; if(Test-Connection $ip -Count 1 -Quiet -ErrorAction SilentlyContinue){"$ip is alive"} }

# 2. SSH to Pi
ssh amogh@<PI_IP>
```

**Pi (SSH):**
```bash
cd ~/home_auto/raspberry_pi
./start.sh
```

**Windows (new terminal):**
```powershell
cd B:\Home_auto\frontend
python -m http.server 3001
```

**Browser:**
```
http://localhost:3001
```

**Voice commands:**
- "Turn on the bedroom fan"
- "Turn off the living room light"

---

## 27. Important Notes

- **Pi IP can change** (DHCP/phone hotspot). Update frontend `API_BASE_URL` when it changes.
- **No secrets in repo:** Do not commit Wi-Fi passwords, API keys, or Porcupine keys.
- **Jabra microphone** uses ALSA `plughw:1,0` in current setup.
- **No Porcupine** required for Raspberry Pi voice system.
- **No PyAudio** for microphone capture (uses ALSA `arecord` intentionally).
- **Frontend served from Windows** (port 3001), **backend runs on Pi** (port 8000).
- **GPIO wiring must match** configured pins (Light=17, Fan=27, active HIGH).
- **Mains electrical work** must be performed safely with proper isolation and ratings.

---

*README last updated: matches current repository state as of implementation completion.*