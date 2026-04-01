"""CyberForge content catalog + CALDERA ability generator.

Running this script regenerates:
  catalog/challenges/independent/*.yml     – challenge definitions
  catalog/killchains/*.yml                 – killchain definitions
  catalog/caldera/abilities/generated/*.yml – CALDERA ability TTPs (deploy + teardown)

Each generated CALDERA ability is a fully self-contained TTP that:
  1. Authenticates to GitLab (token via CALDERA variable #{gitlab.token})
  2. Clones/updates only the specific challenge subdirectory (sparse checkout)
  3. Installs runtime dependencies declared by the challenge type
  4. Starts the challenge service and verifies it is healthy
  5. Reports status back to CALDERA via exit code

A paired teardown ability (`cf-teardown-<id>`) is generated for every deploy
ability so operators can cleanly remove a hosted challenge from a machine.

Killchain abilities include one fleet-level ability (targets any agent in the
operation) and one machine-specific ability per machine role, so an operator
can selectively deploy just `web01` for a killchain without touching the DC.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INDEPENDENT_DIR = ROOT / "catalog" / "challenges" / "independent"
KILLCHAIN_DIR = ROOT / "catalog" / "killchains"
ABILITY_DIR = ROOT / "catalog" / "caldera" / "abilities" / "generated"

DEFAULT_REPO = "https://gitlab.example.com/cyberforge/cyberforge-content.git"

# ---------------------------------------------------------------------------
# Dependency installers keyed by challenge "stack" tag
# ---------------------------------------------------------------------------
# These are injected into the deploy command before setup.sh is called.
# Each entry is a shell snippet that is idempotent (safe to run twice).

_LINUX_DEP_SNIPPETS: dict[str, str] = {
    "docker": (
        "if ! command -v docker >/dev/null 2>&1; then\n"
        "  echo '[CF] Installing Docker...'\n"
        "  curl -fsSL https://get.docker.com | sh\n"
        "  systemctl enable --now docker\n"
        "fi\n"
        "if ! command -v docker compose >/dev/null 2>&1; then\n"
        "  apt-get install -y docker-compose-plugin 2>/dev/null || true\n"
        "fi"
    ),
    "python": (
        "if ! command -v python3 >/dev/null 2>&1; then\n"
        "  apt-get update -q && apt-get install -y python3 python3-pip python3-venv\n"
        "fi"
    ),
    "node": (
        "if ! command -v node >/dev/null 2>&1; then\n"
        "  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -\n"
        "  apt-get install -y nodejs\n"
        "fi"
    ),
    "java": (
        "if ! command -v java >/dev/null 2>&1; then\n"
        "  apt-get update -q && apt-get install -y default-jre-headless\n"
        "fi"
    ),
    "scada": (
        "if ! command -v python3 >/dev/null 2>&1; then\n"
        "  apt-get update -q && apt-get install -y python3 python3-pip\n"
        "fi\n"
        "pip3 install pymodbus 2>/dev/null || true"
    ),
    "network": (
        "apt-get update -q && apt-get install -y arp-scan dsniff net-tools 2>/dev/null || true"
    ),
    "ad": "",   # AD challenges run on Windows; Linux agent only pulls files
    "none": "",
}

_WINDOWS_DEP_SNIPPETS: dict[str, str] = {
    "docker": (
        "if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {\n"
        "  Write-Host '[CF] Docker not found. Install Docker Desktop or Docker CE first.'\n"
        "  exit 1\n"
        "}"
    ),
    "python": (
        "if (-not (Get-Command python -ErrorAction SilentlyContinue)) {\n"
        "  winget install -e --id Python.Python.3 --silent --accept-source-agreements 2>$null\n"
        "}"
    ),
    "node": (
        "if (-not (Get-Command node -ErrorAction SilentlyContinue)) {\n"
        "  winget install -e --id OpenJS.NodeJS --silent --accept-source-agreements 2>$null\n"
        "}"
    ),
    "ad": (
        "if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {\n"
        "  Add-WindowsFeature -Name RSAT-AD-PowerShell -IncludeAllSubFeature 2>$null\n"
        "}"
    ),
    "none": "",
}


# ---------------------------------------------------------------------------
# Shell command builders
# ---------------------------------------------------------------------------

def _linux_deploy_command(
    content_id: str,
    content_path: str,
    setup_script: str = "setup.sh",
    stack: str = "none",
    health_check: str = "",
) -> str:
    dep_block = _LINUX_DEP_SNIPPETS.get(stack, "")
    health_block = (
        "\necho '[CF] Running health check...'\n" + health_check + "\necho '[CF] Health check passed.'"
        if health_check
        else ""
    )
    lines = [
        "set -e",
        "echo '[CF] CyberForge challenge deploy starting: " + content_id + "'",
        "",
        "# --- Authenticate to GitLab ---",
        # CALDERA variable #{gitlab.token} is expanded at agent runtime
        'GITLAB_TOKEN="${GITLAB_TOKEN:-#{gitlab.token}}"',
        'REPO_URL="${REPO_URL:-' + DEFAULT_REPO + '}"',
        "",
        "# Inject token into URL if provided",
        'if [ -n "$GITLAB_TOKEN" ] && [ "$GITLAB_TOKEN" != "#{gitlab.token}" ]; then',
        '  REPO_AUTH_URL="$(echo "$REPO_URL" | sed "s|https://|https://oauth2:${GITLAB_TOKEN}@|")"',
        "else",
        '  REPO_AUTH_URL="$REPO_URL"',
        "fi",
        "",
        "# --- Sparse-checkout only the challenge directory ---",
        'WORKDIR="/opt/cyberforge/' + content_id + '"',
        'if [ -d "$WORKDIR/.git" ]; then',
        "  echo '[CF] Updating existing clone...'",
        '  git -C "$WORKDIR" pull --ff-only',
        "else",
        '  mkdir -p "$WORKDIR"',
        '  git clone --depth 1 --filter=blob:none --sparse "$REPO_AUTH_URL" "$WORKDIR"',
        '  git -C "$WORKDIR" sparse-checkout set "' + content_path + '"',
        "fi",
        "",
        '# --- Change into challenge directory ---',
        'cd "$WORKDIR/' + content_path + '"',
        "",
    ]
    if dep_block:
        lines += ["# --- Install dependencies ---", dep_block, ""]
    lines += [
        "# --- Run challenge setup ---",
        "chmod +x " + setup_script,
        "./" + setup_script,
    ]
    if health_block:
        lines.append(health_block)
    lines += [
        "",
        "echo '[CF] Challenge " + content_id + " deployed successfully.'",
    ]
    return "\n".join(lines)


def _linux_teardown_command(content_id: str, content_path: str, teardown_script: str = "teardown.sh") -> str:
    return "\n".join([
        "set -e",
        "echo '[CF] Tearing down: " + content_id + "'",
        'WORKDIR="/opt/cyberforge/' + content_id + '"',
        'if [ -d "$WORKDIR/' + content_path + '" ]; then',
        '  cd "$WORKDIR/' + content_path + '"',
        '  if [ -f "' + teardown_script + '" ]; then',
        "    chmod +x " + teardown_script,
        "    ./" + teardown_script,
        "  else",
        "    echo '[CF] No teardown script found — stopping any Docker containers if present'",
        '    docker compose down --remove-orphans 2>/dev/null || true',
        "  fi",
        "fi",
        'rm -rf "$WORKDIR"',
        "echo '[CF] Teardown complete: " + content_id + "'",
    ])


def _windows_deploy_command(
    content_id: str,
    content_path: str,
    setup_script: str = "setup.ps1",
    stack: str = "none",
    health_check: str = "",
) -> str:
    dep_block = _WINDOWS_DEP_SNIPPETS.get(stack, "")
    health_block = (
        "\nWrite-Host '[CF] Running health check...'\n" + health_check + "\nWrite-Host '[CF] Health check passed.'"
        if health_check
        else ""
    )
    path_windows = content_path.replace("/", "\\\\")
    lines = [
        '$ErrorActionPreference = "Stop"',
        'Write-Host "[CF] CyberForge challenge deploy starting: ' + content_id + '"',
        "",
        "# --- Authenticate to GitLab ---",
        '$GitlabToken = if ($env:GITLAB_TOKEN) { $env:GITLAB_TOKEN } elseif ("#{gitlab.token}" -ne "#{gitlab.token}") { "#{gitlab.token}" } else { "" }',
        '$RepoUrl = if ($env:REPO_URL) { $env:REPO_URL } else { "' + DEFAULT_REPO + '" }',
        "",
        "if ($GitlabToken) {",
        '  $RepoAuthUrl = $RepoUrl -replace "https://", "https://oauth2:$($GitlabToken)@"',
        "} else {",
        "  $RepoAuthUrl = $RepoUrl",
        "}",
        "",
        "# --- Sparse-checkout only the challenge directory ---",
        '$WorkDir = "C:\\\\CyberForge\\\\' + content_id + '"',
        "if (Test-Path \"$WorkDir\\.git\") {",
        "  Write-Host '[CF] Updating existing clone...'",
        "  git -C $WorkDir pull --ff-only",
        "} else {",
        "  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null",
        "  git clone --depth 1 --filter=blob:none --sparse $RepoAuthUrl $WorkDir",
        '  git -C $WorkDir sparse-checkout set "' + content_path + '"',
        "}",
        "",
        '# --- Change into challenge directory ---',
        "Set-Location \"$WorkDir\\\\" + path_windows + "\"",
        "",
    ]
    if dep_block:
        lines += ["# --- Install dependencies ---", dep_block, ""]
    lines += [
        "# --- Run challenge setup ---",
        "powershell -ExecutionPolicy Bypass -File .\\\\" + setup_script,
    ]
    if health_block:
        lines.append(health_block)
    lines += [
        "",
        'Write-Host "[CF] Challenge ' + content_id + ' deployed successfully."',
    ]
    return "\n".join(lines)


def _windows_teardown_command(content_id: str, content_path: str, teardown_script: str = "teardown.ps1") -> str:
    path_windows = content_path.replace("/", "\\\\")
    return "\n".join([
        '$ErrorActionPreference = "SilentlyContinue"',
        'Write-Host "[CF] Tearing down: ' + content_id + '"',
        '$WorkDir = "C:\\\\CyberForge\\\\' + content_id + '"',
        'if (Test-Path "$WorkDir\\\\" + "' + path_windows + '") {',
        '  Set-Location "$WorkDir\\\\" + "' + path_windows + '"',
        '  if (Test-Path ".\\\\" + "' + teardown_script + '") {',
        "    powershell -ExecutionPolicy Bypass -File .\\\\" + teardown_script,
        "  }",
        "}",
        "Remove-Item -Recurse -Force $WorkDir -ErrorAction SilentlyContinue",
        'Write-Host "[CF] Teardown complete: ' + content_id + '"',
    ])


# ---------------------------------------------------------------------------
# Challenge / killchain definitions
# ---------------------------------------------------------------------------

# stack: maps to dependency installer key above
# health_check_linux / health_check_windows: optional shell snippet run after setup.sh

_CHALLENGES = [
    dict(
        challenge_id="challenge-001-sqli",
        name="SQL Injection Fundamentals",
        description="OWASP Top 10 SQL injection exploitation against a vulnerable query endpoint.",
        domain="OWASP Top 10 Attacks",
        tactic="execution",
        attack_id="T1190",
        technique_name="Exploit Public-Facing Application",
        difficulty="easy",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health || (echo '[CF] Health check failed' && exit 1)",
    ),
    dict(
        challenge_id="challenge-002-xss",
        name="Cross-Site Scripting Fundamentals",
        description="Reflected XSS challenge focused on payload crafting and browser-side execution.",
        domain="OWASP Top 10 Attacks",
        tactic="execution",
        attack_id="T1059.007",
        technique_name="JavaScript",
        difficulty="easy",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health || (echo '[CF] Health check failed' && exit 1)",
    ),
    dict(
        challenge_id="challenge-003-auth-bypass",
        name="Broken Authentication Bypass",
        description="Authentication and session bypass via weak token validation logic.",
        domain="OWASP Top 10 Attacks",
        tactic="credential-access",
        attack_id="T1078",
        technique_name="Valid Accounts",
        difficulty="easy",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health || (echo '[CF] Health check failed' && exit 1)",
    ),
    dict(
        challenge_id="challenge-004-linux-privesc",
        name="Linux SUID Privilege Escalation",
        description="Escalate privileges through intentionally misconfigured SUID binaries.",
        domain="Linux OS attacks",
        tactic="privilege-escalation",
        attack_id="T1548.001",
        technique_name="Setuid and Setgid",
        difficulty="medium",
        os_type="linux",
        stack="none",
        health_check_linux="id && ls -la /usr/local/bin/cf_suid_target 2>/dev/null || echo '[CF] SUID target may not exist yet'",
    ),
    dict(
        challenge_id="challenge-005-windows-powershell",
        name="PowerShell Execution and Defense Evasion",
        description="PowerShell execution workflow and script-based payload staging lab.",
        domain="Python and Powershell for attack",
        tactic="execution",
        attack_id="T1059.001",
        technique_name="PowerShell",
        difficulty="medium",
        os_type="windows",
        stack="none",
        health_check_windows="if (-not (Test-Path C:\\CyberForge\\challenge-005-windows-powershell\\README.txt)) { Write-Error '[CF] Setup incomplete' }",
    ),
    dict(
        challenge_id="challenge-006-web-lfi",
        name="Local File Inclusion Exploitation",
        description="Web file path traversal challenge resulting in credential disclosure.",
        domain="Web Attack Scenarios",
        tactic="collection",
        attack_id="T1005",
        technique_name="Data from Local System",
        difficulty="medium",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health || (echo '[CF] Health check failed' && exit 1)",
    ),
    dict(
        challenge_id="challenge-007-web-file-upload-rce",
        name="Malicious File Upload to RCE",
        description="Upload validation bypass leading to remote code execution.",
        domain="Web Attack Scenarios",
        tactic="execution",
        attack_id="T1505.003",
        technique_name="Web Shell",
        difficulty="medium",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health || (echo '[CF] Health check failed' && exit 1)",
    ),
    dict(
        challenge_id="challenge-008-ad-kerberoast",
        name="Active Directory Kerberoasting",
        description="Enumerate SPNs and perform Kerberoasting against weak service account passwords.",
        domain="AD Attacks",
        tactic="credential-access",
        attack_id="T1558.003",
        technique_name="Kerberoasting",
        difficulty="hard",
        os_type="windows",
        stack="ad",
        health_check_windows="Get-ADUser -Filter * -Properties ServicePrincipalName | Where-Object { $_.ServicePrincipalName } | Measure-Object | Select-Object -ExpandProperty Count",
    ),
    dict(
        challenge_id="challenge-009-ad-adcs-esc1",
        name="Active Directory ADCS ESC1",
        description="Exploit ADCS ESC1 template misconfiguration for privilege escalation.",
        domain="AD Attacks",
        tactic="privilege-escalation",
        attack_id="T1649",
        technique_name="Steal or Forge Authentication Certificates",
        difficulty="hard",
        os_type="windows",
        stack="ad",
        health_check_windows="Get-CATemplate | Measure-Object | Select-Object -ExpandProperty Count",
    ),
    dict(
        challenge_id="challenge-010-ad-enum",
        name="Active Directory Enumeration",
        description="Enumerate trust paths and privileged relationships in Active Directory.",
        domain="AD Attacks",
        tactic="discovery",
        attack_id="T1087.002",
        technique_name="Domain Account",
        difficulty="medium",
        os_type="windows",
        stack="ad",
        health_check_windows="(Get-ADDomain).DNSRoot",
    ),
    dict(
        challenge_id="challenge-011-ot-modbus",
        name="ICS Modbus Unauthorized Write",
        description="Manipulate Modbus registers in an OT simulation environment.",
        domain="OT/ ICS Systems",
        tactic="impact",
        attack_id="T0831",
        technique_name="Manipulation of Control",
        difficulty="hard",
        os_type="linux",
        stack="scada",
        health_check_linux="python3 -c \"from pymodbus.client import ModbusTcpClient; c=ModbusTcpClient('localhost',port=502); print('Modbus OK' if c.connect() else 'Modbus FAIL')\"",
    ),
    dict(
        challenge_id="challenge-012-network-arp-mitm",
        name="ARP Spoofing MITM",
        description="Launch ARP spoofing and traffic interception against isolated targets.",
        domain="Network Attacks",
        tactic="credential-access",
        attack_id="T1557.002",
        technique_name="ARP Cache Poisoning",
        difficulty="medium",
        os_type="linux",
        stack="network",
        health_check_linux="arp-scan --localnet --quiet | head -5 && echo '[CF] Network scan OK'",
    ),
    dict(
        challenge_id="challenge-013-cve-log4shell-sim",
        name="CVE Log4Shell Simulation",
        description="Exploit vulnerable logging behavior similar to high-impact CVE attack chains.",
        domain="Popular and relevant attacks (CVE based, WiFi, Bruteforce attack, etc)",
        tactic="execution",
        attack_id="T1190",
        technique_name="Exploit Public-Facing Application",
        difficulty="hard",
        os_type="linux",
        stack="java",
        health_check_linux="curl -sf http://localhost:8443/health || curl -sf http://localhost:8080/health || echo '[CF] App may still be starting'",
    ),
    dict(
        challenge_id="challenge-014-waf-bypass",
        name="WAF Bypass Payload Evasion",
        description="Bypass signature-based WAF controls with obfuscated request payloads.",
        domain="WAF Bypass Attacks",
        tactic="defense-evasion",
        attack_id="T1562",
        technique_name="Impair Defenses",
        difficulty="hard",
        os_type="linux",
        stack="docker",
        health_check_linux="curl -sf http://localhost:8080/health && curl -sf http://localhost:8888/health || echo '[CF] WAF proxy may still be starting'",
    ),
    dict(
        challenge_id="challenge-015-python-powershell",
        name="Python and PowerShell Multi-Stage",
        description="Cross-platform scripting challenge chaining Python staging and PowerShell execution.",
        domain="Python and Powershell for attack",
        tactic="execution",
        attack_id="T1059",
        technique_name="Command and Scripting Interpreter",
        difficulty="hard",
        os_type="mixed",
        stack="python",
        health_check_linux="python3 --version && echo '[CF] Python runtime OK'",
        health_check_windows="python --version; Write-Host '[CF] Python runtime OK'",
    ),
]

_KILLCHAINS = [
    {
        "id": "killchain-001-web-to-ad",
        "name": "Web Pivot to Domain Compromise",
        "description": "APT-style kill chain from web foothold to AD dominance.",
        "content_type": "killchain",
        "domain": "Complete Cyber Kill Chain Scenario (Recon to Action on Objective)",
        "difficulty": "hard",
        "tactic": "execution",
        "technique": {"attack_id": "T1059.004", "name": "Unix Shell"},
        "gitlab": {"repo_url": DEFAULT_REPO, "content_path": "killchains/killchain-001-web-to-ad"},
        "vulnerabilities": [
            "Initial Access via vulnerable upload endpoint",
            "Privilege Escalation using misconfigured sudoers",
            "Credential Dumping from compromised workstation",
            "Lateral Movement via SMB and WinRM",
            "Domain Privilege Escalation via ADCS misconfiguration",
        ],
        "machines": [
            {"machine_id": "web01",   "os": "linux",   "setup_script": "web01_setup.sh",   "stack": "docker",  "role": "Web server — runs vulnerable upload app",                "health_check": "curl -sf http://localhost:8080/health || exit 1"},
            {"machine_id": "pivot01", "os": "linux",   "setup_script": "pivot01_setup.sh", "stack": "none",    "role": "Linux pivot host with misconfigured sudoers",           "health_check": ""},
            {"machine_id": "ws01",    "os": "windows", "setup_script": "ws01_setup.ps1",   "stack": "none",    "role": "Windows workstation for credential dumping",            "health_check": ""},
            {"machine_id": "dc01",    "os": "windows", "setup_script": "dc01_setup.ps1",   "stack": "ad",      "role": "Domain controller with ADCS misconfiguration",          "health_check": "(Get-ADDomain).DNSRoot"},
        ],
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
        "gitlab": {"repo_url": DEFAULT_REPO, "content_path": "killchains/killchain-002-phishing-to-adcs"},
        "vulnerabilities": [
            "Phishing macro execution",
            "Token theft via in-memory injection",
            "Linux foothold escalation with kernel misconfig",
            "AD Enumeration and trust discovery",
            "ADCS template abuse for privilege escalation",
        ],
        "machines": [
            {"machine_id": "mail01", "os": "linux",   "setup_script": "mail01_setup.sh", "stack": "docker", "role": "Mail server running phishing simulation",  "health_check": "curl -sf http://localhost:25 || true"},
            {"machine_id": "ws02",   "os": "windows", "setup_script": "ws02_setup.ps1",  "stack": "none",   "role": "Victim workstation with macro execution",  "health_check": ""},
            {"machine_id": "app02",  "os": "linux",   "setup_script": "app02_setup.sh",  "stack": "none",   "role": "App server with kernel misconfig",          "health_check": ""},
            {"machine_id": "dc02",   "os": "windows", "setup_script": "dc02_setup.ps1",  "stack": "ad",     "role": "DC with ADCS template misconfiguration",   "health_check": "Get-CATemplate | Measure-Object | Select-Object -ExpandProperty Count"},
        ],
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
        "gitlab": {"repo_url": DEFAULT_REPO, "content_path": "killchains/killchain-003-vpn-breach-ransomware"},
        "vulnerabilities": [
            "VPN brute-force and credential stuffing",
            "Persistence via scheduled task",
            "Privilege escalation on file server",
            "Lateral movement using pass-the-hash",
            "Ransomware-style impact simulation",
        ],
        "machines": [
            {"machine_id": "vpn01",   "os": "linux",   "setup_script": "vpn01_setup.sh",   "stack": "docker", "role": "VPN gateway with brute-force surface",     "health_check": "ss -tlnp | grep 1194 || echo 'VPN port may differ'"},
            {"machine_id": "ws03",    "os": "windows", "setup_script": "ws03_setup.ps1",    "stack": "none",   "role": "Windows workstation for lateral movement",  "health_check": ""},
            {"machine_id": "files01", "os": "windows", "setup_script": "files01_setup.ps1", "stack": "none",   "role": "File server — ransomware target",           "health_check": "Test-Path C:\\shares\\cf_target"},
            {"machine_id": "ops01",   "os": "linux",   "setup_script": "ops01_setup.sh",    "stack": "none",   "role": "Linux ops server for pass-the-hash pivot",  "health_check": ""},
        ],
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
        "gitlab": {"repo_url": DEFAULT_REPO, "content_path": "killchains/killchain-004-supply-chain-domain"},
        "vulnerabilities": [
            "Compromised CI dependency ingestion",
            "Code execution via malicious build artifact",
            "Credential theft from deployment host",
            "Linux to Windows lateral movement",
            "Domain admin escalation through AD ACL abuse",
        ],
        "machines": [
            {"machine_id": "build01",  "os": "linux",   "setup_script": "build01_setup.sh",  "stack": "docker", "role": "CI build server with poisoned dependency",    "health_check": "docker ps | grep build_runner || echo 'Build runner check'"},
            {"machine_id": "deploy01", "os": "windows", "setup_script": "deploy01_setup.ps1", "stack": "none",   "role": "Windows deploy host",                        "health_check": ""},
            {"machine_id": "app03",    "os": "linux",   "setup_script": "app03_setup.sh",     "stack": "none",   "role": "Compromised application server",              "health_check": ""},
            {"machine_id": "dc03",     "os": "windows", "setup_script": "dc03_setup.ps1",     "stack": "ad",     "role": "DC with ACL misconfiguration",                "health_check": "(Get-ADDomain).DNSRoot"},
        ],
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
        "gitlab": {"repo_url": DEFAULT_REPO, "content_path": "killchains/killchain-005-ics-hybrid-objective"},
        "vulnerabilities": [
            "Public-facing service exploitation",
            "Credential abuse on jump host",
            "Pivot into OT segment",
            "AD trust abuse for persistence",
            "Action on objective in ICS simulation",
        ],
        "machines": [
            {"machine_id": "web04",   "os": "linux",   "setup_script": "web04_setup.sh",   "stack": "docker",  "role": "Internet-facing web server",                 "health_check": "curl -sf http://localhost:8080/health || exit 1"},
            {"machine_id": "jump01",  "os": "windows", "setup_script": "jump01_setup.ps1",  "stack": "none",    "role": "Jump host bridging IT and OT segments",      "health_check": ""},
            {"machine_id": "scada01", "os": "linux",   "setup_script": "scada01_setup.sh",  "stack": "scada",   "role": "SCADA/Modbus simulation server",              "health_check": "python3 -c \"from pymodbus.client import ModbusTcpClient; c=ModbusTcpClient('localhost',port=502); print('Modbus OK' if c.connect() else 'FAIL')\""},
            {"machine_id": "dc04",    "os": "windows", "setup_script": "dc04_setup.ps1",    "stack": "ad",      "role": "DC for AD trust abuse",                      "health_check": "(Get-ADDomain).DNSRoot"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Challenge YAML payload builder
# ---------------------------------------------------------------------------

def _challenge_platforms(challenge_id: str, os_type: str, stack: str, **kwargs) -> dict:
    health_linux   = kwargs.get("health_check_linux", "")
    health_windows = kwargs.get("health_check_windows", "")
    path = f"challenges/{challenge_id}"

    if os_type == "windows":
        return {"windows": {"psh": {"command": _windows_deploy_command(challenge_id, path, "setup.ps1", stack, health_windows)}}}
    if os_type == "mixed":
        return {
            "linux":   {"sh":  {"command": _linux_deploy_command(challenge_id, path, "setup.sh", stack, health_linux)}},
            "windows": {"psh": {"command": _windows_deploy_command(challenge_id, path, "setup.ps1", stack, health_windows)}},
        }
    return {"linux": {"sh": {"command": _linux_deploy_command(challenge_id, path, "setup.sh", stack, health_linux)}}}


def build_independent_challenges() -> list[dict]:
    result = []
    for c in _CHALLENGES:
        payload = {
            "id":          c["challenge_id"],
            "name":        c["name"],
            "description": c["description"],
            "domain":      c["domain"],
            "content_type": "independent",
            "difficulty":  c["difficulty"],
            "stack":       c["stack"],
            "gitlab": {
                "repo_url":     DEFAULT_REPO,
                "content_path": f"challenges/{c['challenge_id']}",
            },
            "tactic":    c["tactic"],
            "technique": {"attack_id": c["attack_id"], "name": c["technique_name"]},
            "platforms": _challenge_platforms(
                c["challenge_id"], c["os_type"], c["stack"],
                health_check_linux=c.get("health_check_linux", ""),
                health_check_windows=c.get("health_check_windows", ""),
            ),
        }
        result.append(payload)
    return result


def build_killchains() -> list[dict]:
    result = []
    for kc in _KILLCHAINS:
        # Fleet-level ability: Linux orchestrator deploys everything
        fleet_cmd = _linux_deploy_command(
            kc["id"],
            kc["gitlab"]["content_path"],
            "setup.sh",
            "none",
        )
        kc_payload = dict(kc)
        kc_payload["platforms"] = {
            "linux":   {"sh":  {"command": fleet_cmd}},
            "windows": {"psh": {"command": _windows_deploy_command(kc["id"], kc["gitlab"]["content_path"], "setup.ps1", "none")}},
        }
        result.append(kc_payload)
    return result


# ---------------------------------------------------------------------------
# CALDERA ability builders
# ---------------------------------------------------------------------------

def _build_deploy_ability(
    *,
    ability_id: str,
    name: str,
    description: str,
    tactic: str,
    technique: dict,
    platforms: dict,
    requirements: list[dict] | None = None,
) -> dict:
    ability: dict = {
        "id":          ability_id,
        "name":        name,
        "description": description,
        "tactic":      tactic,
        "technique":   technique,
        "platforms":   platforms,
    }
    if requirements:
        ability["requirements"] = requirements
    return ability


def _build_teardown_ability(
    *,
    ability_id: str,
    name: str,
    content_id: str,
    content_path: str,
    os_type: str,
) -> dict:
    platforms: dict = {}
    if os_type in ("linux", "mixed", "none"):
        platforms["linux"] = {"sh": {"command": _linux_teardown_command(content_id, content_path)}}
    if os_type in ("windows", "mixed", "ad"):
        platforms["windows"] = {"psh": {"command": _windows_teardown_command(content_id, content_path)}}

    return {
        "id":          ability_id,
        "name":        name,
        "description": f"Cleanly tear down and remove the hosted environment for {content_id}.",
        "tactic":      "defense-evasion",
        "technique":   {"attack_id": "T1070", "name": "Indicator Removal"},
        "platforms":   platforms,
    }


def generate_caldera_abilities(challenges: list[dict], killchains: list[dict]) -> list[dict]:
    abilities: list[dict] = []

    # --- Independent challenge deploy + teardown abilities ---
    for c in _CHALLENGES:
        cid = c["challenge_id"]
        os_t = c["os_type"]
        stk = c["stack"]
        path = f"challenges/{cid}"
        health_l = c.get("health_check_linux", "")
        health_w = c.get("health_check_windows", "")

        platforms: dict = {}
        if os_t in ("linux", "mixed"):
            platforms["linux"] = {"sh": {"command": _linux_deploy_command(cid, path, "setup.sh", stk, health_l)}}
        if os_t in ("windows", "mixed"):
            platforms["windows"] = {"psh": {"command": _windows_deploy_command(cid, path, "setup.ps1", stk, health_w)}}

        abilities.append(_build_deploy_ability(
            ability_id=f"cf-deploy-{cid}",
            name=f"[CF] Deploy: {c['name']}",
            description=(
                f"Pull {cid} from GitLab and host it on the target machine.\n"
                f"Domain: {c['domain']} | Difficulty: {c['difficulty']} | Stack: {stk}"
            ),
            tactic=c["tactic"],
            technique={"attack_id": c["attack_id"], "name": c["technique_name"]},
            platforms=platforms,
        ))

        # Teardown companion
        abilities.append(_build_teardown_ability(
            ability_id=f"cf-teardown-{cid}",
            name=f"[CF] Teardown: {c['name']}",
            content_id=cid,
            content_path=path,
            os_type=os_t,
        ))

    # --- Killchain fleet + per-machine abilities ---
    for kc in _KILLCHAINS:
        kid = kc["id"]
        kpath = kc["gitlab"]["content_path"]
        tactic = kc["tactic"]
        technique = kc["technique"]

        # Fleet-level: deploy entire killchain (targets any agent)
        fleet_platforms = {
            "linux":   {"sh":  {"command": _linux_deploy_command(kid, kpath, "setup.sh", "none")}},
            "windows": {"psh": {"command": _windows_deploy_command(kid, kpath, "setup.ps1", "none")}},
        }
        abilities.append(_build_deploy_ability(
            ability_id=f"cf-deploy-{kid}",
            name=f"[CF] Deploy (fleet): {kc['name']}",
            description=(
                f"Deploy all machines for killchain {kid}.\n"
                "Run this ability once per machine in the operation — CALDERA will send it to every agent.\n"
                f"Vulnerabilities: {', '.join(kc['vulnerabilities'])}"
            ),
            tactic=tactic,
            technique=technique,
            platforms=fleet_platforms,
        ))

        # Fleet teardown
        abilities.append(_build_teardown_ability(
            ability_id=f"cf-teardown-{kid}",
            name=f"[CF] Teardown (fleet): {kc['name']}",
            content_id=kid,
            content_path=kpath,
            os_type="mixed",
        ))

        # Per-machine abilities for granular deployment
        for machine in kc["machines"]:
            mid = machine["machine_id"]
            mos = machine["os"]
            mscript = machine["setup_script"]
            mstack = machine.get("stack", "none")
            mhealth = machine.get("health_check", "")
            mpath = f"{kpath}/{mid}"
            mcid = f"{kid}-{mid}"

            mplatforms: dict = {}
            if mos == "linux":
                mplatforms["linux"] = {"sh": {"command": _linux_deploy_command(mcid, mpath, mscript, mstack, mhealth)}}
            else:
                mplatforms["windows"] = {"psh": {"command": _windows_deploy_command(mcid, mpath, mscript, mstack, mhealth)}}

            abilities.append(_build_deploy_ability(
                ability_id=f"cf-deploy-{mcid}",
                name=f"[CF] Deploy machine: {mid} ({kid})",
                description=(
                    f"Deploy only the {mid} machine role for killchain {kid}.\n"
                    f"Role: {machine.get('role', mid)} | OS: {mos} | Stack: {mstack}"
                ),
                tactic="execution",
                technique={
                    "attack_id": "T1059.004" if mos == "linux" else "T1059.001",
                    "name":      "Unix Shell" if mos == "linux" else "PowerShell",
                },
                platforms=mplatforms,
            ))

            # Per-machine teardown
            abilities.append(_build_teardown_ability(
                ability_id=f"cf-teardown-{mcid}",
                name=f"[CF] Teardown machine: {mid} ({kid})",
                content_id=mcid,
                content_path=mpath,
                os_type=mos,
            ))

    return abilities


# ---------------------------------------------------------------------------
# Write all files
# ---------------------------------------------------------------------------

def write_yaml_files() -> None:
    INDEPENDENT_DIR.mkdir(parents=True, exist_ok=True)
    KILLCHAIN_DIR.mkdir(parents=True, exist_ok=True)
    ABILITY_DIR.mkdir(parents=True, exist_ok=True)

    challenges = build_independent_challenges()
    killchains = build_killchains()

    # Write challenge + killchain definitions
    for challenge in challenges:
        out = INDEPENDENT_DIR / f"{challenge['id']}.yml"
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            yaml.safe_dump(challenge, fh, sort_keys=False, allow_unicode=True)

    for killchain in killchains:
        out = KILLCHAIN_DIR / f"{killchain['id']}.yml"
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            yaml.safe_dump(killchain, fh, sort_keys=False, allow_unicode=True)

    # Generate CALDERA abilities
    abilities = generate_caldera_abilities(challenges, killchains)

    # Write one file per ability (CALDERA expects separate files)
    for ability in abilities:
        out = ABILITY_DIR / f"{ability['id']}.yml"
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            yaml.safe_dump([ability], fh, sort_keys=False, allow_unicode=True)

    # Print summary
    deploys  = [a for a in abilities if a["id"].startswith("cf-deploy-")]
    teardown = [a for a in abilities if a["id"].startswith("cf-teardown-")]
    print(f"Generated {len(challenges)} independent challenges")
    print(f"Generated {len(killchains)} killchain definitions")
    print(f"Generated {len(deploys)} deploy abilities")
    print(f"Generated {len(teardown)} teardown abilities")
    print(f"Total CALDERA ability files: {len(abilities)}")
    print(f"Output directory: {ABILITY_DIR}")


def main() -> None:
    write_yaml_files()


if __name__ == "__main__":
    main()
