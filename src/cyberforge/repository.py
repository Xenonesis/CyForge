from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from cyberforge.models import AuditEvent, AuditQuery, ChallengeDefinition, LabSession, LabState


class LabRepository(Protocol):
    def initialize(self) -> None:
        ...

    def healthcheck(self) -> bool:
        ...

    def upsert_challenges(self, challenges: list[ChallengeDefinition]) -> None:
        ...

    def list_challenges(self) -> list[ChallengeDefinition]:
        ...

    def get_challenge(self, challenge_id: str) -> ChallengeDefinition | None:
        ...

    def create_lab(self, user_id: str, challenge_id: str) -> LabSession:
        ...

    def get_lab(self, lab_id: str) -> LabSession | None:
        ...

    def update_lab_state(
        self,
        lab_id: str,
        *,
        state: LabState,
        last_error: str | None = None,
        connection: dict | None = None,
    ) -> LabSession:
        ...

    def create_audit_event(
        self,
        *,
        action: str,
        status: str,
        lab_id: str | None,
        user_id: str | None,
        details: dict,
    ) -> AuditEvent:
        ...

    def list_audit_events(self, query: AuditQuery) -> tuple[list[AuditEvent], int]:
        ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._challenges: dict[str, ChallengeDefinition] = {}
        self._labs: dict[str, LabSession] = {}
        self._audit_events: list[AuditEvent] = []

    def initialize(self) -> None:
        return

    def healthcheck(self) -> bool:
        return True

    def upsert_challenges(self, challenges: list[ChallengeDefinition]) -> None:
        with self._lock:
            for challenge in challenges:
                self._challenges[challenge.id] = challenge

    def list_challenges(self) -> list[ChallengeDefinition]:
        with self._lock:
            return list(self._challenges.values())

    def get_challenge(self, challenge_id: str) -> ChallengeDefinition | None:
        with self._lock:
            return self._challenges.get(challenge_id)

    def create_lab(self, user_id: str, challenge_id: str) -> LabSession:
        lab_id = str(uuid4())
        lab = LabSession(id=lab_id, user_id=user_id, challenge_id=challenge_id)
        with self._lock:
            self._labs[lab_id] = lab
        return lab

    def get_lab(self, lab_id: str) -> LabSession | None:
        with self._lock:
            return self._labs.get(lab_id)

    def update_lab_state(
        self,
        lab_id: str,
        *,
        state: LabState,
        last_error: str | None = None,
        connection: dict | None = None,
    ) -> LabSession:
        with self._lock:
            lab = self._labs[lab_id]
            lab.state = state
            lab.updated_at = datetime.now(UTC)
            if last_error is not None:
                lab.last_error = last_error
            if connection is not None:
                lab.connection = connection
            self._labs[lab_id] = lab
            return lab

    def create_audit_event(
        self,
        *,
        action: str,
        status: str,
        lab_id: str | None,
        user_id: str | None,
        details: dict,
    ) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid4()),
            action=action,
            status=status,
            lab_id=lab_id,
            user_id=user_id,
            details=details,
        )
        with self._lock:
            self._audit_events.insert(0, event)
        return event

    def list_audit_events(self, query: AuditQuery) -> tuple[list[AuditEvent], int]:
        with self._lock:
            events = list(self._audit_events)

        if query.action:
            events = [event for event in events if event.action == query.action]
        if query.status:
            events = [event for event in events if event.status == query.status]
        if query.user_id:
            events = [event for event in events if event.user_id == query.user_id]
        if query.lab_id:
            events = [event for event in events if event.lab_id == query.lab_id]
        if query.request_id:
            events = [
                event
                for event in events
                if str(event.details.get("request_id", "")) == query.request_id
            ]
        if query.start_at:
            events = [event for event in events if event.created_at >= query.start_at]
        if query.end_at:
            events = [event for event in events if event.created_at <= query.end_at]

        total = len(events)
        paged = events[query.offset : query.offset + query.limit]
        return paged, total
