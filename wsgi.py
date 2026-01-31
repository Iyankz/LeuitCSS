"""
LeuitCSS v1.0.0 - WSGI Entry Point
For production deployment with Gunicorn
"""

from main import app

# WSGI application
application = app

if __name__ == '__main__':
    application.run()
