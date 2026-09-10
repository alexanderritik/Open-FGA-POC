"""One-off generator for postman/OpenFGA-ReBAC-New-Architecture.postman_collection.json.
Not part of the runtime app; run manually when the collection needs regenerating.
"""

import json
import uuid
from pathlib import Path


def item(name, method, path, body=None, description="", query=None):
    req = {
        "method": method,
        "header": [{"key": "Content-Type", "value": "application/json"}] if body is not None else [],
        "url": {
            "raw": "{{baseUrl}}" + path + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else ""),
            "host": ["{{baseUrl}}"],
            "path": [p for p in path.strip("/").split("/")],
        },
        "description": description,
    }
    if query:
        req["url"]["query"] = [{"key": k, "value": str(v)} for k, v in query.items()]
    if body is not None:
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return {"name": name, "request": req, "response": []}


def folder(name, items):
    return {"name": name, "item": items}


collection = {
    "info": {
        "_postman_id": str(uuid.uuid4()),
        "name": "OpenFGA ReBAC New Architecture",
        "description": (
            "OpenFGA ReBAC Authorization PoC.\n\n"
            "Architecture: Application PostgreSQL holds business data only "
            "(users, clients, projects, structures, audit_events). OpenFGA holds "
            "all authorization relationships and the entire Zone hierarchy -- "
            "Zone has no table and no ORM model anywhere in this project.\n\n"
            "No authentication: user identity is supplied directly as a string "
            "(e.g. user:parth) to authorization-aware endpoints. There are no "
            "auth headers in this collection.\n\n"
            "Run scripts/seed_demo.py before the '08 - Demo Scenarios' and "
            "'09 - Security Tests' folders -- they assume the India/Emirates/"
            "Mexico demo data and demo users already exist."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "baseUrl", "value": "http://127.0.0.1:8002"},
        {"key": "clientId", "value": "govt-of-india"},
        {"key": "projectId", "value": "indian-railway"},
        {"key": "zoneId", "value": "north"},
        {"key": "nestedZoneId", "value": "central"},
        {"key": "structureId", "value": "yamuna-bridge"},
        {"key": "userId", "value": "user:parth"},
    ],
    "item": [],
}

collection["item"].append(
    folder(
        "01 - Health",
        [
            item("Liveness check", "GET", "/health", description="Basic liveness probe."),
        ],
    )
)

collection["item"].append(
    folder(
        "02 - Clients",
        [
            item(
                "Create client",
                "POST",
                "/clients",
                body={"id": "{{clientId}}", "name": "Govt of India"},
                description="Creates the business record only. No OpenFGA relationships are written for clients.",
            ),
            item("List clients", "GET", "/clients"),
            item("Get client by id", "GET", "/clients/{{clientId}}"),
            item("Get nonexistent client (404)", "GET", "/clients/this-client-does-not-exist"),
        ],
    )
)

collection["item"].append(
    folder(
        "03 - Projects",
        [
            item(
                "Create project",
                "POST",
                "/projects",
                body={"id": "{{projectId}}", "client_id": "{{clientId}}", "name": "Indian Railway"},
                description="Creates the business record AND writes project:<id>#parent@client:<client_id> in OpenFGA.",
            ),
            item("List projects", "GET", "/projects"),
            item("Get project by id", "GET", "/projects/{{projectId}}"),
            item(
                "Create project with nonexistent client (404)",
                "POST",
                "/projects",
                body={"id": "orphan-project", "client_id": "no-such-client", "name": "X"},
            ),
        ],
    )
)

collection["item"].append(
    folder(
        "04 - Zones",
        [
            item(
                "Create root zone (parent = project)",
                "POST",
                "/zones",
                body={"id": "{{zoneId}}", "parent_type": "project", "parent_id": "{{projectId}}"},
                description="Zone has NO table. This writes zone:<id>#parent@project:<parent_id> in OpenFGA only.",
            ),
            item(
                "Create sibling zone",
                "POST",
                "/zones",
                body={"id": "south", "parent_type": "project", "parent_id": "{{projectId}}"},
            ),
            item(
                "Create nested zone (parent = zone)",
                "POST",
                "/zones",
                body={"id": "delhi", "parent_type": "zone", "parent_id": "{{zoneId}}"},
                description="Zone -> Zone recursion: parent_type can be 'zone', supporting arbitrary nesting depth.",
            ),
            item(
                "Create deeply nested zone",
                "POST",
                "/zones",
                body={"id": "{{nestedZoneId}}", "parent_type": "zone", "parent_id": "delhi"},
            ),
            item("Get zone by id", "GET", "/zones/{{zoneId}}"),
            item("Get zone children", "GET", "/zones/{{zoneId}}/children"),
            item("List zones under a project", "GET", "/projects/{{projectId}}/zones"),
            item(
                "Create zone with nonexistent parent (404)",
                "POST",
                "/zones",
                body={"id": "orphan-zone", "parent_type": "zone", "parent_id": "no-such-zone"},
            ),
            item(
                "Create zone that is its own parent (422 circular)",
                "POST",
                "/zones",
                body={"id": "self-loop", "parent_type": "zone", "parent_id": "self-loop"},
            ),
            item(
                "Re-create same zone, same parent (idempotent 200)",
                "POST",
                "/zones",
                body={"id": "{{zoneId}}", "parent_type": "project", "parent_id": "{{projectId}}"},
            ),
        ],
    )
)

collection["item"].append(
    folder(
        "05 - Structures",
        [
            item(
                "Create structure under a zone",
                "POST",
                "/structures",
                body={
                    "id": "{{structureId}}",
                    "name": "Yamuna Bridge",
                    "parent_type": "zone",
                    "parent_id": "{{nestedZoneId}}",
                },
                description="Business row (name) lives in the app DB; parent zone is OpenFGA-only.",
            ),
            item("List structures (business data only)", "GET", "/structures"),
            item("Get structure by id (includes OpenFGA parent)", "GET", "/structures/{{structureId}}"),
            item(
                "Create structure with nonexistent zone (404)",
                "POST",
                "/structures",
                body={"id": "orphan-structure", "name": "X", "parent_type": "zone", "parent_id": "no-such-zone"},
            ),
        ],
    )
)

collection["item"].append(
    folder(
        "06 - Authorization",
        [
            item(
                "Grant client-level viewer",
                "POST",
                "/authorization/grant",
                body={
                    "user": "{{userId}}",
                    "resource_type": "client",
                    "resource_id": "{{clientId}}",
                    "permission": "viewer",
                },
            ),
            item(
                "Check access (should be allowed)",
                "GET",
                "/authorization/check",
                query={
                    "user": "{{userId}}",
                    "resource_type": "structure",
                    "resource_id": "{{structureId}}",
                    "permission": "viewer",
                },
                description="Client-level grant should inherit all the way down to Structure.",
            ),
            item(
                "Check access for ungranted user (should be denied)",
                "GET",
                "/authorization/check",
                query={
                    "user": "user:nobody",
                    "resource_type": "client",
                    "resource_id": "{{clientId}}",
                    "permission": "viewer",
                },
            ),
            item(
                "Revoke grant",
                "DELETE",
                "/authorization/grant",
                query={
                    "user": "{{userId}}",
                    "resource_type": "client",
                    "resource_id": "{{clientId}}",
                    "permission": "viewer",
                },
                description="Idempotent: revoking a non-existent grant also returns 204.",
            ),
            item(
                "Grant on nonexistent resource (404)",
                "POST",
                "/authorization/grant",
                body={"user": "user:x", "resource_type": "zone", "resource_id": "no-such-zone", "permission": "viewer"},
            ),
        ],
    )
)

collection["item"].append(
    folder(
        "07 - Tree",
        [
            item(
                "Get authorized tree (client-level user)",
                "GET",
                "/clients/{{clientId}}/tree",
                query={"user": "{{userId}}"},
                description="Returns only branches user:parth can view. Re-run the 'Grant client-level viewer' request first.",
            ),
            item(
                "Get tree for a zone-level user (pruned)",
                "GET",
                "/clients/{{clientId}}/tree",
                query={"user": "user:carlos"},
                description="Assumes the demo seed has been run (user:carlos has zone-level access to North).",
            ),
            item(
                "Get tree for zero-access user (404, anti-enumeration)",
                "GET",
                "/clients/{{clientId}}/tree",
                query={"user": "user:nobody"},
            ),
            item(
                "Get tree for nonexistent client (identical 404)",
                "GET",
                "/clients/this-client-does-not-exist/tree",
                query={"user": "{{userId}}"},
                description="Must return the exact same 404 shape as the zero-access case above -- anti-enumeration.",
            ),
        ],
    )
)


def demo_check(name, user, resource_type, resource_id):
    return item(
        name,
        "GET",
        "/authorization/check",
        query={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": "viewer"},
    )


collection["item"].append(
    folder(
        "08 - Demo Scenarios",
        [
            folder(
                "India",
                [
                    item(
                        "Get India tree (user:parth, client-level)",
                        "GET",
                        "/clients/govt-of-india/tree",
                        query={"user": "user:parth"},
                    ),
                    item(
                        "Get India tree (user:carlos, zone-level, pruned)",
                        "GET",
                        "/clients/govt-of-india/tree",
                        query={"user": "user:carlos"},
                    ),
                    item(
                        "Get India tree (user:deepa, structure-only, pruned)",
                        "GET",
                        "/clients/govt-of-india/tree",
                        query={"user": "user:deepa"},
                    ),
                    demo_check("user:alice can view Indian Railway (project)", "user:alice", "project", "indian-railway"),
                    demo_check("user:alice can view Yamuna Bridge (inherited)", "user:alice", "structure", "yamuna-bridge"),
                ],
            ),
            folder(
                "Emirates",
                [
                    item(
                        "Get Emirates tree (user:etihad-admin)",
                        "GET",
                        "/clients/emirates/tree",
                        query={"user": "user:etihad-admin"},
                    ),
                    item("List zones under Etihad High Speed Railway", "GET", "/projects/etihad-high-speed-railway/zones"),
                ],
            ),
            folder(
                "Mexico",
                [
                    item(
                        "Get Mexico tree (user:mx-admin)",
                        "GET",
                        "/clients/mexican-government/tree",
                        query={"user": "user:mx-admin"},
                    ),
                    item("List zones under Mexican Railway", "GET", "/projects/mexican-railway/zones"),
                ],
            ),
        ],
    )
)

collection["item"].append(
    folder(
        "09 - Security Tests",
        [
            item(
                "Cross-client denial: Etihad admin cannot see India",
                "GET",
                "/clients/govt-of-india/tree",
                query={"user": "user:etihad-admin"},
                description="Expect 404 -- Emirates admin has no grant anywhere in India's tree.",
            ),
            item(
                "Cross-branch denial: zone-level user cannot see sibling zone",
                "GET",
                "/authorization/check",
                query={"user": "user:carlos", "resource_type": "zone", "resource_id": "south", "permission": "viewer"},
                description="user:carlos has zone-level access to North only. Expect allowed: false.",
            ),
            item(
                "No upward inheritance: structure-only user cannot see zone",
                "GET",
                "/authorization/check",
                query={"user": "user:deepa", "resource_type": "zone", "resource_id": "central", "permission": "viewer"},
                description="user:deepa has structure-only access to Yamuna Bridge. Expect allowed: false.",
            ),
            item(
                "Zero-grant denial",
                "GET",
                "/authorization/check",
                query={
                    "user": "user:nobody",
                    "resource_type": "structure",
                    "resource_id": "yamuna-bridge",
                    "permission": "viewer",
                },
            ),
            item(
                "Anti-enumeration: unauthorized vs nonexistent client (compare 404s)",
                "GET",
                "/clients/this-client-does-not-exist/tree",
                query={"user": "user:nobody"},
            ),
            item(
                "Invalid id shape is rejected (422)",
                "POST",
                "/clients",
                body={"id": "Not A Valid Slug!", "name": "X"},
            ),
            item(
                "Duplicate client id is rejected (409)",
                "POST",
                "/clients",
                body={"id": "{{clientId}}", "name": "Different Name"},
            ),
        ],
    )
)

out_path = Path(__file__).resolve().parent.parent / "postman" / "OpenFGA-ReBAC-New-Architecture.postman_collection.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
print("wrote", out_path, len(json.dumps(collection)), "bytes")
