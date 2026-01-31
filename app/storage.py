"""
LeuitCSS v1.0.0 - Storage Manager
Immutable Configuration Storage

Storage Rules:
- Files are IMMUTABLE
- Append-only (no overwrite, no delete)
- Structure: /leuitcss/{vendor}/{device_id}/{timestamp}/
- Each backup has: config file, metadata.json, checksum.sha256
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from config import get_config


class StorageManager:
    """
    Immutable storage manager for configuration backups.
    
    Directory Structure:
    /leuitcss/
        /{vendor}/
            /{device_id}/
                /{timestamp}/
                    config.{ext}
                    metadata.json
                    checksum.sha256
    
    Rules:
    - Files are IMMUTABLE (no overwrite)
    - Append-only operations
    - Every backup creates new timestamped directory
    """
    
    def __init__(self, base_path: str = None):
        self.config = get_config()
        self.base_path = Path(base_path or self.config.STORAGE_PATH)
        self._ensure_base_directory()
    
    def _ensure_base_directory(self):
        """Create base storage directory if not exists"""
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_backup_path(self, vendor: str, device_id: int, timestamp: datetime) -> Path:
        """
        Generate backup directory path.
        
        Format: {base}/{vendor}/{device_id}/{timestamp}/
        Timestamp format: YYYYMMDD_HHMMSS
        """
        timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
        return self.base_path / vendor / str(device_id) / timestamp_str
    
    def _create_metadata(self, vendor: str, device_id: int, device_ip: str,
                        connection_type: str, backup_command: str,
                        timestamp: datetime, execution_time: float,
                        status: str, checksum: str, file_name: str) -> dict:
        """
        Create metadata dictionary as per specification.
        
        Required fields:
        - vendor
        - device_id
        - device_ip
        - connection_type
        - backup_command_id (vendor determines this)
        - timestamp
        - execution_time
        - status
        - checksum_sha256
        """
        return {
            'vendor': vendor,
            'device_id': device_id,
            'device_ip': device_ip,
            'connection_type': connection_type,
            'backup_command': backup_command,
            'timestamp': timestamp.isoformat(),
            'execution_time_seconds': execution_time,
            'status': status,
            'checksum_sha256': checksum,
            'file_name': file_name,
            'leuitcss_version': '1.0.0'
        }
    
    def save_backup(self, vendor: str, device_id: int, device_name: str,
                   device_ip: str, connection_type: str, backup_command: str,
                   config_output: str, output_extension: str,
                   execution_time: float, timestamp: datetime = None) -> Dict:
        """
        Save backup to immutable storage.
        
        Args:
            vendor: Vendor name
            device_id: Device database ID
            device_name: Device display name
            device_ip: Device IP address
            connection_type: Connection type used (ssh/telnet)
            backup_command: Backup command executed
            config_output: Configuration output string
            output_extension: File extension (.rsc, .txt, etc.)
            execution_time: Backup execution time in seconds
            timestamp: Backup timestamp (defaults to now)
        
        Returns:
            Dict with save result:
                - success: bool
                - file_path: relative path to config file
                - metadata_path: relative path to metadata file
                - checksum_path: relative path to checksum file
                - checksum: SHA256 checksum
                - error: error message if failed
        """
        result = {
            'success': False,
            'file_path': None,
            'metadata_path': None,
            'checksum_path': None,
            'checksum': None,
            'error': None
        }
        
        try:
            timestamp = timestamp or datetime.utcnow()
            backup_dir = self._get_backup_path(vendor, device_id, timestamp)
            
            # Create directory (will fail if exists - immutable)
            backup_dir.mkdir(parents=True, exist_ok=False)
            
            # Calculate checksum
            checksum = hashlib.sha256(config_output.encode()).hexdigest()
            
            # Determine file names
            config_filename = f"config{output_extension}"
            metadata_filename = "metadata.json"
            checksum_filename = "checksum.sha256"
            
            # Save config file
            config_path = backup_dir / config_filename
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_output)
            
            # Create and save metadata
            metadata = self._create_metadata(
                vendor=vendor,
                device_id=device_id,
                device_ip=device_ip,
                connection_type=connection_type,
                backup_command=backup_command,
                timestamp=timestamp,
                execution_time=execution_time,
                status='success',
                checksum=checksum,
                file_name=config_filename
            )
            
            metadata_path = backup_dir / metadata_filename
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Save checksum file
            checksum_path = backup_dir / checksum_filename
            with open(checksum_path, 'w', encoding='utf-8') as f:
                f.write(f"{checksum}  {config_filename}\n")
            
            # Make files read-only (immutable)
            os.chmod(config_path, 0o444)
            os.chmod(metadata_path, 0o444)
            os.chmod(checksum_path, 0o444)
            
            # Calculate relative paths
            relative_dir = backup_dir.relative_to(self.base_path)
            
            result['success'] = True
            result['file_path'] = str(relative_dir / config_filename)
            result['metadata_path'] = str(relative_dir / metadata_filename)
            result['checksum_path'] = str(relative_dir / checksum_filename)
            result['checksum'] = checksum
            result['file_size'] = len(config_output.encode())
            
        except FileExistsError:
            result['error'] = "Backup directory already exists (immutability violation)"
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def get_backup(self, file_path: str) -> Optional[str]:
        """
        Retrieve backup content by relative path.
        
        Args:
            file_path: Relative path to config file
        
        Returns:
            Config content string or None if not found
        """
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            return None
        
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def get_metadata(self, file_path: str) -> Optional[dict]:
        """
        Retrieve metadata for a backup.
        
        Args:
            file_path: Relative path to config file
        
        Returns:
            Metadata dict or None if not found
        """
        config_path = self.base_path / file_path
        metadata_path = config_path.parent / 'metadata.json'
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def verify_checksum(self, file_path: str) -> bool:
        """
        Verify backup file integrity using stored checksum.
        
        Args:
            file_path: Relative path to config file
        
        Returns:
            True if checksum matches, False otherwise
        """
        full_path = self.base_path / file_path
        checksum_path = full_path.parent / 'checksum.sha256'
        
        if not full_path.exists() or not checksum_path.exists():
            return False
        
        # Read stored checksum
        with open(checksum_path, 'r') as f:
            stored_checksum = f.read().split()[0]
        
        # Calculate current checksum
        with open(full_path, 'rb') as f:
            current_checksum = hashlib.sha256(f.read()).hexdigest()
        
        return stored_checksum == current_checksum
    
    def list_backups(self, vendor: str = None, device_id: int = None) -> List[Dict]:
        """
        List available backups with optional filtering.
        
        Args:
            vendor: Filter by vendor (optional)
            device_id: Filter by device ID (optional)
        
        Returns:
            List of backup metadata dicts
        """
        backups = []
        
        # Determine search path
        if vendor and device_id:
            search_path = self.base_path / vendor / str(device_id)
        elif vendor:
            search_path = self.base_path / vendor
        else:
            search_path = self.base_path
        
        if not search_path.exists():
            return backups
        
        # Find all metadata files
        for metadata_file in search_path.rglob('metadata.json'):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    # Add full path info
                    config_file = metadata_file.parent / metadata.get('file_name', 'config.txt')
                    metadata['full_path'] = str(config_file.relative_to(self.base_path))
                    metadata['backup_dir'] = str(metadata_file.parent.relative_to(self.base_path))
                    backups.append(metadata)
            except:
                continue
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return backups
    
    def get_storage_stats(self) -> Dict:
        """
        Get storage statistics.
        
        Returns:
            Dict with storage stats:
                - total_backups: total number of backups
                - total_size_bytes: total storage used
                - backups_by_vendor: count per vendor
        """
        stats = {
            'total_backups': 0,
            'total_size_bytes': 0,
            'backups_by_vendor': {}
        }
        
        for metadata_file in self.base_path.rglob('metadata.json'):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                stats['total_backups'] += 1
                
                vendor = metadata.get('vendor', 'unknown')
                if vendor not in stats['backups_by_vendor']:
                    stats['backups_by_vendor'][vendor] = 0
                stats['backups_by_vendor'][vendor] += 1
                
                # Calculate directory size
                backup_dir = metadata_file.parent
                for file in backup_dir.iterdir():
                    if file.is_file():
                        stats['total_size_bytes'] += file.stat().st_size
                        
            except:
                continue
        
        return stats
    
    def get_absolute_path(self, relative_path: str) -> Path:
        """Get absolute path from relative path"""
        return self.base_path / relative_path


# Singleton instance
_storage_instance = None


def get_storage() -> StorageManager:
    """Get singleton storage manager instance"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageManager()
    return _storage_instance
