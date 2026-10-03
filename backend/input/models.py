from dataclasses import dataclass
from typing import Optional


@dataclass
class InputCommand:
    appliance: str
    action: str
    delay_minutes: Optional[int] = None