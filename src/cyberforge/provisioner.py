"""CyberForge Provisioners — all modes fully functional.

Provisioner          | What it does                                              | When to use
---------------------+-----------------------------------------------------------+-----------------------------------
SSHProvisioner       | SSH into a pre-existing (bare-metal/VM) Linux host,       | Production with real Linux boxes
                     | git-clone the challenge content and run setup.sh there.   | No VirtualBox needed.
DockerProvisioner    | Pull challenge image / docker-compose from GitLab on the  | Single-host Docker-based labs
                     | local machine and start it. Returns mapped host port.      |
VirtualBoxProvisioner| Clone a VBox template VM, start it headless, query its    | Full isolated VM per lab
                     | IP via guestproperty, return real IP.                      |
MockProvisioner      | Fast deterministic in-process stub - NO REAL WORK.        | Unit tests only — not for users.

All provisioners honour the same Provisioner Protocol so the orchestrator is
decoupled from the infrastructure choice.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from cyberforge.models import ChallengeDefinition, LabSession


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class Provisioner(Protocol):
    def preflight(self) -> list[str]: ...
    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict: ...
    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(command: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess and return the result. Raises on non-zero exit if check=True."""
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_for_port(host: str, port: int, *, timeout: int = 60) -> bool:
    """Poll until TCP port is open or timeout expires. Returns True on success."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# 1. SSHProvisioner — real remote Linux host deployment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SSHConfig:
    """Connection profile for a pre-existing remote host."""
    host: str                          # Hostname or IP of the target machine
    user: str = "root"                 # SSH user (needs privilege to run setup.sh)
    port: int = 22
    identity_file: str = ""           # Path to private key, e.g. ~/.ssh/cf_id_rsa
    gitlab_repo_url: str = ""         # https://gitlab.com/your-org/content.git
    gitlab_token: str = ""            # GitLab personal access token (injected via env)
    attacker_host: str = ""           # Attacker machine host (if separate)
    attacker_user: str = "root"
    attacker_identity_file: str = ""
    workdir: str = "/opt/cyberforge"  # Where to clone on the remote machine


class SSHProvisionError(RuntimeError):
    pass


class SSHProvisioner:
    """Deploy challenge content to real remote Linux machines over SSH.

    Deployment flow per lab:
      1. SSH into the target machine.
      2. Sparse-clone the specific challenge directory from GitLab.
      3. Run challenge/setup.sh (installs deps, starts services).
      4. Verify the expected TCP service port is open.
      5. Return real machine IPs and connection metadata.

    Reset flow:
      1. SSH in, run teardown.sh if it exists, then re-run setup.sh.
    """

    def __init__(self, config: SSHConfig) -> None:
        self.config = config

    def _ssh_base(self, host: str, user: str, identity_file: str) -> list[str]:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
        ]
        if identity_file:
            cmd += ["-i", identity_file]
        cmd += [f"{user}@{host}"]
        return cmd

    def _run_remote(
        self,
        host: str,
        user: str,
        identity_file: str,
        remote_cmd: str,
        *,
        timeout: int = 300,
    ) -> str:
        full_cmd = self._ssh_base(host, user, identity_file) + [remote_cmd]
        try:
            result = _run(full_cmd, timeout=timeout, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise SSHProvisionError(
                f"SSH command failed on {host}:\n"
                f"  CMD: {remote_cmd}\n"
                f"  STDOUT: {exc.stdout}\n"
                f"  STDERR: {exc.stderr}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SSHProvisionError(f"SSH command timed out on {host}") from exc

    def _build_deploy_script(self, challenge: ChallengeDefinition) -> str:
        """Build the remote shell script that clones and deploys the challenge."""
        c = self.config
        challenge_id = challenge.id
        content_path = f"challenges/{challenge_id}"

        # Build authenticated GitLab URL
        repo_url = c.gitlab_repo_url
        if c.gitlab_token and "://" in repo_url:
            scheme, rest = repo_url.split("://", 1)
            repo_url = f"{scheme}://oauth2:{c.gitlab_token}@{rest}"

        return f"""set -e
echo "[CF] Deploying challenge: {challenge_id}"

WORKDIR="{c.workdir}/{challenge_id}"

if [ -d "$WORKDIR/.git" ]; then
  echo "[CF] Updating existing clone..."
  git -C "$WORKDIR" pull --ff-only
else
  mkdir -p "$WORKDIR"
  git clone --depth 1 --filter=blob:none --sparse "{repo_url}" "$WORKDIR"
  git -C "$WORKDIR" sparse-checkout set "{content_path}"
fi

cd "$WORKDIR/{content_path}"

if [ -f "requirements.txt" ]; then
  echo "[CF] Installing Python deps..."
  pip3 install -q -r requirements.txt 2>/dev/null || true
fi

if [ -f "package.json" ]; then
  echo "[CF] Installing Node deps..."
  npm install --silent 2>/dev/null || true
fi

chmod +x setup.sh
./setup.sh

echo "[CF] Deploy complete: {challenge_id}"
"""

    def _build_teardown_script(self, challenge: ChallengeDefinition) -> str:
        c = self.config
        challenge_id = challenge.id
        content_path = f"challenges/{challenge_id}"
        return f"""set -e
WORKDIR="{c.workdir}/{challenge_id}"
if [ -d "$WORKDIR/{content_path}" ]; then
  cd "$WORKDIR/{content_path}"
  if [ -f "teardown.sh" ]; then
    chmod +x teardown.sh
    ./teardown.sh
  else
    docker compose down --remove-orphans 2>/dev/null || true
  fi
fi
rm -rf "$WORKDIR"
echo "[CF] Teardown complete."
"""

    def preflight(self) -> list[str]:
        issues: list[str] = []
        c = self.config
        if not c.host:
            issues.append("SSHProvisioner: CYBERFORGE_TARGET_HOST is not configured")
            return issues
        if not c.gitlab_repo_url:
            issues.append("SSHProvisioner: CYBERFORGE_GITLAB_REPO_URL is not configured")
        # Test SSH connectivity
        try:
            self._run_remote(c.host, c.user, c.identity_file, "echo OK", timeout=15)
        except SSHProvisionError as exc:
            issues.append(f"SSHProvisioner: target host unreachable: {exc}")
        return issues

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        c = self.config
        script = self._build_deploy_script(challenge)
        self._run_remote(c.host, c.user, c.identity_file, script, timeout=600)

        # Determine attacker
        attacker = c.attacker_host or c.host

        return {
            "target_ip":    c.host,
            "attacker_ip":  attacker,
            "ssh_user":     c.user,
            "ssh_port":     c.port,
            "protocol":     "ssh",
            "username":     c.user,
            "challenge_name": challenge.name,
            "provisioner":  "ssh",
        }

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        c = self.config
        teardown = self._build_teardown_script(challenge)
        self._run_remote(c.host, c.user, c.identity_file, teardown, timeout=120)
        return self.deploy(challenge=challenge, lab=lab)


# ---------------------------------------------------------------------------
# 2. DockerProvisioner — single-host Docker-based labs (no external VM needed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DockerConfig:
    gitlab_repo_url: str = ""         # Content repository URL
    gitlab_token: str = ""            # Personal access token
    workdir: str = "/opt/cyberforge"  # Local directory to clone into
    default_service_port: int = 8080  # Default port the challenge listens on


class DockerProvisionError(RuntimeError):
    pass


class DockerProvisioner:
    """Clone challenge content locally and start it with docker compose.

    Useful when running CyberForge on a single server with Docker installed.
    Labs are isolated by compose project name (lab UUID).
    """

    def __init__(self, config: DockerConfig) -> None:
        self.config = config

    def _challenge_workdir(self, challenge_id: str) -> str:
        return f"{self.config.workdir}/{challenge_id}"

    def _authenticated_url(self) -> str:
        url = self.config.gitlab_repo_url
        if self.config.gitlab_token and "://" in url:
            scheme, rest = url.split("://", 1)
            return f"{scheme}://oauth2:{self.config.gitlab_token}@{rest}"
        return url

    def _clone_or_update(self, challenge_id: str, content_path: str) -> None:
        workdir = self._challenge_workdir(challenge_id)
        repo_url = self._authenticated_url()
        if not subprocess.run(["test", "-d", f"{workdir}/.git"], shell=False).returncode == 0:
            import os
            os.makedirs(workdir, exist_ok=True)
            _run(["git", "clone", "--depth", "1", "--filter=blob:none",
                  "--sparse", repo_url, workdir])
            _run(["git", "-C", workdir, "sparse-checkout", "set", content_path])
        else:
            _run(["git", "-C", workdir, "pull", "--ff-only"])

    def preflight(self) -> list[str]:
        issues: list[str] = []
        if not self.config.gitlab_repo_url:
            issues.append("DockerProvisioner: CYBERFORGE_GITLAB_REPO_URL is not configured")
        if shutil.which("docker") is None:
            issues.append("DockerProvisioner: docker not found in PATH")
        if shutil.which("git") is None:
            issues.append("DockerProvisioner: git not found in PATH")
        return issues

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        challenge_id = challenge.id
        content_path = f"challenges/{challenge_id}"
        workdir = self._challenge_workdir(challenge_id)
        project = f"cf-{lab.id[:8]}"

        try:
            self._clone_or_update(challenge_id, content_path)
        except subprocess.CalledProcessError as exc:
            raise DockerProvisionError(f"Git clone failed: {exc.stderr}") from exc

        compose_dir = f"{workdir}/{content_path}"

        # Prefer docker-compose.yml, fallback to setup.sh
        import os
        if os.path.exists(f"{compose_dir}/docker-compose.yml"):
            _run(["docker", "compose", "-p", project, "-f",
                  f"{compose_dir}/docker-compose.yml", "up", "-d", "--build"])
        elif os.path.exists(f"{compose_dir}/setup.sh"):
            _run(["bash", f"{compose_dir}/setup.sh"])
        else:
            raise DockerProvisionError(f"No docker-compose.yml or setup.sh found in {compose_dir}")

        # Wait for the service port
        port = self.config.default_service_port
        if not _wait_for_port("127.0.0.1", port, timeout=60):
            raise DockerProvisionError(
                f"Challenge service did not come up on port {port} within 60s"
            )

        return {
            "target_ip":      "127.0.0.1",
            "attacker_ip":    "127.0.0.1",
            "service_port":   port,
            "compose_project": project,
            "challenge_name": challenge.name,
            "provisioner":    "docker",
            "protocol":       "http",
        }

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        challenge_id = challenge.id
        content_path = f"challenges/{challenge_id}"
        workdir = self._challenge_workdir(challenge_id)
        project = str(lab.connection.get("compose_project", f"cf-{lab.id[:8]}"))
        compose_file = f"{workdir}/{content_path}/docker-compose.yml"

        import os
        if os.path.exists(compose_file):
            _run(["docker", "compose", "-p", project, "-f", compose_file,
                  "down", "--volumes", "--remove-orphans"], check=False)

        return self.deploy(challenge=challenge, lab=lab)


# ---------------------------------------------------------------------------
# 3. VirtualBoxProvisioner — full isolated VM per lab
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VirtualBoxConfig:
    attacker_template: str
    target_template: str
    dry_run: bool = True
    binary: str = "VBoxManage"
    ip_wait_timeout: int = 120        # Seconds to wait for VM to get an IP


class VirtualBoxCommandError(RuntimeError):
    pass


class VirtualBoxProvisioner:
    """Provision labs by cloning template VMs with VBoxManage.

    In dry_run=False mode this actually:
      1. Clones the attacker and target template VMs.
      2. Starts them headless.
      3. Polls VBoxManage guestproperty for the real IP address.
      4. Returns actual IPs so the operator can SSH/RDP into the machines.
    """

    def __init__(
        self,
        config: VirtualBoxConfig,
        executor: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.config = config
        self.executor = executor

        if not self.config.dry_run and self.executor is None and shutil.which(self.config.binary) is None:
            raise VirtualBoxCommandError(f"{self.config.binary} not found in PATH")

    def _run_vbox(self, args: list[str], *, allow_fail: bool = False) -> str:
        command = [self.config.binary, *args]
        try:
            if self.config.dry_run:
                return ""
            if self.executor is not None:
                self.executor(command)
                return ""
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
            return result.stdout.strip()
        except Exception as exc:
            if allow_fail:
                return ""
            raise VirtualBoxCommandError(f"VBoxManage failed: {' '.join(command)}") from exc

    @staticmethod
    def _vm_names(lab: LabSession) -> tuple[str, str]:
        short = lab.id.replace("-", "")[:8]
        return (f"cf-{short}-attacker", f"cf-{short}-target")

    def _clone_and_start(self, template: str, vm_name: str) -> None:
        self._run_vbox(["clonevm", template, "--name", vm_name, "--register"])
        self._run_vbox(["startvm", vm_name, "--type", "headless"])

    def _get_vm_ip(self, vm_name: str) -> str:
        """Poll VBoxManage guestproperty until the VM reports an IP (via Guest Additions)."""
        if self.config.dry_run:
            return ""
        deadline = time.monotonic() + self.config.ip_wait_timeout
        while time.monotonic() < deadline:
            try:
                out = self._run_vbox([
                    "guestproperty", "get", vm_name,
                    "/VirtualBox/GuestInfo/Net/0/V4/IP",
                ])
                # Output format: "Value: 192.168.x.x"
                if out.startswith("Value:"):
                    return out.split(":", 1)[1].strip()
            except VirtualBoxCommandError:
                pass
            time.sleep(3)
        raise VirtualBoxCommandError(
            f"VM {vm_name} did not report an IP within {self.config.ip_wait_timeout}s. "
            "Ensure VirtualBox Guest Additions are installed in the template VM."
        )

    def _destroy_vm(self, vm_name: str) -> None:
        self._run_vbox(["controlvm", vm_name, "poweroff"], allow_fail=True)
        self._run_vbox(["unregistervm", vm_name, "--delete"], allow_fail=True)

    def preflight(self) -> list[str]:
        issues: list[str] = []
        if self.config.dry_run:
            return issues
        if self.executor is None and shutil.which(self.config.binary) is None:
            issues.append(f"{self.config.binary} not found in PATH")
            return issues
        for template in (self.config.attacker_template, self.config.target_template):
            try:
                self._run_vbox(["showvminfo", template, "--machinereadable"])
            except VirtualBoxCommandError:
                issues.append(f"VirtualBox template not found or inaccessible: {template}")
        return issues

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        attacker_vm, target_vm = self._vm_names(lab)
        self._clone_and_start(self.config.attacker_template, attacker_vm)
        self._clone_and_start(self.config.target_template, target_vm)

        if self.config.dry_run:
            attacker_ip, target_ip = "dry-run-attacker", "dry-run-target"
        else:
            # Real mode: wait for Guest Additions to report IPs
            attacker_ip = self._get_vm_ip(attacker_vm)
            target_ip   = self._get_vm_ip(target_vm)

        return {
            "attacker_vm":  attacker_vm,
            "target_vm":    target_vm,
            "attacker_ip":  attacker_ip,
            "target_ip":    target_ip,
            "protocol":     "ssh",
            "username":     "student",
            "challenge_name": challenge.name,
            "provisioner":  "virtualbox",
            "dry_run":      self.config.dry_run,
        }

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        attacker_vm = str(lab.connection.get("attacker_vm", self._vm_names(lab)[0]))
        target_vm   = str(lab.connection.get("target_vm",   self._vm_names(lab)[1]))
        self._destroy_vm(attacker_vm)
        self._destroy_vm(target_vm)
        return self.deploy(challenge=challenge, lab=lab)


# ---------------------------------------------------------------------------
# 4. MockProvisioner — UNIT TESTS ONLY, not for end users
# ---------------------------------------------------------------------------

class MockProvisioner:
    """Deterministic stub for unit tests only.
    Returns fake IPs instantly without touching any infrastructure.
    Set CYBERFORGE_PROVISIONER=mock only in automated test runs.
    """

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        base   = int(lab.id.replace("-", "")[:2], 16)
        subnet = 100 + (base % 100)
        return {
            "attacker_ip":  f"192.168.{subnet}.100",
            "target_ip":    f"192.168.{subnet}.101",
            "protocol":     "ssh",
            "username":     "student",
            "challenge_name": challenge.name,
            "provisioner":  "mock",
        }

    def preflight(self) -> list[str]:
        return []

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        return self.deploy(challenge=challenge, lab=lab)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_provisioner(
    *,
    mode: str,
    # VirtualBox
    vbox_attacker_template: str,
    vbox_target_template: str,
    vbox_dry_run: bool,
    # SSH
    ssh_target_host: str = "",
    ssh_target_user: str = "root",
    ssh_target_port: int = 22,
    ssh_identity_file: str = "",
    ssh_attacker_host: str = "",
    # Docker
    docker_workdir: str = "/opt/cyberforge",
    docker_service_port: int = 8080,
    # Shared
    gitlab_repo_url: str = "",
    gitlab_token: str = "",
) -> Provisioner:
    mode_normalized = mode.strip().lower()

    if mode_normalized == "ssh":
        return SSHProvisioner(
            config=SSHConfig(
                host=ssh_target_host,
                user=ssh_target_user,
                port=ssh_target_port,
                identity_file=ssh_identity_file,
                attacker_host=ssh_attacker_host,
                gitlab_repo_url=gitlab_repo_url,
                gitlab_token=gitlab_token,
            )
        )

    if mode_normalized == "docker":
        return DockerProvisioner(
            config=DockerConfig(
                gitlab_repo_url=gitlab_repo_url,
                gitlab_token=gitlab_token,
                workdir=docker_workdir,
                default_service_port=docker_service_port,
            )
        )

    if mode_normalized == "virtualbox":
        return VirtualBoxProvisioner(
            config=VirtualBoxConfig(
                attacker_template=vbox_attacker_template,
                target_template=vbox_target_template,
                dry_run=vbox_dry_run,
            )
        )

    if mode_normalized == "mock":
        return MockProvisioner()

    raise ValueError(
        f"Unsupported provisioner mode: '{mode}'. "
        "Valid options: ssh | docker | virtualbox | mock"
    )
