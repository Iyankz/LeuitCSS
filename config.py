"""
LeuitCSS v1.0.0 - Configuration
Active Configuration Backup System with Read-Only Access

DEFINISI: LeuitCSS adalah Active Configuration Backup System.
BUKAN: Config Manager, Orchestrator, Provisioning Tool, atau Automation Engine.
"""

import os
from pathlib import Path
from datetime import timedelta

# Base Directory
BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Base configuration class"""
    
    # Application Info
    APP_NAME = "LeuitCSS"
    APP_VERSION = "1.0.0"
    APP_DESCRIPTION = "Active Configuration Backup System with Read-Only Access"
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('LEUITCSS_SECRET_KEY', 'change-this-in-production')
    
    # Server Configuration
    PORT = int(os.environ.get('LEUITCSS_PORT', 5000))
    HOST = '0.0.0.0'  # Bind to all interfaces for LAN access
    DEBUG = False  # Always disabled for security
    
    # Database - SQLite
    DATABASE_PATH = os.environ.get('LEUITCSS_DB_PATH', str(BASE_DIR / 'data' / 'leuitcss.db'))
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Encryption - AES-256 with master key from environment variable
    MASTER_KEY = os.environ.get('LEUITCSS_MASTER_KEY')
    
    # Storage Configuration
    STORAGE_PATH = os.environ.get('LEUITCSS_STORAGE_PATH', str(BASE_DIR / 'storage'))
    
    # Log Configuration
    LOG_PATH = os.environ.get('LEUITCSS_LOG_PATH', str(BASE_DIR / 'logs'))
    AUDIT_LOG_FILE = 'audit.log'
    APP_LOG_FILE = 'leuitcss.log'
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Connection Timeouts (in seconds)
    SSH_TIMEOUT = 30
    TELNET_TIMEOUT = 30
    COMMAND_TIMEOUT = 60
    
    # Retry Configuration
    MAX_RETRY = 1  # Maksimal 1 kali retry, tidak looping
    
    # Default Ports
    DEFAULT_SSH_PORT = 22
    DEFAULT_TELNET_PORT = 23
    DEFAULT_API_PORT = 8728  # MikroTik API (Future Phase)
    
    # Supported Vendors (LOCKED for v1.0.0)
    SUPPORTED_VENDORS = ['mikrotik', 'cisco', 'huawei', 'zte', 'juniper', 'generic', 'generic-saved', 'generic-startup']
    
    # Vendor Backup Commands (HARDCODED - NOT EDITABLE)
    # These commands are READ-ONLY and will NEVER enter configuration mode
    VENDOR_COMMANDS = {
        'mikrotik': {
            'connection_types': ['ssh'],  # API is Future Phase
            'backup_command': '/export',
            'output_extension': '.rsc',
            'device_type': 'mikrotik_routeros',
        },
        'cisco': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'show running-config',
            'output_extension': '.txt',
            'device_type': 'cisco_ios',
        },
        'huawei': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'display current-configuration',
            'output_extension': '.txt',
            'device_type': 'huawei',
        },
        'zte': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'show running-config',
            'output_extension': '.txt',
            'device_type': 'zte_zxros',
        },
        'juniper': {
            'connection_types': ['ssh'],
            'backup_command': 'show configuration | display set',
            'output_extension': '.txt',
            'device_type': 'juniper_junos',
        },
        'generic': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'show running-config',
            'output_extension': '.txt',
            'device_type': 'cisco_ios',
        },
        'generic-saved': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'show saved-config',
            'output_extension': '.txt',
            'device_type': 'cisco_ios',
        },
        'generic-startup': {
            'connection_types': ['ssh', 'telnet'],
            'backup_command': 'show startup-config',
            'output_extension': '.txt',
            'device_type': 'cisco_ios',
        },
    }
    
    # Scheduler Configuration
    SCHEDULER_TIMEZONE = 'local'  # Mengikuti timezone server
    
    # Backup Status Constants
    BACKUP_STATUS_SUCCESS = 'success'
    BACKUP_STATUS_FAILED = 'failed'
    BACKUP_STATUS_TIMEOUT = 'timeout'
    BACKUP_STATUS_PENDING = 'pending'
    BACKUP_STATUS_RUNNING = 'running'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    # In production, these MUST be set via environment variables
    @property
    def SECRET_KEY(self):
        key = os.environ.get('LEUITCSS_SECRET_KEY')
        if not key:
            raise ValueError("LEUITCSS_SECRET_KEY environment variable must be set in production")
        return key
    
    @property
    def MASTER_KEY(self):
        key = os.environ.get('LEUITCSS_MASTER_KEY')
        if not key:
            raise ValueError("LEUITCSS_MASTER_KEY environment variable must be set in production")
        return key


# Configuration selector
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('LEUITCSS_ENV', 'development')
    return config.get(env, config['default'])()
