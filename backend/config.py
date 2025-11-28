"""Application configuration."""
import os


class Config:
    """Base configuration."""
    
    # Flask
    DEBUG = os.environ.get('FLASK_ENV') != 'production'
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    
    # Server Management
    SERVER_COMMAND = os.environ.get('SERVER_COMMAND')
    SERVER_DIR = os.environ.get('SERVER_DIR', 'server')
    SERVERS_ROOT = os.environ.get('SERVER_ROOT', os.path.join(os.getcwd(), 'servers'))
    
    # API
    API_VERSION = '1.0.0'
    
    # CORS
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get the appropriate configuration based on environment."""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
