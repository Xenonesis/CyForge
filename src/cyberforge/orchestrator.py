from __future__ import annotations

from cyberforge.models import LabSession, LabState
from cyberforge.provisioner import Provisioner
from cyberforge.repository import LabRepository
from cyberforge.state_machine import InvalidStateTransitionError, assert_transition


class OrchestrationError(RuntimeError):
    """Raised when orchestration cannot continue due to missing resources or state."""


class LabOrchestrator:
    def __init__(self, repository: LabRepository, provisioner: Provisioner) -> None:
        self.repository = repository
        self.provisioner = provisioner

    def deploy_lab(
        self,
        *,
        user_id: str,
        challenge_id: str,
        request_id: str | None = None,
    ) -> LabSession:
        challenge = self.repository.get_challenge(challenge_id)
        if challenge is None:
            raise OrchestrationError(f"challenge not found: {challenge_id}")

        self.repository.create_audit_event(
            action="deploy",
            status="requested",
            lab_id=None,
            user_id=user_id,
            details={"challenge_id": challenge_id, "request_id": request_id},
        )

        lab = self.repository.create_lab(user_id=user_id, challenge_id=challenge_id)

        try:
            assert_transition(lab.state, LabState.DEPLOYING)
            self.repository.update_lab_state(lab.id, state=LabState.DEPLOYING)

            connection = self.provisioner.deploy(challenge=challenge, lab=lab)

            assert_transition(LabState.DEPLOYING, LabState.ACTIVE)
            updated = self.repository.update_lab_state(
                lab.id,
                state=LabState.ACTIVE,
                connection=connection,
                last_error=None,
            )
            self.repository.create_audit_event(
                action="deploy",
                status="success",
                lab_id=updated.id,
                user_id=updated.user_id,
                details={"challenge_id": updated.challenge_id, "request_id": request_id},
            )
            return updated
        except (InvalidStateTransitionError, Exception) as exc:
            failed = self.repository.update_lab_state(
                lab.id,
                state=LabState.FAILED,
                last_error=str(exc),
            )
            self.repository.create_audit_event(
                action="deploy",
                status="failed",
                lab_id=failed.id,
                user_id=failed.user_id,
                details={
                    "error": str(exc),
                    "challenge_id": failed.challenge_id,
                    "request_id": request_id,
                },
            )
            return failed

    def reset_lab(self, *, lab_id: str, request_id: str | None = None) -> LabSession:
        lab = self.repository.get_lab(lab_id)
        if lab is None:
            raise OrchestrationError(f"lab not found: {lab_id}")

        challenge = self.repository.get_challenge(lab.challenge_id)
        if challenge is None:
            raise OrchestrationError(f"challenge not found for lab: {lab.challenge_id}")

        self.repository.create_audit_event(
            action="reset",
            status="requested",
            lab_id=lab.id,
            user_id=lab.user_id,
            details={"challenge_id": lab.challenge_id, "request_id": request_id},
        )

        try:
            assert_transition(lab.state, LabState.RESETTING)
            self.repository.update_lab_state(lab.id, state=LabState.RESETTING)

            connection = self.provisioner.reset(challenge=challenge, lab=lab)

            assert_transition(LabState.RESETTING, LabState.ACTIVE)
            updated = self.repository.update_lab_state(
                lab.id,
                state=LabState.ACTIVE,
                connection=connection,
                last_error=None,
            )
            self.repository.create_audit_event(
                action="reset",
                status="success",
                lab_id=updated.id,
                user_id=updated.user_id,
                details={"challenge_id": updated.challenge_id, "request_id": request_id},
            )
            return updated
        except (InvalidStateTransitionError, Exception) as exc:
            failed = self.repository.update_lab_state(
                lab.id,
                state=LabState.FAILED,
                last_error=str(exc),
            )
            self.repository.create_audit_event(
                action="reset",
                status="failed",
                lab_id=failed.id,
                user_id=failed.user_id,
                details={
                    "error": str(exc),
                    "challenge_id": failed.challenge_id,
                    "request_id": request_id,
                },
            )
            return failed
