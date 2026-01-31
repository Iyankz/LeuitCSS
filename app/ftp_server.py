"""
LeuitCSS v1.0.0 - FTP Ingestion Server
Write-only FTP server for ZTE OLT backup file ingestion

This module provides:
- Write-only FTP access (no read, no delete, no overwrite)
- Single global credential for all ZTE devices
- Subfolder-based device mapping
- Integration with LeuitCSS storage system

FTP Structure:
  /ftp-root/zte/
    <device_name>/
      startrun.dat
      
The device name folder maps to device.name in LeuitCSS database.
"""

import os
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    FTP_AVAILABLE = True
except ImportError:
    FTP_AVAILABLE = False

from config import get_config

logger = logging.getLogger('leuitcss.ftp')


class LeuitFTPAuthorizer(DummyAuthorizer):
    """
    Custom FTP authorizer with write-only permissions.
    Only allows: upload (write), create directory
    Denies: read, list, delete, rename
    """
    
    def __init__(self):
        super().__init__()
        self.config = get_config()
    
    def add_leuit_user(self, username: str, password: str, homedir: str):
        """Add FTP user with write-only permissions"""
        # Permissions:
        # e = change directory (needed for navigation)
        # m = create directory
        # w = write/upload files
        # No: r (read), l (list), d (delete), f (rename), a (append)
        self.add_user(username, password, homedir, perm='emw')


class LeuitFTPHandler(FTPHandler):
    """
    Custom FTP handler for ZTE backup ingestion.
    
    Features:
    - Validates upload is startrun.dat
    - Maps subfolder to device name
    - Stores file using LeuitCSS storage system
    - Creates backup history record
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = get_config()
    
    def on_file_received(self, file: str):
        """Called when a file upload is complete"""
        logger.info(f"FTP file received: {file}")
        
        try:
            file_path = Path(file)
            
            # Validate filename
            if file_path.name.lower() != 'startrun.dat':
                logger.warning(f"FTP rejected non-startrun.dat file: {file_path.name}")
                # File already written, we can't prevent it with pyftpdlib
                # But we don't process it
                return
            
            # Extract device name from path
            # Expected: /ftp-root/zte/<device_name>/startrun.dat
            parts = file_path.parts
            if len(parts) < 2:
                logger.warning(f"FTP file path too short to extract device: {file}")
                return
            
            device_name = parts[-2]  # Parent folder is device name
            
            # Process the backup
            self._process_zte_backup(device_name, file_path)
            
        except Exception as e:
            logger.error(f"FTP file processing error: {e}")
    
    def _process_zte_backup(self, device_name: str, file_path: Path):
        """Process received ZTE backup file"""
        from app.models import Device, BackupHistory
        from app.storage import get_storage
        from app import create_app
        
        app = create_app()
        with app.app_context():
            from sqlalchemy.orm import Session
            from app.models import get_engine
            
            engine = get_engine()
            with Session(engine) as session:
                # Find device by name
                device = session.query(Device).filter(
                    Device.name == device_name,
                    Device.vendor == 'zte'
                ).first()
                
                if not device:
                    logger.warning(f"FTP: No ZTE device found with name: {device_name}")
                    return
                
                logger.info(f"FTP: Processing backup for device: {device.name} (ID: {device.id})")
                
                # Read file content
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                except Exception as e:
                    logger.error(f"FTP: Failed to read file: {e}")
                    return
                
                # Create backup history record
                history = BackupHistory(
                    device_id=device.id,
                    device_name=device.name,
                    vendor=device.vendor,
                    status='running',
                    started_at=datetime.now(),
                    triggered_by='ftp_ingestion'
                )
                session.add(history)
                session.flush()
                
                # Store using LeuitCSS storage
                storage = get_storage()
                try:
                    stored_path = storage.store_backup(
                        device_id=device.id,
                        vendor=device.vendor,
                        content=content.decode('utf-8', errors='replace'),
                        filename_prefix=f"zte_olt_{device.name}"
                    )
                    
                    # Update history
                    history.status = 'success'
                    history.completed_at = datetime.now()
                    history.file_path = stored_path
                    history.file_size_bytes = len(content)
                    history.execution_time_seconds = int(
                        (history.completed_at - history.started_at).total_seconds()
                    )
                    
                    # Update device
                    device.last_backup_at = datetime.now()
                    device.last_backup_status = 'success'
                    
                    logger.info(f"FTP: Backup stored successfully: {stored_path}")
                    
                except Exception as e:
                    history.status = 'failed'
                    history.completed_at = datetime.now()
                    history.error_message = str(e)
                    device.last_backup_status = 'failed'
                    logger.error(f"FTP: Failed to store backup: {e}")
                
                session.commit()
                
                # Clean up temp file
                try:
                    os.remove(file_path)
                except:
                    pass
    
    def on_incomplete_file_received(self, file: str):
        """Called when upload is incomplete"""
        logger.warning(f"FTP incomplete file upload: {file}")
        # Clean up incomplete file
        try:
            os.remove(file)
        except:
            pass


class FTPIngestionServer:
    """
    FTP Ingestion Server for ZTE OLT backups.
    
    IMPORTANT: ZTE OLT requires FTP on port 21 (cannot use custom port).
    This is a hardware limitation of ZTE OLT devices.
    
    Configuration via environment:
    - LEUITCSS_FTP_ENABLED: Enable FTP server (default: false)
    - LEUITCSS_FTP_PORT: FTP port (MUST be 21 for ZTE OLT)
    - LEUITCSS_FTP_USER: FTP username
    - LEUITCSS_FTP_PASSWORD: FTP password
    - LEUITCSS_FTP_ROOT: FTP root directory
    
    Port 21 requires CAP_NET_BIND_SERVICE capability on Python binary.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.config = get_config()
        self.server = None
        self.thread = None
        self.running = False
        
        # FTP Configuration
        self.enabled = os.environ.get('LEUITCSS_FTP_ENABLED', 'false').lower() == 'true'
        self.port = int(os.environ.get('LEUITCSS_FTP_PORT', '21'))
        self.username = os.environ.get('LEUITCSS_FTP_USER', 'leuitcss')
        self.password = os.environ.get('LEUITCSS_FTP_PASSWORD', '')
        self.ftp_root = os.environ.get(
            'LEUITCSS_FTP_ROOT', 
            '/var/lib/leuitcss/ftp-ingestion'
        )
        
        self._initialized = True
    
    def is_available(self) -> bool:
        """Check if FTP server can be started"""
        if not FTP_AVAILABLE:
            logger.warning("pyftpdlib not installed, FTP server unavailable")
            return False
        if not self.enabled:
            return False
        if not self.password:
            logger.warning("FTP password not configured")
            return False
        return True
    
    def setup_directories(self):
        """Create FTP directory structure"""
        ftp_path = Path(self.ftp_root)
        zte_path = ftp_path / 'zte'
        
        ftp_path.mkdir(parents=True, exist_ok=True)
        zte_path.mkdir(exist_ok=True)
        
        # Set permissions
        os.chmod(ftp_path, 0o750)
        os.chmod(zte_path, 0o750)
        
        logger.info(f"FTP directories created: {ftp_path}")
    
    def start(self):
        """Start FTP server in background thread"""
        if not self.is_available():
            logger.info("FTP server not enabled or not available")
            return False
        
        if self.running:
            logger.warning("FTP server already running")
            return True
        
        try:
            self.setup_directories()
            
            # Create authorizer
            authorizer = LeuitFTPAuthorizer()
            authorizer.add_leuit_user(
                self.username,
                self.password,
                self.ftp_root
            )
            
            # Create handler
            handler = LeuitFTPHandler
            handler.authorizer = authorizer
            handler.passive_ports = range(60000, 60100)
            
            # Create server
            self.server = FTPServer(('0.0.0.0', self.port), handler)
            self.server.max_cons = 10
            self.server.max_cons_per_ip = 3
            
            # Start in thread
            self.thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name='FTPIngestionServer'
            )
            self.thread.start()
            self.running = True
            
            logger.info(f"FTP Ingestion Server started on port {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start FTP server: {e}")
            return False
    
    def _run_server(self):
        """Run FTP server (called in thread)"""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"FTP server error: {e}")
            self.running = False
    
    def stop(self):
        """Stop FTP server"""
        if self.server and self.running:
            try:
                self.server.close_all()
                self.running = False
                logger.info("FTP server stopped")
            except Exception as e:
                logger.error(f"Error stopping FTP server: {e}")
    
    def get_status(self) -> dict:
        """Get FTP server status"""
        return {
            'available': FTP_AVAILABLE,
            'enabled': self.enabled,
            'running': self.running,
            'port': self.port,
            'root': self.ftp_root
        }


def get_ftp_server() -> FTPIngestionServer:
    """Get FTP server singleton instance"""
    return FTPIngestionServer()
