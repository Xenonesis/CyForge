from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from cyberforge.models import ChallengeDefinition, LabSession


class Provisioner(Protocol):
    def preflight(self) -> list[str]:
        ...

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        ...

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        ...


class MockProvisioner:
    """Development provisioner that returns deterministic pseudo connection data."""

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        base = int(lab.id.replace("-", "")[:2], 16)
        subnet = 100 + (base % 100)
        return {
            "attacker_ip": f"192.168.{subnet}.100",
            "target_ip": f"192.168.{subnet}.101",
            "protocol": "ssh",
            "username": "student",
            "challenge_name": challenge.name,
        }

    def preflight(self) -> list[str]:
        return []

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        # Reset returns fresh connection metadata while preserving lab identity.
        return self.deploy(challenge=challenge, lab=lab)


@dataclass(frozen=True)
class VirtualBoxConfig:
    attacker_template: str
    target_template: str
    dry_run: bool = True
    binary: str = "VBoxManage"


class VirtualBoxCommandError(RuntimeError):
    pass


class VirtualBoxProvisioner:
    """Provision labs by cloning template VMs with VBoxManage."""

    def __init__(
        self,
        config: VirtualBoxConfig,
        executor: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.config = config
        self.executor = executor

        if not self.config.dry_run and self.executor is None and shutil.which(self.config.binary) is None:
            raise VirtualBoxCommandError(f"{self.config.binary} not found in PATH")

    def _run(self, args: list[str], *, allow_fail: bool = False) -> None:
        command = [self.config.binary, *args]

        try:
            if self.config.dry_run:
                return

            if self.executor is not None:
                self.executor(command)
                return

            subprocess.run(command, check=True, capture_output=True, text=True)
        except Exception as exc:
            if allow_fail:
                return
            raise VirtualBoxCommandError(f"command failed: {' '.join(command)}") from exc

    @staticmethod
    def _names(lab: LabSession) -> tuple[str, str]:
        prefix = lab.id.split("-")[0]
        return (f"cf-{prefix}-attacker", f"cf-{prefix}-target")

    def _clone_and_start(self, template: str, vm_name: str) -> None:
        self._run(["clonevm", template, "--name", vm_name, "--register"])
        self._run(["startvm", vm_name, "--type", "headless"])

    def _destroy_vm(self, vm_name: str) -> None:
        self._run(["controlvm", vm_name, "poweroff"], allow_fail=True)
        self._run(["unregistervm", vm_name, "--delete"], allow_fail=True)

    def preflight(self) -> list[str]:
        issues: list[str] = []
        if self.config.dry_run:
            return issues

        if self.executor is None and shutil.which(self.config.binary) is None:
            issues.append(f"{self.config.binary} not found in PATH")
            return issues

        for template in (self.config.attacker_template, self.config.target_template):
            try:
                self._run(["showvminfo", template, "--machinereadable"])
            except VirtualBoxCommandError:
                issues.append(f"virtualbox template not found or inaccessible: {template}")

        return issues

    def deploy(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        attacker_vm, target_vm = self._names(lab)
        self._clone_and_start(self.config.attacker_template, attacker_vm)
        self._clone_and_start(self.config.target_template, target_vm)

        return {
            "attacker_vm": attacker_vm,
            "target_vm": target_vm,
            "provisioner": "virtualbox",
            "dry_run": self.config.dry_run,
            "challenge_name": challenge.name,
        }

    def reset(self, *, challenge: ChallengeDefinition, lab: LabSession) -> dict:
        attacker_vm = str(lab.connection.get("attacker_vm", self._names(lab)[0]))
        target_vm = str(lab.connection.get("target_vm", self._names(lab)[1]))

        self._destroy_vm(attacker_vm)
        self._destroy_vm(target_vm)

        return self.deploy(challenge=challenge, lab=lab)


def build_provisioner(
    *,
    mode: str,
    vbox_attacker_template: str,
    vbox_target_template: str,
    vbox_dry_run: bool,
) -> Provisioner:
    mode_normalized = mode.strip().lower()
    if mode_normalized == "mock":
        return MockProvisioner()
    if mode_normalized == "virtualbox":
        return VirtualBoxProvisioner(
            config=VirtualBoxConfig(
                attacker_template=vbox_attacker_template,
                target_template=vbox_target_template,
                dry_run=vbox_dry_run,
            )
        )

    raise ValueError(f"unsupported provisioner mode: {mode}")
