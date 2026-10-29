"""Entry point for production servers.

Render:          gunicorn wsgi:app
PythonAnywhere:  from wsgi import app as application   (in the WSGI file)
"""

from app import create_app

app = create_app()
