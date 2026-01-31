#!/usr/bin/env python3
"""
LeuitCSS v1.0.0 - Standalone FTP Ingestion Server
Write-only FTP server for ZTE OLT backup file ingestion

This runs as a separate systemd service with proper privileges for port 21.
"""

import os
import sys
import logging
import signal
from pathlib import Path
from datetime import datetime

# Add app directory to path
sys.path.insert(0, '/opt/leuitcss')

from dotenv import load_dotenv

# Load environment
load_dotenv('/etc/leuitcss/leuitcss.env')

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    print("ERROR: pyftpdlib not installed. Run: pip install pyftpdlib")
    sys.exit(1)

# Configuration
FTP_PORT = int(os.environ.get('LEUITCSS_FTP_PORT', '21'))
FTP_USER = os.environ.get('LEUITCSS_FTP_USER', 'leuitcss')
FTP_PASSWORD = os.environ.get('LEUITCSS_FTP_PASSWORD', '')
FTP_ROOT = os.environ.get('LEUITCSS_FTP_ROOT', '/var/lib/leuitcss/ftp-ingestion')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/leuitcss/ftp-server.log')
    ]
)
logger = logging.getLogger('leuitcss.ftp')


class LeuitFTPHandler(FTPHandler):
    """Custom FTP handler for ZTE backup ingestion"""
    
    def on_file_received(self, file):
        """Called when a file upload is complete"""
        logger.info(f"File received: {file}")
        
        # Only process startrun.dat files
        if not file.endswith('startrun.dat'):
            logger.warning(f"Ignoring non-startrun.dat file: {file}")
            return
        
        logger.info(f"ZTE config file received: {file}")
    
    def on_incomplete_file_received(self, file):
        """Called when upload is incomplete"""
        logger.warning(f"Incomplete file upload: {file}")
        try:
            os.remove(file)
        except:
            pass


def setup_directories():
    """Create FTP directory structure"""
    ftp_path = Path(FTP_ROOT)
    zte_path = ftp_path / 'zte'
    
    ftp_path.mkdir(parents=True, exist_ok=True)
    zte_path.mkdir(exist_ok=True)
    
    # Set permissions - allow leuitcss user to write
    os.chmod(ftp_path, 0o755)
    os.chmod(zte_path, 0o755)
    
    logger.info(f"FTP directories ready: {ftp_path}")


def create_status_file(status: str, port: int = FTP_PORT):
    """Create status file for main app to read"""
    status_file = Path('/var/lib/leuitcss/ftp-server.status')
    try:
        with open(status_file, 'w') as f:
            f.write(f"status={status}\n")
            f.write(f"port={port}\n")
            f.write(f"timestamp={datetime.now().isoformat()}\n")
            f.write(f"pid={os.getpid()}\n")
        os.chmod(status_file, 0o644)
    except Exception as e:
        logger.error(f"Failed to create status file: {e}")


def remove_status_file():
    """Remove status file on shutdown"""
    status_file = Path('/var/lib/leuitcss/ftp-server.status')
    try:
        if status_file.exists():
            status_file.unlink()
    except:
        pass


def main():
    """Main entry point"""
    if not FTP_PASSWORD:
        logger.error("FTP password not configured. Set LEUITCSS_FTP_PASSWORD in .env")
        sys.exit(1)
    
    logger.info(f"Starting LeuitCSS FTP Ingestion Server on port {FTP_PORT}")
    
    # Setup directories
    setup_directories()
    
    # Create authorizer with write-only permissions
    authorizer = DummyAuthorizer()
    # Permissions: e=chdir, m=mkdir, w=write - NO read, list, delete
    authorizer.add_user(FTP_USER, FTP_PASSWORD, FTP_ROOT, perm='emw')
    
    # Create handler
    handler = LeuitFTPHandler
    handler.authorizer = authorizer
    handler.passive_ports = range(60000, 60100)
    handler.banner = "LeuitCSS FTP Ingestion Server - ZTE OLT Only"
    
    # Create and start server
    server = FTPServer(('0.0.0.0', FTP_PORT), handler)
    server.max_cons = 10
    server.max_cons_per_ip = 3
    
    # Signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, stopping FTP server...")
        remove_status_file()
        server.close_all()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create status file
    create_status_file('running', FTP_PORT)
    
    logger.info(f"FTP Server started successfully on port {FTP_PORT}")
    logger.info(f"FTP Root: {FTP_ROOT}")
    logger.info(f"FTP User: {FTP_USER}")
    
    try:
        server.serve_forever()
    except Exception as e:
        logger.error(f"FTP Server error: {e}")
        create_status_file('error', FTP_PORT)
        sys.exit(1)
    finally:
        remove_status_file()


if __name__ == '__main__':
    main()
