"""Manual verification of the core ReBAC behaviors before any API is built:

  project:indian-railway
      -> zone:north
          -> zone:delhi
              -> zone:central
                  -> structure:yamuna-bridge

Confirms:
  1. A user granted `viewer` at zone:north can reach structure:yamuna-bridge
     three levels down (downward inheritance through nested zones).
  2. A user granted `viewer` only at structure:yamuna-bridge cannot reach
     zone:central, zone:delhi, zone:north, the project, or the client
     (no upward inheritance).
  3. A user granted `viewer` at zone:north cannot reach a sibling branch,
     zone:south (no cross-branch inheritance).

Writes and then deletes its own tuples; does not touch the users/clients
created by any other step.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.sync.client.client import OpenFgaClient

from app.core.config import get_settings

HIERARCHY_TUPLES = [
    ClientTuple(user="client:govt-of-india", relation="parent", object="project:indian-railway"),
    ClientTuple(user="project:indian-railway", relation="parent", object="zone:north"),
    ClientTuple(user="zone:north", relation="parent", object="zone:delhi"),
    ClientTuple(user="zone:delhi", relation="parent", object="zone:central"),
    ClientTuple(user="project:indian-railway", relation="parent", object="zone:south"),
    ClientTuple(user="zone:central", relation="parent", object="structure:yamuna-bridge"),
]


def check(client: OpenFgaClient, user: str, relation: str, obj: str) -> bool:
    response = client.check(ClientCheckRequest(user=user, relation=relation, object=obj))
    return bool(response.allowed)


def main() -> None:
    settings = get_settings()
    configuration = ClientConfiguration(
        api_url=settings.fga_api_url,
        store_id=settings.fga_store_id,
        authorization_model_id=settings.fga_model_id,
    )

    with OpenFgaClient(configuration) as client:
        client.write(ClientWriteRequest(writes=HIERARCHY_TUPLES))

        try:
            grant_north = [ClientTuple(user="user:alice", relation="viewer", object="zone:north")]
            grant_structure = [
                ClientTuple(user="user:carlos", relation="viewer", object="structure:yamuna-bridge")
            ]
            client.write(ClientWriteRequest(writes=grant_north + grant_structure))

            print("--- downward inheritance: user:alice granted viewer at zone:north ---")
            results = {
                "zone:north": check(client, "user:alice", "viewer", "zone:north"),
                "zone:delhi": check(client, "user:alice", "viewer", "zone:delhi"),
                "zone:central": check(client, "user:alice", "viewer", "zone:central"),
                "structure:yamuna-bridge": check(client, "user:alice", "viewer", "structure:yamuna-bridge"),
                "zone:south (sibling branch)": check(client, "user:alice", "viewer", "zone:south"),
            }
            for label, allowed in results.items():
                print(f"  alice -> {label}: {allowed}")

            assert results["zone:north"] is True
            assert results["zone:delhi"] is True
            assert results["zone:central"] is True
            assert results["structure:yamuna-bridge"] is True, "downward inheritance through 3 nested zones failed"
            assert results["zone:south (sibling branch)"] is False, "cross-branch leakage detected"

            print("--- no upward inheritance: user:carlos granted viewer at structure:yamuna-bridge only ---")
            results = {
                "structure:yamuna-bridge": check(client, "user:carlos", "viewer", "structure:yamuna-bridge"),
                "zone:central": check(client, "user:carlos", "viewer", "zone:central"),
                "zone:delhi": check(client, "user:carlos", "viewer", "zone:delhi"),
                "zone:north": check(client, "user:carlos", "viewer", "zone:north"),
                "project:indian-railway": check(client, "user:carlos", "viewer", "project:indian-railway"),
                "client:govt-of-india": check(client, "user:carlos", "viewer", "client:govt-of-india"),
            }
            for label, allowed in results.items():
                print(f"  carlos -> {label}: {allowed}")

            assert results["structure:yamuna-bridge"] is True
            assert results["zone:central"] is False, "upward leakage: structure -> zone:central"
            assert results["zone:delhi"] is False, "upward leakage: structure -> zone:delhi"
            assert results["zone:north"] is False, "upward leakage: structure -> zone:north"
            assert results["project:indian-railway"] is False, "upward leakage: structure -> project"
            assert results["client:govt-of-india"] is False, "upward leakage: structure -> client"

            print("\nAll assertions passed.")
        finally:
            client.write(
                ClientWriteRequest(
                    deletes=HIERARCHY_TUPLES
                    + [
                        ClientTuple(user="user:alice", relation="viewer", object="zone:north"),
                        ClientTuple(user="user:carlos", relation="viewer", object="structure:yamuna-bridge"),
                    ]
                )
            )


if __name__ == "__main__":
    main()
