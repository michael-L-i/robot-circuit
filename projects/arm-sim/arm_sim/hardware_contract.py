"""Porting contract only. No hardware implementation or motor commands are supplied."""
from dataclasses import dataclass
from typing import Protocol, Literal

@dataclass(frozen=True)
class VoltageReading:
    volts: float | None
    valid_contact: bool
    timestamp: float
    reference: str = 'circuit_ground'

class BenchAdapter(Protocol):
    """Implement with calibrated, guarded primitives on the actual arm.

    Each method must return only after completion or raise on failure.
    A real adapter must supply physical sensor readings, never World data.
    """
    def pick_probe(self) -> None: ...
    def measure_test_pad(self) -> VoltageReading: ...
    def dock_probe(self) -> None: ...
    def pick_jumper(self) -> None: ...
    def place_on_mesh(self) -> None: ...
    def observe_led(self) -> bool | None: ...
    def stop(self) -> None: ...
