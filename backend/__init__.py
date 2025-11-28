"""Backend package initialization."""

from backend.core import create_app, get_config  # noqa: F401

__all__ = [
	'create_app',
	'get_config',
]
