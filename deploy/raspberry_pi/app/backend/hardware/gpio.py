from backend.core.controller import HardwareInterface
from backend.config import config
import logging

logger = logging.getLogger(__name__)

_GPIO_AVAILABLE = False
_GPIO_MODULE = None

try:
    import RPi.GPIO as GPIO
    _GPIO_MODULE = GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    try:
        import gpiozero
        _GPIO_MODULE = gpiozero
        _GPIO_AVAILABLE = True
    except ImportError:
        pass


class RaspberryPiGPIO(HardwareInterface):
    def __init__(
        self,
        light_pin: int | None = None,
        fan_pin: int | None = None,
        active_high: bool | None = None,
    ):
        self._initialized = False
        self._light_pin = light_pin or config.gpio.light_pin
        self._fan_pin = fan_pin or config.gpio.fan_pin
        self._active_high = active_high if active_high is not None else config.gpio.active_high
        self._pin_map = {
            "light": self._light_pin,
            "fan": self._fan_pin,
        }
        self._states = {"light": "off", "fan": "off"}
        self._gpio = None

    def initialize(self) -> bool:
        if self._initialized:
            logger.debug("GPIO already initialized")
            return True

        if not _GPIO_AVAILABLE:
            logger.warning("RPi.GPIO/gpiozero not available. Running in mock mode.")
            return False

        try:
            self._setup_gpio()
            self._initialized = True
            logger.info(f"GPIO initialized: light=GPIO{self._light_pin}, fan=GPIO{self._fan_pin}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            return False

    def _setup_gpio(self):
        if _GPIO_MODULE.__name__ == "RPi.GPIO":
            self._setup_rpi_gpio()
        elif _GPIO_MODULE.__name__ == "gpiozero":
            self._setup_gpiozero()
        else:
            raise RuntimeError("Unknown GPIO module")

    def _setup_rpi_gpio(self):
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in [self._light_pin, self._fan_pin]:
            GPIO.setup(pin, GPIO.OUT)
            initial_state = GPIO.HIGH if not self._active_high else GPIO.LOW
            GPIO.output(pin, initial_state)

    def _setup_gpiozero(self):
        import gpiozero
        self._light_device = gpiozero.OutputDevice(self._light_pin, active_high=self._active_high, initial_value=False)
        self._fan_device = gpiozero.OutputDevice(self._fan_pin, active_high=self._active_high, initial_value=False)

    def _get_pin(self, appliance: str) -> int:
        if appliance not in self._pin_map:
            raise ValueError(f"Unknown appliance: {appliance}")
        return self._pin_map[appliance]

    def _set_gpio_state(self, pin: int, state: str):
        on_value = True if self._active_high else False
        off_value = False if self._active_high else True

        if _GPIO_MODULE.__name__ == "RPi.GPIO":
            import RPi.GPIO as GPIO
            GPIO.output(pin, GPIO.HIGH if state == "on" else GPIO.LOW)
        elif _GPIO_MODULE.__name__ == "gpiozero":
            if state == "on":
                if pin == self._light_pin:
                    self._light_device.on()
                elif pin == self._fan_pin:
                    self._fan_device.on()
            else:
                if pin == self._light_pin:
                    self._light_device.off()
                elif pin == self._fan_pin:
                    self._fan_device.off()

    def _get_gpio_state(self, pin: int) -> str:
        if _GPIO_MODULE.__name__ == "RPi.GPIO":
            import RPi.GPIO as GPIO
            value = GPIO.input(pin)
            if self._active_high:
                return "on" if value == GPIO.HIGH else "off"
            else:
                return "off" if value == GPIO.HIGH else "on"
        elif _GPIO_MODULE.__name__ == "gpiozero":
            if pin == self._light_pin:
                value = self._light_device.value
            elif pin == self._fan_pin:
                value = self._fan_device.value
            else:
                return "off"
            return "on" if value else "off"
        return "off"

    def set_state(self, appliance: str, state: str) -> bool:
        if appliance not in self._pin_map:
            logger.error(f"Unknown appliance for GPIO: {appliance}")
            return False

        if state not in ("on", "off"):
            logger.error(f"Invalid state: {state}")
            return False

        if not self._initialized and _GPIO_AVAILABLE:
            if not self.initialize():
                logger.warning("GPIO not initialized, using mock state tracking only")

        self._states[appliance] = state

        if self._initialized and _GPIO_AVAILABLE:
            try:
                pin = self._get_pin(appliance)
                self._set_gpio_state(pin, state)
                logger.info(f"GPIO: {appliance} (pin {pin}) -> {state}")
            except Exception as e:
                logger.error(f"Failed to set GPIO state for {appliance}: {e}")
                return False

        return True

    def get_state(self, appliance: str) -> str:
        if appliance not in self._pin_map:
            logger.error(f"Unknown appliance for GPIO: {appliance}")
            return "off"

        if self._initialized and _GPIO_AVAILABLE:
            try:
                pin = self._get_pin(appliance)
                actual_state = self._get_gpio_state(pin)
                self._states[appliance] = actual_state
            except Exception as e:
                logger.warning(f"Failed to read GPIO state for {appliance}: {e}")

        return self._states.get(appliance, "off")

    def cleanup(self):
        if self._initialized and _GPIO_AVAILABLE:
            try:
                if _GPIO_MODULE.__name__ == "RPi.GPIO":
                    import RPi.GPIO as GPIO
                    GPIO.cleanup([self._light_pin, self._fan_pin])
                elif _GPIO_MODULE.__name__ == "gpiozero":
                    if hasattr(self, '_light_device'):
                        self._light_device.close()
                    if hasattr(self, '_fan_device'):
                        self._fan_device.close()
                self._initialized = False
                logger.info("GPIO cleaned up")
            except Exception as e:
                logger.error(f"Error during GPIO cleanup: {e}")

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def gpio_available(self) -> bool:
        return _GPIO_AVAILABLE


def create_hardware(use_mock: bool = False) -> HardwareInterface:
    if use_mock or not _GPIO_AVAILABLE:
        from backend.core.controller import MockHardwareInterface
        return MockHardwareInterface()
    return RaspberryPiGPIO()