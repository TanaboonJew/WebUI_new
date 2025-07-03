#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import django

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'WebUI.settings')

    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        import django
        django.setup()

        from core.scheduler import start_scheduler
        start_scheduler()

    try:
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

if __name__ == '__main__':
    main()
