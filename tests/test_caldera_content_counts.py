from pathlib import Path


def test_generated_caldera_ability_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    abilities_dir = root / "catalog" / "caldera" / "abilities" / "generated"

    files = list(abilities_dir.glob("*.yml"))
    # 15 independent + 5 killchain top-level + 20 killchain machine abilities
    assert len(files) == 40


def test_domain_coverage_present_in_independent_challenges() -> None:
    root = Path(__file__).resolve().parents[1]
    challenge_dir = root / "catalog" / "challenges" / "independent"
    payloads = [path.read_text(encoding="utf-8") for path in challenge_dir.glob("*.yml")]

    expected_domains = [
        "OWASP Top 10 Attacks",
        "Web Attack Scenarios",
        "AD Attacks",
        "Linux OS attacks",
        "OT/ ICS Systems",
        "Network Attacks",
        "Popular and relevant attacks (CVE based, WiFi, Bruteforce attack, etc)",
        "WAF Bypass Attacks",
        "Python and Powershell for attack",
    ]

    joined = "\n".join(payloads)
    for domain in expected_domains:
        assert domain in joined
