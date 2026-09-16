# Demo pack

Presentation material for demoing the OpenFGA ReBAC PoC. The diagrams are
real Excalidraw scene files — open any of them in excalidraw.io via
**File → Open** (or drag the file onto the page). Everything stays fully
editable once opened.

## Contents

| File | What it shows |
|---|---|
| `diagrams/00-what-is-rebac.excalidraw` | What ReBAC is, how it differs from traditional RBAC, and when to choose OpenFGA/ReBAC over plain RBAC |
| `diagrams/01-architecture.excalidraw` | System architecture: API client → FastAPI app → Application Postgres + OpenFGA → OpenFGA's own Postgres |
| `diagrams/02-core-apis.excalidraw` | The handful of endpoints the demo actually needs, grouped by narrative stage (setup → build hierarchy → authorize → prove it), each stage tagged with which screenshot (06–12) proves it actually works |
| `diagrams/03-database-schema.excalidraw` | All application DB tables and how they relate — solid arrows for real foreign keys, dashed arrows for OpenFGA-only relationships |
| `diagrams/04-openfga-role.excalidraw` | OpenFGA's role stated plainly (authorization source of truth, stores no business data) + an empty placeholder box for you to paste OpenFGA's own architecture screenshot into |
| `ROADMAP.md` | Phase-by-phase plan for porting this pattern into the `api-python-infinitus` backend |
| `diagrams/06-list-of-clients.{excalidraw,png}` | Title card + real Postman screenshot: `GET /clients` response |
| `diagrams/07-list-of-projects.{excalidraw,png}` | Title card + real Postman screenshot: `GET /projects` response |
| `diagrams/08-zone-endpoints.{excalidraw,png}` | Title card + real Postman screenshot: the `04 - Zones` folder (all recursive zone requests) |
| `diagrams/09-grant-client-level-viewer.{excalidraw,png}` | Title card + real Postman screenshot: `POST /authorization/grant` request body |
| `diagrams/10-check-access-allowed.{excalidraw,png}` | Title card + real Postman screenshot: `GET /authorization/check` → `{"allowed": true}` |
| `diagrams/11-authorized-tree-response.{excalidraw,png}` | Title card + real Postman screenshot: `GET /clients/{id}/tree` pruned response |
| `diagrams/12-security-tests-overview.{excalidraw,png}` | Title card + real Postman screenshot: the `09 - Security Tests` folder |
| `diagrams/13-openfga-data-sync.excalidraw` | How a create call (e.g. `POST /projects`) syncs into an OpenFGA tuple — the DB-commit-then-OpenFGA-write sequence and the compensating rollback on failure, followed the same way by Project, Structure, and Zone; Client is the one exception (no parent tuple) |
| `diagrams/14-audit-and-logging.excalidraw` | Two separate audit trails (the app's own `audit_events` table vs. OpenFGA's internal changelog) and how one OpenFGA deployment serves many applications — including mobile — each isolated by its own store/model |

Each numbered screenshot (06–12) has a matching `.excalidraw` file with the
same number — just a title-card heading naming what the screenshot shows
and which Postman request it came from. Present the heading, then flip to
the `.png` right after it as the live evidence.

## Suggested demo order

0. **00 — What is ReBAC, and why do we need it?** Set up the motivation before showing any code: define ReBAC, contrast it with traditional RBAC, and state plainly when to reach for OpenFGA over a fixed role list — fine-grained, resource-specific sharing and permissions that flow through a deep, changing hierarchy.
1. **01 — Architecture.** Orient the room: one FastAPI app, two datastores, OpenFGA owns authorization + the Zone hierarchy.
2. **02 — Core APIs.** Walk the four stages left to right — this is also the order to actually call them in Postman (`postman/OpenFGA-ReBAC-New-Architecture.postman_collection.json`, folders `02`–`07`) if you want to live-demo instead of just showing the diagram.
3. **03 — Database schema.** Show the tables, then point out the dashed arrows: nothing about *who can see what* or *how zones nest* lives in SQL.
4. **04 — OpenFGA's role.** Before presenting, paste OpenFGA's own architecture diagram (screenshot from openfga.dev) into the empty placeholder box — I deliberately left it blank rather than fetching one myself.
5. **06–12 — Real screenshots.** Walk the same setup → hierarchy → authorize → prove-it → security narrative again, this time with actual Postman evidence: clients list (06), projects list (07), zone endpoints (08), granting access (09), a passing check (10), the pruned tree response (11), and the security-test suite (12).
6. **13 — How the sync actually works.** Now that they've seen it work, show the mechanism: creating a Project, Structure, or Zone writes the business row to Postgres first, *then* the OpenFGA tuple — with a compensating rollback if that second write fails, so the two stores never drift apart. Client is the one exception called out (no parent tuple — it's the root of the hierarchy).
7. **14 — Audit, logging, and multi-tenancy.** Two different logs answer two different questions: the app's `audit_events` table (action/result/metadata/created_at) says *who did what and did it succeed*; OpenFGA's own changelog table (store_id/user/relation/object/operation/timestamp) says *exactly when a permission was granted or revoked*. Close with the scaling story: one OpenFGA deployment, many applications (including mobile), each isolated by its own store and model.

## Note on the live demo itself

If you want to run the actual API during the demo (not just show diagrams), see the main [README.md](../README.md) `Setup` section — `docker compose up -d`, `alembic upgrade head`, `python scripts/bootstrap_openfga.py`, `uvicorn app.main:app --reload --port 8002`, then `python scripts/seed_demo.py` for the India/Emirates/Mexico/Argentina scenarios referenced in the Postman collection's `08 - Demo Scenarios` folder.
