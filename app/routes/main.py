"""
LeuitCSS v1.0.0 - Main Routes
Dashboard, device management, and schedule management
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g, session
import logging

from app.forms import DeviceForm, DeviceEditForm, ScheduleForm
from app.auth import login_required, get_current_admin
from app.encryption import encrypt_credential
from app.audit import get_audit_logger
from app.models import Device, BackupSchedule, BackupHistory
from app.collector import get_collector
from app.scheduler import get_scheduler
from app.storage import get_storage
from config import get_config

main_bp = Blueprint('main', __name__)
logger = logging.getLogger('leuitcss.routes')


@main_bp.route('/')
def index():
    """Redirect to dashboard or login"""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - overview of system status"""
    total_devices = g.db_session.query(Device).count()
    active_devices = g.db_session.query(Device).filter(Device.is_active == True).count()
    
    total_schedules = g.db_session.query(BackupSchedule).count()
    active_schedules = g.db_session.query(BackupSchedule).filter(BackupSchedule.is_active == True).count()
    
    recent_backups = g.db_session.query(BackupHistory).order_by(
        BackupHistory.started_at.desc()
    ).limit(10).all()
    
    total_backups = g.db_session.query(BackupHistory).count()
    successful_backups = g.db_session.query(BackupHistory).filter(
        BackupHistory.status == 'success'
    ).count()
    failed_backups = g.db_session.query(BackupHistory).filter(
        BackupHistory.status.in_(['failed', 'timeout'])
    ).count()
    
    storage = get_storage()
    storage_stats = storage.get_storage_stats()
    
    scheduler = get_scheduler()
    scheduled_jobs = scheduler.get_jobs()
    
    # Server time
    server_time = datetime.now()
    
    return render_template('main/dashboard.html',
        total_devices=total_devices,
        active_devices=active_devices,
        total_schedules=total_schedules,
        active_schedules=active_schedules,
        recent_backups=recent_backups,
        total_backups=total_backups,
        successful_backups=successful_backups,
        failed_backups=failed_backups,
        storage_stats=storage_stats,
        scheduled_jobs=scheduled_jobs,
        server_time=server_time
    )


# =============================================================================
# Device Routes
# =============================================================================

@main_bp.route('/devices')
@login_required
def devices():
    """List all devices"""
    devices = g.db_session.query(Device).order_by(Device.name).all()
    config = get_config()
    
    return render_template('main/devices.html', 
        devices=devices,
        vendor_commands=config.VENDOR_COMMANDS
    )


@main_bp.route('/devices/add', methods=['GET', 'POST'])
@login_required
def device_add():
    """Add new device"""
    form = DeviceForm()
    
    if form.validate_on_submit():
        device = Device(
            name=form.name.data,
            description=form.description.data,
            vendor=form.vendor.data,
            ip_address=form.ip_address.data,
            port=form.port.data,
            connection_type=form.connection_type.data,
            username=encrypt_credential(form.username.data),
            password=encrypt_credential(form.password.data),
            enable_password=encrypt_credential(form.enable_password.data) if form.enable_password.data else None,
            is_active=form.is_active.data
        )
        
        g.db_session.add(device)
        g.db_session.commit()
        
        admin = get_current_admin(g.db_session)
        audit = get_audit_logger()
        audit.set_db_session(g.db_session)
        audit.log_device_add(admin.username, device.id, device.name)
        
        flash(f'Device "{device.name}" added successfully!', 'success')
        return redirect(url_for('main.device_detail', device_id=device.id))
    
    config = get_config()
    return render_template('main/device_form.html', 
        form=form, 
        action='Add',
        vendor_commands=config.VENDOR_COMMANDS
    )


@main_bp.route('/devices/<int:device_id>')
@login_required
def device_detail(device_id):
    """Device detail page"""
    device = g.db_session.query(Device).filter(Device.id == device_id).first()
    if not device:
        abort(404)
    
    backups = g.db_session.query(BackupHistory).filter(
        BackupHistory.device_id == device_id
    ).order_by(BackupHistory.started_at.desc()).limit(50).all()
    
    schedules = g.db_session.query(BackupSchedule).filter(
        BackupSchedule.device_id == device_id
    ).all()
    
    config = get_config()
    vendor_config = config.VENDOR_COMMANDS.get(device.vendor, {})
    
    return render_template('main/device_detail.html',
        device=device,
        backups=backups,
        schedules=schedules,
        vendor_config=vendor_config
    )


@main_bp.route('/devices/<int:device_id>/edit', methods=['GET', 'POST'])
@login_required
def device_edit(device_id):
    """Edit device"""
    device = g.db_session.query(Device).filter(Device.id == device_id).first()
    if not device:
        abort(404)
    
    form = DeviceEditForm(obj=device)
    
    if form.validate_on_submit():
        changes = {}
        
        if device.name != form.name.data:
            changes['name'] = {'old': device.name, 'new': form.name.data}
        if device.ip_address != form.ip_address.data:
            changes['ip_address'] = {'old': device.ip_address, 'new': form.ip_address.data}
        if device.vendor != form.vendor.data:
            changes['vendor'] = {'old': device.vendor, 'new': form.vendor.data}
        
        device.name = form.name.data
        device.description = form.description.data
        device.vendor = form.vendor.data
        device.ip_address = form.ip_address.data
        device.port = form.port.data
        device.connection_type = form.connection_type.data
        device.username = encrypt_credential(form.username.data)
        device.is_active = form.is_active.data
        
        if form.password.data:
            device.password = encrypt_credential(form.password.data)
            changes['password'] = 'changed'
        
        if form.enable_password.data:
            device.enable_password = encrypt_credential(form.enable_password.data)
            changes['enable_password'] = 'changed'
        
        g.db_session.commit()
        
        scheduler = get_scheduler()
        for schedule in device.schedules:
            if schedule.is_active:
                scheduler.update_schedule(schedule, device)
        
        admin = get_current_admin(g.db_session)
        audit = get_audit_logger()
        audit.set_db_session(g.db_session)
        audit.log_device_update(admin.username, device.id, changes)
        
        flash(f'Device "{device.name}" updated successfully!', 'success')
        return redirect(url_for('main.device_detail', device_id=device.id))
    
    config = get_config()
    return render_template('main/device_form.html',
        form=form,
        device=device,
        action='Edit',
        vendor_commands=config.VENDOR_COMMANDS
    )


@main_bp.route('/devices/<int:device_id>/delete', methods=['POST'])
@login_required
def device_delete(device_id):
    """Delete device"""
    device = g.db_session.query(Device).filter(Device.id == device_id).first()
    if not device:
        abort(404)
    
    device_name = device.name
    
    scheduler = get_scheduler()
    for schedule in device.schedules:
        scheduler.remove_schedule(schedule.id)
    
    g.db_session.delete(device)
    g.db_session.commit()
    
    admin = get_current_admin(g.db_session)
    audit = get_audit_logger()
    audit.set_db_session(g.db_session)
    audit.log_device_delete(admin.username, device_id, device_name)
    
    flash(f'Device "{device_name}" deleted successfully!', 'success')
    return redirect(url_for('main.devices'))


@main_bp.route('/devices/<int:device_id>/backup', methods=['POST'])
@login_required
def device_backup(device_id):
    """Trigger manual backup for device"""
    device = g.db_session.query(Device).filter(Device.id == device_id).first()
    if not device:
        abort(404)
    
    if not device.is_active:
        flash(f'Device "{device.name}" is inactive. Cannot perform backup.', 'warning')
        return redirect(url_for('main.device_detail', device_id=device.id))
    
    try:
        # Get collector with current db session
        collector = get_collector()
        collector.set_db_session(g.db_session)
        
        # Execute backup
        result = collector.backup_device(device, triggered_by='manual')
        
        if result['success']:
            flash(f'Backup successful! File saved.', 'success')
        else:
            flash(f'Backup failed: {result.get("error", "Unknown error")}', 'danger')
            
    except Exception as e:
        logger.exception(f"Backup error for device {device_id}: {e}")
        flash(f'Backup error: {str(e)}', 'danger')
    
    return redirect(url_for('main.device_detail', device_id=device.id))


# =============================================================================
# Schedule Routes
# =============================================================================

@main_bp.route('/schedules')
@login_required
def schedules():
    """List all schedules"""
    schedules = g.db_session.query(BackupSchedule).join(Device).order_by(
        Device.name, BackupSchedule.frequency
    ).all()
    
    return render_template('main/schedules.html', schedules=schedules)


@main_bp.route('/schedules/add', methods=['GET', 'POST'])
@login_required
def schedule_add():
    """Add new schedule"""
    form = ScheduleForm()
    
    devices = g.db_session.query(Device).filter(Device.is_active == True).order_by(Device.name).all()
    form.device_id.choices = [(d.id, f"{d.name} ({d.vendor})") for d in devices]
    
    if form.validate_on_submit():
        schedule = BackupSchedule(
            device_id=form.device_id.data,
            frequency=form.frequency.data,
            time_hour=form.time_hour.data,
            time_minute=form.time_minute.data,
            day_of_week=form.day_of_week.data if form.frequency.data == 'weekly' else None,
            day_of_month=form.day_of_month.data if form.frequency.data == 'monthly' else None,
            is_active=form.is_active.data
        )
        
        g.db_session.add(schedule)
        g.db_session.commit()
        
        device = g.db_session.query(Device).filter(Device.id == schedule.device_id).first()
        if schedule.is_active and device:
            scheduler = get_scheduler()
            scheduler.add_schedule(schedule, device)
        
        admin = get_current_admin(g.db_session)
        audit = get_audit_logger()
        audit.set_db_session(g.db_session)
        audit.log_schedule_add(admin.username, schedule.id, schedule.device_id)
        
        flash('Schedule added successfully!', 'success')
        return redirect(url_for('main.schedules'))
    
    return render_template('main/schedule_form.html', form=form, action='Add')


@main_bp.route('/schedules/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def schedule_edit(schedule_id):
    """Edit schedule"""
    schedule = g.db_session.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        abort(404)
    
    form = ScheduleForm(obj=schedule)
    
    devices = g.db_session.query(Device).filter(Device.is_active == True).order_by(Device.name).all()
    form.device_id.choices = [(d.id, f"{d.name} ({d.vendor})") for d in devices]
    
    if form.validate_on_submit():
        changes = {}
        
        if schedule.frequency != form.frequency.data:
            changes['frequency'] = {'old': schedule.frequency, 'new': form.frequency.data}
        if schedule.time_hour != form.time_hour.data:
            changes['time_hour'] = {'old': schedule.time_hour, 'new': form.time_hour.data}
        
        schedule.device_id = form.device_id.data
        schedule.frequency = form.frequency.data
        schedule.time_hour = form.time_hour.data
        schedule.time_minute = form.time_minute.data
        schedule.day_of_week = form.day_of_week.data if form.frequency.data == 'weekly' else None
        schedule.day_of_month = form.day_of_month.data if form.frequency.data == 'monthly' else None
        schedule.is_active = form.is_active.data
        
        g.db_session.commit()
        
        device = g.db_session.query(Device).filter(Device.id == schedule.device_id).first()
        scheduler = get_scheduler()
        
        if schedule.is_active and device:
            scheduler.update_schedule(schedule, device)
        else:
            scheduler.remove_schedule(schedule.id)
        
        admin = get_current_admin(g.db_session)
        audit = get_audit_logger()
        audit.set_db_session(g.db_session)
        audit.log_schedule_update(admin.username, schedule.id, changes)
        
        flash('Schedule updated successfully!', 'success')
        return redirect(url_for('main.schedules'))
    
    return render_template('main/schedule_form.html', form=form, schedule=schedule, action='Edit')


@main_bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def schedule_delete(schedule_id):
    """Delete schedule"""
    schedule = g.db_session.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        abort(404)
    
    scheduler = get_scheduler()
    scheduler.remove_schedule(schedule.id)
    
    g.db_session.delete(schedule)
    g.db_session.commit()
    
    flash('Schedule deleted successfully!', 'success')
    return redirect(url_for('main.schedules'))


# =============================================================================
# Server Status Route
# =============================================================================

@main_bp.route('/server-status')
@login_required
def server_status():
    """Server Status - Read-only observability page"""
    import subprocess
    import os
    import platform
    from pathlib import Path
    
    config = get_config()
    server_time = datetime.now()
    
    # Server Information
    server_info = {
        'hostname': platform.node(),
        'os': '',
        'kernel': platform.release(),
        'uptime': ''
    }
    
    # Get OS info
    try:
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    server_info['os'] = line.split('=')[1].strip().strip('"')
                    break
    except:
        server_info['os'] = f"{platform.system()} {platform.release()}"
    
    # Get server uptime - format: "2 days 3:31:17"
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            
            if days > 0:
                server_info['uptime'] = f"{days} days {hours}:{minutes:02d}:{seconds:02d}"
            else:
                server_info['uptime'] = f"{hours}:{minutes:02d}:{seconds:02d}"
    except:
        server_info['uptime'] = 'Unknown'
    
    # Service Information - LeuitCSS main service
    service_info = {
        'status': 'unknown',
        'uptime': 'N/A',
        'started_at': None,
        'memory_usage': None,
        'pid': None
    }
    
    try:
        result = subprocess.run(
            ['systemctl', 'show', 'leuitcss', '--no-pager', 
             '--property=ActiveState,MainPID,MemoryCurrent,ActiveEnterTimestamp'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            started_timestamp = None
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'ActiveState':
                        service_info['status'] = 'running' if value == 'active' else value
                    elif key == 'MainPID':
                        service_info['pid'] = value if value != '0' else None
                    elif key == 'MemoryCurrent':
                        if value and value != '[not set]':
                            try:
                                mem_bytes = int(value)
                                service_info['memory_usage'] = f"{mem_bytes / 1024 / 1024:.1f} MB"
                            except:
                                pass
                    elif key == 'ActiveEnterTimestamp':
                        if value and value not in ('n/a', ''):
                            service_info['started_at'] = value
                            started_timestamp = value
            
            # Calculate service uptime
            if service_info['status'] == 'running' and started_timestamp:
                try:
                    # Parse systemd timestamp: "Thu 2026-01-30 10:15:30 WIB"
                    # Remove timezone and parse
                    parts = started_timestamp.split()
                    if len(parts) >= 3:
                        date_str = parts[1]  # 2026-01-30
                        time_str = parts[2]  # 10:15:30
                        datetime_str = f"{date_str} {time_str}"
                        from datetime import datetime as dt
                        started_dt = dt.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                        now_dt = dt.now()
                        uptime_delta = now_dt - started_dt
                        
                        total_seconds = int(uptime_delta.total_seconds())
                        days = total_seconds // 86400
                        hours = (total_seconds % 86400) // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        
                        if days > 0:
                            service_info['uptime'] = f"{days} days {hours}:{minutes:02d}:{seconds:02d}"
                        else:
                            service_info['uptime'] = f"{hours}:{minutes:02d}:{seconds:02d}"
                except Exception as e:
                    logger.debug(f"Failed to parse service uptime: {e}")
    except:
        pass
    
    # FTP Service Information
    ftp_service_info = {
        'status': 'stopped',
        'uptime': 'N/A',
        'pid': None
    }
    
    try:
        result = subprocess.run(
            ['systemctl', 'show', 'leuitcss-ftp', '--no-pager',
             '--property=ActiveState,MainPID,ActiveEnterTimestamp'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            started_timestamp = None
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'ActiveState':
                        ftp_service_info['status'] = 'running' if value == 'active' else 'stopped'
                    elif key == 'MainPID':
                        ftp_service_info['pid'] = value if value != '0' else None
                    elif key == 'ActiveEnterTimestamp':
                        if value and value not in ('n/a', ''):
                            started_timestamp = value
            
            # Calculate FTP service uptime
            if ftp_service_info['status'] == 'running' and started_timestamp:
                try:
                    parts = started_timestamp.split()
                    if len(parts) >= 3:
                        date_str = parts[1]
                        time_str = parts[2]
                        datetime_str = f"{date_str} {time_str}"
                        from datetime import datetime as dt
                        started_dt = dt.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                        now_dt = dt.now()
                        uptime_delta = now_dt - started_dt
                        
                        total_seconds = int(uptime_delta.total_seconds())
                        days = total_seconds // 86400
                        hours = (total_seconds % 86400) // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        
                        if days > 0:
                            ftp_service_info['uptime'] = f"{days} days {hours}:{minutes:02d}:{seconds:02d}"
                        else:
                            ftp_service_info['uptime'] = f"{hours}:{minutes:02d}:{seconds:02d}"
                except:
                    pass
    except:
        pass
    
    # Resource Information
    resource_info = {
        'cpu_percent': 0,
        'memory_used': '0 GB',
        'memory_total': '0 GB',
        'memory_percent': 0,
        'disk_used': '0 GB',
        'disk_total': '0 GB',
        'disk_free': '0 GB',
        'disk_percent': 0
    }
    
    # CPU usage
    try:
        with open('/proc/stat', 'r') as f:
            cpu_line = f.readline()
            cpu_values = cpu_line.split()[1:8]
            cpu_values = [int(v) for v in cpu_values]
            idle = cpu_values[3]
            total = sum(cpu_values)
            resource_info['cpu_percent'] = round(((total - idle) / total) * 100, 1) if total > 0 else 0
    except:
        pass
    
    # Memory info
    try:
        with open('/proc/meminfo', 'r') as f:
            mem_info = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(':')
                    value = int(parts[1])  # in KB
                    mem_info[key] = value
            
            total_kb = mem_info.get('MemTotal', 0)
            available_kb = mem_info.get('MemAvailable', mem_info.get('MemFree', 0))
            used_kb = total_kb - available_kb
            
            resource_info['memory_total'] = f"{total_kb / 1024 / 1024:.1f} GB"
            resource_info['memory_used'] = f"{used_kb / 1024 / 1024:.1f} GB"
            resource_info['memory_percent'] = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0
    except:
        pass
    
    # Disk info
    try:
        statvfs = os.statvfs('/')
        total_bytes = statvfs.f_frsize * statvfs.f_blocks
        free_bytes = statvfs.f_frsize * statvfs.f_bavail
        used_bytes = total_bytes - free_bytes
        
        resource_info['disk_total'] = f"{total_bytes / 1024 / 1024 / 1024:.1f} GB"
        resource_info['disk_used'] = f"{used_bytes / 1024 / 1024 / 1024:.1f} GB"
        resource_info['disk_free'] = f"{free_bytes / 1024 / 1024 / 1024:.1f} GB"
        resource_info['disk_percent'] = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
    except:
        pass
    
    # Backup Storage Info
    backup_path = Path(config.STORAGE_PATH if hasattr(config, 'STORAGE_PATH') else '/var/lib/leuitcss/storage')
    backup_storage = {
        'path': str(backup_path),
        'total_size': '0 B',
        'total_files': 0,
        'avg_file_size': None,
        'oldest_backup': None,
        'newest_backup': None
    }
    
    try:
        if backup_path.exists():
            total_size = 0
            file_count = 0
            oldest_time = None
            newest_time = None
            
            for file_path in backup_path.rglob('*'):
                if file_path.is_file():
                    file_count += 1
                    stat = file_path.stat()
                    total_size += stat.st_size
                    mtime = stat.st_mtime
                    
                    if oldest_time is None or mtime < oldest_time:
                        oldest_time = mtime
                    if newest_time is None or mtime > newest_time:
                        newest_time = mtime
            
            backup_storage['total_files'] = file_count
            
            # Format size
            if total_size < 1024:
                backup_storage['total_size'] = f"{total_size} B"
            elif total_size < 1024 * 1024:
                backup_storage['total_size'] = f"{total_size / 1024:.1f} KB"
            elif total_size < 1024 * 1024 * 1024:
                backup_storage['total_size'] = f"{total_size / 1024 / 1024:.1f} MB"
            else:
                backup_storage['total_size'] = f"{total_size / 1024 / 1024 / 1024:.2f} GB"
            
            # Average file size
            if file_count > 0:
                avg_size = total_size / file_count
                if avg_size < 1024:
                    backup_storage['avg_file_size'] = f"{avg_size:.0f} B"
                elif avg_size < 1024 * 1024:
                    backup_storage['avg_file_size'] = f"{avg_size / 1024:.1f} KB"
                else:
                    backup_storage['avg_file_size'] = f"{avg_size / 1024 / 1024:.1f} MB"
            
            # Format dates
            if oldest_time:
                backup_storage['oldest_backup'] = datetime.fromtimestamp(oldest_time).strftime('%Y-%m-%d %H:%M')
            if newest_time:
                backup_storage['newest_backup'] = datetime.fromtimestamp(newest_time).strftime('%Y-%m-%d %H:%M')
    except:
        pass
    
    return render_template('main/server_status.html',
        server_time=server_time,
        server_info=server_info,
        service_info=service_info,
        ftp_service_info=ftp_service_info,
        resource_info=resource_info,
        backup_storage=backup_storage
    )


# =============================================================================
# FTP Settings Route (ZTE Ingestion)
# =============================================================================

@main_bp.route('/ftp-settings')
@login_required
def ftp_settings():
    """FTP Settings page for ZTE OLT backup ingestion"""
    import os
    import subprocess
    
    # Get FTP service status from systemd
    ftp_status = {
        'available': True,  # pyftpdlib check done at service level
        'enabled': False,
        'running': False,
        'port': 21,
        'root': os.environ.get('LEUITCSS_FTP_ROOT', '/var/lib/leuitcss/ftp-ingestion')
    }
    
    try:
        # Check if service is running
        result = subprocess.run(
            ['systemctl', 'is-active', 'leuitcss-ftp'],
            capture_output=True, text=True, timeout=5
        )
        ftp_status['running'] = result.stdout.strip() == 'active'
        ftp_status['enabled'] = ftp_status['running']
        
        # Check if service is enabled (auto-start)
        result2 = subprocess.run(
            ['systemctl', 'is-enabled', 'leuitcss-ftp'],
            capture_output=True, text=True, timeout=5
        )
        # enabled at boot vs currently running are different
    except:
        pass
    
    ftp_username = os.environ.get('LEUITCSS_FTP_USER', 'leuitcss')
    
    return render_template('main/ftp_settings.html',
        ftp_status=ftp_status,
        ftp_username=ftp_username
    )


@main_bp.route('/ftp-settings/update', methods=['POST'])
@login_required
def ftp_settings_update():
    """Update FTP settings - controls leuitcss-ftp systemd service"""
    import subprocess
    import shutil
    
    ftp_enabled = request.form.get('ftp_enabled') == 'on'
    
    # Find systemctl path
    systemctl_path = shutil.which('systemctl') or '/usr/bin/systemctl'
    logger.info(f"FTP control: enabled={ftp_enabled}, systemctl={systemctl_path}")
    
    operation_success = False
    error_message = None
    
    try:
        if ftp_enabled:
            # Start FTP service via systemd
            cmd = ['sudo', systemctl_path, 'start', 'leuitcss-ftp']
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            logger.info(f"Result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")
            
            if result.returncode == 0:
                flash('FTP server started on port 21.', 'success')
                operation_success = True
            else:
                error_message = result.stderr or 'Unknown error'
                logger.error(f"Failed to start FTP: {error_message}")
                flash(f'Failed to start FTP server: {error_message}', 'danger')
        else:
            # Stop FTP service via systemd
            cmd = ['sudo', systemctl_path, 'stop', 'leuitcss-ftp']
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            logger.info(f"Result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")
            
            if result.returncode == 0:
                flash('FTP server stopped.', 'success')
                operation_success = True
            else:
                error_message = result.stderr or 'Unknown error'
                logger.error(f"Failed to stop FTP: {error_message}")
                flash(f'Failed to stop FTP server: {error_message}', 'danger')
        
        # Log audit with actual result
        audit = get_audit_logger()
        admin_username = session.get('admin_username', 'admin')
        audit.log(
            action='ftp_settings_changed',
            actor_type='admin',
            actor_id=admin_username,
            resource_type='ftp_server',
            details={'enabled': ftp_enabled, 'port': 21},
            success=operation_success,
            error_message=error_message
        )
        
    except subprocess.TimeoutExpired:
        flash('FTP service control timed out.', 'danger')
        logger.error("FTP service control timed out")
    except Exception as e:
        logger.error(f"FTP settings update error: {e}")
        flash(f'Error updating FTP settings: {str(e)}', 'danger')
    
    return redirect(url_for('main.ftp_settings'))
