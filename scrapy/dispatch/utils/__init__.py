"""This module is used to port the utils required by the django signals API over
from django.utils. Originally written by the Django project.
"""

from scrapy.dispatch.utils.inspect import func_accepts_kwargs
from scrapy.dispatch.utils.robustapply import robust_apply
