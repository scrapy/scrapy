"""Helper functions for working with templates"""

import os
import re
import string


def render_templatefile(path, **kwargs):
    with open(path, 'rb') as file:
        raw = file.read()

    content = string.Template(raw).substitute(**kwargs)

    with open(path.rstrip('.tmpl'), 'wb') as file:
        file.write(content)
    if path.endswith('.tmpl'):
        os.remove(path)

CAMELCASE_INVALID_CHARS = re.compile('[^a-zA-Z\d]')
def string_camelcase(string):
    """ Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub('', string.title())


def get_template_dir(settings, name="project"):
    if name == "project":
        folder_name = settings.get('TEMPLATES_PROJECT',
                                   settings['TEMPLATES_PROJECT_BASE'])
    else:
        folder_name = settings.get('TEMPLATES_SPIDERS',
                                   settings['TEMPLATES_SPIDERS_BASE'])
    if os.path.isabs(folder_name):
        return folder_name
    else:
        for base_dir in settings.getlist('TEMPLATES_DIR', settings['TEMPLATES_DIR_BASE']):
            path = os.path.join(base_dir, folder_name)
            if os.path.exists(path):
                return path
