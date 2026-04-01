from __future__ import annotations

from pathlib import Path

from cyberforge.models import ChallengeDefinition


def _required_paths_for_content(content: ChallengeDefinition) -> tuple[list[str], list[str]]:
    payload = content.model_dump()
    errors: list[str] = []
    required_paths: list[str] = []

    content_id = str(payload.get("id", "unknown"))
    gitlab = payload.get("gitlab")
    if not isinstance(gitlab, dict):
        errors.append(f"{content_id}: missing gitlab metadata")
        return required_paths, errors

    content_path = gitlab.get("content_path")
    if not isinstance(content_path, str) or not content_path.strip():
        errors.append(f"{content_id}: missing gitlab.content_path")
        return required_paths, errors

    content_path = content_path.strip().replace("\\", "/").strip("/")

    platforms = payload.get("platforms", {})
    if isinstance(platforms, dict):
        if "linux" in platforms:
            required_paths.append(f"{content_path}/setup.sh")
        if "windows" in platforms:
            required_paths.append(f"{content_path}/setup.ps1")

    if payload.get("content_type") == "killchain":
        machines = payload.get("machines", [])
        if not isinstance(machines, list) or not machines:
            errors.append(f"{content_id}: killchain missing machines list")
        else:
            for machine in machines:
                if not isinstance(machine, dict):
                    errors.append(f"{content_id}: invalid machine definition")
                    continue
                machine_id = machine.get("machine_id")
                setup_script = machine.get("setup_script")
                if not isinstance(machine_id, str) or not machine_id:
                    errors.append(f"{content_id}: machine missing machine_id")
                    continue
                if not isinstance(setup_script, str) or not setup_script:
                    errors.append(f"{content_id}: machine {machine_id} missing setup_script")
                    continue
                required_paths.append(f"{content_path}/{machine_id}/{setup_script}")

    return required_paths, errors


def validate_content_structure(
    *,
    content_items: list[ChallengeDefinition],
    content_root: Path,
) -> list[str]:
    """Validate required setup scripts exist in configured local GitLab mirror path."""
    failures: list[str] = []

    if not content_root.exists():
        return [f"content root does not exist: {content_root}"]

    for content in content_items:
        required_paths, errors = _required_paths_for_content(content)
        failures.extend(errors)

        for relative in required_paths:
            absolute = content_root / relative
            if not absolute.exists():
                failures.append(f"{content.id}: missing required file {relative}")

    return failures
