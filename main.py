"""
LeuitCSS v1.0.0 - Main Application
Active Configuration Backup System with Read-Only Access

DEFINISI PRODUK:
LeuitCSS adalah ACTIVE CONFIGURATION BACKUP SYSTEM dengan READ-ONLY ACCESS.

LeuitCSS:
- Login ke perangkat jaringan
- Menjalankan perintah BACKUP yang sudah ditentukan
- Mengambil konfigurasi perangkat
- Menyimpan hasil backup secara immutable

LeuitCSS BUKAN:
- Config Manager
- Orchestrator  
- Provisioning Tool
- Automation Engine
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

from flask import Flask, g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from app.models import Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('leuitcss')

# Global session factory
_session_factory = None


def create_app(config_class=None):
    """
    Application factory for LeuitCSS.
    """
    global _session_factory
    
    application = Flask(__name__,
                template_folder='templates',
                static_folder='static')
    
    # Load configuration
    config = config_class or get_config()
    application.config.from_object(config)
    
    # Ensure directories exist
    Path(config.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Path(config.LOG_PATH).mkdir(parents=True, exist_ok=True)
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize database
    engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        connect_args={'check_same_thread': False}  # SQLite specific
    )
    Base.metadata.create_all(engine)
    
    # Create scoped session factory
    session_factory = sessionmaker(bind=engine)
    _session_factory = scoped_session(session_factory)
    
    # Store in app config for access
    application.config['SESSION_FACTORY'] = _session_factory
    
    # Request handlers for db session
    @application.before_request
    def create_session():
        g.db_session = _session_factory()
    
    @application.teardown_request
    def remove_session(exception=None):
        session = g.pop('db_session', None)
        if session is not None:
            if exception:
                session.rollback()
            session.close()
        _session_factory.remove()
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.backup import backup_bp
    
    application.register_blueprint(auth_bp)
    application.register_blueprint(main_bp)
    application.register_blueprint(backup_bp)
    
    # Initialize audit logger
    from app.audit import get_audit_logger
    audit = get_audit_logger()
    audit.init_app(application)
    
    # Initialize scheduler
    from app.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.init_app(application)
    scheduler.set_db_session_factory(_session_factory)
    
    # Start scheduler (only in main process)
    if not application.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler.start()
    
    # Context processor for templates
    @application.context_processor
    def inject_globals():
        return {
            'app_name': config.APP_NAME,
            'app_version': config.APP_VERSION,
            'current_year': datetime.utcnow().year
        }
    
    # Error handlers
    @application.errorhandler(404)
    def not_found(error):
        from flask import render_template
        return render_template('errors/404.html'), 404
    
    @application.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        return render_template('errors/500.html'), 500
    
    logger.info(f"LeuitCSS v{config.APP_VERSION} initialized")
    
    return application


# Helper to get db_session - used by routes
def get_db_session():
    """Get current database session from Flask g object"""
    return getattr(g, 'db_session', None) or _session_factory()


# Create app instance
app = create_app()

# Proxy class for db_session access
class _DBSessionProxy:
    """Proxy to access db_session from Flask g object"""
    def query(self, *args, **kwargs):
        return get_db_session().query(*args, **kwargs)
    
    def add(self, *args, **kwargs):
        return get_db_session().add(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        return get_db_session().delete(*args, **kwargs)
    
    def commit(self):
        return get_db_session().commit()
    
    def rollback(self):
        return get_db_session().rollback()
    
    def close(self):
        return get_db_session().close()


# Export db_session proxy for routes
db_session = _DBSessionProxy()


if __name__ == '__main__':
    # Get port from environment variable
    port = int(os.environ.get('LEUITCSS_PORT', 5000))
    
    # Development server - bind to 0.0.0.0 for LAN access
    # Debug is disabled for security
    app.run(host='0.0.0.0', port=port, debug=False)
