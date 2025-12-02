"""Entrypoint for running the Fabricator backend with ``python -m``."""
from . import create_app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
