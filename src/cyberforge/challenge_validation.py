from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from cyberforge.models import ChallengeDefinition


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "challenge.schema.json"


def _load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as schema_file:
        return json.load(schema_file)


def validate_challenge_payload(payload: dict[str, Any]) -> list[str]:
    """Validate payload against JSON schema and model constraints."""
    schema = _load_schema()
    validator = Draft202012Validator(schema)

    errors = [
        f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(payload), key=str)
    ]

    if errors:
        return errors

    try:
        ChallengeDefinition.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive catch
        return [str(exc)]

    return []


def load_challenge_catalog(catalog_root: Path) -> tuple[list[ChallengeDefinition], dict[str, list[str]]]:
    """Load and validate all challenge YAML files from a catalog directory."""
    challenges: list[ChallengeDefinition] = []
    failures: dict[str, list[str]] = {}

    for challenge_file in sorted(catalog_root.glob("**/*.y*ml")):
        with challenge_file.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        errors = validate_challenge_payload(payload)
        if errors:
            failures[str(challenge_file)] = errors
            continue

        challenges.append(ChallengeDefinition.model_validate(payload))

    return challenges, failures
