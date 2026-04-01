from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEPENDENT_DIR = ROOT / "catalog" / "challenges" / "independent"
KILLCHAIN_DIR = ROOT / "catalog" / "killchains"
ABILITY_DIR = ROOT / "catalog" / "caldera" / "abilities" / "generated"

DEFAULT_REPO = "https://gitlab.example.com/cyberforge/cyberforge-content.git"


def _linux_command(content_id: str, content_path: str, script_name: str) -> str:
    return "\n".join(
        [
            "set -e",
            f'REPO_URL="${{REPO_URL:-{DEFAULT_REPO}}}"',
            f'WORKDIR="/tmp/cyberforge-{content_id}"',
            'if [ -d "$WORKDIR" ]; then rm -rf "$WORKDIR"; fi',
            'git clone --depth 1 "$REPO_URL" "$WORKDIR"',
            f'cd "$WORKDIR/{content_path}"',
            f"chmod +x {script_name}",
            f"./{script_name}",
        ]
    )


def _windows_command(content_id: str, content_path: str, script_name: str) -> str:
    path_windows = content_path.replace("/", "\\\\")
    return "\n".join(
        [
            f'$RepoUrl = if ($env:REPO_URL) {{ $env:REPO_URL }} else {{ "{DEFAULT_REPO}" }}',
            f'$WorkDir = "C:\\\\Temp\\\\cyberforge-{content_id}"',
            'if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }',
            'git clone --depth 1 $RepoUrl $WorkDir',
            f'Set-Location "$WorkDir\\\\{path_windows}"',
            f'powershell -ExecutionPolicy Bypass -File .\\\\{script_name}',
        ]
    )


def _challenge_payload(
    *,
    challenge_id: str,
    name: str,
    description: str,
    domain: str,
    tactic: str,
    attack_id: str,
    technique_name: str,
    difficulty: str,
    os_type: str,
) -> dict:
    payload: dict = {
        "id": challenge_id,
        "name": name,
        "description": description,
        "domain": domain,
        "content_type": "independent",
        "difficulty": difficulty,
        "gitlab": {
            "repo_url": DEFAULT_REPO,
            "content_path": f"challenges/{challenge_id}",
        },
        "tactic": tactic,
        "technique": {
            "attack_id": attack_id,
            "name": technique_name,
        },
    }

    if os_type == "windows":
        payload["platforms"] = {
            "windows": {
                "psh": {
                    "command": _windows_command(
                        challenge_id,
                        f"challenges/{challenge_id}",
                        "setup.ps1",
                    )
                }
            }
        }
    elif os_type == "mixed":
        payload["platforms"] = {
            "linux": {
                "sh": {
                    "command": _linux_command(
                        challenge_id,
                        f"challenges/{challenge_id}",
                        "setup.sh",
                    )
                }
            },
            "windows": {
                "psh": {
                    "command": _windows_command(
                        challenge_id,
                        f"challenges/{challenge_id}",
                        "setup.ps1",
                    )
                }
            },
        }
    else:
        payload["platforms"] = {
            "linux": {
                "sh": {
                    "command": _linux_command(
                        challenge_id,
                        f"challenges/{challenge_id}",
                        "setup.sh",
                    )
                }
            }
        }

    return payload


def build_independent_challenges() -> list[dict]:
    return [
        _challenge_payload(
            challenge_id="challenge-001-sqli",
            name="SQL Injection Fundamentals",
            description="OWASP Top 10 SQL injection exploitation against a vulnerable query endpoint.",
            domain="OWASP Top 10 Attacks",
            tactic="execution",
            attack_id="T1190",
            technique_name="Exploit Public-Facing Application",
            difficulty="easy",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-002-xss",
            name="Cross-Site Scripting Fundamentals",
            description="Reflected XSS challenge focused on payload crafting and browser-side execution.",
            domain="OWASP Top 10 Attacks",
            tactic="execution",
            attack_id="T1059.007",
            technique_name="JavaScript",
            difficulty="easy",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-003-auth-bypass",
            name="Broken Authentication Bypass",
            description="Authentication and session bypass via weak token validation logic.",
            domain="OWASP Top 10 Attacks",
            tactic="credential-access",
            attack_id="T1078",
            technique_name="Valid Accounts",
            difficulty="easy",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-004-linux-privesc",
            name="Linux SUID Privilege Escalation",
            description="Escalate privileges through intentionally misconfigured SUID binaries.",
            domain="Linux OS attacks",
            tactic="privilege-escalation",
            attack_id="T1548.001",
            technique_name="Setuid and Setgid",
            difficulty="medium",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-005-windows-powershell",
            name="PowerShell Execution and Defense Evasion",
            description="PowerShell execution workflow and script-based payload staging lab.",
            domain="Python and Powershell for attack",
            tactic="execution",
            attack_id="T1059.001",
            technique_name="PowerShell",
            difficulty="medium",
            os_type="windows",
        ),
        _challenge_payload(
            challenge_id="challenge-006-web-lfi",
            name="Local File Inclusion Exploitation",
            description="Web file path traversal challenge resulting in credential disclosure.",
            domain="Web Attack Scenarios",
            tactic="collection",
            attack_id="T1005",
            technique_name="Data from Local System",
            difficulty="medium",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-007-web-file-upload-rce",
            name="Malicious File Upload to RCE",
            description="Upload validation bypass leading to remote code execution.",
            domain="Web Attack Scenarios",
            tactic="execution",
            attack_id="T1505.003",
            technique_name="Web Shell",
            difficulty="medium",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-008-ad-kerberoast",
            name="Active Directory Kerberoasting",
            description="Enumerate SPNs and perform Kerberoasting against weak service account passwords.",
            domain="AD Attacks",
            tactic="credential-access",
            attack_id="T1558.003",
            technique_name="Kerberoasting",
            difficulty="hard",
            os_type="windows",
        ),
        _challenge_payload(
            challenge_id="challenge-009-ad-adcs-esc1",
            name="Active Directory ADCS ESC1",
            description="Exploit ADCS ESC1 template misconfiguration for privilege escalation.",
            domain="AD Attacks",
            tactic="privilege-escalation",
            attack_id="T1649",
            technique_name="Steal or Forge Authentication Certificates",
            difficulty="hard",
            os_type="windows",
        ),
        _challenge_payload(
            challenge_id="challenge-010-ad-enum",
            name="Active Directory Enumeration",
            description="Enumerate trust paths and privileged relationships in Active Directory.",
            domain="AD Attacks",
            tactic="discovery",
            attack_id="T1087.002",
            technique_name="Domain Account",
            difficulty="medium",
            os_type="windows",
        ),
        _challenge_payload(
            challenge_id="challenge-011-ot-modbus",
            name="ICS Modbus Unauthorized Write",
            description="Manipulate Modbus registers in an OT simulation environment.",
            domain="OT/ ICS Systems",
            tactic="impact",
            attack_id="T0831",
            technique_name="Manipulation of Control",
            difficulty="hard",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-012-network-arp-mitm",
            name="ARP Spoofing MITM",
            description="Launch ARP spoofing and traffic interception against isolated targets.",
            domain="Network Attacks",
            tactic="credential-access",
            attack_id="T1557.002",
            technique_name="ARP Cache Poisoning",
            difficulty="medium",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-013-cve-log4shell-sim",
            name="CVE Log4Shell Simulation",
            description="Exploit vulnerable logging behavior similar to high-impact CVE attack chains.",
            domain="Popular and relevant attacks (CVE based, WiFi, Bruteforce attack, etc)",
            tactic="execution",
            attack_id="T1190",
            technique_name="Exploit Public-Facing Application",
            difficulty="hard",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-014-waf-bypass",
            name="WAF Bypass Payload Evasion",
            description="Bypass signature-based WAF controls with obfuscated request payloads.",
            domain="WAF Bypass Attacks",
            tactic="defense-evasion",
            attack_id="T1562",
            technique_name="Impair Defenses",
            difficulty="hard",
            os_type="linux",
        ),
        _challenge_payload(
            challenge_id="challenge-015-python-powershell",
            name="Python and PowerShell Multi-Stage",
            description="Cross-platform scripting challenge chaining Python staging and PowerShell execution.",
            domain="Python and Powershell for attack",
            tactic="execution",
            attack_id="T1059",
            technique_name="Command and Scripting Interpreter",
            difficulty="hard",
            os_type="mixed",
        ),
    ]


def build_killchains() -> list[dict]:
    return [
        {
            "id": "killchain-001-web-to-ad",
            "name": "Web Pivot to Domain Compromise",
            "description": "APT-style kill chain from web foothold to AD dominance.",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "tactic": "execution",
            "technique": {"attack_id": "T1059.004", "name": "Unix Shell"},
            "platforms": {
                "linux": {
                    "sh": {
                        "command": _linux_command(
                            "killchain-001-web-to-ad",
                            "killchains/killchain-001-web-to-ad",
                            "setup.sh",
                        )
                    }
                },
                "windows": {
                    "psh": {
                        "command": _windows_command(
                            "killchain-001-web-to-ad",
                            "killchains/killchain-001-web-to-ad",
                            "setup.ps1",
                        )
                    }
                },
            },
            "machines": [
                {"machine_id": "web01", "os": "linux", "setup_script": "web01_setup.sh"},
                {"machine_id": "pivot01", "os": "linux", "setup_script": "pivot01_setup.sh"},
                {"machine_id": "ws01", "os": "windows", "setup_script": "ws01_setup.ps1"},
                {"machine_id": "dc01", "os": "windows", "setup_script": "dc01_setup.ps1"},
            ],
            "vulnerabilities": [
                "Initial Access via vulnerable upload endpoint",
                "Privilege Escalation using misconfigured sudoers",
                "Credential Dumping from compromised workstation",
                "Lateral Movement via SMB and WinRM",
                "Domain Privilege Escalation via ADCS misconfiguration",
            ],
            "gitlab": {
                "repo_url": DEFAULT_REPO,
                "content_path": "killchains/killchain-001-web-to-ad",
            },
        },
        {
            "id": "killchain-002-phishing-to-adcs",
            "name": "Phishing, Lateral Movement, ADCS Abuse",
            "description": "Email lure to workstation compromise to certificate abuse.",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "tactic": "execution",
            "technique": {"attack_id": "T1059.001", "name": "PowerShell"},
            "platforms": {
                "linux": {
                    "sh": {
                        "command": _linux_command(
                            "killchain-002-phishing-to-adcs",
                            "killchains/killchain-002-phishing-to-adcs",
                            "setup.sh",
                        )
                    }
                },
                "windows": {
                    "psh": {
                        "command": _windows_command(
                            "killchain-002-phishing-to-adcs",
                            "killchains/killchain-002-phishing-to-adcs",
                            "setup.ps1",
                        )
                    }
                },
            },
            "machines": [
                {"machine_id": "mail01", "os": "linux", "setup_script": "mail01_setup.sh"},
                {"machine_id": "ws02", "os": "windows", "setup_script": "ws02_setup.ps1"},
                {"machine_id": "app02", "os": "linux", "setup_script": "app02_setup.sh"},
                {"machine_id": "dc02", "os": "windows", "setup_script": "dc02_setup.ps1"},
            ],
            "vulnerabilities": [
                "Phishing macro execution",
                "Token theft via in-memory injection",
                "Linux foothold escalation with kernel misconfig",
                "AD Enumeration and trust discovery",
                "ADCS template abuse for privilege escalation",
            ],
            "gitlab": {
                "repo_url": DEFAULT_REPO,
                "content_path": "killchains/killchain-002-phishing-to-adcs",
            },
        },
        {
            "id": "killchain-003-vpn-breach-ransomware",
            "name": "VPN Breach to Ransomware Objective",
            "description": "Credential access and hybrid AD/Linux movement ending in action on objective.",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "tactic": "impact",
            "technique": {"attack_id": "T1486", "name": "Data Encrypted for Impact"},
            "platforms": {
                "linux": {
                    "sh": {
                        "command": _linux_command(
                            "killchain-003-vpn-breach-ransomware",
                            "killchains/killchain-003-vpn-breach-ransomware",
                            "setup.sh",
                        )
                    }
                },
                "windows": {
                    "psh": {
                        "command": _windows_command(
                            "killchain-003-vpn-breach-ransomware",
                            "killchains/killchain-003-vpn-breach-ransomware",
                            "setup.ps1",
                        )
                    }
                },
            },
            "machines": [
                {"machine_id": "vpn01", "os": "linux", "setup_script": "vpn01_setup.sh"},
                {"machine_id": "ws03", "os": "windows", "setup_script": "ws03_setup.ps1"},
                {"machine_id": "files01", "os": "windows", "setup_script": "files01_setup.ps1"},
                {"machine_id": "ops01", "os": "linux", "setup_script": "ops01_setup.sh"},
            ],
            "vulnerabilities": [
                "VPN brute-force and credential stuffing",
                "Persistence via scheduled task",
                "Privilege escalation on file server",
                "Lateral movement using pass-the-hash",
                "Ransomware-style impact simulation",
            ],
            "gitlab": {
                "repo_url": DEFAULT_REPO,
                "content_path": "killchains/killchain-003-vpn-breach-ransomware",
            },
        },
        {
            "id": "killchain-004-supply-chain-domain",
            "name": "Supply Chain Compromise to Domain Control",
            "description": "Trojanized package delivery leading to cross-platform compromise.",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "tactic": "execution",
            "technique": {"attack_id": "T1195", "name": "Supply Chain Compromise"},
            "platforms": {
                "linux": {
                    "sh": {
                        "command": _linux_command(
                            "killchain-004-supply-chain-domain",
                            "killchains/killchain-004-supply-chain-domain",
                            "setup.sh",
                        )
                    }
                },
                "windows": {
                    "psh": {
                        "command": _windows_command(
                            "killchain-004-supply-chain-domain",
                            "killchains/killchain-004-supply-chain-domain",
                            "setup.ps1",
                        )
                    }
                },
            },
            "machines": [
                {"machine_id": "build01", "os": "linux", "setup_script": "build01_setup.sh"},
                {"machine_id": "deploy01", "os": "windows", "setup_script": "deploy01_setup.ps1"},
                {"machine_id": "app03", "os": "linux", "setup_script": "app03_setup.sh"},
                {"machine_id": "dc03", "os": "windows", "setup_script": "dc03_setup.ps1"},
            ],
            "vulnerabilities": [
                "Compromised CI dependency ingestion",
                "Code execution via malicious build artifact",
                "Credential theft from deployment host",
                "Linux to Windows lateral movement",
                "Domain admin escalation through AD ACL abuse",
            ],
            "gitlab": {
                "repo_url": DEFAULT_REPO,
                "content_path": "killchains/killchain-004-supply-chain-domain",
            },
        },
        {
            "id": "killchain-005-ics-hybrid-objective",
            "name": "Hybrid IT/OT Intrusion to Objective",
            "description": "Crossing enterprise and OT segments with Linux and AD pivoting.",
            "content_type": "killchain",
            "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
            "difficulty": "hard",
            "tactic": "impact",
            "technique": {"attack_id": "T0831", "name": "Manipulation of Control"},
            "platforms": {
                "linux": {
                    "sh": {
                        "command": _linux_command(
                            "killchain-005-ics-hybrid-objective",
                            "killchains/killchain-005-ics-hybrid-objective",
                            "setup.sh",
                        )
                    }
                },
                "windows": {
                    "psh": {
                        "command": _windows_command(
                            "killchain-005-ics-hybrid-objective",
                            "killchains/killchain-005-ics-hybrid-objective",
                            "setup.ps1",
                        )
                    }
                },
            },
            "machines": [
                {"machine_id": "web04", "os": "linux", "setup_script": "web04_setup.sh"},
                {"machine_id": "jump01", "os": "windows", "setup_script": "jump01_setup.ps1"},
                {"machine_id": "scada01", "os": "linux", "setup_script": "scada01_setup.sh"},
                {"machine_id": "dc04", "os": "windows", "setup_script": "dc04_setup.ps1"},
            ],
            "vulnerabilities": [
                "Public-facing service exploitation",
                "Credential abuse on jump host",
                "Pivot into OT segment",
                "AD trust abuse for persistence",
                "Action on objective in ICS simulation",
            ],
            "gitlab": {
                "repo_url": DEFAULT_REPO,
                "content_path": "killchains/killchain-005-ics-hybrid-objective",
            },
        },
    ]


def write_yaml_files() -> None:
    INDEPENDENT_DIR.mkdir(parents=True, exist_ok=True)
    KILLCHAIN_DIR.mkdir(parents=True, exist_ok=True)
    ABILITY_DIR.mkdir(parents=True, exist_ok=True)

    challenges = build_independent_challenges()
    killchains = build_killchains()

    for challenge in challenges:
        with (INDEPENDENT_DIR / f"{challenge['id']}.yml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump(challenge, handle, sort_keys=False)

    for killchain in killchains:
        with (KILLCHAIN_DIR / f"{killchain['id']}.yml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump(killchain, handle, sort_keys=False)

    abilities: list[dict] = []

    for challenge in [*challenges, *killchains]:
        abilities.append(
            {
                "id": f"cf-{challenge['id']}",
                "name": f"CyberForge Deploy {challenge['name']}",
                "description": f"Deploy {challenge['id']} from GitLab content.",
                "tactic": challenge["tactic"],
                "technique": challenge["technique"],
                "platforms": challenge["platforms"],
            }
        )

    for killchain in killchains:
        for machine in killchain["machines"]:
            machine_id = machine["machine_id"]
            os_type = machine["os"]
            setup_script = machine["setup_script"]
            content_id = f"{killchain['id']}-{machine_id}"
            content_path = f"killchains/{killchain['id']}/{machine_id}"

            platforms = {}
            if os_type == "linux":
                platforms = {
                    "linux": {
                        "sh": {
                            "command": _linux_command(content_id, content_path, setup_script)
                        }
                    }
                }
            else:
                platforms = {
                    "windows": {
                        "psh": {
                            "command": _windows_command(content_id, content_path, setup_script)
                        }
                    }
                }

            abilities.append(
                {
                    "id": f"cf-{killchain['id']}-{machine_id}",
                    "name": f"CyberForge Deploy {killchain['id']} {machine_id}",
                    "description": f"Deploy machine {machine_id} from {killchain['id']}.",
                    "tactic": "execution",
                    "technique": {
                        "attack_id": "T1059.004" if os_type == "linux" else "T1059.001",
                        "name": "Unix Shell" if os_type == "linux" else "PowerShell",
                    },
                    "platforms": platforms,
                }
            )

    for ability in abilities:
        with (ABILITY_DIR / f"{ability['id']}.yml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump([ability], handle, sort_keys=False)


def main() -> None:
    write_yaml_files()
    print("Generated independent challenges, killchains, and CALDERA abilities.")


if __name__ == "__main__":
    main()
