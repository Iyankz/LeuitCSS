"""
LeuitCSS v1.0.0 - Backup Scheduler
APScheduler-based auto backup scheduler

Scheduler Features:
- Daily, weekly, monthly schedules
- Custom time per device (HH:MM)
- Timezone follows server
- Max 1 retry on failure
- No looping

ACTIVE MODE: Scheduler truly executes backup operations
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from config import get_config
from app.models import Device, BackupSchedule
from app.collector import get_collector
from app.audit import get_audit_logger

# Configure logging
logger = logging.getLogger('leuitcss.scheduler')


class BackupSchedulerService:
    """
    APScheduler-based backup scheduler.
    
    This scheduler:
    - Runs per device
    - Supports daily/weekly/monthly schedules
    - Uses server timezone
    - Executes REAL backup operations (ACTIVE MODE)
    """
    
    def __init__(self, app=None, db_session_factory=None):
        self.config = get_config()
        self.db_session_factory = db_session_factory
        self.audit = get_audit_logger()
        
        # Configure APScheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers=5)
        }
        
        job_defaults = {
            'coalesce': True,  # Combine missed runs into one
            'max_instances': 1,  # Prevent concurrent runs of same job
            'misfire_grace_time': 3600  # 1 hour grace period
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )
        
        self._started = False
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
    
    def set_db_session_factory(self, factory):
        """Set database session factory"""
        self.db_session_factory = factory
    
    def _get_job_id(self, schedule_id: int) -> str:
        """Generate unique job ID for schedule"""
        return f"backup_schedule_{schedule_id}"
    
    def _build_cron_trigger(self, schedule: BackupSchedule) -> CronTrigger:
        """
        Build APScheduler CronTrigger from schedule configuration.
        
        Supports:
        - Daily: every day at HH:MM
        - Weekly: specific day(s) at HH:MM
        - Monthly: specific day at HH:MM
        """
        hour = schedule.time_hour
        minute = schedule.time_minute
        
        if schedule.frequency == 'daily':
            return CronTrigger(hour=hour, minute=minute)
        
        elif schedule.frequency == 'weekly':
            # day_of_week: "0,2,4" for Mon, Wed, Fri
            days = schedule.day_of_week or "0"  # Default Monday
            return CronTrigger(day_of_week=days, hour=hour, minute=minute)
        
        elif schedule.frequency == 'monthly':
            # day_of_month: "1" or "15" or "last"
            day = schedule.day_of_month or "1"
            if day.lower() == 'last':
                day = 'last'
            return CronTrigger(day=day, hour=hour, minute=minute)
        
        else:
            raise ValueError(f"Unsupported frequency: {schedule.frequency}")
    
    def _execute_backup(self, device_id: int, schedule_id: int):
        """
        Execute backup for a device (called by scheduler).
        
        This runs in a separate thread from APScheduler.
        """
        logger.info(f"Scheduler executing backup for device {device_id} (schedule {schedule_id})")
        
        if not self.db_session_factory:
            logger.error("Database session factory not set")
            return
        
        # Create new session for this thread
        db_session = self.db_session_factory()
        
        try:
            # Get device
            device = db_session.query(Device).filter(Device.id == device_id).first()
            
            if not device:
                logger.error(f"Device {device_id} not found")
                return
            
            if not device.is_active:
                logger.info(f"Device {device_id} is inactive, skipping backup")
                return
            
            # Execute backup
            collector = get_collector(db_session)
            result = collector.backup_device(device, triggered_by='scheduler')
            
            if result['success']:
                logger.info(f"Backup successful for device {device.name}: {result['file_path']}")
            else:
                logger.error(f"Backup failed for device {device.name}: {result['error']}")
            
            # Update schedule last_run
            schedule = db_session.query(BackupSchedule).filter(
                BackupSchedule.id == schedule_id
            ).first()
            
            if schedule:
                schedule.last_run = datetime.utcnow()
                # Calculate next run
                job = self.scheduler.get_job(self._get_job_id(schedule_id))
                if job:
                    schedule.next_run = job.next_run_time
                db_session.commit()
                
        except Exception as e:
            logger.exception(f"Error executing backup for device {device_id}: {e}")
            db_session.rollback()
            
        finally:
            db_session.close()
    
    def add_schedule(self, schedule: BackupSchedule, device: Device):
        """
        Add a backup schedule to the scheduler.
        
        Args:
            schedule: BackupSchedule model instance
            device: Device model instance
        """
        if not schedule.is_active:
            logger.info(f"Schedule {schedule.id} is inactive, not adding to scheduler")
            return
        
        job_id = self._get_job_id(schedule.id)
        
        # Remove existing job if any
        self.remove_schedule(schedule.id)
        
        try:
            trigger = self._build_cron_trigger(schedule)
            
            self.scheduler.add_job(
                func=self._execute_backup,
                trigger=trigger,
                id=job_id,
                name=f"Backup {device.name} ({schedule.frequency})",
                args=[device.id, schedule.id],
                replace_existing=True
            )
            
            logger.info(f"Added schedule {schedule.id} for device {device.name}")
            
            # Update next_run in schedule
            job = self.scheduler.get_job(job_id)
            if job and self.db_session_factory:
                db_session = self.db_session_factory()
                try:
                    db_schedule = db_session.query(BackupSchedule).filter(
                        BackupSchedule.id == schedule.id
                    ).first()
                    if db_schedule:
                        db_schedule.next_run = job.next_run_time
                        db_session.commit()
                finally:
                    db_session.close()
                    
        except Exception as e:
            logger.error(f"Failed to add schedule {schedule.id}: {e}")
    
    def remove_schedule(self, schedule_id: int):
        """Remove a schedule from the scheduler"""
        job_id = self._get_job_id(schedule_id)
        
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed schedule {schedule_id} from scheduler")
        except:
            pass  # Job might not exist
    
    def update_schedule(self, schedule: BackupSchedule, device: Device):
        """Update an existing schedule"""
        self.add_schedule(schedule, device)  # add_schedule handles replacement
    
    def load_all_schedules(self):
        """Load all active schedules from database"""
        if not self.db_session_factory:
            logger.error("Database session factory not set")
            return
        
        db_session = self.db_session_factory()
        
        try:
            schedules = db_session.query(BackupSchedule).filter(
                BackupSchedule.is_active == True
            ).all()
            
            for schedule in schedules:
                device = db_session.query(Device).filter(
                    Device.id == schedule.device_id,
                    Device.is_active == True
                ).first()
                
                if device:
                    self.add_schedule(schedule, device)
            
            logger.info(f"Loaded {len(schedules)} schedules")
            
        finally:
            db_session.close()
    
    def start(self):
        """Start the scheduler"""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("Backup scheduler started")
            
            # Load all schedules
            self.load_all_schedules()
    
    def stop(self):
        """Stop the scheduler"""
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Backup scheduler stopped")
    
    def get_jobs(self) -> List[dict]:
        """Get list of scheduled jobs"""
        jobs = []
        
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return jobs
    
    def trigger_now(self, schedule_id: int):
        """Trigger a schedule to run immediately"""
        job_id = self._get_job_id(schedule_id)
        job = self.scheduler.get_job(job_id)
        
        if job:
            # Run the job function directly in a thread
            from concurrent.futures import ThreadPoolExecutor
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(job.func, *job.args)
            logger.info(f"Triggered immediate backup for schedule {schedule_id}")
        else:
            logger.warning(f"Schedule {schedule_id} not found in scheduler")


# Singleton instance
_scheduler_instance = None


def get_scheduler() -> BackupSchedulerService:
    """Get singleton scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = BackupSchedulerService()
    return _scheduler_instance
