"""Keep one physical movement command in flight at a time."""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    Action,
    BUTTON_DOWN,
    BUTTON_FOCUS,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_UP,
    SafeAction,
)


_CONTROL_MASK = BUTTON_FOCUS | BUTTON_UP | BUTTON_DOWN | BUTTON_LEFT | BUTTON_RIGHT
INPUT_PICKUP_MAX_FRAMES = 2


def bounded_delivery_age(snapshot_frame: int, issue_frame: int) -> int | None:
    """Return an age still covered by the hard pickup branches."""
    age = issue_frame - snapshot_frame
    if 0 <= age <= INPUT_PICKUP_MAX_FRAMES:
        return age
    return None


def covered_current_retry(
    snapshot_frame: int,
    observed_frame: int,
    horizon: int,
    current: Action,
    safe_actions: tuple[SafeAction, ...],
) -> bool:
    """Whether one late frame may retain an explicitly certified current input."""
    age = observed_frame - snapshot_frame
    return (
        age == INPUT_PICKUP_MAX_FRAMES + 1
        and age < horizon
        and any(candidate.action == current for candidate in safe_actions)
    )


@dataclass(frozen=True)
class LeaseStatus:
    action: Action | None = None
    timed_out: bool = False


def _issued_mask(action: Action) -> int:
    mask = BUTTON_FOCUS if action.focused else 0
    if action.dx < 0:
        mask |= BUTTON_LEFT
    elif action.dx > 0:
        mask |= BUTTON_RIGHT
    if action.dy < 0:
        mask |= BUTTON_UP
    elif action.dy > 0:
        mask |= BUTTON_DOWN
    return mask


class InputLease:
    """Hold a desired direction until the game reports that it sampled it."""

    def __init__(self) -> None:
        self.desired: Action | None = None
        self.issued_frame: int | None = None

    def status(self, native_input: int, frame: int) -> LeaseStatus:
        if self.desired is None or self.issued_frame is None:
            return LeaseStatus()
        if native_input & _CONTROL_MASK == _issued_mask(self.desired):
            self.cleared()
            return LeaseStatus()
        elapsed = frame - self.issued_frame
        if elapsed < 0 or elapsed >= INPUT_PICKUP_MAX_FRAMES:
            return LeaseStatus(timed_out=True)
        return LeaseStatus(action=self.desired)

    def issued(self, frame: int, action: Action) -> None:
        self.desired = action
        self.issued_frame = frame

    def cleared(self) -> None:
        self.desired = None
        self.issued_frame = None
