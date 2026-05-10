"""Abstract base class for Minecraft server installers."""
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any

DIR_PERMISSIONS = 0o775

# Allowlist for version tokens that flow into filenames or subprocess args.
# Covers Mojang/loader version shapes: ``1.20.1``, ``b1.7.3``, ``21.1.228``,
# ``54.1.16``, ``1.21.4-rc1`` — alphanumerics + ``. _ - +`` — and rejects
# path separators, whitespace, shell metacharacters, and ``..``-only tokens.
# Modelled on ``ModrinthClient._FILENAME_RE`` (the established pattern for
# the same kind of trust-boundary check on user-influenced strings).
_LOADER_VERSION_RE = re.compile(r"^[A-Za-z0-9._+\-]+$")


def _validate_version_token(value: str, *, field_name: str) -> str:
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
        or not _LOADER_VERSION_RE.match(value)
        or value.strip(".") == ""
    ):
        raise ValueError(
            f"Invalid {field_name} {value!r}: "
            f"must match {_LOADER_VERSION_RE.pattern} "
            f"and must not be a dots-only segment"
        )
    return value


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

        Defence-in-depth complement to ``_validate_version_token``: the
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
