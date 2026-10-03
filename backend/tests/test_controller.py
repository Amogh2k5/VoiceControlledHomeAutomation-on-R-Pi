import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import HomeController, MockHardwareInterface, ApplianceType, VALID_ACTIONS
from backend.input.models import InputCommand


def test_initial_states():
    controller = HomeController()
    states = controller.get_all_states()
    
    for appliance, state in states.items():
        assert state == "off", f"Expected {appliance} to be OFF, got {state}"
    
    print("OK All initial states are OFF")


def test_get_set_state():
    controller = HomeController()
    
    assert controller.get_state("light") == "off"
    assert controller.get_state("fan") == "off"
    
    controller.set_state("light", "on")
    assert controller.get_state("light") == "on"
    
    controller.set_state("light", "off")
    assert controller.get_state("light") == "off"
    
    controller.set_state("fan", "on")
    assert controller.get_state("fan") == "on"
    
    controller.set_state("fan", "off")
    assert controller.get_state("fan") == "off"
    
    print("OK Physical appliance state management works")


def test_virtual_appliance_state():
    controller = HomeController()
    
    virtual_appliances = ["tv", "ac", "plug", "geyser", "exhaust", "garden lights"]
    
    for appliance in virtual_appliances:
        assert controller.get_state(appliance) == "off"
        controller.set_state(appliance, "on")
        assert controller.get_state(appliance) == "on"
        controller.set_state(appliance, "off")
        assert controller.get_state(appliance) == "off"
    
    print("OK Virtual appliance state management works")


def test_appliance_type_classification():
    controller = HomeController()
    
    assert controller.is_physical("light")
    assert controller.is_physical("fan")
    assert not controller.is_virtual("light")
    assert not controller.is_virtual("fan")
    
    virtual_appliances = ["tv", "ac", "plug", "geyser", "exhaust", "garden lights"]
    for appliance in virtual_appliances:
        assert controller.is_virtual(appliance), f"Expected {appliance} to be virtual"
        assert not controller.is_physical(appliance), f"Expected {appliance} to not be physical"
    
    print("OK Appliance type classification correct")


def test_execute_immediate_command():
    controller = HomeController()
    
    cmd = InputCommand(appliance="light", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    
    assert result.success
    assert result.appliance == "light"
    assert result.action == "on"
    assert result.execution_type.value == "immediate"
    assert result.delay_minutes is None
    assert "turned on" in result.message.lower()
    assert controller.get_state("light") == "on"
    
    print("OK Immediate command execution works")


def test_execute_scheduled_command():
    controller = HomeController()
    
    cmd = InputCommand(appliance="fan", action="on", delay_minutes=10)
    result = controller.execute(cmd)
    
    assert result.success
    assert result.appliance == "fan"
    assert result.action == "on"
    assert result.execution_type.value == "scheduled"
    assert result.delay_minutes == 10
    assert "scheduled" in result.message.lower()
    assert controller.get_state("fan") == "off"
    
    print("OK Scheduled command returns correct status")


def test_execute_already_in_state():
    controller = HomeController()
    controller.set_state("light", "on")
    
    cmd = InputCommand(appliance="light", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    
    assert result.success
    assert "already on" in result.message.lower()
    assert controller.get_state("light") == "on"
    
    print("OK Already-in-state handled correctly")


def test_invalid_appliance():
    controller = HomeController()
    
    cmd = InputCommand(appliance="helicopter", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    
    assert not result.success
    assert "unknown appliance" in result.message.lower()
    
    print("OK Invalid appliance rejected")


def test_invalid_action():
    controller = HomeController()
    
    cmd = InputCommand(appliance="light", action="blue", delay_minutes=None)
    result = controller.execute(cmd)
    
    assert not result.success
    assert "invalid action" in result.message.lower()
    
    print("OK Invalid action rejected")


def test_negative_delay():
    controller = HomeController()
    
    cmd = InputCommand(appliance="light", action="on", delay_minutes=-5)
    result = controller.execute(cmd)
    
    assert not result.success
    assert "invalid delay" in result.message.lower()
    
    print("OK Negative delay rejected")


def test_zero_delay():
    controller = HomeController()
    
    cmd = InputCommand(appliance="light", action="on", delay_minutes=0)
    result = controller.execute(cmd)
    
    assert not result.success
    assert "delay must be greater than 0" in result.message.lower()
    
    print("OK Zero delay rejected")


def test_execute_scheduled():
    controller = HomeController()
    
    result = controller.execute_scheduled("fan", "on")
    
    assert result.success
    assert result.appliance == "fan"
    assert result.action == "on"
    assert result.execution_type.value == "immediate"
    assert controller.get_state("fan") == "on"
    
    print("OK execute_scheduled works")


def test_hardware_interface():
    mock_hw = MockHardwareInterface()
    controller = HomeController(hardware=mock_hw)
    
    controller.set_state("light", "on")
    assert mock_hw.get_state("light") == "on"
    
    controller.set_state("light", "off")
    assert mock_hw.get_state("light") == "off"
    
    print("OK Hardware interface integration works")


def test_appliance_registry():
    from backend.core import APPLIANCE_REGISTRY
    
    physical = ["light", "fan"]
    virtual = ["tv", "ac", "plug", "geyser", "exhaust", "garden lights"]
    
    for appliance in physical:
        assert appliance in APPLIANCE_REGISTRY
        assert APPLIANCE_REGISTRY[appliance] == ApplianceType.PHYSICAL
    
    for appliance in virtual:
        assert appliance in APPLIANCE_REGISTRY
        assert APPLIANCE_REGISTRY[appliance] == ApplianceType.VIRTUAL
    
    print("OK Appliance registry complete and correct")


if __name__ == "__main__":
    print("Testing HomeController...\n")
    
    test_initial_states()
    test_get_set_state()
    test_virtual_appliance_state()
    test_appliance_type_classification()
    test_execute_immediate_command()
    test_execute_scheduled_command()
    test_execute_already_in_state()
    test_invalid_appliance()
    test_invalid_action()
    test_negative_delay()
    test_zero_delay()
    test_execute_scheduled()
    test_hardware_interface()
    test_appliance_registry()
    
    print("\nAll tests passed!")