"""
LeuitCSS v1.0.0 - Authentication Routes
Login, logout, and setup routes

Routes:
- /login: Admin login
- /logout: Admin logout
- /setup: Initial admin account creation
- /change-password: Change admin password
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g

from app.forms import LoginForm, SetupForm, PasswordChangeForm
from app.auth import (
    get_auth_service, login_admin, logout_admin, 
    login_required, get_current_admin
)
from app.audit import get_audit_logger

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    # Check if already logged in
    if 'admin_id' in session:
        return redirect(url_for('main.dashboard'))
    
    # Check if setup is needed
    auth_service = get_auth_service(g.db_session)
    
    if not auth_service.admin_exists():
        return redirect(url_for('auth.setup'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        admin = auth_service.authenticate(form.username.data, form.password.data)
        
        if admin:
            login_admin(admin)
            flash('Login successful!', 'success')
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Admin logout"""
    username = logout_admin()
    
    if username:
        audit = get_audit_logger()
        audit.set_db_session(g.db_session)
        audit.log_logout(username)
    
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/setup')
def setup():
    """System not initialized - show CLI instructions"""
    auth_service = get_auth_service(g.db_session)
    
    # Redirect if admin already exists
    if auth_service.admin_exists():
        return redirect(url_for('auth.login'))
    
    return render_template('auth/setup.html')


@auth_bp.route('/forgot-password')
def forgot_password():
    """Forgot password - show CLI instructions"""
    return render_template('auth/forgot_password.html')


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change admin password"""
    form = PasswordChangeForm()
    admin = get_current_admin(g.db_session)
    
    if form.validate_on_submit():
        auth_service = get_auth_service(g.db_session)
        
        if auth_service.change_password(
            admin=admin,
            current_password=form.current_password.data,
            new_password=form.new_password.data
        ):
            flash('Password changed successfully!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Current password is incorrect.', 'danger')
    
    return render_template('auth/change_password.html', form=form)
