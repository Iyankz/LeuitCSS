"""
LeuitCSS v1.0.0 - Application Package
Active Configuration Backup System with Read-Only Access

This package contains:
- models: Database models (SQLAlchemy)
- adapters: Vendor-specific connection adapters
- collector: Backup collection engine
- storage: Immutable storage manager
- scheduler: APScheduler-based auto backup
- auth: Single admin authentication
- audit: Dual audit logging (file + DB)
- encryption: AES-256 credential encryption
- forms: WTForms for Web UI
"""

__version__ = '1.0.0'
__description__ = 'Active Configuration Backup System with Read-Only Access'
