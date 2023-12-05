import os

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testfixtures.tests.test_django.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line()

if __name__ == "__main__": # pragma: no cover
    main()
