"""TPS sampling: command selection, reply parsing, and the live sampling loop.

The stat card on the overview page was rendered from `runtime.tps`, which no
backend code ever produced — it read "—" on every server in every state. The
value now comes from a background thread that types the loader's tick-rate
command into the console and reads the answer back out of stdout, so the tests
cover both halves: the per-loader trivia (as a table) and the loop itself
(against a shell process pretending to be a server).
"""
import subprocess
import time

import pytest

from backend.server import tps
from backend.server.manager import ServerManager


def _wait(cond, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


# --- which command to send -------------------------------------------------

@pytest.mark.parametrize("loader,version,expected", [
    ("paper", "1.21.1", "tps"),
    ("Purpur", "1.20.1", "tps"),          # case-insensitive
    ("pufferfish", "1.19.2", "tps"),
    ("folia", "1.21.4", "tps"),
    ("forge", "1.20.1", "forge tps"),
    ("forge", "1.7.10", "forge tps"),     # no version floor for Forge
    ("neoforge", "1.21.1", "neoforge tps"),
    ("neoforge", "1.20.1", "forge tps"),  # pre-rename fork point
    ("vanilla", "1.20.3", "tick query"),  # first release with /tick
    ("vanilla", "1.21", "tick query"),
    ("fabric", "1.21.4", "tick query"),
    ("quilt", "1.20.6", "tick query"),
    ("vanilla", "26.1", "tick query"),    # year-based versioning
])
def test_probe_command_for_supported_servers(loader, version, expected):
    probe = tps.probe_for(loader, version)
    assert probe is not None, f"{loader} {version} should be samplable"
    assert probe.command == expected


@pytest.mark.parametrize("loader,version", [
    ("vanilla", "1.20.2"),   # /tick landed in 1.20.3
    ("fabric", "1.19.2"),
    ("quilt", "1.16.5"),
    ("vanilla", "24w14a"),   # snapshot: unparseable, so assume nothing
    ("vanilla", ""),
    ("", "1.21.1"),
    (None, "1.21.1"),
    ("someunknownloader", "1.21.1"),
])
def test_no_probe_when_the_server_cannot_answer(loader, version):
    """Guessing a command here would log an error line every sample interval."""
    assert tps.probe_for(loader, version) is None


# --- reading the reply -----------------------------------------------------

def test_reads_paper_reply():
    assert tps.classify("TPS from last 1m, 5m, 15m: 19.8, 20.0, 20.0") == (tps.TPS_VALUE, 19.8)


def test_reads_paper_reply_with_colour_codes_and_capped_marker():
    line = "§6TPS from last 1m, 5m, 15m: §a*20.0, §a20.0, §a20.0"
    assert tps.classify(line) == (tps.TPS_VALUE, 20.0)


def test_reads_forge_overall_line_not_per_dimension():
    overall = "Overall: Mean tick time: 3.933 ms. Mean TPS: 19.250"
    dimension = "minecraft:overworld: Mean tick time: 2.100 ms. Mean TPS: 20.000"
    assert tps.classify(overall) == (tps.TPS_VALUE, 19.25)
    # Per-dimension lines are part of the same reply but carry no overall
    # figure; they are recognised only so they can be suppressed.
    assert tps.classify(dimension) == (tps.NOISE, 0.0)


def test_reads_vanilla_tick_query_across_its_lines():
    assert tps.classify("Target tick rate: 20.0 per second.") == (tps.TARGET_RATE, 20.0)
    assert tps.classify("Average time per tick: 62.5ms (Target: 50.0ms)") == (tps.MSPT, 62.5)
    assert tps.classify("Percentiles: P50: 0.5ms P95: 0.9ms P99: 1.5ms; sample: 100") == (
        tps.NOISE, 0.0
    )


def test_unknown_command_reply_is_recognised_as_noise():
    assert tps.classify("Unknown or incomplete command, see below for error") == (tps.NOISE, 0.0)


def test_ordinary_log_lines_are_ignored():
    assert tps.classify("Starting minecraft server version 1.21.1") is None
    assert tps.classify("Notch joined the game") is None


def test_rate_from_mspt_caps_at_the_target():
    # Ticks finishing early do not make the server run faster than its target.
    assert tps.rate_from_mspt(0.6) == 20.0
    # Overrunning ticks do pull it down: 62.5ms/tick is 16 ticks a second.
    assert tps.rate_from_mspt(62.5) == pytest.approx(16.0)
    assert tps.rate_from_mspt(0.0) == 20.0


# --- consuming replies off the log stream ----------------------------------

def _sampling_manager(loader: str = "paper", version: str = "1.21.1") -> ServerManager:
    mgr = ServerManager(cwd=".", command=["true"], loader=loader, version=version)
    mgr._tps_probe = tps.probe_for(loader, version)
    return mgr


PREFIX = "[12:00:00] [Server thread/INFO]: "


def test_reply_to_our_own_probe_is_recorded_and_hidden():
    mgr = _sampling_manager()
    mgr._tps_pending_until = time.monotonic() + 5  # a probe is in flight
    suppressed = mgr._consume_tps_line(PREFIX + "TPS from last 1m, 5m, 15m: 18.5, 20.0, 20.0")
    assert suppressed is True, "our own poll must not scroll the user's console"
    assert mgr._tps == 18.5


def test_reply_to_a_user_typed_command_is_recorded_but_left_visible():
    mgr = _sampling_manager()
    mgr._tps_pending_until = 0.0  # nothing in flight: this is the user's own tps
    suppressed = mgr._consume_tps_line(PREFIX + "TPS from last 1m, 5m, 15m: 18.5, 20.0, 20.0")
    assert suppressed is False
    assert mgr._tps == 18.5  # still a free sample


def test_chat_cannot_spoof_a_tick_rate():
    """A player typing the reply into chat must not reach the dashboard."""
    mgr = _sampling_manager()
    mgr._tps_pending_until = time.monotonic() + 5
    for chat in (
        PREFIX + "<Notch> TPS from last 1m, 5m, 15m: 2.0, 2.0, 2.0",
        PREFIX + "[Not Secure] <Notch> TPS from last 1m, 5m, 15m: 2.0, 2.0, 2.0",
    ):
        assert mgr._consume_tps_line(chat) is False
    assert mgr._tps is None


def test_vanilla_reply_uses_the_target_rate_it_announced():
    mgr = _sampling_manager("vanilla", "1.21.1")
    mgr._tps_pending_until = time.monotonic() + 5
    assert mgr._consume_tps_line(PREFIX + "Target tick rate: 20.0 per second.") is True
    assert mgr._consume_tps_line(PREFIX + "Average time per tick: 100.0ms (Target: 50.0ms)") is True
    assert mgr._tps == pytest.approx(10.0)
    # The trailing percentile line belongs to the same reply and is hidden too —
    # the window is what governs, not "the first line that carried a number".
    assert mgr._consume_tps_line(PREFIX + "Percentiles: P50: 0.5ms P95: 0.9ms") is True


# The four lines a real Fabric 26.2 server sends back, copied verbatim from
# logs/latest.log. The third has no log prefix: vanilla sends the whole reply as
# one multi-line chat component, so log4j stamps only the first line — and the
# bare line is the one carrying the number. Requiring a prefix therefore dropped
# the only line that mattered while letting the rest reach the console, which is
# exactly how this shipped broken the first time.
REAL_TICK_QUERY_REPLY = [
    "[11:43:03] [Server thread/INFO]: The game is running normally\n",
    "[11:43:03] [Server thread/INFO]: Target tick rate: 20.0 per second.\n",
    "Average time per tick: 0.4ms (Target: 50.0ms)\n",
    "[11:43:03] [Server thread/INFO]: Percentiles: P50: 0.3ms P95: 0.6ms P99: 6.8ms. Sample: 100\n",
]


def test_reads_a_real_vanilla_tick_query_reply():
    mgr = _sampling_manager("fabric", "26.2")
    assert mgr._tps_probe is not None and mgr._tps_probe.command == "tick query"
    mgr._tps_pending_until = time.monotonic() + 5

    suppressed = [mgr._consume_tps_line(line) for line in REAL_TICK_QUERY_REPLY]

    # 0.4ms per tick is comfortably inside the 50ms budget, so the server is
    # keeping up and the rate sits at the target.
    assert mgr._tps == pytest.approx(20.0)
    # Every line of the reply is ours, including the bare one; none should reach
    # the console the user reads.
    assert all(suppressed), f"leaked to console: {[l for l, s in zip(REAL_TICK_QUERY_REPLY, suppressed) if not s]}"


def test_real_reply_reports_a_server_that_is_behind():
    """The same four lines, from a server taking 80ms over a 50ms budget."""
    mgr = _sampling_manager("fabric", "26.2")
    mgr._tps_pending_until = time.monotonic() + 5
    for line in REAL_TICK_QUERY_REPLY:
        mgr._consume_tps_line(line.replace("0.4ms (Target", "80.0ms (Target"))
    assert mgr._tps == pytest.approx(12.5)  # 1000 / 80


def test_bare_continuation_line_is_read_outside_any_prefix():
    """The regression guard: no prefix must not mean "not a reading"."""
    mgr = _sampling_manager("fabric", "26.2")
    mgr._tps_pending_until = time.monotonic() + 5
    mgr._consume_tps_line("Average time per tick: 62.5ms (Target: 50.0ms)\n")
    assert mgr._tps == pytest.approx(16.0)


def test_unsampled_loaders_skip_the_parsing_entirely():
    mgr = _sampling_manager("fabric", "1.19.2")
    assert mgr._tps_probe is None
    mgr._tps_pending_until = time.monotonic() + 5
    assert mgr._consume_tps_line(PREFIX + "TPS from last 1m, 5m, 15m: 5.0, 5.0, 5.0") is False
    assert mgr._tps is None


# --- what status() publishes -----------------------------------------------

class _AliveProc:
    pid = 4321
    stdin = None

    def poll(self):
        return None


def test_status_publishes_a_fresh_reading():
    mgr = _sampling_manager()
    mgr._process = _AliveProc()
    mgr._tps = 19.456
    mgr._tps_at = time.monotonic()
    status = mgr.status()
    assert status["tps"] == 19.46  # rounded for display
    assert status["tpsSupported"] is True


def test_status_drops_a_stale_reading():
    """A number that stopped updating still reads as "the server is fine"."""
    mgr = _sampling_manager()
    mgr._process = _AliveProc()
    mgr._tps = 20.0
    mgr._tps_at = time.monotonic() - ServerManager.TPS_STALE_AFTER_SEC - 1
    status = mgr.status()
    assert "tps" not in status
    assert status["tpsSupported"] is True


def test_status_reports_unsupported_servers_as_such():
    mgr = _sampling_manager("fabric", "1.19.2")
    mgr._process = _AliveProc()
    status = mgr.status()
    assert "tps" not in status
    assert status["tpsSupported"] is False


def test_stopped_server_reports_no_tps_at_all():
    mgr = _sampling_manager()
    mgr._tps = 20.0
    mgr._tps_at = time.monotonic()
    status = mgr.status()
    assert "tps" not in status
    assert "tpsSupported" not in status


# --- the sampling loop, against a process that answers ---------------------

# A shell stand-in for a Paper server: announces it has finished loading, then
# answers `tps` until told to stop.
FAKE_SERVER = r"""
echo '[12:00:00] [Server thread/INFO]: Done (1.234s)! For help, type "help"'
while read -r cmd; do
  case "$cmd" in
    tps) echo '[12:00:01] [Server thread/INFO]: TPS from last 1m, 5m, 15m: 19.9, 20.0, 20.0' ;;
    stop) exit 0 ;;
    *) echo "[12:00:01] [Server thread/INFO]: Unknown or incomplete command" ;;
  esac
done
"""

# A server that has finished loading but does not know the command.
FAKE_DEAF_SERVER = r"""
echo '[12:00:00] [Server thread/INFO]: Done (1.234s)! For help, type "help"'
while read -r cmd; do
  case "$cmd" in
    stop) exit 0 ;;
    *) echo "[12:00:01] [Server thread/INFO]: Unknown or incomplete command" ;;
  esac
done
"""


# A vanilla-family stand-in that answers `tick query` with the exact four lines
# a real 26.2 server sends, bare continuation line and all.
FAKE_VANILLA_SERVER = r"""
echo '[11:42:33] [Server thread/INFO]: Done (0.824s)! For help, type "help"'
while read -r cmd; do
  case "$cmd" in
    "tick query")
      echo '[11:43:03] [Server thread/INFO]: The game is running normally'
      echo '[11:43:03] [Server thread/INFO]: Target tick rate: 20.0 per second.'
      echo 'Average time per tick: 0.4ms (Target: 50.0ms)'
      echo '[11:43:03] [Server thread/INFO]: Percentiles: P50: 0.3ms P95: 0.6ms P99: 6.8ms. Sample: 100'
      ;;
    stop) exit 0 ;;
  esac
done
"""


def _spawn_fake(script: str, loader: str = "paper") -> ServerManager:
    mgr = ServerManager(cwd=".", command=["sh", "-c", script], loader=loader, version="1.21.1")
    mgr.TPS_SAMPLE_INTERVAL_SEC = 0.05
    mgr.TPS_RESPONSE_TIMEOUT_SEC = 1.0
    with mgr._lock:  # mimic start(), which holds the lock across _spawn_process
        started, message = mgr._spawn_process(mgr.command)
    assert started, message
    return mgr


def test_sampler_polls_a_running_server_and_fills_in_the_stat():
    mgr = _spawn_fake(FAKE_SERVER)
    try:
        assert _wait(lambda: mgr.status().get("tps") == 19.9), "no reading arrived"
        # The poll's own reply stays out of the console the user reads...
        console = "".join(text for _, text in mgr._stdout_buffer)
        assert "TPS from last 1m" not in console
        # ...while everything else the server said is still there.
        assert "Done (1.234s)" in console
    finally:
        mgr.stop()


def test_stop_clears_the_reading_and_the_sampler():
    mgr = _spawn_fake(FAKE_SERVER)
    assert _wait(lambda: mgr.status().get("tps") == 19.9), "no reading arrived"
    thread = mgr._tps_thread
    mgr.stop()
    assert "tps" not in mgr.status()
    assert thread is not None and not thread.is_alive()


def test_sampler_gives_up_on_a_server_that_never_answers():
    """A wrong guess must cost one blank card, not an error line every 15s."""
    mgr = _spawn_fake(FAKE_DEAF_SERVER)
    try:
        thread = mgr._tps_thread
        assert thread is not None
        thread.join(timeout=10)
        assert not thread.is_alive(), "sampler kept polling a server that never answers"
        assert "tps" not in mgr.status()
        # The unknown-command replies were recognised as probe fallout and kept
        # out of the console rather than printed once per attempt.
        console = "".join(text for _, text in mgr._stdout_buffer)
        assert "Unknown or incomplete command" not in console
    finally:
        mgr.stop()


def test_sampler_reads_a_real_vanilla_reply_end_to_end():
    """The whole path: probe sent, four lines back, number on the stat card."""
    mgr = ServerManager(
        cwd=".",
        command=["sh", "-c", FAKE_VANILLA_SERVER],
        loader="fabric",
        version="26.2",
    )
    mgr.TPS_SAMPLE_INTERVAL_SEC = 0.05
    mgr.TPS_RESPONSE_TIMEOUT_SEC = 1.0
    with mgr._lock:
        started, message = mgr._spawn_process(mgr.command)
    assert started, message
    try:
        assert _wait(lambda: mgr.status().get("tps") == 20.0), "no reading arrived"
        console = "".join(text for _, text in mgr._stdout_buffer)
        # None of the reply reaches the user's console — in particular the bare
        # "Average time per tick" line, which used to leak on every poll.
        for fragment in (
            "The game is running normally",
            "Target tick rate",
            "Average time per tick",
            "Percentiles",
        ):
            assert fragment not in console, f"{fragment!r} leaked into the console"
        assert "Done (0.824s)" in console
    finally:
        mgr.stop()


def test_no_sampler_thread_for_a_server_that_cannot_answer():
    mgr = ServerManager(
        cwd=".", command=["sh", "-c", "sleep 2"], loader="fabric", version="1.19.2"
    )
    with mgr._lock:
        started, message = mgr._spawn_process(mgr.command)
    assert started, message
    try:
        assert mgr._tps_thread is None
        assert mgr._tps_probe is None
    finally:
        mgr._process.kill()
        mgr._process.wait(timeout=5)
