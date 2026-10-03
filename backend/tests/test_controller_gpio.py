import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import HomeController
from backend.hardware import RaspberryPiGPIO
from backend.input.models import InputCommand


def test_controller_with_gpio():
    gpio = RaspberryPiGPIO()
    controller = HomeController(hardware=gpio)

    print("Testing controller with RaspberryPiGPIO...")
    cmd = InputCommand(appliance="light", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    light_state = controller.get_state("light")
    print(f"light ON: {result.message}, state={light_state}")

    cmd = InputCommand(appliance="fan", action="on", delay_minutes=None)
    result = controller.execute(cmd)
    fan_state = controller.get_state("fan")
    print(f"fan ON: {result.message}, state={fan_state}")

    cmd = InputCommand(appliance="light", action="off", delay_minutes=None)
    result = controller.execute(cmd)
    light_state = controller.get_state("light")
    print(f"light OFF: {result.message}, state={light_state}")

    cmd = InputCommand(appliance="fan", action="off", delay_minutes=None)
    result = controller.execute(cmd)
    fan_state = controller.get_state("fan")
    print(f"fan OFF: {result.message}, state={fan_state}")

    print("Controller with RaspberryPiGPIO works!")


if __name__ == "__main__":
    test_controller_with_gpio()