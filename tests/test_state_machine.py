from cyberforge.models import LabState
from cyberforge.state_machine import InvalidStateTransitionError, assert_transition


def test_valid_transition_idle_to_deploying() -> None:
    assert_transition(LabState.IDLE, LabState.DEPLOYING)


def test_invalid_transition_idle_to_active() -> None:
    try:
        assert_transition(LabState.IDLE, LabState.ACTIVE)
        assert False, "expected InvalidStateTransitionError"
    except InvalidStateTransitionError:
        assert True
