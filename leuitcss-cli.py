#!/usr/bin/env python3
"""
LeuitCSS v1.0.0 - CLI Management Tool

Commands:
- reset-password <username>  : Reset admin password
- init                       : Initialize database and create default admin
- status                     : Show system status

Usage:
    leuitcss reset-password admin
    leuitcss init
    leuitcss status
"""

import os
import sys
import secrets
import string
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import get_config
from app.models import Base, Admin, Device, BackupSchedule, BackupHistory
from app.auth import AuthService


def generate_strong_password(length=16):
    """Generate a strong random password"""
    # Ensure at least one of each required character type
    lowercase = secrets.choice(string.ascii_lowercase)
    uppercase = secrets.choice(string.ascii_uppercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice('!@#$%^&*')
    
    # Fill the rest with random characters
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    remaining = ''.join(secrets.choice(alphabet) for _ in range(length - 4))
    
    # Combine and shuffle
    password_list = list(lowercase + uppercase + digit + special + remaining)
    secrets.SystemRandom().shuffle(password_list)
    
    return ''.join(password_list)


def get_db_session():
    """Create database session"""
    config = get_config()
    engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        connect_args={'check_same_thread': False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def cmd_reset_password(args):
    """Reset admin password"""
    username = args.username
    
    print(f"\n{'='*60}")
    print("LeuitCSS - Password Reset")
    print(f"{'='*60}\n")
    
    session = get_db_session()
    
    # Find admin
    admin = session.query(Admin).filter(Admin.username == username).first()
    
    if not admin:
        print(f"[ERROR] User '{username}' not found.")
        print(f"Available users: ", end="")
        admins = session.query(Admin).all()
        if admins:
            print(", ".join([a.username for a in admins]))
        else:
            print("No users found. Run 'leuitcss init' first.")
        session.close()
        return 1
    
    # Generate new password
    new_password = generate_strong_password()
    
    # Update password
    auth_service = AuthService(session)
    admin.password_hash = auth_service.hash_password(new_password)
    session.commit()
    session.close()
    
    print(f"[SUCCESS] Password reset for user '{username}'")
    print()
    print(f"{'='*60}")
    print(f"  NEW PASSWORD: {new_password}")
    print(f"{'='*60}")
    print()
    print("[WARNING] This password will NOT be shown again!")
    print("[WARNING] Please save it in a secure location.")
    print()
    
    return 0


def cmd_init(args):
    """Initialize database and create default admin"""
    print(f"\n{'='*60}")
    print("LeuitCSS - System Initialization")
    print(f"{'='*60}\n")
    
    config = get_config()
    
    # Check master key
    if not os.environ.get('LEUITCSS_MASTER_KEY'):
        print("[ERROR] LEUITCSS_MASTER_KEY environment variable not set!")
        print("Please set it before initialization:")
        print()
        master_key = secrets.token_hex(32)
        print(f"  export LEUITCSS_MASTER_KEY={master_key}")
        print()
        return 1
    
    session = get_db_session()
    
    # Check if admin already exists
    existing_admin = session.query(Admin).first()
    if existing_admin:
        print(f"[INFO] Admin account already exists: {existing_admin.username}")
        print("[INFO] Use 'leuitcss reset-password <username>' to reset password.")
        session.close()
        return 0
    
    # Create default admin with random password
    username = "admin"
    password = generate_strong_password()
    
    auth_service = AuthService(session)
    admin = Admin(
        username=username,
        password_hash=auth_service.hash_password(password),
        is_active=True
    )
    session.add(admin)
    session.commit()
    session.close()
    
    print("[SUCCESS] System initialized successfully!")
    print()
    print(f"{'='*60}")
    print("  DEFAULT ADMIN CREDENTIALS")
    print(f"{'='*60}")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print(f"{'='*60}")
    print()
    print("[WARNING] This password will NOT be shown again!")
    print("[WARNING] Please save it in a secure location.")
    print()
    
    # Get server IP for access info
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "<SERVER_IP>"
    
    port = os.environ.get('LEUITCSS_PORT', '5000')
    
    print(f"[INFO] Access Web UI at: http://{local_ip}:{port}")
    print()
    
    return 0


def cmd_status(args):
    """Show system status"""
    print(f"\n{'='*60}")
    print("LeuitCSS - System Status")
    print(f"{'='*60}\n")
    
    config = get_config()
    
    # Check master key
    master_key_set = bool(os.environ.get('LEUITCSS_MASTER_KEY'))
    print(f"Master Key: {'[SET]' if master_key_set else '[NOT SET]'}")
    
    # Database
    try:
        session = get_db_session()
        
        admin_count = session.query(Admin).count()
        device_count = session.query(Device).count()
        schedule_count = session.query(BackupSchedule).count()
        backup_count = session.query(BackupHistory).count()
        
        print(f"Database: [OK]")
        print(f"  - Admins: {admin_count}")
        print(f"  - Devices: {device_count}")
        print(f"  - Schedules: {schedule_count}")
        print(f"  - Backups: {backup_count}")
        
        session.close()
    except Exception as e:
        print(f"Database: [ERROR] {e}")
    
    # Storage
    from pathlib import Path
    storage_path = Path(config.STORAGE_PATH)
    if storage_path.exists():
        # Count files
        file_count = sum(1 for _ in storage_path.rglob('config.*'))
        print(f"Storage: [OK] {storage_path}")
        print(f"  - Backup files: {file_count}")
    else:
        print(f"Storage: [NOT CREATED] {storage_path}")
    
    # Log
    log_path = Path(config.LOG_PATH)
    if log_path.exists():
        print(f"Logs: [OK] {log_path}")
    else:
        print(f"Logs: [NOT CREATED] {log_path}")
    
    print()
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='leuitcss',
        description='LeuitCSS - Active Configuration Backup System CLI'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # reset-password command
    reset_parser = subparsers.add_parser('reset-password', help='Reset admin password')
    reset_parser.add_argument('username', help='Username to reset password for')
    
    # init command
    init_parser = subparsers.add_parser('init', help='Initialize system and create default admin')
    
    # status command
    status_parser = subparsers.add_parser('status', help='Show system status')
    
    args = parser.parse_args()
    
    if args.command == 'reset-password':
        return cmd_reset_password(args)
    elif args.command == 'init':
        return cmd_init(args)
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
