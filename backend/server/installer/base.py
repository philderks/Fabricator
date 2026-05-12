"""Abstract base class for Minecraft server installers."""
import hashlib
import logging
import os
import re
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any, TypeVar

import requests


logger = logging.getLogger(__name__)

T = TypeVar("T")

DIR_PERMISSIONS = 0o775

# Streaming chunk size for ``download_with_hash_verify``; matches the value
# used at the Modrinth-client + per-loader sites prior to consolidation. 64 KiB
# strikes a balance between per-chunk syscall overhead and progress-callback
# granularity for multi-MB installer JARs.
_DOWNLOAD_CHUNK_SIZE = 65536

# Allowlist for version tokens that flow into filenames or subprocess args.
# Covers Mojang/loader version shapes: ``1.20.1``, ``b1.7.3``, ``21.1.228``,
# ``54.1.16``, ``1.21.4-rc1`` — alphanumerics + ``. _ - +`` — and rejects
# path separators, whitespace, shell metacharacters, and ``..``-only tokens.
# Modelled on ``ModrinthClient._FILENAME_RE`` (the established pattern for
# the same kind of trust-boundary check on user-influenced strings).
LOADER_VERSION_RE = re.compile(r"^[A-Za-z0-9._+\-]{1,128}$")


def validate_version_token(value: str, *, field_name: str) -> str:
    """Reject version strings that could escape filename / subprocess contexts.

    ``mc_version`` arrives from user JSON (POST /api/servers); ``build`` and
    ``loader_version`` arrive from third-party promotions / Maven payloads —
    all three are externally controlled and must be whitelisted before they
    land in a path component or a subprocess argument.

    The all-dots case (``.``, ``..``, ``...``) is explicitly rejected on top
    of the regex: a dots-only token matches the alphanumeric-and-dots
    allowlist but resolves to a parent / current dir when used as a path
    segment (e.g. NeoForge's ``libraries/.../<loader_version>/...``).

    Returns the validated string. Raises ``ValueError`` on rejection so the
    install route surfaces a clear failure rather than continuing into a
    poisoned path.
    """
    if (
        not isinstance(value, str)
        or not LOADER_VERSION_RE.match(value)
        or value.strip(".") == ""
    ):
        raise ValueError(
            f"Invalid {field_name} {value!r}: "
            f"must match {LOADER_VERSION_RE.pattern} "
            f"and must not be a dots-only segment"
        )
    return value


class HashVerifyError(Exception):
    """Raised when a downloaded file's hash does not match the expected value.

    Distinct from ``requests.RequestException`` so callers can branch on the
    integrity-failure path (delete + abort install) versus a transient network
    error (retryable, B12).
    """


def _is_retryable_status(status: int) -> bool:
    """Return True for HTTP statuses worth retrying on an idempotent GET.

    5xx (server-side hiccups), 408 (request timeout), and 429 (rate-limit) are
    the conventional "retry with backoff" set. 4xx-other (400/401/403/404)
    indicates a caller-side problem that retrying cannot fix and must surface
    immediately so the install route reports a clear failure.
    """
    return status in (408, 429) or 500 <= status < 600


def request_with_retry(
    request_callable: Callable[[], T],
    *,
    retries: int = 3,
    initial_backoff: float = 0.5,
    backoff_factor: float = 2.0,
    max_backoff: float = 8.0,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
) -> T:
    """Run ``request_callable`` with exponential backoff for transient errors.

    Wrap the network-side work — typically a ``session.get(...)`` plus
    ``raise_for_status()`` and JSON / SHA1 parsing — in a closure and pass it
    in. The closure is re-invoked on retry, so any per-attempt setup (a fresh
    response, a fresh stream) is correctly redone.

    Retries on:
        * ``requests.ConnectionError`` and ``requests.Timeout`` — transient
          network-side conditions (DNS hiccup, TCP reset, idle-socket timeout).
        * ``requests.HTTPError`` if ``response.status_code`` is retryable per
          :func:`_is_retryable_status` (5xx + 408 + 429).

    Does NOT retry:
        * 4xx-other (400/401/403/404) — caller-side problem, not transient.
        * :class:`HashVerifyError` — a cryptographic mismatch is never
          transient. Retrying after a hash mismatch would offer a
          malicious / corrupted upstream another shot at slipping bad bytes
          past the gate.
        * ``ValueError`` / ``OSError`` / any other non-listed exception — only
          the explicit ``requests.*`` whitelist is retried.

    ``retries`` is the count of *additional* attempts after the first; the
    callable is invoked at most ``retries + 1`` times. Default 3 retries
    matches the common "fast initial + three backed-off retries" pattern at
    Maven / Modrinth / piston-meta.

    ``on_retry(attempt, exception)`` is invoked for each retry (``attempt`` is
    1-indexed). Typically forwards to ``logger.warning`` for visibility.
    Exceptions raised by ``on_retry`` itself are swallowed (parity with the
    ``_report`` / ``run_subprocess_streaming`` callback contracts) so a
    misbehaving logger never aborts an in-flight install.

    On exhaustion the last raised exception propagates unchanged.
    """
    attempt = 0
    backoff = initial_backoff
    last_exc: BaseException | None = None
    while True:
        try:
            return request_callable()
        except requests.HTTPError as exc:
            response = exc.response
            if response is None or not _is_retryable_status(response.status_code):
                raise
            if attempt >= retries:
                raise
            last_exc = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= retries:
                raise
            last_exc = exc
        attempt += 1
        # last_exc is provably non-None here — each except-arm sets it before
        # reaching this point. The assert documents that for strict type
        # checkers and short-circuits if the invariant is ever broken.
        assert last_exc is not None
        if on_retry is not None:
            try:
                on_retry(attempt, last_exc)
            except Exception:
                pass
        time.sleep(min(backoff, max_backoff))
        backoff *= backoff_factor


class SubprocessTimeout(Exception):
    """Raised by :func:`run_subprocess_streaming` after a force-kill on timeout.

    The helper kills the child, drains its pipes, and joins the reader threads
    before raising — a cleaner contract than ``subprocess.TimeoutExpired``,
    which leaves the child running and pipes attached on some platforms (the
    NeoForge bug B12a addresses).
    """


def run_subprocess_streaming(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    on_line: Optional[Callable[[str], None]] = None,
    on_stderr_line: Optional[Callable[[str], None]] = None,
    poll_interval: float = 0.1,
    **subprocess_kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run a subprocess streaming stdout/stderr line-by-line with a hard timeout.

    Replacement for ``subprocess.run(..., capture_output=True, timeout=...)``
    at the loader-installer call sites where:

    * Stdout/stderr can be very large (verbose Java-8 Forge installer logs hit
      tens of MB). ``capture_output=True`` buffers the lot in RAM; this helper
      streams via reader threads and forwards each line to ``on_line`` so the
      user can watch progress live (typically wired to ``logger.info``).
    * Wall-clock-timeout enforcement must guarantee the child is killed and
      its pipes drained — ``subprocess.run``'s ``TimeoutExpired`` path is
      not reliable across platforms (the underlying ``Popen.communicate``
      returns but the child may persist). This helper does its own poll loop
      and on timeout calls ``proc.kill()`` + ``proc.wait()`` + drains the
      reader threads before raising :class:`SubprocessTimeout`.

    ``on_line`` defaults to ``None`` (drop). ``on_stderr_line`` defaults to
    ``on_line`` so callers wanting a single combined logger only pass one
    callback. Callback exceptions are swallowed (parity with ``_report``):
    a misbehaving logger never crashes the install.

    Returns a :class:`subprocess.CompletedProcess` whose ``stdout`` / ``stderr``
    are the joined captured-line strings (newline-delimited, trailing newline
    preserved on the last line if the child emitted one). Existing call sites
    that previously inspected ``returncode`` and the last stderr line still
    work without changes.

    Raises:
        SubprocessTimeout: ``timeout`` elapsed before the child exited.
        OSError: child could not be spawned (e.g. ``java`` not on PATH).
    """
    if on_stderr_line is None:
        on_stderr_line = on_line

    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered text mode
        **subprocess_kwargs,
    )

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    def _pump(pipe, sink: List[str], cb: Optional[Callable[[str], None]]) -> None:
        try:
            for raw_line in iter(pipe.readline, ""):
                # Strip the trailing newline from the callback view but
                # retain the original (with newline) in the joined buffer
                # so existing splitlines()-based inspection at the callsite
                # is unchanged.
                sink.append(raw_line)
                if cb is not None:
                    line = raw_line.rstrip("\r\n")
                    try:
                        cb(line)
                    except Exception:
                        # Swallow per the _report contract: a misbehaving
                        # logger / observer must never abort an install.
                        pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    stdout_thread = threading.Thread(
        target=_pump, args=(proc.stdout, stdout_lines, on_line), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_pump, args=(proc.stderr, stderr_lines, on_stderr_line), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    deadline: Optional[float] = (
        time.monotonic() + timeout if timeout is not None else None
    )
    timed_out = False

    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(poll_interval)
    except BaseException:
        # SIGINT / KeyboardInterrupt mid-poll: don't leak the child.
        try:
            proc.kill()
        finally:
            proc.wait()
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        raise

    if timed_out:
        try:
            proc.kill()
        finally:
            # Wait for the kill to take effect and reader threads to drain
            # — do NOT raise without joining or we leave a zombie.
            proc.wait()
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        raise SubprocessTimeout(
            f"Subprocess {args[0]!r} exceeded timeout of {timeout}s "
            f"and was terminated."
        )

    # Normal exit: just join readers so the buffers are complete.
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


def download_with_hash_verify(
    url: str,
    target: Path,
    *,
    sha1: Optional[str] = None,
    sha512: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 60,
    chunk_size: int = _DOWNLOAD_CHUNK_SIZE,
    progress_callback: Optional["Callable[[int, int], None]"] = None,
    retries: int = 0,
) -> None:
    """Download ``url`` to ``target`` and verify the body hash.

    Lazy-init: only the requested hash algorithms run. Both ``sha1`` and
    ``sha512`` are optional; passing ``None`` for both downloads without an
    integrity check (the helper still streams + cleans up on network/OSError
    errors, which is why Loader sites without an upstream-published hash —
    e.g. Fabric Meta's ``/server/jar`` endpoint — still go through here).

    Clean-slate-on-failure (B12a contract): on ANY failure path — network
    error, OSError mid-stream, hash mismatch, or final ``os.replace`` failure
    — both the sibling ``.tmp`` AND any pre-existing ``target`` are unlinked
    before the original exception is re-raised. The next install pass that
    file-existence-checks ``target`` will therefore correctly re-download
    instead of treating a stale-from-prior-run JAR as complete. Hash mismatch
    raises :class:`HashVerifyError`; network/OS errors re-raise the original.

    ``progress_callback`` (optional) is invoked as ``(bytes_done, bytes_total)``
    after each written chunk. ``bytes_total`` is taken from the ``Content-Length``
    header (0 if absent). All exceptions raised by the callback are swallowed
    so a misbehaving observer never aborts an in-flight install.

    Atomic-write invariant (B12a): bytes are streamed to a sibling ``.tmp``
    file and ``os.replace``'d into ``target`` only after the hash gate passes.
    A network mid-stream failure or hash mismatch leaves ``target`` absent —
    no partial / corrupt JAR can be observed by a subsequent install pass.

    ``retries`` (B12b): when > 0, the entire download attempt (including the
    HTTP request, stream, and hash check) is wrapped in
    :func:`request_with_retry` so transient network errors (5xx / 408 / 429 /
    ConnectionError / Timeout) are retried with exponential backoff. A
    :class:`HashVerifyError` is NEVER retried (cryptographic mismatch is by
    definition non-transient). Default ``0`` keeps the legacy single-attempt
    contract for callers that have not opted in.

    Note: the unlink-on-failure semantics mean any pre-existing file at
    ``target`` is removed when a network or OS error aborts the download.
    Do not pass a ``target`` path that aliases a file you want preserved
    across a partial-download failure — atomicity of pre-existing data is
    the caller's responsibility.
    """

    def _attempt() -> None:
        sha1_hasher = hashlib.sha1() if sha1 else None
        sha512_hasher = hashlib.sha512() if sha512 else None

        nonlocal_target = Path(target)
        nonlocal_target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = nonlocal_target.with_suffix(nonlocal_target.suffix + ".tmp")

        http = session if session is not None else requests
        bytes_done = 0

        try:
            with http.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                bytes_total = int(response.headers.get("Content-Length", 0))
                with open(tmp_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        if sha1_hasher is not None:
                            sha1_hasher.update(chunk)
                        if sha512_hasher is not None:
                            sha512_hasher.update(chunk)
                        bytes_done += len(chunk)
                        if progress_callback is not None:
                            try:
                                progress_callback(bytes_done, bytes_total)
                            except Exception:
                                pass
        except (requests.RequestException, OSError):
            tmp_path.unlink(missing_ok=True)
            # Pre-existing partial ``target`` from an earlier failed run is
            # also cleaned up — the contract is that on any failure path the
            # caller observes a clean slate at ``target``.
            nonlocal_target.unlink(missing_ok=True)
            raise

        # Verify after the file is fully written. SHA-512 first because it's
        # the strictly stronger guarantee — if both are supplied we want the
        # strong check to gate even if SHA-1 happens to collide with attacker
        # input.
        if sha512_hasher is not None and sha512:
            actual = sha512_hasher.hexdigest().lower()
            if actual != sha512.lower():
                tmp_path.unlink(missing_ok=True)
                nonlocal_target.unlink(missing_ok=True)
                raise HashVerifyError(
                    f"SHA512 mismatch for {url}: expected {sha512}, got {actual}"
                )
        if sha1_hasher is not None and sha1:
            actual = sha1_hasher.hexdigest().lower()
            if actual != sha1.lower():
                tmp_path.unlink(missing_ok=True)
                nonlocal_target.unlink(missing_ok=True)
                raise HashVerifyError(
                    f"SHA1 mismatch for {url}: expected {sha1}, got {actual}"
                )

        # No-hash path (e.g. Fabric Meta's server JAR endpoint has no upstream
        # hash): fall back to Content-Length size-check as best-effort tamper
        # detection. Chunked encoding (Content-Length absent → bytes_total=0)
        # is logged as a known limitation; truncation in that case stays
        # undetectable until the JAR fails to boot.
        if sha1 is None and sha512 is None:
            if bytes_total > 0 and bytes_done != bytes_total:
                tmp_path.unlink(missing_ok=True)
                nonlocal_target.unlink(missing_ok=True)
                raise HashVerifyError(
                    f"Size mismatch for {url}: "
                    f"Content-Length={bytes_total} but wrote {bytes_done} bytes"
                )
            if bytes_total == 0:
                logger.warning(
                    "Downloaded %s without Content-Length (chunked encoding) "
                    "and no upstream hash — body size cannot be verified.",
                    url,
                )

        # Hash gate cleared (or hashing was disabled): atomically promote the
        # ``.tmp`` to the final ``target``. ``os.replace`` is atomic on the
        # same filesystem on POSIX and Windows alike — partial-file races
        # between a crashing download and the next install pass are
        # eliminated.
        try:
            os.replace(tmp_path, nonlocal_target)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise

    if retries > 0:
        request_with_retry(_attempt, retries=retries)
    else:
        _attempt()


class InstallStatus(Enum):
    """Installation status enum."""
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class LaunchSpec:
    """Normalized launch specification produced by an installer.

    Supported ``type`` values:
        - ``"jar"`` — boot via ``-jar <jar>``. Use ``jar`` field.
        - ``"args_file"`` — boot via ``@<args_file>`` (a Java argument
          file produced by a third-party installer, e.g. NeoForge).
          Use ``args_file`` field.
    """
    type: str
    jar: Optional[str] = None
    jvm_args: List[str] = field(default_factory=list)
    program_args: List[str] = field(default_factory=list)
    args_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "jar": self.jar,
            "jvm_args": list(self.jvm_args),
            "program_args": list(self.program_args),
            "args_file": self.args_file,
        }


@dataclass
class InstallResult:
    """Result of an installation attempt."""
    success: bool
    status: InstallStatus
    message: str
    server_jar: Optional[Path] = None
    details: Optional[Dict[str, Any]] = None
    launch: Optional[LaunchSpec] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
            "server_jar": str(self.server_jar) if self.server_jar else None,
            "details": self.details,
            "launch": self.launch.to_dict() if self.launch else None,
        }


class InstallerBase(ABC):
    """Abstract base class for Minecraft server installers."""

    @staticmethod
    def _canonicalize_mc_version(v: str) -> str:
        """Strip trailing '.0' patch from a Minecraft version string.

        Mojang's release naming uses bare 'x.y' for x.y.0 releases — Modrinth
        and other downstream consumers tag with that bare form. Loaders whose
        own APIs return the explicit 'x.y.0' form (notably NeoForge) must run
        their MC version strings through this helper before returning them
        from get_minecraft_versions(), so all loaders surface the same
        canonical form.

        1.21.0 → 1.21
        1.20.1 → 1.20.1   (unchanged)
        1.21   → 1.21     (unchanged)
        a1.2.0 → a1.2     (alpha versions also normalized)

        Two-part versions (1.21) are returned unchanged. Versions ending in
        something else (e.g. snapshots like '26.2-snapshot-6') are returned
        unchanged.
        """
        if not isinstance(v, str):
            return v
        if v.endswith(".0") and v.count(".") == 2:
            return v[:-2]
        return v

    def __init__(self, install_path: Path):
        """Initialize installer with target path.

        Args:
            install_path: Directory where server will be installed
        """
        self.install_path = Path(install_path)
        self.java_exec: Optional[str] = None

    @property
    @abstractmethod
    def loader_name(self) -> str:
        """Return the name of the mod loader (e.g., 'fabric', 'forge')."""
        pass

    @property
    def requires_java_for_install(self) -> bool:
        """Whether this installer needs a usable Java to run.

        Most installers download a pre-built JAR and don't invoke Java
        themselves; the install completes regardless of Java availability,
        and Java is only needed at server-start time. Loaders whose
        installer is itself a Java process (NeoForge, Forge) override
        this to ``True`` so the install route can short-circuit with a
        ``java_missing``/``java_too_old`` response before invoking
        ``install_with_config``.
        """
        return False

    def set_java_exec(self, path: Optional[str]) -> None:
        """Hand over the resolved Java executable path.

        Used by the install route for installers that invoke Java
        themselves — e.g. NeoForge runs ``java -jar <installer>
        --installServer`` as a subprocess and must use the same JVM
        that the runtime path resolves (managed Java install or
        explicit ``javaPath`` override on the server record).

        Default implementation simply records the path on
        ``self.java_exec``. Loaders that don't invoke Java during
        install ignore this attribute.
        """
        self.java_exec = path

    def _report(
        self,
        callback: Optional["Callable[[str, Dict[str, Any]], None]"],
        phase: str,
        **detail: Any,
    ) -> None:
        """Emit a progress event to the callback, swallowing all exceptions.

        Progress reporting MUST never crash the install. A misbehaving
        callback that raises (e.g. because the calling thread shut down
        the progress store) is silently ignored.

        ``detail`` becomes the second arg of the callback as a dict —
        bytes_done/bytes_total for download phases, error for ``failed``,
        empty for phase-only emissions.
        """
        if callback is None:
            return
        try:
            callback(phase, dict(detail))
        except Exception:
            pass

    @abstractmethod
    def get_available_versions(self, mc_version: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get loader-native version metadata for ``mc_version``.

        Shape is loader-specific — the frontend treats this payload opaquely
        per loader. Loaders that do not expose a separate loader version
        (e.g. Vanilla) must return ``[]``.
        """
        pass

    @abstractmethod
    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Get supported Minecraft versions in normalized form.

        Returns:
            List of dicts with shape:
                ``{"version": str, "stable": bool, "type": Optional[str]}``

            ``type`` is loader-native (e.g. "release" / "snapshot" for
            Vanilla, may be omitted by loaders without that distinction).
            ``stable`` is the only field every consumer can rely on.
        """
        pass

    @abstractmethod
    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> InstallResult:
        """Install the server.

        Args:
            mc_version: Minecraft version to install
            loader_version: Optional specific loader version (uses latest if None)
            progress_callback: Optional ``(phase, detail_dict)`` callback for
                streaming install progress to a per-server-id store.
                ``None`` ⇒ silent install (existing call sites keep working).

        Returns:
            InstallResult with success status and details
        """
        pass

    def _ensure_install_dir(self) -> None:
        """Create installation directory if it doesn't exist.

        Uses 0o775 so that both the service user (owner) and members
        of its group can read/write — required for the Java process
        and for admin users who need to manage servers manually.
        """
        self.install_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.install_path, DIR_PERMISSIONS)
        except OSError:
            pass

    def _resolve_within_install_path(self, *parts: str) -> Path:
        """Build a path under ``install_path`` with traversal-rejection.

        Each segment in ``parts`` is appended; the resolved final path must
        be a descendant of ``install_path.resolve()`` or ``ValueError`` is
        raised. Used at every loader filename / args_file / launcher-jar
        construction site so a poisoned ``mc_version`` / ``build`` /
        ``loader_version`` cannot escape the per-server install directory.

        Defence-in-depth complement to ``validate_version_token``: the
        whitelist regex blocks the obvious vectors (``../``, NUL bytes,
        spaces) at the input boundary; this helper catches anything that
        slips past — symlink lookups, absolute-path segments, future
        regex weaknesses.
        """
        candidate = (self.install_path / Path(*parts)).resolve()
        try:
            candidate.relative_to(self.install_path.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Path escapes install_path: {parts!r}"
            ) from exc
        return candidate

    def _write_eula(self, accepted: bool = True) -> Path:
        """Write eula.txt file.
        
        Args:
            accepted: Whether EULA is accepted
            
        Returns:
            Path to eula.txt
        """
        eula_path = self.install_path / "eula.txt"
        eula_path.write_text(f"eula={'true' if accepted else 'false'}\n")
        return eula_path

    def _write_server_properties(self, properties: Dict[str, Any]) -> Path:
        """Write server.properties file.
        
        Args:
            properties: Dictionary of server properties
            
        Returns:
            Path to server.properties
        """
        props_path = self.install_path / "server.properties"
        
        lines = ["# Minecraft Server Properties", "# Generated by Fabricator"]
        for key, value in properties.items():
            # Convert Python types to properties format
            if isinstance(value, bool):
                value = str(value).lower()
            lines.append(f"{key}={value}")
        
        props_path.write_text("\n".join(lines) + "\n")
        return props_path

    def generate_server_properties(self, server_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate server.properties from server configuration.
        
        Args:
            server_config: Server configuration from storage
            
        Returns:
            Dictionary of server.properties values
        """
        level_type_value = server_config.get("levelType", "default") or "default"
        if ":" not in level_type_value:
            level_type_value = f"minecraft:{level_type_value}"

        return {
            "server-port": server_config.get("port", 25565),
            "server-ip": server_config.get("serverIp", ""),
            "motd": server_config.get("motd", "A Minecraft Server"),
            "bug-report-link": server_config.get("bugReportLink", ""),
            "max-players": server_config.get("maxPlayers", 20),
            "difficulty": server_config.get("difficulty", "normal"),
            "gamemode": server_config.get("gamemode", "survival"),
            "force-gamemode": server_config.get("forceGamemode", False),
            "hardcore": server_config.get("hardcore", False),
            "allow-flight": server_config.get("allowFlight", False),
            "pvp": server_config.get("pvp", True),
            "spawn-protection": server_config.get("spawnProtection", 16),
            "function-permission-level": server_config.get("functionPermissionLevel", 2),
            "op-permission-level": server_config.get("opPermissionLevel", 4),
            "player-idle-timeout": server_config.get("playerIdleTimeout", 0),
            "pause-when-empty-seconds": server_config.get("pauseWhenEmptySeconds", 60),
            "view-distance": server_config.get("viewDistance", 10),
            "simulation-distance": server_config.get("simulationDistance", 10),
            "level-name": server_config.get("levelName", "world"),
            "level-type": level_type_value,
            "level-seed": server_config.get("seed", ""),
            "generator-settings": server_config.get("generatorSettings", ""),
            "max-world-size": server_config.get("maxWorldSize", 29_999_984),
            "generate-structures": server_config.get("generateStructures", True),
            "spawn-animals": server_config.get("spawnAnimals", True),
            "spawn-monsters": server_config.get("spawnMonsters", True),
            "spawn-npcs": server_config.get("spawnNpcs", True),
            "entity-broadcast-range-percentage": server_config.get("entityBroadcastRangePercentage", 100),
            "max-chained-neighbor-updates": server_config.get("maxChainedNeighborUpdates", 1_000_000),
            "max-tick-time": server_config.get("maxTickTime", 60_000),
            "network-compression-threshold": server_config.get("networkCompressionThreshold", 256),
            "region-file-compression": server_config.get("regionFileCompression", "deflate"),
            "sync-chunk-writes": server_config.get("syncChunkWrites", True),
            "use-native-transport": server_config.get("useNativeTransport", True),
            "online-mode": server_config.get("onlineMode", True),
            "enforce-secure-profile": server_config.get("enforceSecureProfile", True),
            "hide-online-players": server_config.get("hideOnlinePlayers", False),
            "prevent-proxy-connections": server_config.get("preventProxyConnections", False),
            "log-ips": server_config.get("logIps", True),
            "accepts-transfers": server_config.get("acceptsTransfers", False),
            "enable-status": server_config.get("enableStatus", True),
            "status-heartbeat-interval": server_config.get("statusHeartbeatInterval", 0),
            "white-list": server_config.get("whitelist", False),
            "enforce-whitelist": server_config.get("enforceWhitelist", False),
            "enable-command-block": server_config.get("commandBlocks", True),
            "broadcast-console-to-ops": server_config.get("broadcastConsoleToOps", True),
            "broadcast-rcon-to-ops": server_config.get("broadcastRconToOps", True),
            "enable-code-of-conduct": server_config.get("enableCodeOfConduct", False),
            "enable-jmx-monitoring": server_config.get("enableJmxMonitoring", False),
            "enable-query": server_config.get("enableQuery", False),
            "query.port": server_config.get("queryPort", server_config.get("port", 25565)),
            "enable-rcon": server_config.get("enableRcon", False),
            "rcon.port": server_config.get("rconPort", 25575),
            "rcon.password": server_config.get("rconPassword", ""),
            "rate-limit": server_config.get("rateLimit", 0),
            "resource-pack": server_config.get("resourcePack", ""),
            "resource-pack-sha1": server_config.get("resourcePackSha1", ""),
            "resource-pack-prompt": server_config.get("resourcePackPrompt", ""),
            "resource-pack-id": server_config.get("resourcePackId", ""),
            "require-resource-pack": server_config.get("requireResourcePack", False),
            "initial-enabled-packs": server_config.get("initialEnabledPacks", "vanilla"),
            "initial-disabled-packs": server_config.get("initialDisabledPacks", ""),
            "text-filtering-config": server_config.get("textFilteringConfig", ""),
            "text-filtering-version": server_config.get("textFilteringVersion", 0),
        }
