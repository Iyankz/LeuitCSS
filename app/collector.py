"""
LeuitCSS v1.0.0 - Backup Collector
Active Backup Collection Engine

This is the core engine that:
1. Connects to devices (READ-ONLY)
2. Executes HARDCODED backup commands
3. Collects configuration output
4. Stores to immutable storage

CRITICAL RULES:
- READ-ONLY access only
- HARDCODED commands per vendor
- Maximum 1 retry on failure
- No configuration mode
- No push/restore
"""

import time
from datetime import datetime
from typing import Dict, Optional

from config import get_config
from app.adapters import get_adapter
from app.storage import get_storage
from app.audit import get_audit_logger
from app.models import Device, BackupHistory, BackupStatus


class BackupCollector:
    """
    Active Backup Collector - Read-Only Device Access
    
    This collector performs:
    - Login to device (SSH/Telnet)
    - Execute predefined backup command
    - Collect output/file
    - Store to immutable storage
    
    NOT allowed:
    - Terminal interaktif
    - Input command dari user
    - Mode konfigurasi
    - Restore atau push config
    """
    
    def __init__(self, db_session=None):
        self.config = get_config()
        self.storage = get_storage()
        self.audit = get_audit_logger()
        self.db_session = db_session
    
    def set_db_session(self, db_session):
        """Set database session"""
        self.db_session = db_session
        self.audit.set_db_session(db_session)
    
    def _get_vendor_config(self, vendor: str) -> dict:
        """Get vendor-specific configuration (HARDCODED)"""
        return self.config.VENDOR_COMMANDS.get(vendor.lower())
    
    def _prepare_device_info(self, device: Device) -> dict:
        """Prepare device info dict for adapter"""
        return {
            'device_id': device.id,  # Needed for ZTE FTP inbox path
            'ip_address': device.ip_address,
            'port': device.port,
            'username': device.username,  # Still encrypted
            'password': device.password,  # Still encrypted
            'enable_password': device.enable_password,  # Still encrypted
            'connection_type': device.connection_type
        }
    
    def _create_backup_history(self, device: Device, triggered_by: str = 'scheduler') -> BackupHistory:
        """Create initial backup history record"""
        vendor_config = self._get_vendor_config(device.vendor)
        
        history = BackupHistory(
            device_id=device.id,
            device_name=device.name,
            device_ip=device.ip_address,
            vendor=device.vendor,
            connection_type=device.connection_type,
            backup_command=vendor_config['backup_command'],
            status=BackupStatus.RUNNING.value,
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
            retry_count=0
        )
        
        if self.db_session:
            self.db_session.add(history)
            self.db_session.commit()
        
        return history
    
    def _update_backup_history(self, history: BackupHistory, success: bool,
                               execution_time: float = None, file_path: str = None,
                               file_size: int = None, checksum: str = None,
                               error_message: str = None):
        """Update backup history with results"""
        history.completed_at = datetime.utcnow()
        history.execution_time_seconds = int(execution_time) if execution_time else None
        
        if success:
            history.status = BackupStatus.SUCCESS.value
            history.file_path = file_path
            history.file_size_bytes = file_size
            history.checksum_sha256 = checksum
        else:
            if 'timeout' in str(error_message).lower():
                history.status = BackupStatus.TIMEOUT.value
            else:
                history.status = BackupStatus.FAILED.value
            history.error_message = error_message
        
        if self.db_session:
            self.db_session.commit()
    
    def _update_device_status(self, device: Device, status: str):
        """Update device last backup status"""
        device.last_backup_status = status
        device.last_backup_at = datetime.utcnow()
        
        if self.db_session:
            self.db_session.commit()
    
    def backup_device(self, device: Device, triggered_by: str = 'scheduler',
                     retry: bool = True) -> Dict:
        """
        Execute backup for a single device.
        
        This method:
        1. Creates backup history record
        2. Connects to device (READ-ONLY)
        3. Executes HARDCODED backup command
        4. Saves output to immutable storage
        5. Updates backup history
        
        Args:
            device: Device model instance
            triggered_by: Who triggered the backup (scheduler/manual)
            retry: Whether to retry on failure (max 1 retry)
        
        Returns:
            Dict with backup result:
                - success: bool
                - history_id: backup history ID
                - file_path: path to backup file (if success)
                - checksum: SHA256 checksum (if success)
                - error: error message (if failed)
        """
        result = {
            'success': False,
            'history_id': None,
            'file_path': None,
            'checksum': None,
            'error': None,
            'device_id': device.id,
            'device_name': device.name
        }
        
        # Validate vendor
        vendor_config = self._get_vendor_config(device.vendor)
        if not vendor_config:
            result['error'] = f"Unsupported vendor: {device.vendor}"
            return result
        
        # Check connection type support
        if device.connection_type not in vendor_config['connection_types']:
            result['error'] = f"Connection type {device.connection_type} not supported for {device.vendor}"
            return result
        
        # Log backup start
        self.audit.log_backup_start(device.id, device.name, triggered_by)
        
        # Create backup history record
        history = self._create_backup_history(device, triggered_by)
        result['history_id'] = history.id
        
        # Prepare device info
        device_info = self._prepare_device_info(device)
        
        # Get vendor adapter
        try:
            adapter = get_adapter(device.vendor, device_info)
        except ValueError as e:
            result['error'] = str(e)
            self._update_backup_history(history, False, error_message=str(e))
            self._update_device_status(device, BackupStatus.FAILED.value)
            self.audit.log_backup_complete(device.id, device.name, False, str(e))
            return result
        
        # Execute backup
        backup_result = adapter.backup()
        
        if backup_result['success']:
            # Save to immutable storage
            storage_result = self.storage.save_backup(
                vendor=device.vendor,
                device_id=device.id,
                device_name=device.name,
                device_ip=device.ip_address,
                connection_type=device.connection_type,
                backup_command=vendor_config['backup_command'],
                config_output=backup_result['output'],
                output_extension=vendor_config['output_extension'],
                execution_time=backup_result['execution_time']
            )
            
            if storage_result['success']:
                result['success'] = True
                result['file_path'] = storage_result['file_path']
                result['checksum'] = storage_result['checksum']
                
                self._update_backup_history(
                    history, True,
                    execution_time=backup_result['execution_time'],
                    file_path=storage_result['file_path'],
                    file_size=storage_result['file_size'],
                    checksum=storage_result['checksum']
                )
                self._update_device_status(device, BackupStatus.SUCCESS.value)
                self.audit.log_backup_complete(
                    device.id, device.name, True,
                    file_path=storage_result['file_path'],
                    checksum=storage_result['checksum']
                )
            else:
                result['error'] = f"Storage error: {storage_result['error']}"
                self._update_backup_history(history, False, error_message=result['error'])
                self._update_device_status(device, BackupStatus.FAILED.value)
                self.audit.log_backup_complete(device.id, device.name, False, result['error'])
        else:
            # Backup failed
            result['error'] = backup_result['error']
            
            # Retry once if enabled and not already retried
            if retry and history.retry_count < self.config.MAX_RETRY:
                history.retry_count += 1
                if self.db_session:
                    self.db_session.commit()
                
                # Recursive call with retry=False to prevent infinite loop
                retry_result = self.backup_device(device, triggered_by, retry=False)
                
                if retry_result['success']:
                    return retry_result
                
                # Update with final failure
                result['error'] = f"Failed after retry: {retry_result['error']}"
            
            self._update_backup_history(
                history, False,
                execution_time=backup_result.get('execution_time'),
                error_message=result['error']
            )
            self._update_device_status(device, BackupStatus.FAILED.value)
            self.audit.log_backup_complete(device.id, device.name, False, result['error'])
        
        return result
    
    def backup_all_devices(self, triggered_by: str = 'manual') -> Dict:
        """
        Execute backup for all active devices.
        
        Returns:
            Dict with overall results:
                - total: total devices
                - success: successful backups
                - failed: failed backups
                - results: list of individual results
        """
        if not self.db_session:
            raise RuntimeError("Database session not set")
        
        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'results': []
        }
        
        devices = self.db_session.query(Device).filter(Device.is_active == True).all()
        results['total'] = len(devices)
        
        for device in devices:
            result = self.backup_device(device, triggered_by)
            results['results'].append(result)
            
            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        return results


# Singleton instance
_collector_instance = None


def get_collector(db_session=None) -> BackupCollector:
    """Get singleton backup collector instance"""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = BackupCollector(db_session)
    elif db_session:
        _collector_instance.set_db_session(db_session)
    return _collector_instance
