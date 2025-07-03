#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'WebUI.settings')

    try:
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # ✅ เรียก start_scheduler เฉพาะเมื่อใช้ runserver เท่านั้น
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        import django
        django.setup()

        from core.scheduler import start_scheduler
        start_scheduler()


if __name__ == '__main__':
    main()
