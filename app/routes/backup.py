"""
LeuitCSS v1.0.0 - Backup Routes
Backup history viewing, download, and statistics
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_file, Response, g

from app.auth import login_required
from app.models import Device, BackupHistory
from app.storage import get_storage

backup_bp = Blueprint('backup', __name__, url_prefix='/backups')


@backup_bp.route('/')
@login_required
def backup_list():
    """List all backup history"""
    vendor = request.args.get('vendor')
    device_id = request.args.get('device_id', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    query = g.db_session.query(BackupHistory)
    
    if vendor:
        query = query.filter(BackupHistory.vendor == vendor)
    if device_id:
        query = query.filter(BackupHistory.device_id == device_id)
    if status:
        query = query.filter(BackupHistory.status == status)
    
    query = query.order_by(BackupHistory.started_at.desc())
    
    total = query.count()
    backups = query.offset((page - 1) * per_page).limit(per_page).all()
    
    vendors = g.db_session.query(BackupHistory.vendor).distinct().all()
    vendors = [v[0] for v in vendors if v[0]]
    
    devices = g.db_session.query(Device).order_by(Device.name).all()
    
    return render_template('backup/list.html',
        backups=backups,
        vendors=vendors,
        devices=devices,
        current_vendor=vendor,
        current_device_id=device_id,
        current_status=status,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 1
    )


@backup_bp.route('/<int:backup_id>')
@login_required
def backup_detail(backup_id):
    """Backup detail page"""
    backup = g.db_session.query(BackupHistory).filter(BackupHistory.id == backup_id).first()
    if not backup:
        abort(404)
    
    storage = get_storage()
    metadata = None
    checksum_valid = None
    
    if backup.file_path:
        metadata = storage.get_metadata(backup.file_path)
        checksum_valid = storage.verify_checksum(backup.file_path)
    
    return render_template('backup/detail.html',
        backup=backup,
        metadata=metadata,
        checksum_valid=checksum_valid
    )


@backup_bp.route('/<int:backup_id>/download')
@login_required
def backup_download(backup_id):
    """Download backup file"""
    backup = g.db_session.query(BackupHistory).filter(BackupHistory.id == backup_id).first()
    if not backup:
        abort(404)
    
    if not backup.file_path:
        flash('Backup file not available.', 'warning')
        return redirect(url_for('backup.backup_detail', backup_id=backup_id))
    
    storage = get_storage()
    file_path = storage.get_absolute_path(backup.file_path)
    
    if not file_path.exists():
        flash('Backup file not found.', 'danger')
        return redirect(url_for('backup.backup_detail', backup_id=backup_id))
    
    timestamp = backup.started_at.strftime('%Y%m%d_%H%M%S')
    ext = file_path.suffix
    download_name = f"{backup.device_name}_{backup.vendor}_{timestamp}{ext}"
    
    return send_file(file_path, as_attachment=True, download_name=download_name)


@backup_bp.route('/<int:backup_id>/view')
@login_required
def backup_view(backup_id):
    """View backup content"""
    backup = g.db_session.query(BackupHistory).filter(BackupHistory.id == backup_id).first()
    if not backup:
        abort(404)
    
    if not backup.file_path:
        flash('Backup file not available.', 'warning')
        return redirect(url_for('backup.backup_detail', backup_id=backup_id))
    
    storage = get_storage()
    content = storage.get_backup(backup.file_path)
    
    if content is None:
        flash('Backup file not found.', 'danger')
        return redirect(url_for('backup.backup_detail', backup_id=backup_id))
    
    return render_template('backup/view.html', backup=backup, content=content)


@backup_bp.route('/<int:backup_id>/raw')
@login_required
def backup_raw(backup_id):
    """Get raw backup content"""
    backup = g.db_session.query(BackupHistory).filter(BackupHistory.id == backup_id).first()
    if not backup or not backup.file_path:
        abort(404)
    
    storage = get_storage()
    content = storage.get_backup(backup.file_path)
    
    if content is None:
        abort(404)
    
    return Response(content, mimetype='text/plain')


@backup_bp.route('/stats')
@login_required
def backup_stats():
    """Backup statistics page"""
    # Overall stats
    total_backups = g.db_session.query(BackupHistory).count()
    successful = g.db_session.query(BackupHistory).filter(BackupHistory.status == 'success').count()
    failed = g.db_session.query(BackupHistory).filter(BackupHistory.status == 'failed').count()
    timeout = g.db_session.query(BackupHistory).filter(BackupHistory.status == 'timeout').count()
    
    # Stats by vendor - using simple queries
    vendor_stats = []
    vendor_rows = g.db_session.query(BackupHistory.vendor).distinct().all()
    for row in vendor_rows:
        vendor_name = row[0]
        if vendor_name:
            total = g.db_session.query(BackupHistory).filter(BackupHistory.vendor == vendor_name).count()
            success = g.db_session.query(BackupHistory).filter(
                BackupHistory.vendor == vendor_name,
                BackupHistory.status == 'success'
            ).count()
            fail = g.db_session.query(BackupHistory).filter(
                BackupHistory.vendor == vendor_name,
                BackupHistory.status == 'failed'
            ).count()
            vendor_stats.append({
                'vendor': vendor_name,
                'total': total,
                'success': success,
                'failed': fail
            })
    
    # Stats by device - using simple queries
    device_stats = []
    device_rows = g.db_session.query(
        BackupHistory.device_name,
        BackupHistory.device_id
    ).distinct().all()
    for row in device_rows:
        device_name, device_id = row[0], row[1]
        if device_name:
            total = g.db_session.query(BackupHistory).filter(
                BackupHistory.device_id == device_id
            ).count()
            last = g.db_session.query(BackupHistory).filter(
                BackupHistory.device_id == device_id
            ).order_by(BackupHistory.started_at.desc()).first()
            device_stats.append({
                'device_name': device_name,
                'device_id': device_id,
                'total': total,
                'last_backup': last.started_at if last else None
            })
    
    # Storage stats
    storage = get_storage()
    storage_stats = storage.get_storage_stats()
    
    return render_template('backup/stats.html',
        total_backups=total_backups,
        successful=successful,
        failed=failed,
        timeout=timeout,
        vendor_stats=vendor_stats,
        device_stats=device_stats,
        storage_stats=storage_stats
    )


@backup_bp.route('/vendor/<vendor>')
@login_required
def backups_by_vendor(vendor):
    """Filter backups by vendor"""
    return redirect(url_for('backup.backup_list', vendor=vendor))


@backup_bp.route('/device/<int:device_id>')
@login_required
def backups_by_device(device_id):
    """Filter backups by device"""
    return redirect(url_for('backup.backup_list', device_id=device_id))
