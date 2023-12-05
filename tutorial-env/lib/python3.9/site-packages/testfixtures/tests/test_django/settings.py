SECRET_KEY = 'fake-key'
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    "testfixtures.tests.test_django",
]

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3'}}

DEFAULT_AUTO_FIELD='django.db.models.AutoField'
