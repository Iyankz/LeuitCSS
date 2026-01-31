"""
LeuitCSS v1.0.0 - Authentication Module
Single admin account authentication for Web UI

Features:
- Single admin account (as per spec)
- bcrypt password hashing
- Session-based authentication
- Login/logout audit logging
"""

import bcrypt
from datetime import datetime
from functools import wraps
from flask import session, redirect, url_for, flash, request

from app.models import Admin
from app.audit import get_audit_logger


class AuthService:
    """
    Authentication service for single admin account.
    
    Only one admin account is supported in v1.0.0.
    """
    
    def __init__(self, db_session=None):
        self.db_session = db_session
        self.audit = get_audit_logger()
    
    def set_db_session(self, db_session):
        """Set database session"""
        self.db_session = db_session
        self.audit.set_db_session(db_session)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode(), salt).decode()
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against bcrypt hash"""
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    
    def create_admin(self, username: str, password: str) -> Admin:
        """
        Create admin account.
        
        Note: Only one admin account is allowed in v1.0.0.
        This will raise an error if an admin already exists.
        """
        if not self.db_session:
            raise RuntimeError("Database session not set")
        
        # Check if admin already exists
        existing = self.db_session.query(Admin).first()
        if existing:
            raise ValueError("Admin account already exists. Only one admin is allowed in v1.0.0")
        
        admin = Admin(
            username=username,
            password_hash=self.hash_password(password),
            is_active=True
        )
        
        self.db_session.add(admin)
        self.db_session.commit()
        
        self.audit.log(
            action='admin_create',
            actor_type='system',
            actor_id='setup',
            resource_type='admin',
            resource_id=admin.id,
            details={'username': username}
        )
        
        return admin
    
    def authenticate(self, username: str, password: str) -> Admin:
        """
        Authenticate admin user.
        
        Returns:
            Admin object if authenticated, None otherwise
        """
        if not self.db_session:
            raise RuntimeError("Database session not set")
        
        admin = self.db_session.query(Admin).filter(
            Admin.username == username,
            Admin.is_active == True
        ).first()
        
        if not admin:
            self.audit.log_login(username, success=False, error_message="User not found")
            return None
        
        if not self.verify_password(password, admin.password_hash):
            self.audit.log_login(username, success=False, error_message="Invalid password")
            return None
        
        # Update last login
        admin.last_login = datetime.utcnow()
        self.db_session.commit()
        
        self.audit.log_login(username, success=True)
        
        return admin
    
    def change_password(self, admin: Admin, current_password: str, new_password: str) -> bool:
        """
        Change admin password.
        
        Args:
            admin: Admin object
            current_password: Current password for verification
            new_password: New password to set
        
        Returns:
            True if password changed successfully
        """
        if not self.verify_password(current_password, admin.password_hash):
            self.audit.log(
                action='password_change',
                actor_type='admin',
                actor_id=admin.username,
                success=False,
                error_message="Current password incorrect"
            )
            return False
        
        admin.password_hash = self.hash_password(new_password)
        self.db_session.commit()
        
        self.audit.log(
            action='password_change',
            actor_type='admin',
            actor_id=admin.username,
            success=True
        )
        
        return True
    
    def get_admin(self) -> Admin:
        """Get the single admin account"""
        if not self.db_session:
            raise RuntimeError("Database session not set")
        
        return self.db_session.query(Admin).filter(Admin.is_active == True).first()
    
    def admin_exists(self) -> bool:
        """Check if admin account exists"""
        if not self.db_session:
            return False
        return self.db_session.query(Admin).first() is not None


def login_required(f):
    """
    Decorator to require login for routes.
    
    Usage:
        @app.route('/dashboard')
        @login_required
        def dashboard():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_current_admin(db_session) -> Admin:
    """
    Get currently logged in admin from session.
    
    Returns:
        Admin object or None
    """
    admin_id = session.get('admin_id')
    if not admin_id:
        return None
    
    return db_session.query(Admin).filter(Admin.id == admin_id).first()


def login_admin(admin: Admin):
    """Store admin in session"""
    session['admin_id'] = admin.id
    session['admin_username'] = admin.username
    session.permanent = True


def logout_admin():
    """Clear admin from session"""
    username = session.get('admin_username')
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    return username


# Singleton instance
_auth_instance = None


def get_auth_service(db_session=None) -> AuthService:
    """Get singleton auth service instance"""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = AuthService(db_session)
    elif db_session:
        _auth_instance.set_db_session(db_session)
    return _auth_instance
