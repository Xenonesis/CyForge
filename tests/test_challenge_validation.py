from pathlib import Path

from cyberforge.challenge_validation import load_challenge_catalog, validate_challenge_payload


def test_catalog_loads_all_independent_challenges() -> None:
    root = Path(__file__).resolve().parents[1] / "catalog" / "challenges" / "independent"
    challenges, failures = load_challenge_catalog(root)

    assert not failures
    assert len(challenges) == 15


def test_catalog_loads_all_killchains() -> None:
    root = Path(__file__).resolve().parents[1] / "catalog" / "killchains"
    challenges, failures = load_challenge_catalog(root)

    assert not failures
    assert len(challenges) == 5


def test_invalid_payload_fails_schema() -> None:
    payload = {
        "id": "bad",
        "name": "bad",
        "description": "bad",
        "tactic": "x",
        "technique": {"attack_id": "invalid", "name": "x"},
        "platforms": {},
    }

    errors = validate_challenge_payload(payload)
    assert errors
