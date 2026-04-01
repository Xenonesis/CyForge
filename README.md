# CyberForge

CyberForge is an automated cyber range orchestration platform. This repository contains the first MVP implementation slice:

- Challenge catalog loading and schema validation
- Lab lifecycle state machine
- Deploy/reset API endpoints
- CALDERA ability templates and sample challenge definitions
- SQLAlchemy-backed lab/session persistence (PostgreSQL-compatible)
- Local VirtualBox provisioner adapter (configurable, with dry-run)
- Minimal web control deck for challenge deploy/reset actions
- Startup preflight for repository connectivity and provisioner readiness
- Persistent deploy/reset audit events with API retrieval
- Dark mode support and richer control deck UX
- Expanded catalog: 15 independent challenges + 5 kill chains
- Generated CALDERA TTP YAML abilities for per-challenge and per-machine deployment

## Current Scope

- 15 independent challenge definitions
- 5 AD/Linux killchain scenarios (5 vulnerabilities each)
- Deterministic lab state transitions: `idle -> deploying -> active -> resetting`
- Reset failure handling: transitions to `failed` with error context
- PostgreSQL-compatible persistence for challenges and lab sessions
- VirtualBox provisioner implementation with mode switching
- Web UI served from `/`
- Web UI supports light and dark mode
- Web UI supports content filters by type, domain, and difficulty

## Quickstart

1. Create a virtual environment.
2. Install dependencies:

```powershell
pip install -e .[dev]
```

1. Run the API:

```powershell
uvicorn cyberforge.main:app --reload
```

1. Open API docs:

- [API docs](http://127.0.0.1:8000/docs)
- [Control deck UI](http://127.0.0.1:8000/)

## Configuration

The application is configured with environment variables:

- `CYBERFORGE_REPOSITORY`: `sqlalchemy` (default) or `memory`
- `CYBERFORGE_DATABASE_URL`: SQLAlchemy URL (default `sqlite+pysqlite:///./cyberforge.db`)
- `CYBERFORGE_PROVISIONER`: `mock` (default) or `virtualbox`
- `CYBERFORGE_VBOX_ATTACKER_TEMPLATE`: VirtualBox attacker template VM name
- `CYBERFORGE_VBOX_TARGET_TEMPLATE`: VirtualBox target template VM name
- `CYBERFORGE_VBOX_DRY_RUN`: `true` (default) or `false`
- `CYBERFORGE_CONTENT_ROOT`: local mirror path of GitLab content (optional)
- `CYBERFORGE_VALIDATE_CONTENT_STRUCTURE`: validate required setup scripts at startup (`true`/`false`, default `false`)

## Catalog Requirements Coverage

Implemented content includes these domains:

1. OWASP Top 10 Attacks
2. Web Attack Scenarios
3. AD Attacks (Kerberos, ADCS, AD enum)
4. Linux OS attacks
5. OT/ICS systems
6. Network attacks
7. Popular and relevant attacks (CVE/WiFi/bruteforce style)
8. Complete cyber kill chain scenario (as 5 dedicated killchains)
9. WAF bypass attacks
10. Python and PowerShell attack workflows

### PostgreSQL Example

```powershell
$env:CYBERFORGE_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/cyberforge"
$env:CYBERFORGE_REPOSITORY = "sqlalchemy"
uvicorn cyberforge.main:app --reload
```

### VirtualBox Example

```powershell
$env:CYBERFORGE_PROVISIONER = "virtualbox"
$env:CYBERFORGE_VBOX_DRY_RUN = "false"
$env:CYBERFORGE_VBOX_ATTACKER_TEMPLATE = "cf-attacker-template"
$env:CYBERFORGE_VBOX_TARGET_TEMPLATE = "cf-target-template"
uvicorn cyberforge.main:app --reload
```

## Audit Events API

- `GET /api/v1/audit/events` returns paginated audit events.

Supported query params:

- `action`: `deploy` or `reset`
- `status`: `requested`, `success`, `failed`
- `user_id`, `lab_id`
- `request_id`
- `start_at`, `end_at` (ISO-8601)
- `limit` (1-500), `offset`

Event fields include action, status, lab_id, user_id, details, and created_at.

Response shape:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

## Correlation ID

All API requests support optional `X-Request-ID` header. If provided, it is echoed in the response and persisted in deploy/reset audit event details for end-to-end traceability.

## Killchain and Catalog APIs

- `GET /api/v1/challenges`: all deployable content (independent + killchain)
- `GET /api/v1/killchains`: killchain-only catalog
- `GET /api/v1/catalog/summary`: counts by content type and domain

## CALDERA Export APIs

- `GET /api/v1/caldera/abilities`: flat ability list
- `GET /api/v1/caldera/export/index`: grouped bundle index
- `GET /api/v1/caldera/export/independent`: ready-to-import YAML bundle
- `GET /api/v1/caldera/export/killchain-scenarios`: ready-to-import YAML bundle
- `GET /api/v1/caldera/export/killchain-machines`: ready-to-import YAML bundle
- `GET /api/v1/caldera/export/all`: full ready-to-import YAML bundle

## CALDERA TTP YAML Generation

This repository includes a generator that builds:

- 15 independent challenge definitions
- 5 killchain definitions
- CALDERA ability YAMLs (per challenge, per killchain, and per killchain machine)

Run generator:

```powershell
python tools/build_content_catalog.py
```

## Startup Content Structure Validation

When `CYBERFORGE_VALIDATE_CONTENT_STRUCTURE=true`, startup fails if required setup scripts are missing in the configured local GitLab mirror path (`CYBERFORGE_CONTENT_ROOT`).

Example:

```powershell
$env:CYBERFORGE_VALIDATE_CONTENT_STRUCTURE = "true"
$env:CYBERFORGE_CONTENT_ROOT = "C:\\gitlab-mirror\\cyberforge-content"
uvicorn cyberforge.main:app --reload
```

## Run Tests

```powershell
pytest
```

## Folder Layout

- `src/cyberforge`: API and orchestration implementation
- `catalog/challenges/independent`: YAML challenge definitions (15)
- `catalog/killchains`: killchain scenario definitions (5)
- `catalog/caldera/abilities`: CALDERA ability templates
- `catalog/caldera/abilities/generated`: generated deployable CALDERA TTP YAML files
- `schemas`: JSON schema for challenge definition validation
- `tests`: unit and API tests
- `tasks`: implementation checklist and review notes
