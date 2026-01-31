"""
LeuitCSS v1.0.0 - Vendor Adapters
Read-Only Device Access for Configuration Backup

CRITICAL RULES:
- All operations are READ-ONLY
- Commands are HARDCODED per vendor
- NO configuration mode access
- NO push/restore operations
- NO arbitrary command execution
"""

import time
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Tuple, Optional
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from config import get_config
from app.encryption import decrypt_credential


class VendorAdapter(ABC):
    """
    Abstract base class for vendor-specific adapters.
    
    All adapters implement READ-ONLY backup operations only.
    Commands are HARDCODED and cannot be modified.
    """
    
    def __init__(self, device_info: dict):
        """
        Initialize adapter with device information.
        
        Args:
            device_info: Dict containing:
                - ip_address: Device IP
                - port: Custom port (optional)
                - username: Encrypted username
                - password: Encrypted password
                - enable_password: Encrypted enable password (optional)
                - connection_type: ssh or telnet
        """
        self.config = get_config()
        self.device_info = device_info
        self.connection = None
        
    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Return vendor name"""
        pass
    
    @property
    @abstractmethod
    def device_type(self) -> str:
        """Return netmiko device type"""
        pass
    
    @property
    @abstractmethod
    def backup_command(self) -> str:
        """Return HARDCODED backup command"""
        pass
    
    @property
    @abstractmethod
    def output_extension(self) -> str:
        """Return output file extension"""
        pass
    
    def _get_connection_params(self) -> dict:
        """Build connection parameters for netmiko"""
        connection_type = self.device_info.get('connection_type', 'ssh')
        
        # Determine port
        port = self.device_info.get('port')
        if not port:
            if connection_type == 'telnet':
                port = self.config.DEFAULT_TELNET_PORT
            else:
                port = self.config.DEFAULT_SSH_PORT
        
        # Decrypt credentials
        username = decrypt_credential(self.device_info['username'])
        password = decrypt_credential(self.device_info['password'])
        
        params = {
            'device_type': self.device_type,
            'host': self.device_info['ip_address'],
            'port': port,
            'username': username,
            'password': password,
            'timeout': self.config.SSH_TIMEOUT,
        }
        
        # Add telnet suffix if using telnet
        if connection_type == 'telnet':
            params['device_type'] = f"{self.device_type}_telnet"
        else:
            # SSH: Disable strict host key checking and allow legacy algorithms
            # Many network devices (Huawei, ZTE, older Cisco) use ssh-rsa which is 
            # disabled by default in OpenSSH 8.8+ (Ubuntu 22.04+)
            params['allow_agent'] = False
            params['use_keys'] = False
            # Don't use system SSH config which may block legacy algorithms
            params['ssh_config_file'] = None
            # Netmiko 4.x+ supports disabled_algorithms parameter
            # Set to empty dict to allow all algorithms including legacy ssh-rsa
            params['disabled_algorithms'] = {'pubkeys': []}
        
        # Add enable password if available
        enable_password = self.device_info.get('enable_password')
        if enable_password:
            params['secret'] = decrypt_credential(enable_password)
        
        return params
    
    def connect(self) -> bool:
        """
        Establish connection to device.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            params = self._get_connection_params()
            self.connection = ConnectHandler(**params)
            return True
        except NetmikoAuthenticationException:
            raise ConnectionError(f"Authentication failed for {self.device_info['ip_address']}")
        except NetmikoTimeoutException:
            raise ConnectionError(f"Connection timeout for {self.device_info['ip_address']}")
        except Exception as e:
            raise ConnectionError(f"Connection failed: {str(e)}")
    
    def disconnect(self):
        """Disconnect from device"""
        if self.connection:
            try:
                self.connection.disconnect()
            except:
                pass
            finally:
                self.connection = None
    
    def execute_backup(self) -> Tuple[str, float]:
        """
        Execute HARDCODED backup command and return output.
        
        This is the ONLY command that can be executed.
        NO other commands are allowed.
        
        Returns:
            Tuple of (output_string, execution_time_seconds)
        """
        if not self.connection:
            raise RuntimeError("Not connected to device")
        
        start_time = time.time()
        
        # Execute HARDCODED backup command
        output = self.connection.send_command(
            self.backup_command,
            read_timeout=self.config.COMMAND_TIMEOUT
        )
        
        execution_time = time.time() - start_time
        
        return output, execution_time
    
    def backup(self) -> dict:
        """
        Perform full backup operation.
        
        Returns:
            Dict containing:
                - success: bool
                - output: str (config output)
                - execution_time: float
                - checksum: str (SHA256)
                - error: str (if failed)
        """
        result = {
            'success': False,
            'output': None,
            'execution_time': 0,
            'checksum': None,
            'error': None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            # Connect to device
            self.connect()
            
            # Execute backup command
            output, exec_time = self.execute_backup()
            
            # Calculate checksum
            checksum = hashlib.sha256(output.encode()).hexdigest()
            
            result['success'] = True
            result['output'] = output
            result['execution_time'] = exec_time
            result['checksum'] = checksum
            
        except Exception as e:
            result['error'] = str(e)
            
        finally:
            self.disconnect()
        
        return result


class MikroTikAdapter(VendorAdapter):
    """
    MikroTik RouterOS adapter.
    
    Connection: SSH only (API is Future Phase)
    Command: /export (HARDCODED)
    Output: .rsc
    """
    
    @property
    def vendor_name(self) -> str:
        return 'mikrotik'
    
    @property
    def device_type(self) -> str:
        return 'mikrotik_routeros'
    
    @property
    def backup_command(self) -> str:
        return '/export'
    
    @property
    def output_extension(self) -> str:
        return '.rsc'


class CiscoAdapter(VendorAdapter):
    """
    Cisco IOS adapter.
    
    Connection: SSH or Telnet
    Command: show running-config (HARDCODED)
    Output: .txt
    """
    
    @property
    def vendor_name(self) -> str:
        return 'cisco'
    
    @property
    def device_type(self) -> str:
        return 'cisco_ios'
    
    @property
    def backup_command(self) -> str:
        return 'show running-config'
    
    @property
    def output_extension(self) -> str:
        return '.txt'
    
    def connect(self) -> bool:
        """Connect and enter enable mode if needed"""
        result = super().connect()
        
        # Enter enable mode if enable password is provided
        if self.device_info.get('enable_password'):
            self.connection.enable()
        
        return result


class HuaweiAdapter(VendorAdapter):
    """
    Huawei adapter.
    
    Connection: SSH or Telnet
    Command: display current-configuration (HARDCODED)
    Output: .txt
    """
    
    @property
    def vendor_name(self) -> str:
        return 'huawei'
    
    @property
    def device_type(self) -> str:
        return 'huawei'
    
    @property
    def backup_command(self) -> str:
        return 'display current-configuration'
    
    @property
    def output_extension(self) -> str:
        return '.txt'


class ZTEAdapter(VendorAdapter):
    """
    ZTE OLT adapter.
    
    Connection: SSH or Telnet
    Backup Method: FTP Upload (NOT SSH output)
    
    ZTE OLT uses a special backup flow:
    1. SSH to device
    2. Send command to upload config to FTP server
    3. Poll FTP folder for incoming file
    4. Move file to immutable storage
    
    Command: file upload cfg-startup startrun.dat ftp ... (HARDCODED)
    Output: startrun.dat (binary config file)
    """
    
    # FTP polling settings
    FTP_POLL_TIMEOUT = 120  # Maximum wait time in seconds
    FTP_POLL_INTERVAL = 3   # Poll every 3 seconds
    
    @property
    def vendor_name(self) -> str:
        return 'zte'
    
    @property
    def device_type(self) -> str:
        return 'zte_zxros'
    
    @property
    def backup_command(self) -> str:
        # This is a template - actual command built in _build_ftp_upload_command
        return 'file upload cfg-startup startrun.dat ftp'
    
    @property
    def output_extension(self) -> str:
        return '.dat'
    
    def _is_ftp_service_running(self) -> bool:
        """Check if FTP service is running via systemd"""
        import subprocess
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'leuitcss-ftp'],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() == 'active'
        except:
            return False
    
    def _get_ftp_config(self) -> dict:
        """Get FTP configuration from environment and check service status"""
        import os
        
        # Check if FTP service is actually running (not just env variable)
        ftp_running = self._is_ftp_service_running()
        
        return {
            'enabled': ftp_running,  # Use actual service status
            'port': int(os.environ.get('LEUITCSS_FTP_PORT', '21')),
            'user': os.environ.get('LEUITCSS_FTP_USER', 'leuitcss'),
            'password': os.environ.get('LEUITCSS_FTP_PASSWORD', ''),
            'root': os.environ.get('LEUITCSS_FTP_ROOT', '/var/lib/leuitcss/ftp-ingestion')
        }
    
    def _get_server_ip(self) -> str:
        """
        Get LeuitCSS server IP address for FTP.
        
        Priority:
        1. LEUITCSS_SERVER_IP from environment (manual override)
        2. Auto-detect based on route to device
        """
        import os
        import socket
        
        # Check for manual override first
        manual_ip = os.environ.get('LEUITCSS_SERVER_IP', '').strip()
        if manual_ip:
            return manual_ip
        
        # Auto-detect: Get the IP that would be used to connect to the device
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.device_info['ip_address'], 80))
            server_ip = s.getsockname()[0]
            s.close()
            return server_ip
        except:
            # Fallback to hostname IP
            return socket.gethostbyname(socket.gethostname())
    
    def _get_ftp_inbox_path(self, device_id: int) -> str:
        """Get FTP inbox path for this device"""
        from pathlib import Path
        ftp_config = self._get_ftp_config()
        inbox_path = Path(ftp_config['root']) / 'zte' / str(device_id)
        inbox_path.mkdir(parents=True, exist_ok=True)
        return str(inbox_path)
    
    def _build_ftp_upload_command(self, device_id: int) -> str:
        """
        Build the HARDCODED FTP upload command for ZTE OLT.
        
        Command format:
        file upload cfg-startup startrun.dat ftp ipaddress <IP> path <PATH> user <USER> password <PASS>
        
        Note: path is RELATIVE to FTP root, not absolute path
        """
        ftp_config = self._get_ftp_config()
        server_ip = self._get_server_ip()
        
        # Path RELATIVE to FTP root (not absolute)
        # FTP root is /var/lib/leuitcss/ftp-ingestion
        # So path should be: zte/<device_id>/
        ftp_path = f"zte/{device_id}/"
        
        # HARDCODED command - cannot be modified from UI
        command = (
            f"file upload cfg-startup startrun.dat ftp "
            f"ipaddress {server_ip} "
            f"path {ftp_path} "
            f"user {ftp_config['user']} "
            f"password {ftp_config['password']}"
        )
        
        return command
    
    def _clear_inbox(self, inbox_path: str):
        """Clear any existing files in inbox before backup"""
        from pathlib import Path
        import os
        
        inbox = Path(inbox_path)
        # Clear startrun.dat if exists
        target_file = inbox / 'startrun.dat'
        if target_file.exists():
            try:
                os.remove(target_file)
            except:
                pass
    
    def _poll_for_file(self, inbox_path: str) -> Optional[str]:
        """
        Poll FTP inbox for incoming file.
        
        Returns:
            Path to received file, or None if timeout
        """
        from pathlib import Path
        
        inbox = Path(inbox_path)
        target_file = inbox / 'startrun.dat'
        
        start_time = time.time()
        
        while (time.time() - start_time) < self.FTP_POLL_TIMEOUT:
            # Check if file exists and has content
            if target_file.exists():
                # Wait a moment for file to finish writing
                time.sleep(1)
                
                # Check file size > 0
                if target_file.stat().st_size > 0:
                    return str(target_file)
            
            time.sleep(self.FTP_POLL_INTERVAL)
        
        return None
    
    def backup(self) -> dict:
        """
        Perform ZTE OLT backup via FTP.
        
        This overrides the parent backup() method because ZTE uses
        a completely different flow (FTP upload instead of SSH output).
        
        Returns:
            Dict containing backup result
        """
        result = {
            'success': False,
            'output': None,
            'execution_time': 0,
            'checksum': None,
            'error': None,
            'timestamp': datetime.utcnow().isoformat(),
            'file_path': None  # For ZTE, we store the file path
        }
        
        start_time = time.time()
        device_id = self.device_info.get('device_id', 0)
        
        try:
            # Check FTP is enabled
            ftp_config = self._get_ftp_config()
            if not ftp_config['enabled']:
                raise RuntimeError("FTP server is not enabled. Enable it in Web UI (ZTE FTP Ingestion)")
            
            if not ftp_config['password']:
                raise RuntimeError("FTP password not configured in .env file")
            
            # Get inbox path and clear it
            inbox_path = self._get_ftp_inbox_path(device_id)
            self._clear_inbox(inbox_path)
            
            # Connect to device
            self.connect()
            
            # Build and execute FTP upload command
            upload_command = self._build_ftp_upload_command(device_id)
            
            # Send command (don't wait for output, ZTE uploads in background)
            self.connection.send_command(
                upload_command,
                read_timeout=30,
                expect_string=r'#|>|\$'  # Return after prompt
            )
            
            # Disconnect SSH - we're done with the device
            self.disconnect()
            
            # Poll for incoming file
            received_file = self._poll_for_file(inbox_path)
            
            if not received_file:
                raise RuntimeError(f"FTP file not received within {self.FTP_POLL_TIMEOUT} seconds")
            
            # Read file content
            with open(received_file, 'rb') as f:
                content = f.read()
            
            # Calculate checksum
            checksum = hashlib.sha256(content).hexdigest()
            
            # Success
            result['success'] = True
            result['output'] = content.decode('utf-8', errors='replace')
            result['execution_time'] = time.time() - start_time
            result['checksum'] = checksum
            result['file_path'] = received_file
            
        except Exception as e:
            result['error'] = str(e)
            result['execution_time'] = time.time() - start_time
            
        finally:
            self.disconnect()
        
        return result


class JuniperAdapter(VendorAdapter):
    """
    Juniper JunOS adapter.
    
    Connection: SSH only
    Command: show configuration | display set (HARDCODED)
    Output: .txt
    """
    
    @property
    def vendor_name(self) -> str:
        return 'juniper'
    
    @property
    def device_type(self) -> str:
        return 'juniper_junos'
    
    @property
    def backup_command(self) -> str:
        return 'show configuration | display set'
    
    @property
    def output_extension(self) -> str:
        return '.txt'


class GenericAdapter(VendorAdapter):
    """
    Generic adapter for whitebox/unbranded devices with Cisco-like CLI.
    
    Connection: SSH or Telnet
    Command: show running-config (HARDCODED)
    Output: .txt
    
    Use for:
    - Whitebox network devices (DCN, etc.)
    - Local/small vendors with Cisco-style CLI
    - Non-branded devices
    - Legacy devices with standard CLI
    
    Note: Uses cisco_ios device type for Cisco-like CLI compatibility.
    """
    
    @property
    def vendor_name(self) -> str:
        return 'generic'
    
    @property
    def device_type(self) -> str:
        return 'cisco_ios'  # Cisco-like CLI compatibility
    
    @property
    def backup_command(self) -> str:
        return 'show running-config'
    
    @property
    def output_extension(self) -> str:
        return '.txt'


class GenericSavedAdapter(VendorAdapter):
    """
    Generic adapter for saved/stored configuration.
    
    Connection: SSH or Telnet
    Command: show saved-config (HARDCODED)
    Output: .txt
    
    Use for devices that store config separately from running config.
    """
    
    @property
    def vendor_name(self) -> str:
        return 'generic-saved'
    
    @property
    def device_type(self) -> str:
        return 'cisco_ios'
    
    @property
    def backup_command(self) -> str:
        return 'show saved-config'
    
    @property
    def output_extension(self) -> str:
        return '.txt'


class GenericStartupAdapter(VendorAdapter):
    """
    Generic adapter for startup configuration.
    
    Connection: SSH or Telnet
    Command: show startup-config (HARDCODED)
    Output: .txt
    
    Use for devices that use startup-config (config loaded at boot).
    """
    
    @property
    def vendor_name(self) -> str:
        return 'generic-startup'
    
    @property
    def device_type(self) -> str:
        return 'cisco_ios'
    
    @property
    def backup_command(self) -> str:
        return 'show startup-config'
    
    @property
    def output_extension(self) -> str:
        return '.txt'


# Vendor adapter registry
VENDOR_ADAPTERS = {
    'mikrotik': MikroTikAdapter,
    'cisco': CiscoAdapter,
    'huawei': HuaweiAdapter,
    'zte': ZTEAdapter,
    'juniper': JuniperAdapter,
    'generic': GenericAdapter,
    'generic-saved': GenericSavedAdapter,
    'generic-startup': GenericStartupAdapter,
}


def get_adapter(vendor: str, device_info: dict) -> VendorAdapter:
    """
    Get the appropriate vendor adapter.
    
    Args:
        vendor: Vendor name (mikrotik, cisco, huawei, zte, juniper, generic, generic-saved, generic-startup)
        device_info: Device connection information
    
    Returns:
        VendorAdapter instance
    
    Raises:
        ValueError: If vendor is not supported
    """
    vendor = vendor.lower()
    
    if vendor not in VENDOR_ADAPTERS:
        raise ValueError(f"Unsupported vendor: {vendor}. Supported: {list(VENDOR_ADAPTERS.keys())}")
    
    return VENDOR_ADAPTERS[vendor](device_info)
