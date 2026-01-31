"""
LeuitCSS v1.0.0 - Audit Logging Module
Dual logging to file and SQLite database

Security Rules:
- Audit log setiap login dan backup
- Logs are IMMUTABLE (append-only)
- Both file and database logging
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from flask import request, has_request_context

from config import get_config


class AuditLogger:
    """
    Audit logger that writes to both file and database.
    All logs are append-only and immutable.
    """
    
    def __init__(self, app=None, db_session=None):
        self.config = get_config()
        self.db_session = db_session
        self._file_logger = None
        self._setup_file_logger()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
    
    def set_db_session(self, db_session):
        """Set database session for DB logging"""
        self.db_session = db_session
    
    def _setup_file_logger(self):
        """Setup file-based audit logging"""
        log_path = Path(self.config.LOG_PATH)
        log_path.mkdir(parents=True, exist_ok=True)
        
        audit_log_file = log_path / self.config.AUDIT_LOG_FILE
        
        self._file_logger = logging.getLogger('leuitcss.audit')
        self._file_logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not self._file_logger.handlers:
            # Rotating file handler (10MB max, keep 10 backups)
            file_handler = RotatingFileHandler(
                audit_log_file,
                maxBytes=10*1024*1024,
                backupCount=10,
                encoding='utf-8'
            )
            
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self._file_logger.addHandler(file_handler)
    
    def _get_request_info(self):
        """Extract request information if in request context"""
        if has_request_context():
            return {
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string[:255] if request.user_agent else None
            }
        return {'ip_address': None, 'user_agent': None}
    
    def _log_to_file(self, action: str, actor_type: str, actor_id: str, 
                     resource_type: str, resource_id: str, details: dict,
                     success: bool, error_message: str):
        """Write log entry to file"""
        request_info = self._get_request_info()
        
        log_entry = {
            'action': action,
            'actor_type': actor_type,
            'actor_id': actor_id,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details,
            'success': success,
            'error_message': error_message,
            'ip_address': request_info['ip_address']
        }
        
        level = logging.INFO if success else logging.WARNING
        self._file_logger.log(level, json.dumps(log_entry, default=str))
    
    def _log_to_db(self, action: str, actor_type: str, actor_id: str,
                   resource_type: str, resource_id: str, details: dict,
                   success: bool, error_message: str):
        """Write log entry to database"""
        if not self.db_session:
            return
        
        from app.models import AuditLog
        
        request_info = self._get_request_info()
        
        audit_entry = AuditLog(
            timestamp=datetime.utcnow(),
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=json.dumps(details, default=str) if details else None,
            ip_address=request_info['ip_address'],
            user_agent=request_info['user_agent'],
            success=success,
            error_message=error_message
        )
        
        try:
            self.db_session.add(audit_entry)
            self.db_session.commit()
        except Exception as e:
            self.db_session.rollback()
            self._file_logger.error(f"Failed to write audit log to DB: {e}")
    
    def log(self, action: str, actor_type: str = 'system', actor_id: str = None,
            resource_type: str = None, resource_id: str = None, details: dict = None,
            success: bool = True, error_message: str = None):
        """
        Log an audit event to both file and database.
        
        Args:
            action: Action performed (login, logout, backup_start, device_add, etc.)
            actor_type: Type of actor (admin, system, scheduler)
            actor_id: Identifier of actor (username or 'system')
            resource_type: Type of resource affected (device, schedule, backup)
            resource_id: ID of resource affected
            details: Additional details as dict
            success: Whether action was successful
            error_message: Error message if failed
        """
        # Always log to file
        self._log_to_file(action, actor_type, actor_id, resource_type, 
                         resource_id, details, success, error_message)
        
        # Log to database if session available
        self._log_to_db(action, actor_type, actor_id, resource_type,
                       resource_id, details, success, error_message)
    
    # Convenience methods for common actions
    
    def log_login(self, username: str, success: bool = True, error_message: str = None):
        """Log admin login attempt"""
        self.log(
            action='login',
            actor_type='admin',
            actor_id=username,
            success=success,
            error_message=error_message
        )
    
    def log_logout(self, username: str):
        """Log admin logout"""
        self.log(
            action='logout',
            actor_type='admin',
            actor_id=username
        )
    
    def log_device_add(self, admin_username: str, device_id: int, device_name: str):
        """Log device addition"""
        self.log(
            action='device_add',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='device',
            resource_id=device_id,
            details={'device_name': device_name}
        )
    
    def log_device_update(self, admin_username: str, device_id: int, changes: dict):
        """Log device update"""
        self.log(
            action='device_update',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='device',
            resource_id=device_id,
            details={'changes': changes}
        )
    
    def log_device_delete(self, admin_username: str, device_id: int, device_name: str):
        """Log device deletion"""
        self.log(
            action='device_delete',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='device',
            resource_id=device_id,
            details={'device_name': device_name}
        )
    
    def log_backup_start(self, device_id: int, device_name: str, triggered_by: str = 'scheduler'):
        """Log backup start"""
        self.log(
            action='backup_start',
            actor_type=triggered_by,
            actor_id=triggered_by,
            resource_type='device',
            resource_id=device_id,
            details={'device_name': device_name}
        )
    
    def log_backup_complete(self, device_id: int, device_name: str, 
                           success: bool, error_message: str = None,
                           file_path: str = None, checksum: str = None):
        """Log backup completion"""
        details = {'device_name': device_name}
        if file_path:
            details['file_path'] = file_path
        if checksum:
            details['checksum'] = checksum
        
        self.log(
            action='backup_complete',
            actor_type='system',
            actor_id='backup_collector',
            resource_type='device',
            resource_id=device_id,
            details=details,
            success=success,
            error_message=error_message
        )
    
    def log_schedule_add(self, admin_username: str, schedule_id: int, device_id: int):
        """Log schedule addition"""
        self.log(
            action='schedule_add',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='schedule',
            resource_id=schedule_id,
            details={'device_id': device_id}
        )
    
    def log_schedule_update(self, admin_username: str, schedule_id: int, changes: dict):
        """Log schedule update"""
        self.log(
            action='schedule_update',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='schedule',
            resource_id=schedule_id,
            details={'changes': changes}
        )


# Global audit logger instance
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance"""
    return audit_logger
