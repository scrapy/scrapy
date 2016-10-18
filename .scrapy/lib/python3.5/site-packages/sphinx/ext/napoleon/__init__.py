# -*- coding: utf-8 -*-
"""
    sphinx.ext.napoleon
    ~~~~~~~~~~~~~~~~~~~

    Support for NumPy and Google style docstrings.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import sys

from six import PY2, iteritems

import sphinx
from sphinx.ext.napoleon.docstring import GoogleDocstring, NumpyDocstring


class Config(object):
    """Sphinx napoleon extension settings in `conf.py`.

    Listed below are all the settings used by napoleon and their default
    values. These settings can be changed in the Sphinx `conf.py` file. Make
    sure that both "sphinx.ext.autodoc" and "sphinx.ext.napoleon" are
    enabled in `conf.py`::

        # conf.py

        # Add any Sphinx extension module names here, as strings
        extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']

        # Napoleon settings
        napoleon_google_docstring = True
        napoleon_numpy_docstring = True
        napoleon_include_private_with_doc = False
        napoleon_include_special_with_doc = False
        napoleon_use_admonition_for_examples = False
        napoleon_use_admonition_for_notes = False
        napoleon_use_admonition_for_references = False
        napoleon_use_ivar = False
        napoleon_use_param = True
        napoleon_use_rtype = True

    .. _Google style:
       http://google.github.io/styleguide/pyguide.html
    .. _NumPy style:
       https://github.com/numpy/numpy/blob/master/doc/HOWTO_DOCUMENT.rst.txt

    Attributes
    ----------
    napoleon_google_docstring : bool, defaults to True
        True to parse `Google style`_ docstrings. False to disable support
        for Google style docstrings.
    napoleon_numpy_docstring : bool, defaults to True
        True to parse `NumPy style`_ docstrings. False to disable support
        for NumPy style docstrings.
    napoleon_include_private_with_doc : bool, defaults to False
        True to include private members (like ``_membername``) with docstrings
        in the documentation. False to fall back to Sphinx's default behavior.

        **If True**::

            def _included(self):
                \"\"\"
                This will be included in the docs because it has a docstring
                \"\"\"
                pass

            def _skipped(self):
                # This will NOT be included in the docs
                pass

    napoleon_include_special_with_doc : bool, defaults to False
        True to include special members (like ``__membername__``) with
        docstrings in the documentation. False to fall back to Sphinx's
        default behavior.

        **If True**::

            def __str__(self):
                \"\"\"
                This will be included in the docs because it has a docstring
                \"\"\"
                return unicode(self).encode('utf-8')

            def __unicode__(self):
                # This will NOT be included in the docs
                return unicode(self.__class__.__name__)

    napoleon_use_admonition_for_examples : bool, defaults to False
        True to use the ``.. admonition::`` directive for the **Example** and
        **Examples** sections. False to use the ``.. rubric::`` directive
        instead. One may look better than the other depending on what HTML
        theme is used.

        This `NumPy style`_ snippet will be converted as follows::

            Example
            -------
            This is just a quick example

        **If True**::

            .. admonition:: Example

               This is just a quick example

        **If False**::

            .. rubric:: Example

            This is just a quick example

    napoleon_use_admonition_for_notes : bool, defaults to False
        True to use the ``.. admonition::`` directive for **Notes** sections.
        False to use the ``.. rubric::`` directive instead.

        Note
        ----
        The singular **Note** section will always be converted to a
        ``.. note::`` directive.

        See Also
        --------
        :attr:`napoleon_use_admonition_for_examples`

    napoleon_use_admonition_for_references : bool, defaults to False
        True to use the ``.. admonition::`` directive for **References**
        sections. False to use the ``.. rubric::`` directive instead.

        See Also
        --------
        :attr:`napoleon_use_admonition_for_examples`

    napoleon_use_ivar : bool, defaults to False
        True to use the ``:ivar:`` role for instance variables. False to use
        the ``.. attribute::`` directive instead.

        This `NumPy style`_ snippet will be converted as follows::

            Attributes
            ----------
            attr1 : int
                Description of `attr1`

        **If True**::

            :ivar attr1: Description of `attr1`
            :vartype attr1: int

        **If False**::

            .. attribute:: attr1

               *int*

               Description of `attr1`

    napoleon_use_param : bool, defaults to True
        True to use a ``:param:`` role for each function parameter. False to
        use a single ``:parameters:`` role for all the parameters.

        This `NumPy style`_ snippet will be converted as follows::

            Parameters
            ----------
            arg1 : str
                Description of `arg1`
            arg2 : int, optional
                Description of `arg2`, defaults to 0

        **If True**::

            :param arg1: Description of `arg1`
            :type arg1: str
            :param arg2: Description of `arg2`, defaults to 0
            :type arg2: int, optional

        **If False**::

            :parameters: * **arg1** (*str*) --
                           Description of `arg1`
                         * **arg2** (*int, optional*) --
                           Description of `arg2`, defaults to 0

    napoleon_use_rtype : bool, defaults to True
        True to use the ``:rtype:`` role for the return type. False to output
        the return type inline with the description.

        This `NumPy style`_ snippet will be converted as follows::

            Returns
            -------
            bool
                True if successful, False otherwise

        **If True**::

            :returns: True if successful, False otherwise
            :rtype: bool

        **If False**::

            :returns: *bool* -- True if successful, False otherwise

    """
    _config_values = {
        'napoleon_google_docstring': (True, 'env'),
        'napoleon_numpy_docstring': (True, 'env'),
        'napoleon_include_private_with_doc': (False, 'env'),
        'napoleon_include_special_with_doc': (False, 'env'),
        'napoleon_use_admonition_for_examples': (False, 'env'),
        'napoleon_use_admonition_for_notes': (False, 'env'),
        'napoleon_use_admonition_for_references': (False, 'env'),
        'napoleon_use_ivar': (False, 'env'),
        'napoleon_use_param': (True, 'env'),
        'napoleon_use_rtype': (True, 'env'),
    }

    def __init__(self, **settings):
        for name, (default, rebuild) in iteritems(self._config_values):
            setattr(self, name, default)
        for name, value in iteritems(settings):
            setattr(self, name, value)


def setup(app):
    """Sphinx extension setup function.

    When the extension is loaded, Sphinx imports this module and executes
    the ``setup()`` function, which in turn notifies Sphinx of everything
    the extension offers.

    Parameters
    ----------
    app : sphinx.application.Sphinx
        Application object representing the Sphinx process

    See Also
    --------
    `The Sphinx documentation on Extensions
    <http://sphinx-doc.org/extensions.html>`_

    `The Extension Tutorial <http://sphinx-doc.org/extdev/tutorial.html>`_

    `The Extension API <http://sphinx-doc.org/extdev/appapi.html>`_

    """
    from sphinx.application import Sphinx
    if not isinstance(app, Sphinx):
        return  # probably called by tests

    app.connect('autodoc-process-docstring', _process_docstring)
    app.connect('autodoc-skip-member', _skip_member)

    for name, (default, rebuild) in iteritems(Config._config_values):
        app.add_config_value(name, default, rebuild)
    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}


def _process_docstring(app, what, name, obj, options, lines):
    """Process the docstring for a given python object.

    Called when autodoc has read and processed a docstring. `lines` is a list
    of docstring lines that `_process_docstring` modifies in place to change
    what Sphinx outputs.

    The following settings in conf.py control what styles of docstrings will
    be parsed:

    * ``napoleon_google_docstring`` -- parse Google style docstrings
    * ``napoleon_numpy_docstring`` -- parse NumPy style docstrings

    Parameters
    ----------
    app : sphinx.application.Sphinx
        Application object representing the Sphinx process.
    what : str
        A string specifying the type of the object to which the docstring
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : str
        The fully qualified name of the object.
    obj : module, class, exception, function, method, or attribute
        The object to which the docstring belongs.
    options : sphinx.ext.autodoc.Options
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.
    lines : list of str
        The lines of the docstring, see above.

        .. note:: `lines` is modified *in place*

    """
    result_lines = lines
    if app.config.napoleon_numpy_docstring:
        docstring = NumpyDocstring(result_lines, app.config, app, what, name,
                                   obj, options)
        result_lines = docstring.lines()
    if app.config.napoleon_google_docstring:
        docstring = GoogleDocstring(result_lines, app.config, app, what, name,
                                    obj, options)
        result_lines = docstring.lines()
    lines[:] = result_lines[:]


def _skip_member(app, what, name, obj, skip, options):
    """Determine if private and special class members are included in docs.

    The following settings in conf.py determine if private and special class
    members are included in the generated documentation:

    * ``napoleon_include_private_with_doc`` --
      include private members if they have docstrings
    * ``napoleon_include_special_with_doc`` --
      include special members if they have docstrings

    Parameters
    ----------
    app : sphinx.application.Sphinx
        Application object representing the Sphinx process
    what : str
        A string specifying the type of the object to which the member
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : str
        The name of the member.
    obj : module, class, exception, function, method, or attribute.
        For example, if the member is the __init__ method of class A, then
        `obj` will be `A.__init__`.
    skip : bool
        A boolean indicating if autodoc will skip this member if `_skip_member`
        does not override the decision
    options : sphinx.ext.autodoc.Options
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.

    Returns
    -------
    bool
        True if the member should be skipped during creation of the docs,
        False if it should be included in the docs.

    """
    has_doc = getattr(obj, '__doc__', False)
    is_member = (what == 'class' or what == 'exception' or what == 'module')
    if name != '__weakref__' and name != '__init__' and has_doc and is_member:
        cls_is_owner = False
        if what == 'class' or what == 'exception':
            if PY2:
                cls = getattr(obj, 'im_class', getattr(obj, '__objclass__',
                              None))
                cls_is_owner = (cls and hasattr(cls, name) and
                                name in cls.__dict__)
            elif sys.version_info >= (3, 3):
                qualname = getattr(obj, '__qualname__', '')
                cls_path, _, _ = qualname.rpartition('.')
                if cls_path:
                    try:
                        if '.' in cls_path:
                            import importlib
                            import functools

                            mod = importlib.import_module(obj.__module__)
                            mod_path = cls_path.split('.')
                            cls = functools.reduce(getattr, mod_path, mod)
                        else:
                            cls = obj.__globals__[cls_path]
                    except Exception:
                        cls_is_owner = False
                    else:
                        cls_is_owner = (cls and hasattr(cls, name) and
                                        name in cls.__dict__)
                else:
                    cls_is_owner = False
            else:
                cls_is_owner = True

        if what == 'module' or cls_is_owner:
            is_special = name.startswith('__') and name.endswith('__')
            is_private = not is_special and name.startswith('_')
            inc_special = app.config.napoleon_include_special_with_doc
            inc_private = app.config.napoleon_include_private_with_doc
            if (is_special and inc_special) or (is_private and inc_private):
                return False
    return skip
