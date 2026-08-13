"""Modrinth ``environment`` metadata as the authority on a mod's side.

Issue #64: Sodium was installed onto a NeoForge server and killed it with
``NoClassDefFoundError: org/lwjgl/Version``. Every signal Fabricator could
read out of the jar said "uncertain" — the manifest declares no mod-level
side and the real code sits in a nested jar — while Modrinth had the answer
all along: ``environment: ["client_only"]``.

These tests pin the two halves of that fix: the value table
(:mod:`backend.modrinth.environment`), and the post-install sweep that lets
it overrule whatever the index and the jar heuristics decided
(``_apply_modrinth_side_metadata``).
"""
from __future__ import annotations

import hashlib
import zipfile
from types import SimpleNamespace

import pytest

from backend.modrinth import environment as env
from backend.modrinth.client import ModrinthClient


# ---------------------------------------------------------------------------
# The environment value table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", sorted(env.SERVER_CAPABLE_ENVIRONMENTS))
def test_server_capable_environments_resolve_to_server(value):
    verdict = env.side_from_environment([value])
    assert verdict.side == "server"
    assert value in verdict.reason


@pytest.mark.parametrize("value", sorted(env.CLIENT_ONLY_ENVIRONMENTS))
def test_client_only_environments_resolve_to_client(value):
    verdict = env.side_from_environment([value])
    assert verdict.side == "client"
    assert value in verdict.reason


def test_sodium_is_client_only():
    """The exact payload the live v2 API returns for Sodium."""
    assert env.side_from_environment(["client_only"])[0] == "client"


@pytest.mark.parametrize("value", [None, [], "", ["unknown"], ["something_new"], 42])
def test_uninformative_environment_is_uncertain(value):
    assert env.side_from_environment(value)[0] == "uncertain"


def test_bare_string_environment_is_accepted():
    """The field is a list, but a scalar must not be silently misread."""
    assert env.side_from_environment("client_only")[0] == "client"


def test_mixed_environment_prefers_server():
    """A contradictory tag set must not strip a mod the server can load (#58)."""
    assert env.side_from_environment(["client_only", "client_and_server"])[0] == "server"


# ---------------------------------------------------------------------------
# Project-level resolution, including the deprecated fields
# ---------------------------------------------------------------------------

def test_environment_outranks_deprecated_fields():
    project = {
        "environment": ["client_and_server"],
        "client_side": "required",
        "server_side": "unsupported",
    }
    verdict = env.side_from_project(project)
    assert verdict.side == "server"
    assert "environment" in verdict.reason


def test_falls_back_to_server_side_when_environment_absent():
    """Covers a project whose metadata has not been migrated yet."""
    verdict = env.side_from_project({"client_side": "required", "server_side": "unsupported"})
    assert verdict.side == "client"
    assert "server_side" in verdict.reason


@pytest.mark.parametrize("server_side,expected", [
    ("required", "server"),
    ("optional", "server"),
    ("unsupported", "client"),
])
def test_deprecated_server_side_values(server_side, expected):
    assert env.side_from_project({"server_side": server_side})[0] == expected


def test_project_with_no_side_metadata_at_all_is_uncertain():
    assert env.side_from_project({"title": "Mystery"})[0] == "uncertain"


# ---------------------------------------------------------------------------
# Bulk lookup
# ---------------------------------------------------------------------------

class _StubClient:
    """Stands in for ModrinthClient's two bulk endpoints."""

    def __init__(self, versions=None, projects=None, raises=None):
        self._versions = versions or {}
        self._projects = projects or []
        self._raises = raises
        self.version_calls = 0
        self.project_calls = 0

    def get_versions_by_hashes(self, hashes, algorithm="sha1"):
        self.version_calls += 1
        if self._raises:
            raise self._raises
        return {h: v for h, v in self._versions.items() if h in hashes}

    def get_projects(self, project_ids):
        self.project_calls += 1
        return [p for p in self._projects if p.get("id") in project_ids]


@pytest.fixture
def hashes(request):
    """Hashes unique to the running test.

    The hash -> version cache is deliberately process-wide and normally reset
    between tests, but ``test_app_factory`` purges ``backend.*`` from
    ``sys.modules`` mid-suite, after which the reset fixture and the code
    under test can be holding two different copies of the cache module.
    Deriving the hashes from the test id sidesteps the whole question: no two
    tests here can ever collide in a shared cache.
    """
    seed = hashlib.sha1(request.node.nodeid.encode()).hexdigest()
    return SimpleNamespace(
        sodium=seed,
        lithium=hashlib.sha1((seed + "lithium").encode()).hexdigest(),
        unknown=hashlib.sha1((seed + "unknown").encode()).hexdigest(),
    )


def _sodium_stub(hashes):
    return _StubClient(
        versions={
            hashes.sodium: {"project_id": "AANobbMI", "id": "v1", "version_number": "0.8.13"},
            hashes.lithium: {"project_id": "gvQqBUqZ", "id": "v2", "version_number": "0.13.0"},
        },
        projects=[
            {"id": "AANobbMI", "slug": "sodium", "title": "Sodium",
             "environment": ["client_only"]},
            {"id": "gvQqBUqZ", "slug": "lithium", "title": "Lithium",
             "environment": ["client_or_server_prefers_both"]},
        ],
    )


def test_sides_by_hash_resolves_both_directions(hashes):
    sides = env.sides_by_hash(_sodium_stub(hashes), [hashes.sodium, hashes.lithium])
    assert sides[hashes.sodium][0] == "client"
    assert sides[hashes.lithium][0] == "server"
    assert "Sodium" in sides[hashes.sodium][1]


def test_sides_by_hash_omits_hashes_modrinth_does_not_know(hashes):
    """A hand-built or repackaged jar simply has no entry — not a wrong one."""
    assert env.sides_by_hash(_sodium_stub(hashes), [hashes.unknown]) == {}


def test_sides_by_hash_never_raises_on_api_failure(hashes):
    """A Modrinth outage degrades classification; it must not fail the install."""
    stub = _StubClient(raises=RuntimeError("modrinth is down"))
    assert env.sides_by_hash(stub, [hashes.sodium]) == {}


def test_sides_by_hash_skips_the_network_when_there_is_nothing_to_ask(hashes):
    stub = _sodium_stub(hashes)
    assert env.sides_by_hash(stub, []) == {}
    assert stub.version_calls == 0


def test_sides_by_path_rekeys_the_result(hashes):
    sides = env.sides_by_path(_sodium_stub(hashes), {"mods/sodium.jar": hashes.sodium})
    assert sides["mods/sodium.jar"][0] == "client"


# ---------------------------------------------------------------------------
# The post-install sweep
# ---------------------------------------------------------------------------

SODIUM_PROJECT = {
    "id": "AANobbMI", "slug": "sodium", "title": "Sodium",
    "environment": ["client_only"],
}
LITHIUM_PROJECT = {
    "id": "gvQqBUqZ", "slug": "lithium", "title": "Lithium",
    "environment": ["client_or_server_prefers_both"],
}


@pytest.fixture
def pack(tmp_path, request, monkeypatch):
    """A server directory plus a client with the Modrinth answers you declare.

    Jars carry the test's own id as their payload, so each one hashes to
    something no other test can produce and the process-wide hash cache cannot
    carry a verdict across tests. Hashing itself is left alone — computing the
    digest of a file on disk is exactly what the sweep does in production, so
    stubbing it would leave that step untested.
    """
    from backend.modrinth.installed import file_sha1

    install_path = tmp_path / "server"
    install_path.mkdir()
    known: dict = {}
    counter = {"n": 0}

    def add_jar(relative: str, project: dict = None) -> str:
        counter["n"] += 1
        path = install_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(
                "com/example/Demo.class",
                f"{request.node.nodeid}#{counter['n']}".encode(),
            )
        digest = file_sha1(path)
        if project is not None:
            known[digest] = project
        return digest

    def add_file(relative: str, content: str = "{}") -> None:
        path = install_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def get_versions_by_hashes(hashes, algorithm="sha1"):
        return {
            digest: {"project_id": project["id"], "id": "v1", "version_number": "1.0"}
            for digest, project in known.items() if digest in hashes
        }

    def get_projects(project_ids):
        return [p for p in known.values() if p["id"] in project_ids]

    client = ModrinthClient()
    monkeypatch.setattr(client, "get_versions_by_hashes", get_versions_by_hashes)
    monkeypatch.setattr(client, "get_projects", get_projects)

    return SimpleNamespace(
        client=client,
        install_path=install_path,
        add_jar=add_jar,
        add_file=add_file,
    )


def _result(installed, uncertain=()):
    return {
        "files_installed": list(installed),
        "files_skipped": [],
        "uncertain_mod_files": [
            {"path": path, "reason": "no side declared"} for path in uncertain
        ],
    }


def test_sweep_removes_a_client_only_mod_the_index_insisted_on(pack):
    """The reproduction of #64, end to end.

    The pack index claimed the jar was server-required and the jar heuristics
    had no opinion, so it landed in ``files_installed``. Modrinth says
    ``client_only``, and that has to be the last word.
    """
    pack.add_jar("mods/sodium.jar", SODIUM_PROJECT)
    result = _result(["mods/sodium.jar"], uncertain=["mods/sodium.jar"])

    removed = pack.client._apply_modrinth_side_metadata(pack.install_path, result, {})

    assert removed == ["mods/sodium.jar"]
    assert not (pack.install_path / "mods" / "sodium.jar").exists()
    assert result["files_installed"] == []
    assert result["files_skipped"] == ["mods/sodium.jar"]
    assert result["uncertain_mod_files"] == []


def test_sweep_clears_the_uncertain_warning_for_a_server_safe_mod(pack):
    """Modrinth vouching for a jar leaves the user no decision to make."""
    pack.add_jar("mods/lithium.jar", LITHIUM_PROJECT)
    result = _result(["mods/lithium.jar"], uncertain=["mods/lithium.jar"])

    removed = pack.client._apply_modrinth_side_metadata(pack.install_path, result, {})

    assert removed == []
    assert (pack.install_path / "mods" / "lithium.jar").is_file()
    assert result["files_installed"] == ["mods/lithium.jar"]
    assert result["uncertain_mod_files"] == []


def test_sweep_respects_an_explicit_user_override(pack):
    """Only the user knows what they are building — their choice outranks ours."""
    pack.add_jar("mods/sodium.jar", SODIUM_PROJECT)
    result = _result(["mods/sodium.jar"])

    removed = pack.client._apply_modrinth_side_metadata(
        pack.install_path, result, {"mods/sodium.jar": "server"},
    )

    assert removed == []
    assert (pack.install_path / "mods" / "sodium.jar").is_file()
    assert result["files_installed"] == ["mods/sodium.jar"]


def test_sweep_handles_jars_that_arrived_through_overrides(pack):
    """Overrides are reported with a prefix but live at the bare path on disk."""
    pack.add_jar("mods/sodium.jar", SODIUM_PROJECT)
    result = _result(["overrides/mods/sodium.jar"])

    removed = pack.client._apply_modrinth_side_metadata(pack.install_path, result, {})

    assert removed == ["overrides/mods/sodium.jar"]
    assert not (pack.install_path / "mods" / "sodium.jar").exists()
    assert result["files_skipped"] == ["overrides/mods/sodium.jar"]


def test_sweep_ignores_non_mod_files(pack):
    """Configs and resource packs are not jars in mods/ and are never hashed."""
    pack.add_file("config/sodium.json")
    result = _result(["config/sodium.json"])

    assert pack.client._apply_modrinth_side_metadata(pack.install_path, result, {}) == []
    assert result["files_installed"] == ["config/sodium.json"]


def test_sweep_is_a_no_op_when_modrinth_knows_nothing(pack):
    """An unrecognised jar keeps whatever the earlier layers decided."""
    pack.add_jar("mods/homemade.jar")
    result = _result(["mods/homemade.jar"], uncertain=["mods/homemade.jar"])

    assert pack.client._apply_modrinth_side_metadata(pack.install_path, result, {}) == []
    assert result["files_installed"] == ["mods/homemade.jar"]
    assert len(result["uncertain_mod_files"]) == 1


def test_sweep_leaves_a_jar_it_cannot_find_on_disk_alone(pack):
    """A path in the report with nothing behind it must not crash the sweep."""
    result = _result(["mods/vanished.jar"])

    assert pack.client._apply_modrinth_side_metadata(pack.install_path, result, {}) == []
    assert result["files_installed"] == ["mods/vanished.jar"]


def test_client_required_server_optional_is_not_installed():
    """Regression: "optional on the server" must not mean "install it".

    Fog is tagged ``client_only_server_optional`` on Modrinth, and its jar
    references ``net/minecraft/client/KeyMapping``. Treating the tag as
    server-capable overrode the jar scan's correct client verdict and killed a
    real NeoForge server with "Attempted to load class ... for invalid dist
    DEDICATED_SERVER" — the very failure #64 is about. Skipping costs an
    optional enhancement the user can still add by hand.
    """
    assert env.side_from_environment(["client_only_server_optional"])[0] == "client"


def test_server_capable_values_all_have_a_real_server_side():
    """Guards the distinction the Fog regression turned on.

    Everything in the server set must be a mod the server requires or can use
    on its own. "Optional on the server" is not that, and must never be added
    back here.
    """
    assert "client_only_server_optional" not in env.SERVER_CAPABLE_ENVIRONMENTS
    assert not (env.SERVER_CAPABLE_ENVIRONMENTS & env.CLIENT_ONLY_ENVIRONMENTS)
