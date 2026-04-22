"""Minecraft version to Java compatibility helpers."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Optional


def skip_java_enforcement() -> bool:
    """Return True when Java version checks should not block install/start.

    Set environment variable ``FABRICATOR_SKIP_JAVA_CHECK`` to ``1``, ``true``,
    ``yes``, or ``on`` for local development/testing only. Do not enable in
    production: servers may fail at runtime with the wrong JVM.
    """
    val = os.environ.get("FABRICATOR_SKIP_JAVA_CHECK", "").strip().lower()
    return val in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class JavaCompatibility:
    """Compatibility resolution output for a Minecraft version."""

    mc_version: str
    required_java: Optional[int]
    confidence: str
    reason: str
    warning: Optional[str] = None

    @property
    def enforceable(self) -> bool:
        return self.required_java is not None

    def to_dict(self) -> dict:
        return {
            "mc_version": self.mc_version,
            "required_java": self.required_java,
            "confidence": self.confidence,
            "reason": self.reason,
            "warning": self.warning,
            "enforceable": self.enforceable,
        }


def _parse_mc_version(version: str) -> tuple[int, int, int] | None:
    if not version:
        return None
    # Accept "1.21", "1.21.1", "1.21.x", "1.21-rc1", etc.
    match = re.match(r"^\s*(\d+)\.(\d+)(?:\.(\d+|x|X))?", str(version))
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch_raw = match.group(3)
    if patch_raw is None or patch_raw.lower() == "x":
        patch = 0
    else:
        patch = int(patch_raw)
    return major, minor, patch


def resolve_required_java(mc_version: str) -> JavaCompatibility:
    """Resolve Java requirement for a Minecraft version.

    Rules:
    - <= 1.16.5 -> Java 8
    - 1.17.x -> Java 16
    - 1.18 - 1.20.4 -> Java 17
    - 1.20.5 - 1.21.x -> Java 21
    - 1.26+ -> Java 25
    - 1.22.x - 1.25.x -> unknown (warn)
    """
    parsed = _parse_mc_version(mc_version)
    if not parsed:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=None,
            confidence="low",
            reason="Could not parse version format.",
            warning=(
                "Could not determine Java requirement for this Minecraft version. "
                "Starting with Java 21 is usually safe for modern releases."
            ),
        )

    major, minor, patch = parsed

    # Mojang switched to year-based versioning (e.g. 24.x, 25.x, 26.x).
    # These releases require Java 25+.
    if major >= 24:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=25,
            confidence="medium",
            reason=f"Minecraft {major}.x uses year-based versioning and requires Java 25.",
        )

    if major != 1:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=None,
            confidence="low",
            reason=f"Unsupported major version family: {major}.",
            warning=(
                "Minecraft version family is not recognized. "
                "Please verify Java requirement manually."
            ),
        )

    if minor <= 16:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=8,
            confidence="high",
            reason="Minecraft 1.16.5 and older run on Java 8.",
        )

    if minor == 17:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=16,
            confidence="high",
            reason="Minecraft 1.17.x requires Java 16.",
        )

    if 18 <= minor <= 19:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=17,
            confidence="high",
            reason="Minecraft 1.18+ through 1.19.x requires Java 17.",
        )

    if minor == 20:
        if patch >= 5:
            return JavaCompatibility(
                mc_version=mc_version,
                required_java=21,
                confidence="high",
                reason="Minecraft 1.20.5+ requires Java 21.",
            )
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=17,
            confidence="high",
            reason="Minecraft 1.20.4 and older require Java 17.",
        )

    if minor == 21:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=21,
            confidence="high",
            reason="Minecraft 1.21.x uses Java 21.",
        )

    if 22 <= minor <= 25:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=None,
            confidence="low",
            reason="Version falls in an unmapped jump range (1.22.x-1.25.x).",
            warning=(
                "Java requirement for this gap range is not mapped yet. "
                "Try Java 21 first and update if startup logs require newer Java."
            ),
        )

    if minor >= 26:
        return JavaCompatibility(
            mc_version=mc_version,
            required_java=25,
            confidence="medium",
            reason="Minecraft 1.26+ is configured to require Java 25.",
        )

    return JavaCompatibility(
        mc_version=mc_version,
        required_java=None,
        confidence="low",
        reason="No matching compatibility rule.",
        warning="Could not determine Java requirement with confidence.",
    )

