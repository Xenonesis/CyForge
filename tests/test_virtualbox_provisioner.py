from cyberforge.models import ChallengeDefinition, LabSession
from cyberforge.provisioner import VirtualBoxConfig, VirtualBoxProvisioner


def test_virtualbox_provisioner_emits_expected_commands() -> None:
    seen: list[list[str]] = []

    def executor(command: list[str]) -> None:
        seen.append(command)

    provisioner = VirtualBoxProvisioner(
        config=VirtualBoxConfig(
            attacker_template="attacker-template",
            target_template="target-template",
            dry_run=False,
            binary="VBoxManage",
        ),
        executor=executor,
    )

    challenge = ChallengeDefinition(
        id="challenge-001-sqli",
        name="SQLi",
        description="SQLi test",
        tactic="execution",
        technique={"attack_id": "T1190", "name": "Exploit Public-Facing Application"},
        platforms={"linux": {"sh": {"command": "echo hi"}}},
    )
    lab = LabSession(id="abcd1234-0000-0000-0000-000000000000", user_id="u1", challenge_id=challenge.id)

    result = provisioner.deploy(challenge=challenge, lab=lab)

    assert result["attacker_vm"] == "cf-abcd1234-attacker"
    assert result["target_vm"] == "cf-abcd1234-target"
    assert any(cmd[1:4] == ["clonevm", "attacker-template", "--name"] for cmd in seen)
    assert any(cmd[1:4] == ["clonevm", "target-template", "--name"] for cmd in seen)


def test_virtualbox_preflight_checks_templates() -> None:
    seen: list[list[str]] = []

    def executor(command: list[str]) -> None:
        seen.append(command)

    provisioner = VirtualBoxProvisioner(
        config=VirtualBoxConfig(
            attacker_template="attacker-template",
            target_template="target-template",
            dry_run=False,
            binary="VBoxManage",
        ),
        executor=executor,
    )

    issues = provisioner.preflight()

    assert issues == []
    assert any(cmd[1:3] == ["showvminfo", "attacker-template"] for cmd in seen)
    assert any(cmd[1:3] == ["showvminfo", "target-template"] for cmd in seen)
