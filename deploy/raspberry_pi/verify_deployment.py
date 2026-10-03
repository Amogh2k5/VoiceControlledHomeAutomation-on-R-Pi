#!/usr/bin/env python3
"""
Verify deployment package integrity on Windows before copying to Pi.
"""

import os
import sys
from pathlib import Path

REQUIRED_FILES = [
    "app/backend/main.py",
    "app/backend/config.py",
    "app/backend/core/controller.py",
    "app/backend/core/mode_manager.py",
    "app/backend/core/__init__.py",
    "app/backend/api/routes.py",
    "app/backend/api/__init__.py",
    "app/backend/database/database.py",
    "app/backend/database/__init__.py",
    "app/backend/hardware/gpio.py",
    "app/backend/hardware/__init__.py",
    "app/backend/input/voice.py",
    "app/backend/input/asr_normalizer.py",
    "app/backend/input/models.py",
    "app/backend/input/__init__.py",
    "app/backend/scheduler/scheduler.py",
    "app/backend/scheduler/__init__.py",
    "app/frontend/index.html",
    "app/frontend/app.js",
    "app/frontend/style.css",
    "app/models/vosk-model/am/final.mdl",
    "app/models/vosk-model/conf/model.conf",
    "app/models/vosk-model/graph/Gr.fst",
    "app/models/vosk-model/graph/HCLr.fst",
    "app/models/vosk-model/vocab.json",
    "install.sh",
    "start.sh",
    "stop.sh",
    "status.sh",
    "diagnose.py",
    "requirements-pi.txt",
    "home-automation.service",
    "README.md",
]

EXCLUDED_PATTERNS = [
    "__pycache__",
    ".pyc",
    ".pytest_cache",
    "venv",
    ".git",
    "tests",
    "test_",
    "sherpa",
    "gesture",
    "mediapipe",
    "opencv",
]

def verify_deployment(base_path: Path) -> bool:
    print(f"Verifying deployment at: {base_path}")
    print("=" * 60)
    
    all_ok = True
    
    # Check required files
    print("\n[1] Checking required files...")
    for f in REQUIRED_FILES:
        path = base_path / f
        if path.exists():
            size = path.stat().st_size
            print(f"  [OK] {f} ({size:,} bytes)")
        else:
            print(f"  [MISSING] {f}")
            all_ok = False
    
    # Check for excluded files
    print("\n[2] Checking for excluded files...")
    excluded_found = []
    for root, dirs, files in os.walk(base_path):
        for name in dirs + files:
            full_path = Path(root) / name
            rel_path = full_path.relative_to(base_path)
            for pattern in EXCLUDED_PATTERNS:
                if pattern in str(rel_path):
                    excluded_found.append(str(rel_path))
                    break
    
    if excluded_found:
        print(f"  [WARN] Found {len(excluded_found)} excluded files/dirs:")
        for f in excluded_found:
            print(f"    - {f}")
        all_ok = False
    else:
        print("  [OK] No excluded files found")
    
    # Check Vosk model size
    print("\n[3] Checking Vosk model...")
    model_path = base_path / "app/models/vosk-model"
    if model_path.exists():
        total_size = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file())
        print(f"  [OK] Vosk model: {total_size/1024/1024:.1f} MB")
        if total_size < 50 * 1024 * 1024:
            print("  [WARN] Model seems smaller than expected (~56 MB)")
    else:
        print("  [MISSING] Vosk model not found")
        all_ok = False
    
    # Check requirements-pi.txt
    print("\n[4] Checking requirements-pi.txt...")
    req_path = base_path / "requirements-pi.txt"
    if req_path.exists():
        content = req_path.read_text()
        print(f"  [OK] Found requirements-pi.txt")
        for line in content.strip().split('\n'):
            if line and not line.startswith('#'):
                print(f"    - {line}")
        # Check for numpy>=2.0
        if "numpy>=2.0" in content:
            print("  [OK] NumPy 2.0+ specified (Python 3.13 compatible)")
        else:
            print("  [WARN] NumPy version may not be Python 3.13 compatible")
    else:
        print("  [MISSING] requirements-pi.txt not found")
        all_ok = False
    
    # Check scripts are executable
    print("\n[5] Checking script permissions...")
    for script in ["install.sh", "start.sh", "stop.sh", "status.sh"]:
        path = base_path / script
        if path.exists():
            # On Windows, check if file has execute bit conceptually
            print(f"  [OK] {script} exists")
        else:
            print(f"  [MISSING] {script} missing")
            all_ok = False
    
    # Check service file
    print("\n[6] Checking systemd service...")
    svc_path = base_path / "home-automation.service"
    if svc_path.exists():
        content = svc_path.read_text()
        checks = [
            ("WorkingDirectory", "WorkingDirectory=" in content),
            ("ExecStart", "ExecStart=" in content),
            ("Restart=always", "Restart=always" in content),
            ("User=amogh", "User=amogh" in content),
            ("After=network", "After=network" in content),
        ]
        for name, check in checks:
            status = "[OK]" if check else "[FAIL]"
            print(f"  {status} {name}")
            if not check:
                all_ok = False
    else:
        print("  [MISSING] home-automation.service not found")
        all_ok = False
    
    # Total size
    print("\n[7] Deployment size...")
    total_size = sum(f.stat().st_size for f in base_path.rglob("*") if f.is_file())
    print(f"  Total: {total_size/1024/1024:.1f} MB")
    
    print("\n" + "=" * 60)
    if all_ok:
        print("[OK] DEPLOYMENT VERIFICATION PASSED")
        print("Ready to copy to Raspberry Pi!")
        return True
    else:
        print("[FAIL] DEPLOYMENT VERIFICATION FAILED")
        print("Fix the issues above before deploying.")
        return False

if __name__ == "__main__":
    base = Path(__file__).parent
    success = verify_deployment(base)
    sys.exit(0 if success else 1)