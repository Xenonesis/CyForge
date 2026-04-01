from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from cyberforge.models import AuditEvent, AuditQuery, ChallengeDefinition, LabSession, LabState


class Base(DeclarativeBase):
    pass


class ChallengeRow(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tactic: Mapped[str] = mapped_column(String(120), nullable=False)
    technique: Mapped[dict] = mapped_column(JSON, nullable=False)
    platforms: Mapped[dict] = mapped_column(JSON, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class LabRow(Base):
    __tablename__ = "labs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    challenge_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    connection: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    lab_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SQLAlchemyRepository:
    """Repository implementation with PostgreSQL/SQLAlchemy persistence."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, future=True)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        # Lightweight compatibility patch for existing local DBs created before `extra` column existed.
        with self.engine.begin() as connection:
            try:
                connection.execute(text("ALTER TABLE challenges ADD COLUMN extra JSON"))
            except Exception:
                pass

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def _to_challenge_model(self, row: ChallengeRow) -> ChallengeDefinition:
        payload = {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "tactic": row.tactic,
            "technique": row.technique,
            "platforms": row.platforms,
        }
        payload.update(row.extra or {})
        return ChallengeDefinition.model_validate(payload)

    @staticmethod
    def _extract_extra(challenge: ChallengeDefinition) -> dict:
        payload = challenge.model_dump()
        reserved = {"id", "name", "description", "tactic", "technique", "platforms"}
        return {key: value for key, value in payload.items() if key not in reserved}

    def _to_lab_model(self, row: LabRow) -> LabSession:
        return LabSession(
            id=row.id,
            user_id=row.user_id,
            challenge_id=row.challenge_id,
            state=LabState(row.state),
            created_at=row.created_at,
            updated_at=row.updated_at,
            connection=row.connection or {},
            last_error=row.last_error,
        )

    def _to_audit_model(self, row: AuditEventRow) -> AuditEvent:
        return AuditEvent(
            id=row.id,
            action=row.action,
            status=row.status,
            lab_id=row.lab_id,
            user_id=row.user_id,
            details=row.details or {},
            created_at=row.created_at,
        )

    def upsert_challenges(self, challenges: list[ChallengeDefinition]) -> None:
        with self.session_factory() as session:
            for challenge in challenges:
                row = session.get(ChallengeRow, challenge.id)
                if row is None:
                    row = ChallengeRow(
                        id=challenge.id,
                        name=challenge.name,
                        description=challenge.description,
                        tactic=challenge.tactic,
                        technique=challenge.technique,
                        platforms=challenge.platforms,
                        extra=self._extract_extra(challenge),
                    )
                    session.add(row)
                else:
                    row.name = challenge.name
                    row.description = challenge.description
                    row.tactic = challenge.tactic
                    row.technique = challenge.technique
                    row.platforms = challenge.platforms
                    row.extra = self._extract_extra(challenge)
            session.commit()

    def list_challenges(self) -> list[ChallengeDefinition]:
        with self.session_factory() as session:
            rows = session.query(ChallengeRow).order_by(ChallengeRow.id.asc()).all()
            return [self._to_challenge_model(row) for row in rows]

    def get_challenge(self, challenge_id: str) -> ChallengeDefinition | None:
        with self.session_factory() as session:
            row = session.get(ChallengeRow, challenge_id)
            if row is None:
                return None
            return self._to_challenge_model(row)

    def create_lab(self, user_id: str, challenge_id: str) -> LabSession:
        now = datetime.now(UTC)
        row = LabRow(
            id=str(uuid4()),
            user_id=user_id,
            challenge_id=challenge_id,
            state=LabState.IDLE.value,
            created_at=now,
            updated_at=now,
            connection={},
            last_error=None,
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_lab_model(row)

    def get_lab(self, lab_id: str) -> LabSession | None:
        with self.session_factory() as session:
            row = session.get(LabRow, lab_id)
            if row is None:
                return None
            return self._to_lab_model(row)

    def update_lab_state(
        self,
        lab_id: str,
        *,
        state: LabState,
        last_error: str | None = None,
        connection: dict | None = None,
    ) -> LabSession:
        with self.session_factory() as session:
            row = session.get(LabRow, lab_id)
            if row is None:
                raise KeyError(f"lab not found: {lab_id}")

            row.state = state.value
            row.updated_at = datetime.now(UTC)
            if last_error is not None:
                row.last_error = last_error
            if connection is not None:
                row.connection = connection

            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_lab_model(row)

    def create_audit_event(
        self,
        *,
        action: str,
        status: str,
        lab_id: str | None,
        user_id: str | None,
        details: dict,
    ) -> AuditEvent:
        row = AuditEventRow(
            id=str(uuid4()),
            action=action,
            status=status,
            lab_id=lab_id,
            user_id=user_id,
            details=details,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_audit_model(row)

    def list_audit_events(self, query: AuditQuery) -> tuple[list[AuditEvent], int]:
        with self.session_factory() as session:
            rows = session.query(AuditEventRow).order_by(AuditEventRow.created_at.desc()).all()

        events = [self._to_audit_model(row) for row in rows]

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
