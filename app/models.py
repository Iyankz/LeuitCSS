"""
LeuitCSS v1.0.0 - Database Models
SQLite database for metadata storage

Models:
- Admin: Single admin account for Web UI authentication
- Device: Network devices to backup
- BackupSchedule: Scheduler configuration per device
- BackupHistory: Backup execution history and metadata
- AuditLog: Security audit trail
"""

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import enum

Base = declarative_base()


class ConnectionType(enum.Enum):
    """Supported connection types"""
    SSH = 'ssh'
    TELNET = 'telnet'
    # API = 'api'  # Future Phase


class BackupStatus(enum.Enum):
    """Backup execution status"""
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    TIMEOUT = 'timeout'


class ScheduleFrequency(enum.Enum):
    """Backup schedule frequency"""
    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'


class VendorType(enum.Enum):
    """Supported vendors (LOCKED for v1.0.0)"""
    MIKROTIK = 'mikrotik'
    CISCO = 'cisco'
    HUAWEI = 'huawei'
    ZTE = 'zte'
    JUNIPER = 'juniper'


class Admin(Base):
    """
    Single admin account for Web UI authentication.
    Only one admin account is supported in v1.0.0
    """
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # bcrypt hash
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<Admin {self.username}>"


class Device(Base):
    """
    Network device registered for backup.
    
    IMPORTANT: LeuitCSS only performs READ-ONLY operations.
    - No configuration changes
    - No push/restore
    - Only predefined backup commands
    """
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Vendor (determines backup command - HARDCODED)
    vendor = Column(String(20), nullable=False)  # mikrotik, cisco, huawei, zte, juniper
    
    # Connection Details
    ip_address = Column(String(45), nullable=False)  # IPv4 or IPv6
    port = Column(Integer, nullable=True)  # Custom port, uses default if null
    connection_type = Column(String(10), nullable=False, default='ssh')  # ssh, telnet
    
    # Credentials (ENCRYPTED with AES-256)
    username = Column(String(255), nullable=False)  # Encrypted
    password = Column(String(255), nullable=False)  # Encrypted
    enable_password = Column(String(255), nullable=True)  # Encrypted, for Cisco enable mode
    
    # Status
    is_active = Column(Boolean, default=True)
    last_backup_status = Column(String(20), nullable=True)
    last_backup_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    schedules = relationship("BackupSchedule", back_populates="device", cascade="all, delete-orphan")
    backup_history = relationship("BackupHistory", back_populates="device", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Device {self.name} ({self.vendor}@{self.ip_address})>"


class BackupSchedule(Base):
    """
    Backup schedule configuration per device.
    
    Supports:
    - Daily: Every day at specified time
    - Weekly: Specific day(s) of week at specified time
    - Monthly: Specific day of month at specified time
    """
    __tablename__ = 'backup_schedules'
    
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    
    # Schedule Configuration
    frequency = Column(String(10), nullable=False)  # daily, weekly, monthly
    time_hour = Column(Integer, nullable=False)  # 0-23 (HH)
    time_minute = Column(Integer, nullable=False, default=0)  # 0-59 (MM)
    
    # For weekly: 0=Monday, 6=Sunday (comma-separated for multiple days)
    day_of_week = Column(String(20), nullable=True)  # e.g., "0,2,4" for Mon,Wed,Fri
    
    # For monthly: 1-31 (or 'last' for last day)
    day_of_month = Column(String(10), nullable=True)  # e.g., "1" or "15" or "last"
    
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    next_run = Column(DateTime, nullable=True)
    last_run = Column(DateTime, nullable=True)
    
    # Relationships
    device = relationship("Device", back_populates="schedules")
    
    def __repr__(self):
        return f"<BackupSchedule {self.device_id} - {self.frequency} at {self.time_hour:02d}:{self.time_minute:02d}>"


class BackupHistory(Base):
    """
    Backup execution history with full metadata.
    
    IMMUTABLE: Records are append-only, never modified or deleted.
    
    Metadata stored (as per specification):
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
    __tablename__ = 'backup_history'
    
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    
    # Snapshot of device info at backup time
    device_name = Column(String(100), nullable=False)
    device_ip = Column(String(45), nullable=False)
    vendor = Column(String(20), nullable=False)
    connection_type = Column(String(10), nullable=False)
    
    # Backup command used (HARDCODED per vendor)
    backup_command = Column(String(255), nullable=False)
    
    # Execution Details
    status = Column(String(20), nullable=False)  # success, failed, timeout
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    execution_time_seconds = Column(Integer, nullable=True)  # Duration in seconds
    
    # File Details
    file_path = Column(String(500), nullable=True)  # Relative path in storage
    file_size_bytes = Column(Integer, nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    
    # Error Details (if failed)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)  # Max 1 retry
    
    # Triggered by
    triggered_by = Column(String(20), default='scheduler')  # scheduler, manual
    
    # Relationships
    device = relationship("Device", back_populates="backup_history")
    
    def __repr__(self):
        return f"<BackupHistory {self.device_name} - {self.status} at {self.started_at}>"


class AuditLog(Base):
    """
    Security audit log for all operations.
    
    Logs:
    - Admin login/logout
    - Device additions/modifications
    - Backup executions
    - Failed access attempts
    
    IMMUTABLE: Append-only, never modified or deleted.
    """
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Actor
    actor_type = Column(String(20), nullable=False)  # admin, system, scheduler
    actor_id = Column(String(50), nullable=True)  # admin username or 'system'
    
    # Action
    action = Column(String(50), nullable=False)  # login, logout, device_add, backup_start, etc.
    resource_type = Column(String(50), nullable=True)  # device, schedule, backup, etc.
    resource_id = Column(String(50), nullable=True)
    
    # Details
    details = Column(Text, nullable=True)  # JSON string with additional info
    ip_address = Column(String(45), nullable=True)  # Client IP
    user_agent = Column(String(255), nullable=True)
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<AuditLog {self.action} by {self.actor_id} at {self.timestamp}>"


def init_db(database_uri: str):
    """Initialize database and create all tables"""
    engine = create_engine(database_uri)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Create a new database session"""
    Session = sessionmaker(bind=engine)
    return Session()
