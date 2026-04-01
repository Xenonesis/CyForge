from __future__ import annotations

from dataclasses import dataclass
from os import getenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    repository_backend: str
    provisioner_mode: str
    vbox_attacker_template: str
    vbox_target_template: str
    vbox_dry_run: bool
    content_root: str
    validate_content_structure: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=getenv("CYBERFORGE_DATABASE_URL", "sqlite+pysqlite:///./cyberforge.db"),
            repository_backend=getenv("CYBERFORGE_REPOSITORY", "sqlalchemy").strip().lower(),
            provisioner_mode=getenv("CYBERFORGE_PROVISIONER", "mock").strip().lower(),
            vbox_attacker_template=getenv("CYBERFORGE_VBOX_ATTACKER_TEMPLATE", "cf-attacker-template"),
            vbox_target_template=getenv("CYBERFORGE_VBOX_TARGET_TEMPLATE", "cf-target-template"),
            vbox_dry_run=_as_bool(getenv("CYBERFORGE_VBOX_DRY_RUN"), True),
            content_root=getenv("CYBERFORGE_CONTENT_ROOT", "").strip(),
            validate_content_structure=_as_bool(getenv("CYBERFORGE_VALIDATE_CONTENT_STRUCTURE"), False),
        )
