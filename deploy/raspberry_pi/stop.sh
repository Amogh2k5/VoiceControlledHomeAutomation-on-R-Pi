#!/bin/bash
set -e

echo "Stopping Home Automation System..."

# Kill uvicorn processes for this application
pkill -f "uvicorn backend.main:app" || true

# Give processes time to shut down gracefully
sleep 1

# Force kill if still running
pkill -9 -f "uvicorn backend.main:app" || true

echo "Home Automation System stopped."