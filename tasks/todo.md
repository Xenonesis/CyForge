# CyberForge Implementation Todo

## Active Plan

- [x] Bootstrap project skeleton
- [x] Implement lifecycle state machine
- [x] Build deploy/reset orchestration API
- [x] Add challenge YAML validation pipeline
- [x] Add 5 MVP challenge definitions and CALDERA templates
- [x] Add tests and verify local run
- [x] Add PostgreSQL-compatible SQLAlchemy repository
- [x] Add VirtualBox provisioner mode with command adapter
- [x] Add minimal frontend control deck (`/`)
- [x] Extend tests for UI/system-info and provisioner command paths
- [x] Add startup preflight checks for repository/provisioner
- [x] Add persistent audit events and API endpoint
- [x] Extend tests for audit events and preflight verification
- [x] Add audit filters and pagination API contract
- [x] Add request correlation IDs end-to-end (header + audit)
- [x] Add frontend audit explorer and UI/UX refinement
- [x] Expand catalog to 15 independent challenges across required domains
- [x] Add 5 AD/Linux killchain scenario definitions (5 vulnerabilities each)
- [x] Generate CALDERA TTP YAML for challenge and per-machine killchain hosting
- [x] Add UI dark mode and content-type filtering
- [x] Add UI domain and difficulty filtering
- [x] Add CALDERA export index and grouped bundle endpoints
- [x] Add startup content-structure validation for GitLab mirror scripts

## Review Notes

- Initialized Python FastAPI MVP service with local mock provisioner first.
- Focused on deterministic state handling and challenge schema validation before real hypervisor integration.
- Test suite result: 5 passed.
- Replaced deprecated FastAPI startup event with lifespan hook.
- Added repository mode switching (`memory` or `sqlalchemy`) via environment configuration.
- Added provisioner mode switching (`mock` or `virtualbox`) with VirtualBox dry-run support.
- Added static frontend with challenge selection, deploy, and reset controls.
- Validation result after continuation work: 7 tests passed.
- Added startup preflight enforcement for repository health and provisioner readiness.
- Added deploy/reset audit event persistence with retrieval endpoint.
- Validation result after hardening continuation: 8 tests passed.
- Expanded audit API with action/status/user/lab/request/time filters and pagination metadata.
- Added `X-Request-ID` middleware and correlation propagation into audit details.
- Refreshed control deck UI and added audit explorer with filters, pagination controls, and request visibility.
- Validation result after UI/UX + API continuation: 9 tests passed.
- Added generated content catalog: 15 independent challenges + 5 killchains.
- Added generated CALDERA abilities (40 files) including per-machine killchain abilities for selective hosting.
- Added catalog summary and killchain APIs for UI and operational visibility.
- Added dark mode support with persisted theme preference.
- Validation result after full catalog/UI expansion: 12 tests passed.
- Added domain and difficulty filters in control deck UI.
- Added grouped CALDERA export endpoints for independent/killchain-scenario/killchain-machine/all bundles.
- Added optional startup enforcement for required script existence in configured content root.
- Validation result after 1,2,3 continuation: 14 tests passed.
