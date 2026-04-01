from pathlib import Path

from cyberforge.content_structure_validation import validate_content_structure
from cyberforge.models import ChallengeDefinition


def test_content_structure_validation_passes_with_required_files(tmp_path: Path) -> None:
    (tmp_path / "challenges" / "challenge-001-sqli").mkdir(parents=True)
    (tmp_path / "challenges" / "challenge-001-sqli" / "setup.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    content = ChallengeDefinition.model_validate(
        {
            "id": "challenge-001-sqli",
            "name": "SQLi",
            "description": "Test",
            "content_type": "independent",
            "domain": "OWASP Top 10 Attacks",
            "difficulty": "easy",
            "gitlab": {"content_path": "challenges/challenge-001-sqli"},
            "tactic": "execution",
            "technique": {"attack_id": "T1190", "name": "Exploit Public-Facing Application"},
            "platforms": {"linux": {"sh": {"command": "./setup.sh"}}},
        }
    )

    failures = validate_content_structure(content_items=[content], content_root=tmp_path)
    assert failures == []


def test_content_structure_validation_fails_when_files_missing(tmp_path: Path) -> None:
    (tmp_path / "killchains" / "killchain-001-web-to-ad" / "web01").mkdir(parents=True)
    (tmp_path / "killchains" / "killchain-001-web-to-ad" / "setup.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "killchains" / "killchain-001-web-to-ad" / "web01" / "web01_setup.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    killchain = ChallengeDefinition.model_validate(
        {
            "id": "killchain-001-web-to-ad",
            "name": "Killchain Fixture",
            "description": "Test",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "gitlab": {"content_path": "killchains/killchain-001-web-to-ad"},
            "tactic": "execution",
            "technique": {"attack_id": "T1059.004", "name": "Unix Shell"},
            "platforms": {
                "linux": {"sh": {"command": "./setup.sh"}},
                "windows": {"psh": {"command": ".\\setup.ps1"}},
            },
            "machines": [
                {"machine_id": "web01", "os": "linux", "setup_script": "web01_setup.sh"},
                {"machine_id": "dc01", "os": "windows", "setup_script": "dc01_setup.ps1"},
            ],
        }
    )

    failures = validate_content_structure(content_items=[killchain], content_root=tmp_path)
    assert failures
    assert any("setup.ps1" in message for message in failures)
    assert any("dc01_setup.ps1" in message for message in failures)
