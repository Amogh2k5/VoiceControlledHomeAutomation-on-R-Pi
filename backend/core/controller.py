from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

from backend.input.models import InputCommand

logger = logging.getLogger(__name__)


class ApplianceType(Enum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"


class ExecutionType(Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"


@dataclass
class CommandResult:
    success: bool
    appliance: str
    action: str
    execution_type: ExecutionType
    delay_minutes: Optional[int]
    message: str
    scheduled_time: Optional[str] = None


class HardwareInterface:
    def set_state(self, appliance: str, state: str) -> bool:
        raise NotImplementedError

    def get_state(self, appliance: str) -> str:
        raise NotImplementedError


class MockHardwareInterface(HardwareInterface):
    def __init__(self):
        self._states = {}

    def set_state(self, appliance: str, state: str) -> bool:
        self._states[appliance] = state
        logger.debug(f"Mock hardware: {appliance} -> {state}")
        return True

    def get_state(self, appliance: str) -> str:
        return self._states.get(appliance, "off")


APPLIANCE_REGISTRY = {
    "light": ApplianceType.PHYSICAL,
    "fan": ApplianceType.PHYSICAL,
    "tv": ApplianceType.VIRTUAL,
    "ac": ApplianceType.VIRTUAL,
    "plug": ApplianceType.VIRTUAL,
    "geyser": ApplianceType.VIRTUAL,
    "exhaust": ApplianceType.VIRTUAL,
    "garden lights": ApplianceType.VIRTUAL,
}

VALID_ACTIONS = {"on", "off"}

INITIAL_STATES = {appliance: "off" for appliance in APPLIANCE_REGISTRY}


class HomeController:
    def __init__(self, hardware: Optional[HardwareInterface] = None):
        self._states = INITIAL_STATES.copy()
        self._hardware = hardware or MockHardwareInterface()
        self._command_history = []

    def get_state(self, appliance: str) -> str:
        if appliance not in APPLIANCE_REGISTRY:
            raise ValueError(f"Unknown appliance: {appliance}")
        return self._states.get(appliance, "off")

    def set_state(self, appliance: str, state: str) -> bool:
        if appliance not in APPLIANCE_REGISTRY:
            raise ValueError(f"Unknown appliance: {appliance}")
        if state not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {state}")

        self._states[appliance] = state

        if APPLIANCE_REGISTRY[appliance] == ApplianceType.PHYSICAL:
            self._hardware.set_state(appliance, state)

        logger.info(f"Appliance state changed: {appliance} -> {state}")
        return True

    def get_all_states(self) -> dict:
        return self._states.copy()

    def get_appliance_type(self, appliance: str) -> ApplianceType:
        if appliance not in APPLIANCE_REGISTRY:
            raise ValueError(f"Unknown appliance: {appliance}")
        return APPLIANCE_REGISTRY[appliance]

    def is_physical(self, appliance: str) -> bool:
        return self.get_appliance_type(appliance) == ApplianceType.PHYSICAL

    def is_virtual(self, appliance: str) -> bool:
        return self.get_appliance_type(appliance) == ApplianceType.VIRTUAL

    def validate_command(self, command: InputCommand) -> tuple[bool, str]:
        if command.appliance not in APPLIANCE_REGISTRY:
            return False, f"Unknown appliance: {command.appliance}"

        if command.action not in VALID_ACTIONS:
            return False, f"Invalid action: {command.action}"

        if command.delay_minutes is not None:
            if command.delay_minutes < 0:
                return False, f"Invalid delay: {command.delay_minutes} minutes"
            if command.delay_minutes == 0:
                return False, "Delay must be greater than 0"

        return True, "Valid command"

    def execute(self, command: InputCommand) -> CommandResult:
        valid, message = self.validate_command(command)
        if not valid:
            logger.warning(f"Command validation failed: {message}")
            return CommandResult(
                success=False,
                appliance=command.appliance,
                action=command.action,
                execution_type=ExecutionType.IMMEDIATE,
                delay_minutes=command.delay_minutes,
                message=message,
            )

        if command.delay_minutes is not None:
            logger.info(f"Command scheduled: {command.appliance} {command.action} in {command.delay_minutes} minutes")
            return CommandResult(
                success=True,
                appliance=command.appliance,
                action=command.action,
                execution_type=ExecutionType.SCHEDULED,
                delay_minutes=command.delay_minutes,
                message=f"Command scheduled for {command.delay_minutes} minutes from now",
            )

        current_state = self.get_state(command.appliance)
        if current_state == command.action:
            message = f"{command.appliance} is already {command.action}"
            logger.info(message)
            return CommandResult(
                success=True,
                appliance=command.appliance,
                action=command.action,
                execution_type=ExecutionType.IMMEDIATE,
                delay_minutes=None,
                message=message,
            )

        self.set_state(command.appliance, command.action)

        logger.info(f"Command executed: {command.appliance} {command.action}")
        return CommandResult(
            success=True,
            appliance=command.appliance,
            action=command.action,
            execution_type=ExecutionType.IMMEDIATE,
            delay_minutes=None,
            message=f"{command.appliance} turned {command.action}",
        )

    def execute_scheduled(self, appliance: str, action: str) -> CommandResult:
        command = InputCommand(appliance=appliance, action=action, delay_minutes=None)
        return self.execute(command)

    def get_command_history(self) -> list:
        return self._command_history.copy()

    def add_to_history(self, command: InputCommand, result: CommandResult) -> None:
        self._command_history.append({
            "appliance": command.appliance,
            "action": command.action,
            "delay_minutes": command.delay_minutes,
            "success": result.success,
            "message": result.message,
            "execution_type": result.execution_type.value,
        })