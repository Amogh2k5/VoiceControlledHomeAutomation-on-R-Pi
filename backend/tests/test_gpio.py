import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.hardware.gpio import RaspberryPiGPIO, create_hardware
from backend.core.controller import MockHardwareInterface, HardwareInterface
from backend.config import config


def test_gpio_config():
    assert hasattr(config.gpio, 'light_pin')
    assert hasattr(config.gpio, 'fan_pin')
    assert hasattr(config.gpio, 'active_high')
    
    print(f"OK GPIO config: light_pin={config.gpio.light_pin}, fan_pin={config.gpio.fan_pin}, active_high={config.gpio.active_high}")


def test_gpio_pin_mapping():
    gpio = RaspberryPiGPIO()
    
    assert "light" in gpio._pin_map
    assert "fan" in gpio._pin_map
    assert gpio._pin_map["light"] == config.gpio.light_pin
    assert gpio._pin_map["fan"] == config.gpio.fan_pin
    
    print("OK GPIO pin mapping correct")


def test_mock_hardware():
    mock = MockHardwareInterface()
    
    assert mock.set_state("light", "on")
    assert mock.get_state("light") == "on"
    
    assert mock.set_state("light", "off")
    assert mock.get_state("light") == "off"
    
    assert mock.set_state("fan", "on")
    assert mock.get_state("fan") == "on"
    
    assert mock.set_state("fan", "off")
    assert mock.get_state("fan") == "off"
    
    # Mock accepts any appliance (controller validates)
    assert mock.set_state("invalid", "on")
    assert mock.get_state("invalid") == "on"
    
    print("OK MockHardwareInterface works")


def test_create_hardware_mock():
    hardware = create_hardware(use_mock=True)
    
    assert isinstance(hardware, HardwareInterface)
    assert isinstance(hardware, MockHardwareInterface)
    
    assert hardware.set_state("light", "on")
    assert hardware.get_state("light") == "on"
    
    print("OK create_hardware with mock works")


def test_raspberry_pi_gpio_mock_mode():
    gpio = RaspberryPiGPIO()
    
    assert gpio.set_state("light", "on")
    assert gpio.get_state("light") == "on"
    
    assert gpio.set_state("light", "off")
    assert gpio.get_state("light") == "off"
    
    assert gpio.set_state("fan", "on")
    assert gpio.get_state("fan") == "on"
    
    assert gpio.set_state("fan", "off")
    assert gpio.get_state("fan") == "off"
    
    assert not gpio.set_state("invalid", "on")
    assert gpio.get_state("invalid") == "off"
    
    print("OK RaspberryPiGPIO mock mode works")


def test_gpio_cleanup():
    gpio = RaspberryPiGPIO()
    gpio.cleanup()
    print("OK GPIO cleanup works")


def test_context_manager():
    gpio = RaspberryPiGPIO()
    with gpio as h:
        assert h.set_state("light", "on")
        assert h.get_state("light") == "on"
    
    print("OK GPIO context manager works")


def test_invalid_appliance():
    gpio = RaspberryPiGPIO()
    
    assert not gpio.set_state("tv", "on")
    assert not gpio.set_state("ac", "off")
    assert gpio.get_state("tv") == "off"
    
    print("OK Invalid appliance rejected")


def test_invalid_state():
    gpio = RaspberryPiGPIO()
    
    assert not gpio.set_state("light", "invalid")
    assert not gpio.set_state("light", "on ")
    
    print("OK Invalid state rejected")


if __name__ == "__main__":
    print("Testing GPIO Hardware Layer...\n")
    
    test_gpio_config()
    test_gpio_pin_mapping()
    test_mock_hardware()
    test_create_hardware_mock()
    test_raspberry_pi_gpio_mock_mode()
    test_gpio_cleanup()
    test_context_manager()
    test_invalid_appliance()
    test_invalid_state()
    
    print("\nAll tests passed!")