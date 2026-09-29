from backend.server.manager import ServerManager


def test_parse_jvm_memory_stats_zgc():
    output = """\
61191:
ZHeap            used 2930M, capacity 7856M, max capacity 8192M
 Cache           4926M (2)
  size classes   1G (1), 2G (1)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == 2930 * 1024**2
    assert stats.committed_bytes == 7856 * 1024**2
    assert stats.max_bytes == 8192 * 1024**2


def test_parse_jvm_memory_stats_g1():
    output = """\
64195:
garbage-first heap   total reserved 1048576K, committed 264192K, used 134420K [0x00000000c0000000, 0x0000000100000000)
 region size 1024K, 2 young (2048K), 1 survivors (1024K)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == 134420 * 1024
    assert stats.committed_bytes == 264192 * 1024
    assert stats.max_bytes == 1048576 * 1024


def test_parse_jvm_memory_stats_parallel():
    output = """\
64268:
PSYoungGen      total 76288K, used 5242K [0x00000000eab00000, 0x00000000f0000000, 0x0000000100000000)
 eden space 65536K, 8% used [0x00000000eab00000,0x00000000eb01ebd0,0x00000000eeb00000)
 from space 10752K, 0% used [0x00000000ef580000,0x00000000ef580000,0x00000000f0000000)
 to   space 10752K, 0% used [0x00000000eeb00000,0x00000000eeb00000,0x00000000ef580000)
ParOldGen       total 175104K, used 132228K [0x00000000c0000000, 0x00000000cab00000, 0x00000000eab00000)
 object space 175104K, 75% used [0x00000000c0000000,0x00000000c8121198,0x00000000cab00000)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == (5242 + 132228) * 1024
    assert stats.committed_bytes == (76288 + 175104) * 1024
    assert stats.max_bytes == 1024**3


def test_parse_jvm_memory_stats_serial():
    output = """\
64331:
DefNew     total 78656K, used 5596K [0x00000000c0000000, 0x00000000c5550000, 0x00000000d5550000)
 eden space 69952K,   8% used [0x00000000c0000000, 0x00000000c05770f0, 0x00000000c4450000)
 from space 8704K,   0% used [0x00000000c4450000, 0x00000000c4450000, 0x00000000c4cd0000)
 to   space 8704K,   0% used [0x00000000c4cd0000, 0x00000000c4cd0000, 0x00000000c5550000)
Tenured    total 174784K, used 132228K [0x00000000d5550000, 0x00000000e0000000, 0x0000000100000000)
 the  space 174784K,  75% used [0x00000000d5550000, 0x00000000dd671198,0x00000000e0000000)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == (5596 + 132228) * 1024
    assert stats.committed_bytes == (78656 + 174784) * 1024
    assert stats.max_bytes == 1024**3


def test_parse_jvm_memory_stats_shenandoah():
    output = """\
64383:
Shenandoah Heap
 1024M max, 1024M soft max, 256M committed, 131M used
 2048 x 512 K regions
Status: not cancelled
Reserved region:
 - [0x00000000c0000000, 0x0000000100000000)
Collection set:
 - map (vanilla): 0x0000000000011800
 - map (biased):  0x0000000000010000
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == 131 * 1024**2
    assert stats.committed_bytes == 256 * 1024**2
    assert stats.max_bytes == 1024 * 1024**2


def test_parse_jvm_memory_stats_unknown_format():
    assert ServerManager._parse_jvm_memory_stats("unknown format") is None


# JDK 17/21 print G1 without "reserved"/"committed" and indent every line by
# one space; Serial uses the long generation names. Formats taken from the
# jdk17u/jdk21u print_on() sources.

def test_parse_jvm_memory_stats_g1_jdk17_21():
    output = """\
64195:
 garbage-first heap   total 264192K, used 134420K [0x00000000c0000000, 0x0000000100000000)
  region size 1024K, 2 young (2048K), 1 survivors (1024K)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == 134420 * 1024
    assert stats.committed_bytes == 264192 * 1024
    assert stats.max_bytes == 1024**3


def test_parse_jvm_memory_stats_parallel_jdk17_21():
    output = """\
64268:
 PSYoungGen      total 76288K, used 5242K [0x00000000eab00000, 0x00000000f0000000, 0x0000000100000000)
  eden space 65536K, 8% used [0x00000000eab00000,0x00000000eb01ebd0,0x00000000eeb00000)
 ParOldGen       total 175104K, used 132228K [0x00000000c0000000, 0x00000000cab00000, 0x00000000eab00000)
  object space 175104K, 75% used [0x00000000c0000000,0x00000000c8121198,0x00000000cab00000)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == (5242 + 132228) * 1024
    assert stats.max_bytes == 1024**3


def test_parse_jvm_memory_stats_serial_jdk17_21():
    output = """\
64331:
 def new generation   total 78656K, used 5596K [0x00000000c0000000, 0x00000000c5550000, 0x00000000d5550000)
  eden space 69952K,   8% used [0x00000000c0000000, 0x00000000c05770f0, 0x00000000c4450000)
 tenured generation   total 174784K, used 132228K [0x00000000d5550000, 0x00000000e0000000, 0x0000000100000000)
   the space 174784K,  75% used [0x00000000d5550000, 0x00000000dd671198, 0x00000000e0000000)
"""

    stats = ServerManager._parse_jvm_memory_stats(output)

    assert stats is not None
    assert stats.used_bytes == (5596 + 132228) * 1024
    assert stats.committed_bytes == (78656 + 174784) * 1024
    assert stats.max_bytes == 1024**3


def test_failed_probe_is_cached(tmp_path, monkeypatch):
    """A probe that yields nothing must not re-spawn jcmd on every status
    call; get_status() is polled from many code paths."""
    manager = ServerManager(cwd=str(tmp_path), command=["java", "-jar", "server.jar"])
    monkeypatch.setattr(ServerManager, "is_running", property(lambda self: True))
    manager._process = object()
    calls = []
    monkeypatch.setattr(manager, "_probe_jvm_memory_stats", lambda: calls.append(1))

    assert manager._get_jvm_memory_stats() is None
    assert manager._get_jvm_memory_stats() is None
    assert len(calls) == 1


def test_heap_stats_only_probed_when_requested(client, app, tmp_servers_root, monkeypatch):
    """Heap stats are opt-in: the detail route runs the jcmd probe only for
    ?heap=1, and status() (the hot path) never does."""
    from backend.server.registry import get_server_process_registry
    from tests.test_settings_allowlist import _make_server

    sid = _make_server(app, tmp_servers_root, 25950, "heap-optin")
    probes = []

    class FakeManager:
        def jvm_heap_info(self):
            probes.append(1)
            return {"heapUsedBytes": 1, "heapCommittedBytes": 2, "heapMaxBytes": 3}

    registry = get_server_process_registry()
    monkeypatch.setattr(registry, "get_manager", lambda server_id: FakeManager())
    monkeypatch.setattr(
        registry, "get_status",
        lambda server_id: {"status": "running", "ram": {"rssBytes": 5}},
    )

    plain = client.get(f"/api/servers/{sid}").get_json()
    assert plain["runtime"]["ram"] == {"rssBytes": 5}
    assert probes == []

    ram = client.get(f"/api/servers/{sid}?heap=1").get_json()["runtime"]["ram"]
    assert ram == {"rssBytes": 5, "heapUsedBytes": 1, "heapCommittedBytes": 2, "heapMaxBytes": 3}
    assert probes == [1]


def test_status_does_not_probe_jvm(tmp_path, monkeypatch):
    manager = ServerManager(cwd=str(tmp_path), command=["java", "-jar", "server.jar"])
    monkeypatch.setattr(
        manager, "_get_jvm_memory_stats",
        lambda: (_ for _ in ()).throw(AssertionError("status() probed jcmd")),
    )

    assert "status" in manager.status()
