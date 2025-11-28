"""Entry point for the Fabricator application."""
from backend.core import create_app, get_config


if __name__ == '__main__':
    app = create_app()
    config = get_config()
    
    app.run(
        debug=config.DEBUG,
        host=config.HOST,
        port=config.PORT
    )
