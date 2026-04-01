from __future__ import annotations

from cyberforge.models import LabState


class InvalidStateTransitionError(ValueError):
    """Raised when the requested state transition is not allowed."""


_ALLOWED_TRANSITIONS: dict[LabState, set[LabState]] = {
    LabState.IDLE: {LabState.DEPLOYING, LabState.TERMINATED},
    LabState.DEPLOYING: {LabState.ACTIVE, LabState.FAILED, LabState.TERMINATED},
    LabState.ACTIVE: {LabState.RESETTING, LabState.TERMINATED, LabState.FAILED},
    LabState.RESETTING: {LabState.ACTIVE, LabState.FAILED, LabState.TERMINATED},
    LabState.FAILED: {LabState.DEPLOYING, LabState.RESETTING, LabState.TERMINATED},
    LabState.TERMINATED: set(),
}


def assert_transition(current: LabState, target: LabState) -> None:
    """Validate state transition against the allowed transition map."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"invalid transition: {current.value} -> {target.value}"
        )
