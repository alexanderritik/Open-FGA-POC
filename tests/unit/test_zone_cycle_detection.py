"""Unit tests for the zone ancestor-walk cycle detection
(app/services/zone_service._assert_no_cycle), isolated from OpenFGA and
from the duplicate-id short-circuit in create_zone that normally makes a
"real" cycle unreachable through the API. A fake AuthorizationService
lets us directly exercise the walk over an arbitrarily deep/cyclic chain.
"""

import pytest

from app.services.exceptions import CircularReferenceError
from app.services.zone_service import _assert_no_cycle


class FakeAuthService:
    """Duck-typed stand-in for AuthorizationService: only `read_parent` is
    used by `_assert_no_cycle`."""

    def __init__(self, parents: dict[tuple[str, str], str]) -> None:
        self._parents = parents

    async def read_parent(self, object_type: str, object_id: str) -> str | None:
        return self._parents.get((object_type, object_id))


async def test_no_cycle_for_a_fresh_valid_chain():
    # zone:b's parent is zone:a; zone:a's parent is project:p.
    auth = FakeAuthService({("zone", "b"): "zone:a", ("zone", "a"): "project:p"})
    await _assert_no_cycle(auth, new_zone_id="c", parent_type="zone", parent_id="b")


async def test_cycle_detected_several_levels_up_the_ancestor_chain():
    # parent's chain: parent -> mid -> target. Creating "target" with
    # parent="parent" would make target its own great-grandparent.
    auth = FakeAuthService({("zone", "parent"): "zone:mid", ("zone", "mid"): "zone:target"})
    with pytest.raises(CircularReferenceError):
        await _assert_no_cycle(auth, new_zone_id="target", parent_type="zone", parent_id="parent")


async def test_self_parent_is_always_a_cycle():
    auth = FakeAuthService({})
    with pytest.raises(CircularReferenceError):
        await _assert_no_cycle(auth, new_zone_id="x", parent_type="zone", parent_id="x")


async def test_project_parent_can_never_cycle():
    auth = FakeAuthService({})
    await _assert_no_cycle(auth, new_zone_id="x", parent_type="project", parent_id="some-project")


async def test_walk_stops_cleanly_at_an_unrecorded_parent():
    """If the chain simply ends (parent has no recorded parent tuple),
    that's not a cycle — it's the caller's job (_assert_parent_exists) to
    have already rejected a nonexistent parent before this runs."""
    auth = FakeAuthService({})
    await _assert_no_cycle(auth, new_zone_id="c", parent_type="zone", parent_id="orphan-with-no-parent")
