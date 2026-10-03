#!/usr/bin/env python3
"""
Deployment verification script for Raspberry Pi Zero 2 W home automation system.

Checks:
- Python version
- Virtual environment
- Required packages
- Vosk model
- SQLite database
- FastAPI/Uvicorn
- Microphone/ALSA
- GPIO availability
- Configuration
- Required files
- Systemd service configuration
"""

import sys
import os
import json
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add app to path - use script's location, not cwd
SCRIPT_DIR = Path(__file__).parent.resolve()
APP_DIR = SCRIPT_DIR / "app"
sys.path.insert(0, str(APP_DIR))

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BLUE}{Colors.BOLD}{text}{Colors.RESET}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.RESET}")

def print_check(name: str, passed: bool, details: str = ""):
    status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
    print(f"  {status} {name}")
    if details:
        print(f"       {details}")

def print_warning(name: str, details: str = ""):
    print(f"  {Colors.YELLOW}⚠ WARN{Colors.RESET} {name}")
    if details:
        print(f"       {details}")

def print_info(name: str, details: str = ""):
    print(f"  {Colors.BLUE}ℹ INFO{Colors.RESET} {name}")
    if details:
        print(f"       {details}")

def check_python_version() -> Tuple[bool, str]:
    """Check Python version is 3.13+"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    if version.major == 3 and version.minor >= 13:
        return True, f"Python {version_str}"
    elif version.major == 3 and version.minor >= 11:
        return True, f"Python {version_str} (3.13+ recommended)"
    else:
        return False, f"Python {version_str} (requires 3.11+)"

def check_virtual_env() -> Tuple[bool, str]:
    """Check if running in virtual environment"""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    venv_path = os.environ.get('VIRTUAL_ENV', 'Not set')
    if in_venv:
        return True, f"Virtual environment active: {venv_path}"
    else:
        return False, "Not running in virtual environment"

def check_packages() -> Tuple[bool, List[str]]:
    """Check required Python packages"""
    required = [
        ("vosk", "vosk"),
        ("pyaudio", "pyaudio"),
        ("pvporcupine", "pvporcupine"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic_settings"),
        ("numpy", "numpy"),
        ("apscheduler", "apscheduler"),
        ("python-multipart", "multipart"),
    ]
    
    results = []
    all_passed = True
    for package_name, import_name in required:
        try:
            module = __import__(import_name)
            version = getattr(module, '__version__', 'unknown')
            results.append(f"{package_name}: {version}")
        except ImportError as e:
            all_passed = False
            results.append(f"{package_name}: MISSING ({e})")
    
    return all_passed, results

def check_vosk_model() -> Tuple[bool, str]:
    """Check Vosk model exists and is loadable"""
    # Use the application's config to get the canonical model path, resolved relative to APP_DIR
    try:
        from backend.config import config
        model_path = config.vosk.model_path
        # Resolve relative paths against APP_DIR (where the app actually runs from)
        path = (APP_DIR / model_path).resolve()
    except Exception:
        # Fallback to environment variable or default, resolved against APP_DIR
        model_path = os.environ.get('VOSK_MODEL_PATH', './models/vosk-model')
        path = (APP_DIR / model_path).resolve()
    
    if not path.exists():
        return False, f"Model directory not found: {path}"
    
    required_files = ['am/final.mdl', 'conf/model.conf', 'graph/Gr.fst', 'graph/HCLr.fst']
    for f in required_files:
        if not (path / f).exists():
            return False, f"Missing model file: {f}"
    
    # Try loading the model
    try:
        from vosk import Model
        model = Model(str(path))
        return True, f"Model loaded successfully from {path}"
    except Exception as e:
        return False, f"Failed to load model: {e}"

def check_sqlite() -> Tuple[bool, str]:
    """Check SQLite database"""
    # Use config for database path, resolved relative to APP_DIR
    try:
        from backend.config import config
        db_path = (APP_DIR / config.database.path).resolve()
    except Exception:
        db_path = Path(os.environ.get('DATABASE_PATH', './data/home_automation.db')).resolve()
    
    try:
        import sqlite3
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        conn.close()
        return True, f"SQLite {version} - Database at {db_path}"
    except Exception as e:
        return False, f"SQLite error: {e}"

def check_fastapi() -> Tuple[bool, str]:
    """Check FastAPI and Uvicorn can be imported"""
    try:
        import fastapi
        import uvicorn
        return True, f"FastAPI {fastapi.__version__}, Uvicorn {uvicorn.__version__}"
    except Exception as e:
        return False, f"Import error: {e}"

def check_microphone() -> Tuple[bool, str]:
    """Check microphone/ALSA availability"""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        
        # List input devices
        input_devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_devices.append(f"  [{i}] {info['name']} ({info['maxInputChannels']} ch)")
        
        p.terminate()
        
        if input_devices:
            return True, f"Found {len(input_devices)} input device(s):\n" + "\n".join(input_devices)
        else:
            return False, "No input devices found"
    except Exception as e:
        return False, f"PyAudio error: {e}"

def check_gpio() -> Tuple[bool, str]:
    """Check GPIO availability"""
    # Check if running on Raspberry Pi
    is_pi = False
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read()
            if 'Raspberry Pi' in model:
                is_pi = True
    except:
        pass
    
    if not is_pi:
        return True, "Not on Raspberry Pi - GPIO will use mock mode"
    
    # Check RPi.GPIO
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        # Test pins 17 and 27
        GPIO.setup(17, GPIO.OUT)
        GPIO.setup(27, GPIO.OUT)
        GPIO.output(17, GPIO.LOW)
        GPIO.output(27, GPIO.LOW)
        GPIO.cleanup([17, 27])
        return True, "RPi.GPIO available - pins 17, 27 tested"
    except Exception as e:
        # Try gpiozero
        try:
            import gpiozero
            return True, f"gpiozero available (RPi.GPIO failed: {e})"
        except Exception as e2:
            return False, f"Neither RPi.GPIO nor gpiozero available: {e2}"

def check_configuration() -> Tuple[bool, str]:
    """Check configuration"""
    try:
        from backend.config import config
        issues = []
        
        # Check GPIO config
        if config.gpio.enabled:
            if not config.gpio.light_pin or not config.gpio.fan_pin:
                issues.append("GPIO enabled but pins not configured")
        
        # Check Vosk config - resolve relative to APP_DIR
        model_path = (APP_DIR / config.vosk.model_path).resolve()
        if not model_path.exists():
            issues.append(f"Vosk model path does not exist: {model_path}")
        
        # Check database path - resolve relative to APP_DIR
        db_path = (APP_DIR / config.database.path).resolve()
        if not db_path.parent.exists():
            issues.append(f"Database directory does not exist: {db_path.parent}")
        
        if issues:
            return False, "; ".join(issues)
        return True, "Configuration valid"
    except Exception as e:
        return False, f"Configuration error: {e}"

def check_required_files() -> Tuple[bool, List[str]]:
    """Check required files exist"""
    required_files = [
        "backend/main.py",
        "backend/config.py",
        "backend/core/controller.py",
        "backend/core/mode_manager.py",
        "backend/core/__init__.py",
        "backend/api/routes.py",
        "backend/api/__init__.py",
        "backend/database/database.py",
        "backend/database/__init__.py",
        "backend/hardware/gpio.py",
        "backend/hardware/__init__.py",
        "backend/input/voice.py",
        "backend/input/asr_normalizer.py",
        "backend/input/models.py",
        "backend/input/__init__.py",
        "backend/scheduler/scheduler.py",
        "backend/scheduler/__init__.py",
        "frontend/index.html",
        "frontend/app.js",
        "frontend/style.css",
        "models/vosk-model/am/final.mdl",
        "models/vosk-model/conf/model.conf",
        "models/vosk-model/graph/Gr.fst",
        "models/vosk-model/graph/HCLr.fst",
    ]
    
    missing = []
    for f in required_files:
        if not (APP_DIR / f).exists():
            missing.append(f)
    
    if missing:
        return False, missing
    return True, []

def check_systemd_service() -> Tuple[bool, str]:
    """Check systemd service configuration"""
    service_path = Path("/etc/systemd/system/home-automation.service")
    local_service = Path(__file__).parent / "home-automation.service"
    
    if not local_service.exists():
        return False, "Local service file not found"
    
    if service_path.exists():
        # Check if enabled
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "home-automation"],
                capture_output=True, text=True
            )
            enabled = result.stdout.strip() == "enabled"
            
            # Check if active
            result = subprocess.run(
                ["systemctl", "is-active", "home-automation"],
                capture_output=True, text=True
            )
            active = result.stdout.strip() == "active"
            
            status = []
            if enabled:
                status.append("enabled")
            else:
                status.append("not enabled")
            if active:
                status.append("running")
            else:
                status.append("stopped")
            
            return True, f"Service installed: {', '.join(status)}"
        except Exception as e:
            return False, f"Error checking service: {e}"
    else:
        return False, "Service not installed (run: sudo cp home-automation.service /etc/systemd/system/)"

def check_alsa() -> Tuple[bool, str]:
    """Check ALSA configuration"""
    try:
        result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
        if result.returncode == 0 and "card" in result.stdout:
            lines = [l.strip() for l in result.stdout.strip().split('\n') if 'card' in l.lower()]
            return True, f"ALSA capture devices:\n" + "\n".join(f"  {l}" for l in lines)
        else:
            return False, "No ALSA capture devices found"
    except FileNotFoundError:
        return False, "arecord not found (alsa-utils not installed)"
    except Exception as e:
        return False, f"ALSA check failed: {e}"

def check_disk_space() -> Tuple[bool, str]:
    """Check available disk space"""
    try:
        stat = os.statvfs('.')
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        if free_gb >= 1.0:
            return True, f"{free_gb:.1f} GB free"
        else:
            return False, f"Only {free_gb:.1f} GB free (need at least 1 GB)"
    except Exception as e:
        return False, f"Disk space check failed: {e}"

def check_memory() -> Tuple[bool, str]:
    """Check available memory"""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        mem_total = int([l for l in lines if l.startswith('MemTotal:')][0].split()[1])
        mem_available = int([l for l in lines if l.startswith('MemAvailable:')][0].split()[1])
        total_mb = mem_total / 1024
        avail_mb = mem_available / 1024
        return True, f"Total: {total_mb:.0f} MB, Available: {avail_mb:.0f} MB"
    except Exception as e:
        return False, f"Memory check failed: {e}"

def main():
    print_header("Raspberry Pi Home Automation - Deployment Verification")
    print(f"Platform: {platform.platform()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Hostname: {platform.node()}")
    
    all_passed = True
    warnings = []
    
    # Python version
    print_header("Python Environment")
    passed, msg = check_python_version()
    print_check("Python version", passed, msg)
    if not passed:
        all_passed = False
    
    passed, msg = check_virtual_env()
    print_check("Virtual environment", passed, msg)
    if not passed:
        all_passed = False
    
    # Packages
    print_header("Python Packages")
    passed, results = check_packages()
    for r in results:
        pkg_passed = "MISSING" not in r
        print_check(r.split(":")[0], pkg_passed, r)
    if not passed:
        all_passed = False
    
    # Vosk model
    print_header("Vosk Model")
    passed, msg = check_vosk_model()
    print_check("Vosk model", passed, msg)
    if not passed:
        all_passed = False
    
    # SQLite
    print_header("Database")
    passed, msg = check_sqlite()
    print_check("SQLite database", passed, msg)
    if not passed:
        all_passed = False
    
    # FastAPI
    print_header("Web Framework")
    passed, msg = check_fastapi()
    print_check("FastAPI/Uvicorn", passed, msg)
    if not passed:
        all_passed = False
    
    # Microphone
    print_header("Audio Input")
    passed, msg = check_microphone()
    print_check("Microphone/PyAudio", passed, msg)
    if not passed:
        all_passed = False
    
    passed, msg = check_alsa()
    print_check("ALSA devices", passed, msg)
    if not passed:
        warnings.append(f"ALSA: {msg}")
    
    # GPIO
    print_header("GPIO Hardware")
    passed, msg = check_gpio()
    print_check("GPIO", passed, msg)
    if not passed:
        warnings.append(f"GPIO: {msg}")
    
    # Configuration
    print_header("Configuration")
    passed, msg = check_configuration()
    print_check("Configuration", passed, msg)
    if not passed:
        all_passed = False
    
    # Required files
    print_header("Required Files")
    passed, missing = check_required_files()
    if passed:
        print_check("All required files present", True, f"{len(missing)} files checked")
    else:
        print_check("Required files", False, f"Missing: {', '.join(missing)}")
        all_passed = False
    
    # Systemd service
    print_header("Systemd Service")
    passed, msg = check_systemd_service()
    print_check("Systemd service", passed, msg)
    if not passed:
        warnings.append(f"Systemd: {msg}")
    
    # System resources
    print_header("System Resources")
    passed, msg = check_disk_space()
    print_check("Disk space", passed, msg)
    if not passed:
        all_passed = False
    
    passed, msg = check_memory()
    print_check("Memory", passed, msg)
    if passed and "Available:" in msg:
        # Parse available memory
        try:
            avail_mb = int(msg.split("Available: ")[1].split(" MB")[0])
            if avail_mb < 200:
                warnings.append(f"Low memory: {avail_mb} MB available")
        except:
            pass
    
    # Summary
    print_header("SUMMARY")
    if all_passed and not warnings:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL CHECKS PASSED{Colors.RESET}")
        print("System is ready for deployment!")
        return 0
    elif all_passed and warnings:
        print(f"{Colors.YELLOW}{Colors.BOLD}✓ CORE CHECKS PASSED (with warnings){Colors.RESET}")
        for w in warnings:
            print(f"  {Colors.YELLOW}⚠{Colors.RESET} {w}")
        print("System should work but review warnings above.")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ DEPLOYMENT NOT READY{Colors.RESET}")
        print("Fix the failed checks above before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())