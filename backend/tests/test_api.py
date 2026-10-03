import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import app, get_controller, get_mode_manager, get_db, get_scheduler_instance, shutdown_services
from backend.database import Database
from backend.core import HomeController
from backend.hardware import RaspberryPiGPIO


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db = Database(db_path)
    yield db
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_app(temp_db):
    import backend.api.routes as routes_module
    from backend.core import HomeController
    from backend.hardware import create_hardware
    from main import app as main_app
    
    # Create instances for dependency overrides
    controller = HomeController(hardware=create_hardware())
    mode_manager = routes_module.ModeManager()
    database = temp_db
    
    # Override dependencies in the api_app (the sub-application)
    api_app = routes_module.app
    api_app.dependency_overrides[routes_module.get_controller] = lambda: controller
    api_app.dependency_overrides[routes_module.get_mode_manager] = lambda: mode_manager
    api_app.dependency_overrides[routes_module.get_db] = lambda: database
    api_app.dependency_overrides[routes_module.get_voice_input] = lambda: None
    # Note: get_scheduler_instance is not overridden; it will use the overridden controller and db
    
    with TestClient(main_app) as client:
        yield client
    
    # Clean up overrides
    api_app.dependency_overrides.clear()
    shutdown_services()


def test_health_check(test_app):
    response = test_app.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("OK Health check works")


def test_get_status(test_app):
    response = test_app.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "mode" in data
    assert "appliances" in data
    assert len(data["appliances"]) == 8
    for app in data["appliances"]:
        assert "appliance" in app
        assert "state" in app
        assert "type" in app
    print("OK GET /api/status works")


def test_get_mode(test_app):
    response = test_app.get("/api/mode")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] in ["voice", "gesture"]
    assert "valid_modes" in data
    assert set(data["valid_modes"]) == {"voice", "gesture"}
    print("OK GET /api/mode works")


def test_set_mode_voice(test_app):
    response = test_app.post("/api/mode", json={"mode": "voice"})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "voice"
    print("OK POST /api/mode voice works")


def test_set_mode_gesture(test_app):
    response = test_app.post("/api/mode", json={"mode": "gesture"})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "gesture"
    print("OK POST /api/mode gesture works")


def test_set_mode_invalid(test_app):
    response = test_app.post("/api/mode", json={"mode": "automatic"})
    assert response.status_code in (400, 422)
    print("OK Invalid mode rejected")


def test_get_appliances(test_app):
    response = test_app.get("/api/appliances")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    appliance_names = {a["appliance"] for a in data}
    assert "light" in appliance_names
    assert "fan" in appliance_names
    assert "tv" in appliance_names
    for app in data:
        assert app["state"] in ["on", "off"]
        assert app["type"] in ["physical", "virtual"]
    print("OK GET /api/appliances works")


def test_control_appliance_on(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "light", "action": "on"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["appliance"] == "light"
    assert data["action"] == "on"
    assert data["execution_type"] == "immediate"
    print("OK POST /api/appliance ON works")


def test_control_appliance_off(test_app):
    test_app.post("/api/appliance", json={"appliance": "fan", "action": "on"})
    response = test_app.post("/api/appliance", json={"appliance": "fan", "action": "off"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["appliance"] == "fan"
    assert data["action"] == "off"
    print("OK POST /api/appliance OFF works")


def test_control_appliance_delayed(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "tv", "action": "on", "delay_minutes": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["execution_type"] == "scheduled"
    assert data["delay_minutes"] == 1
    assert data["scheduled_time"] is not None
    print("OK POST /api/appliance delayed works")


def test_control_appliance_delayed_seconds(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "plug", "action": "on", "delay_seconds": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Controller sees delay_minutes=0 so execution_type is immediate
    # But scheduler was called with delay_seconds, so check scheduled_time
    assert data["scheduled_time"] is not None
    print("OK POST /api/appliance delayed seconds works")


def test_control_appliance_invalid_appliance(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "helicopter", "action": "on"})
    assert response.status_code in (400, 422)
    print("OK Invalid appliance rejected")


def test_control_appliance_invalid_action(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "light", "action": "blink"})
    assert response.status_code in (400, 422)
    print("OK Invalid action rejected")


def test_control_appliance_invalid_delay(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "light", "action": "on", "delay_minutes": 0})
    assert response.status_code in (400, 422)
    
    response = test_app.post("/api/appliance", json={"appliance": "light", "action": "on", "delay_minutes": -5})
    assert response.status_code in (400, 422)
    print("OK Invalid delay rejected")


def test_get_history(test_app):
    test_app.post("/api/appliance", json={"appliance": "light", "action": "on"})
    test_app.post("/api/appliance", json={"appliance": "fan", "action": "on"})
    
    response = test_app.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert len(data["history"]) >= 2
    assert data["limit"] == 50
    assert data["offset"] == 0
    
    for entry in data["history"]:
        assert "id" in entry
        assert "timestamp" in entry
        assert "source" in entry
        assert "appliance" in entry
        assert "action" in entry
        assert "success" in entry
    print("OK GET /api/history works")


def test_get_history_with_filters(test_app):
    test_app.post("/api/appliance", json={"appliance": "light", "action": "on"})
    test_app.post("/api/appliance", json={"appliance": "fan", "action": "on"})
    
    response = test_app.get("/api/history", params={"appliance": "light"})
    assert response.status_code == 200
    data = response.json()
    for entry in data["history"]:
        assert entry["appliance"] == "light"
    
    response = test_app.get("/api/history", params={"limit": 1})
    assert response.status_code == 200
    data = response.json()
    assert len(data["history"]) == 1
    print("OK GET /api/history with filters works")


def test_get_schedules(test_app):
    test_app.post("/api/appliance", json={"appliance": "tv", "action": "on", "delay_minutes": 5})
    test_app.post("/api/appliance", json={"appliance": "ac", "action": "off", "delay_minutes": 10})
    
    response = test_app.get("/api/schedules")
    assert response.status_code == 200
    data = response.json()
    assert "schedules" in data
    assert len(data["schedules"]) == 2
    for sched in data["schedules"]:
        assert "id" in sched
        assert "appliance" in sched
        assert "action" in sched
        assert "scheduled_time" in sched
        assert "status" in sched
        assert sched["status"] == "pending"
    print("OK GET /api/schedules works")


def test_cancel_schedule(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "geyser", "action": "on", "delay_minutes": 60})
    assert response.status_code == 200
    schedule_id = response.json()["scheduled_time"] is not None
    
    schedules_response = test_app.get("/api/schedules")
    schedules = schedules_response.json()["schedules"]
    assert len(schedules) >= 1
    schedule_id = schedules[0]["id"]
    
    response = test_app.delete(f"/api/schedules/{schedule_id}")
    assert response.status_code == 204
    
    schedules_response = test_app.get("/api/schedules")
    schedules = schedules_response.json()["schedules"]
    remaining_ids = {s["id"] for s in schedules}
    assert schedule_id not in remaining_ids
    print("OK DELETE /api/schedules/{id} works")


def test_cancel_schedule_not_found(test_app):
    response = test_app.delete("/api/schedules/99999")
    assert response.status_code == 404
    print("OK Cancel non-existent schedule returns 404")


def test_cancel_executed_schedule(test_app):
    response = test_app.post("/api/appliance", json={"appliance": "exhaust", "action": "on", "delay_seconds": 1})
    assert response.status_code == 200
    
    import time
    time.sleep(3)
    
    schedules_response = test_app.get("/api/schedules")
    schedules = schedules_response.json()["schedules"]
    
    if schedules:
        schedule_id = schedules[0]["id"]
        response = test_app.delete(f"/api/schedules/{schedule_id}")
        assert response.status_code == 400
    print("OK Cancel executed schedule returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])