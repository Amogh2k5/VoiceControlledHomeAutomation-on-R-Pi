#!/bin/bash
set -e

if pgrep -f "uvicorn backend.main:app" > /dev/null; then
    echo "Home automation system is RUNNING."
    pgrep -f "uvicorn backend.main:app" | while read pid; do
        echo "  PID: $pid"
    done
    
    # Check if API is responding
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "  API: Responding"
    else
        echo "  API: Not responding (may be starting up)"
    fi
    exit 0
else
    echo "Home automation system is NOT RUNNING."
    exit 1
fi