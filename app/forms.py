"""
LeuitCSS v1.0.0 - Web Forms
WTForms for Web UI

Forms available:
- LoginForm: Admin login
- DeviceForm: Add/edit device (registration via Web UI)
- ScheduleForm: Add/edit backup schedule
- PasswordChangeForm: Change admin password

Note: All forms are for READ-ONLY system configuration.
NO forms for push/restore/edit config operations.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, IntegerField,
    TextAreaField, BooleanField, TimeField, HiddenField
)
from wtforms.validators import (
    DataRequired, Length, IPAddress, NumberRange, Optional,
    ValidationError, EqualTo
)

from config import get_config


class LoginForm(FlaskForm):
    """Admin login form"""
    username = StringField('Username', validators=[
        DataRequired(message="Username is required"),
        Length(min=3, max=50, message="Username must be between 3 and 50 characters")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required")
    ])


class DeviceForm(FlaskForm):
    """
    Device registration form.
    
    Allows adding devices for backup via Web UI.
    Does NOT allow configuration changes to devices.
    """
    name = StringField('Device Name', validators=[
        DataRequired(message="Device name is required"),
        Length(min=1, max=100, message="Name must be between 1 and 100 characters")
    ])
    
    description = TextAreaField('Description', validators=[
        Optional(),
        Length(max=500, message="Description cannot exceed 500 characters")
    ])
    
    # Vendor selection (LOCKED - only supported vendors)
    vendor = SelectField('Vendor', validators=[
        DataRequired(message="Vendor is required")
    ], choices=[
        ('mikrotik', 'MikroTik'),
        ('cisco', 'Cisco'),
        ('huawei', 'Huawei'),
        ('zte', 'ZTE'),
        ('juniper', 'Juniper'),
        ('generic', 'Generic (running-config)'),
        ('generic-saved', 'Generic (saved-config)'),
        ('generic-startup', 'Generic (startup-config)')
    ])
    
    ip_address = StringField('IP Address', validators=[
        DataRequired(message="IP address is required"),
        IPAddress(message="Invalid IP address format")
    ])
    
    port = IntegerField('Port (optional)', validators=[
        Optional(),
        NumberRange(min=1, max=65535, message="Port must be between 1 and 65535")
    ])
    
    # Connection type (limited per vendor)
    connection_type = SelectField('Connection Type', validators=[
        DataRequired(message="Connection type is required")
    ], choices=[
        ('ssh', 'SSH'),
        ('telnet', 'Telnet')
    ])
    
    username = StringField('Username', validators=[
        DataRequired(message="Username is required"),
        Length(min=1, max=100, message="Username must be between 1 and 100 characters")
    ])
    
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required")
    ])
    
    # Enable password (for Cisco devices)
    enable_password = PasswordField('Enable Password (Cisco only)', validators=[
        Optional()
    ])
    
    is_active = BooleanField('Active', default=True)
    
    def validate_connection_type(self, field):
        """Validate connection type is supported by vendor"""
        config = get_config()
        vendor_config = config.VENDOR_COMMANDS.get(self.vendor.data)
        
        if vendor_config:
            supported = vendor_config.get('connection_types', ['ssh'])
            if field.data not in supported:
                raise ValidationError(
                    f"{self.vendor.data} only supports: {', '.join(supported)}"
                )


class DeviceEditForm(DeviceForm):
    """
    Device edit form.
    
    Same as DeviceForm but password is optional (keep existing if not provided).
    """
    password = PasswordField('Password (leave blank to keep current)', validators=[
        Optional()
    ])
    
    enable_password = PasswordField('Enable Password (leave blank to keep current)', validators=[
        Optional()
    ])


class ScheduleForm(FlaskForm):
    """
    Backup schedule form.
    
    Supports daily, weekly, and monthly schedules.
    """
    device_id = SelectField('Device', validators=[
        DataRequired(message="Device is required")
    ], coerce=int)
    
    frequency = SelectField('Frequency', validators=[
        DataRequired(message="Frequency is required")
    ], choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ])
    
    time_hour = IntegerField('Hour (0-23)', validators=[
        DataRequired(message="Hour is required"),
        NumberRange(min=0, max=23, message="Hour must be between 0 and 23")
    ])
    
    time_minute = IntegerField('Minute (0-59)', validators=[
        DataRequired(message="Minute is required"),
        NumberRange(min=0, max=59, message="Minute must be between 0 and 59")
    ])
    
    # For weekly schedule
    day_of_week = StringField('Days of Week (0=Mon, 6=Sun, comma-separated)', validators=[
        Optional(),
        Length(max=20)
    ])
    
    # For monthly schedule
    day_of_month = StringField('Day of Month (1-31 or "last")', validators=[
        Optional(),
        Length(max=10)
    ])
    
    is_active = BooleanField('Active', default=True)
    
    def validate_day_of_week(self, field):
        """Validate day of week format for weekly schedule"""
        if self.frequency.data == 'weekly' and field.data:
            days = field.data.split(',')
            for day in days:
                day = day.strip()
                if not day.isdigit() or int(day) < 0 or int(day) > 6:
                    raise ValidationError(
                        "Days must be 0-6 (0=Monday, 6=Sunday), comma-separated"
                    )
    
    def validate_day_of_month(self, field):
        """Validate day of month format for monthly schedule"""
        if self.frequency.data == 'monthly' and field.data:
            value = field.data.strip().lower()
            if value != 'last':
                if not value.isdigit() or int(value) < 1 or int(value) > 31:
                    raise ValidationError(
                        "Day must be 1-31 or 'last'"
                    )


class PasswordChangeForm(FlaskForm):
    """Admin password change form"""
    current_password = PasswordField('Current Password', validators=[
        DataRequired(message="Current password is required")
    ])
    
    new_password = PasswordField('New Password', validators=[
        DataRequired(message="New password is required"),
        Length(min=8, message="Password must be at least 8 characters")
    ])
    
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(message="Please confirm your new password"),
        EqualTo('new_password', message="Passwords must match")
    ])


class SetupForm(FlaskForm):
    """Initial setup form for creating admin account"""
    username = StringField('Admin Username', validators=[
        DataRequired(message="Username is required"),
        Length(min=3, max=50, message="Username must be between 3 and 50 characters")
    ])
    
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required"),
        Length(min=8, message="Password must be at least 8 characters")
    ])
    
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password"),
        EqualTo('password', message="Passwords must match")
    ])
