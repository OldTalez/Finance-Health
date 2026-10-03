"""
WSGI config for Finance Platform API.
"""

import os
import sys
from pathlib import Path

# Add current directory to Python path so imports work
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

application = get_wsgi_application()
