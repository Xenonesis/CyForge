"""CyberForge application settings — loaded from environment variables or .env file.

Priority (highest to lowest):
  1. Actual environment variables (set in shell / systemd / docker)
  2. .env file at the project root (auto-loaded via python-dotenv if available)
  3. Defaults coded here

All variables are prefixed CYBERFORGE_ to avoid conflicts.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from os import getenv
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env from project root if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        env_file = Path(__file__).resolve().parents[2] / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        pass  # python-dotenv is optional; env vars are always picked up


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- Database ---
    database_url: str
    repository_backend: str

    # --- Provisioner mode: mock | ssh | docker | virtualbox ---
    provisioner_mode: str

    # --- VirtualBox provisioner ---
    vbox_attacker_template: str
    vbox_target_template: str
    vbox_dry_run: bool

    # --- SSH provisioner (real remote machines) ---
    ssh_target_host: str
    ssh_target_user: str
    ssh_target_port: int
    ssh_identity_file: str
    ssh_attacker_host: str          # Optional separate attacker machine

    # --- Docker provisioner (single-host Docker labs) ---
    docker_workdir: str
    docker_service_port: int

    # --- GitLab (shared by SSH and Docker provisioners) ---
    gitlab_repo_url: str
    gitlab_token: str               # Personal access token (keep secret!)

    # --- Content catalog ---
    content_root: str
    validate_content_structure: bool

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()

        return cls(
            # Database
            database_url=getenv(
                "CYBERFORGE_DATABASE_URL",
                "sqlite+pysqlite:///./cyberforge.db",
            ),
            repository_backend=getenv("CYBERFORGE_REPOSITORY", "sqlalchemy").strip().lower(),

            # Provisioner
            provisioner_mode=getenv("CYBERFORGE_PROVISIONER", "mock").strip().lower(),

            # VirtualBox
            vbox_attacker_template=getenv("CYBERFORGE_VBOX_ATTACKER_TEMPLATE", "cf-attacker-template"),
            vbox_target_template=getenv("CYBERFORGE_VBOX_TARGET_TEMPLATE", "cf-target-template"),
            vbox_dry_run=_as_bool(getenv("CYBERFORGE_VBOX_DRY_RUN"), True),

            # SSH provisioner
            ssh_target_host=getenv("CYBERFORGE_TARGET_HOST", "").strip(),
            ssh_target_user=getenv("CYBERFORGE_TARGET_USER", "root").strip(),
            ssh_target_port=_as_int(getenv("CYBERFORGE_TARGET_PORT"), 22),
            ssh_identity_file=getenv("CYBERFORGE_SSH_IDENTITY_FILE", "").strip(),
            ssh_attacker_host=getenv("CYBERFORGE_ATTACKER_HOST", "").strip(),

            # Docker provisioner
            docker_workdir=getenv("CYBERFORGE_DOCKER_WORKDIR", "/opt/cyberforge").strip(),
            docker_service_port=_as_int(getenv("CYBERFORGE_DOCKER_SERVICE_PORT"), 8080),

            # GitLab
            gitlab_repo_url=getenv("CYBERFORGE_GITLAB_REPO_URL", "").strip(),
            gitlab_token=getenv("CYBERFORGE_GITLAB_TOKEN", "").strip(),

            # Content
            content_root=getenv("CYBERFORGE_CONTENT_ROOT", "").strip(),
            validate_content_structure=_as_bool(
                getenv("CYBERFORGE_VALIDATE_CONTENT_STRUCTURE"), False
            ),
        )

    def provisioner_configured(self) -> bool:
        """Return True if the selected provisioner has the required settings."""
        mode = self.provisioner_mode
        if mode == "ssh":
            return bool(self.ssh_target_host and self.gitlab_repo_url)
        if mode == "docker":
            return bool(self.gitlab_repo_url)
        if mode == "virtualbox":
            return bool(self.vbox_attacker_template and self.vbox_target_template)
        if mode == "mock":
            return True
        return False

    def provisioner_missing_config(self) -> list[str]:
        """Return list of missing config keys for the selected provisioner."""
        mode = self.provisioner_mode
        missing = []
        if mode == "ssh":
            if not self.ssh_target_host:
                missing.append("CYBERFORGE_TARGET_HOST")
            if not self.gitlab_repo_url:
                missing.append("CYBERFORGE_GITLAB_REPO_URL")
        if mode == "docker":
            if not self.gitlab_repo_url:
                missing.append("CYBERFORGE_GITLAB_REPO_URL")
            if shutil.which("docker") is None:
                missing.append("docker (not found in PATH)")
        if mode == "virtualbox":
            if not self.vbox_attacker_template:
                missing.append("CYBERFORGE_VBOX_ATTACKER_TEMPLATE")
            if not self.vbox_target_template:
                missing.append("CYBERFORGE_VBOX_TARGET_TEMPLATE")
        return missing
