import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.hardware import create_hardware
from backend.core.controller import MockHardwareInterface, HardwareInterface
from backend.input.models import InputCommand
from backend.core import HomeController


def test_create_hardware_mock():
    hw = create_hardware(use_mock=True)
    assert isinstance(hw, MockHardwareInterface)
    assert isinstance(hw, HardwareInterface)
    hw.set_state("light", "on")
    assert hw.get_state("light") == "on"
    print("OK create_hardware with mock works")


def test_create_hardware_auto():
    hw = create_hardware(use_mock=False)
    assert isinstance(hw, HardwareInterface)
    hw.set_state("light", "on")
    assert hw.get_state("light") == "on"
    print("OK create_hardware auto (mock fallback) works")


def test_controller_with_create_hardware():
    hw = create_hardware(use_mock=True)
    controller = HomeController(hardware=hw)
    cmd = InputCommand(appliance="fan", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    assert result.success
    assert controller.get_state("fan") == "on"
    print("OK Controller with create_hardware works")


if __name__ == "__main__":
    test_create_hardware_mock()
    test_create_hardware_auto()
    test_controller_with_create_hardware()
    print("\nAll create_hardware tests passed!")