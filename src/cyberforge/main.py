from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from cyberforge.challenge_validation import load_challenge_catalog, validate_challenge_payload
from cyberforge.content_structure_validation import validate_content_structure
from cyberforge.models import (
    AuditEventPage,
    AuditQuery,
    DeployLabRequest,
    ValidateChallengeRequest,
    ValidationResult,
)
from cyberforge.orchestrator import LabOrchestrator, OrchestrationError
from cyberforge.provisioner import build_provisioner
from cyberforge.repository import InMemoryRepository
from cyberforge.settings import Settings
from cyberforge.sql_repository import SQLAlchemyRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEPENDENT_CATALOG_ROOT = PROJECT_ROOT / "catalog" / "challenges" / "independent"
KILLCHAIN_CATALOG_ROOT = PROJECT_ROOT / "catalog" / "killchains"
STATIC_ROOT = PROJECT_ROOT / "static"
CALDERA_GENERATED_ABILITIES_ROOT = PROJECT_ROOT / "catalog" / "caldera" / "abilities" / "generated"

catalog_summary: dict[str, dict] = {
    "content": {"independent": 0, "killchain": 0, "total": 0},
    "domains": {},
}

settings = Settings.from_env()

if settings.repository_backend == "memory":
    repository = InMemoryRepository()
elif settings.repository_backend == "sqlalchemy":
    repository = SQLAlchemyRepository(settings.database_url)
else:
    raise RuntimeError(f"unsupported repository backend: {settings.repository_backend}")

provisioner = build_provisioner(
    mode=settings.provisioner_mode,
    # VirtualBox
    vbox_attacker_template=settings.vbox_attacker_template,
    vbox_target_template=settings.vbox_target_template,
    vbox_dry_run=settings.vbox_dry_run,
    # SSH
    ssh_target_host=settings.ssh_target_host,
    ssh_target_user=settings.ssh_target_user,
    ssh_target_port=settings.ssh_target_port,
    ssh_identity_file=settings.ssh_identity_file,
    ssh_attacker_host=settings.ssh_attacker_host,
    # Docker
    docker_workdir=settings.docker_workdir,
    docker_service_port=settings.docker_service_port,
    # GitLab
    gitlab_repo_url=settings.gitlab_repo_url,
    gitlab_token=settings.gitlab_token,
)
orchestrator = LabOrchestrator(repository=repository, provisioner=provisioner)

@asynccontextmanager
async def app_lifespan(_: FastAPI):
    repository.initialize()

    if not repository.healthcheck():
        raise RuntimeError("repository healthcheck failed")

    preflight_issues = provisioner.preflight()
    if preflight_issues:
        missing = settings.provisioner_missing_config()
        detail = " | ".join(preflight_issues)
        if missing:
            detail += f" | Missing config: {', '.join(missing)}"
        raise RuntimeError(f"Provisioner preflight failed: {detail}")

    independent, independent_failures = load_challenge_catalog(INDEPENDENT_CATALOG_ROOT)
    killchains, killchain_failures = load_challenge_catalog(KILLCHAIN_CATALOG_ROOT)

    failures = {**independent_failures, **killchain_failures}
    if failures:
        raise RuntimeError(f"catalog validation failed: {failures}")

    all_content = [*independent, *killchains]

    if settings.validate_content_structure:
        if not settings.content_root:
            raise RuntimeError(
                "content structure validation enabled but CYBERFORGE_CONTENT_ROOT is not configured"
            )
        structure_failures = validate_content_structure(
            content_items=all_content,
            content_root=Path(settings.content_root),
        )
        if structure_failures:
            raise RuntimeError(f"content structure validation failed: {structure_failures}")

    repository.upsert_challenges(all_content)

    domain_counts: dict[str, int] = {}
    for item in all_content:
        payload = item.model_dump()
        domain = str(payload.get("domain", "uncategorized"))
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    catalog_summary["content"] = {
        "independent": len(independent),
        "killchain": len(killchains),
        "total": len(all_content),
    }
    catalog_summary["domains"] = domain_counts
    yield


app = FastAPI(title="CyberForge MVP API", version="0.1.0", lifespan=app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _parse_optional_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_content_payload(payload: dict) -> dict:
    if "content_type" not in payload:
        payload["content_type"] = "killchain" if str(payload.get("id", "")).startswith("killchain-") else "independent"
    return payload


def _list_caldera_ability_files() -> list[Path]:
    return sorted(CALDERA_GENERATED_ABILITIES_ROOT.glob("*.yml"))


def _classify_ability_bundle(stem: str) -> str:
    if stem.startswith("cf-challenge-"):
        return "independent"
    if stem.startswith("cf-killchain-"):
        parts = stem.split("-")
        return "killchain-machines" if len(parts) >= 7 else "killchain-scenarios"
    return "other"


def _caldera_bundle_index() -> dict:
    grouped: dict[str, list[dict]] = {
        "independent": [],
        "killchain-scenarios": [],
        "killchain-machines": [],
        "other": [],
    }

    for ability_file in _list_caldera_ability_files():
        stem = ability_file.stem
        bundle = _classify_ability_bundle(stem)
        grouped[bundle].append(
            {
                "id": stem,
                "path": str(ability_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            }
        )

    return {
        "bundles": [
            {"name": name, "count": len(items), "abilities": items}
            for name, items in grouped.items()
            if items
        ],
        "total": sum(len(items) for items in grouped.values()),
    }


@app.get("/", include_in_schema=False)
def web_root() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/system/info")
def system_info() -> dict:
    missing = settings.provisioner_missing_config()
    return {
        "provisioner_mode":      settings.provisioner_mode,
        "provisioner_ready":     len(missing) == 0,
        "provisioner_missing":   missing,
        "repository_backend":    settings.repository_backend,
        "gitlab_repo_configured": bool(settings.gitlab_repo_url),
        "ssh_target_host":       settings.ssh_target_host or None,
        "vbox_dry_run":          settings.vbox_dry_run,
        "content_validation":    settings.validate_content_structure,
    }


@app.get("/api/v1/audit/events", response_model=AuditEventPage)
def list_audit_events(
    action: str | None = None,
    status: str | None = None,
    user_id: str | None = None,
    lab_id: str | None = None,
    request_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditEventPage:
    try:
        query = AuditQuery(
            action=action,
            status=status,
            user_id=user_id,
            lab_id=lab_id,
            request_id=request_id,
            start_at=_parse_optional_iso_datetime(start_at),
            end_at=_parse_optional_iso_datetime(end_at),
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid datetime filter: {exc}") from exc

    items, total = repository.list_audit_events(query)
    return AuditEventPage(items=items, total=total, limit=limit, offset=offset)


@app.get("/api/v1/challenges")
def list_challenges() -> list[dict]:
    return [_normalize_content_payload(challenge.model_dump()) for challenge in repository.list_challenges()]


@app.get("/api/v1/killchains")
def list_killchains() -> list[dict]:
    killchains = []
    for challenge in repository.list_challenges():
        payload = _normalize_content_payload(challenge.model_dump())
        content_type = str(payload.get("content_type", "")).strip().lower()
        if content_type == "killchain" or payload.get("id", "").startswith("killchain-"):
            killchains.append(payload)
    return killchains


@app.get("/api/v1/catalog/summary")
def get_catalog_summary() -> dict:
    return catalog_summary


@app.get("/api/v1/caldera/abilities")
def list_caldera_abilities() -> list[dict]:
    abilities = []
    for ability_file in _list_caldera_ability_files():
        abilities.append(
            {
                "id": ability_file.stem,
                "path": str(ability_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            }
        )
    return abilities


@app.get("/api/v1/caldera/export/index")
def caldera_export_index() -> dict:
    return _caldera_bundle_index()


@app.get("/api/v1/caldera/export/{bundle_name}")
def caldera_export_bundle(bundle_name: str) -> PlainTextResponse:
    normalized = bundle_name.strip().lower()
    supported = {"independent", "killchain-scenarios", "killchain-machines", "all"}
    if normalized not in supported:
        raise HTTPException(status_code=404, detail=f"unsupported bundle: {bundle_name}")

    selected: list[Path] = []
    for ability_file in _list_caldera_ability_files():
        bucket = _classify_ability_bundle(ability_file.stem)
        if normalized == "all" or bucket == normalized:
            selected.append(ability_file)

    if not selected:
        raise HTTPException(status_code=404, detail=f"no abilities found for bundle: {bundle_name}")

    docs = [ability.read_text(encoding="utf-8").strip() for ability in selected]
    output = "\n\n---\n\n".join(doc for doc in docs if doc)

    return PlainTextResponse(
        output,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f'attachment; filename="cyberforge-caldera-{normalized}.yml"'
        },
    )


@app.post("/api/v1/challenges/validate", response_model=ValidationResult)
def validate_challenge(request: ValidateChallengeRequest) -> ValidationResult:
    errors = validate_challenge_payload(request.payload)
    return ValidationResult(valid=not errors, errors=errors)


@app.post("/api/v1/labs/deploy")
def deploy_lab(request: DeployLabRequest, http_request: Request) -> dict:
    try:
        session = orchestrator.deploy_lab(
            user_id=request.user_id,
            challenge_id=request.challenge_id,
            request_id=http_request.state.request_id,
        )
    except OrchestrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return session.model_dump()


@app.get("/api/v1/labs/{lab_id}")
def get_lab(lab_id: str) -> dict:
    lab = repository.get_lab(lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail=f"lab not found: {lab_id}")
    return lab.model_dump()


@app.post("/api/v1/labs/{lab_id}/reset")
def reset_lab(lab_id: str, http_request: Request) -> dict:
    try:
        session = orchestrator.reset_lab(lab_id=lab_id, request_id=http_request.state.request_id)
    except OrchestrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return session.model_dump()
