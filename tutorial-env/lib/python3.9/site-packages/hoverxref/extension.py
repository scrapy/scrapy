import os
import inspect
import types
from docutils import nodes
import sphinx
from sphinx.ext.intersphinx import InventoryAdapter
from sphinx.ext.intersphinx import missing_reference as sphinx_missing_reference
from sphinx.roles import XRefRole
from sphinx.util.fileutil import copy_asset
from sphinx.util import logging

from . import __version__
from .domains import (
    HoverXRefBaseDomain,
    HoverXRefBibtexDomainMixin,
    HoverXRefPythonDomainMixin,
    HoverXRefStandardDomainMixin,
)

logger = logging.getLogger(__name__)


HOVERXREF_ASSETS_FILES = [
    'js/hoverxref.js_t',  # ``_t`` tells Sphinx this is a template
]

TOOLTIP_ASSETS_FILES = [
    # Tooltipster's Styles
    'js/tooltipster.bundle.min.js',
    'css/tooltipster.custom.css',
    'css/tooltipster.bundle.min.css',

    # Tooltipster's Themes
    'css/tooltipster-sideTip-shadow.min.css',
    'css/tooltipster-sideTip-punk.min.css',
    'css/tooltipster-sideTip-noir.min.css',
    'css/tooltipster-sideTip-light.min.css',
    'css/tooltipster-sideTip-borderless.min.css',
]

MODAL_ASSETS_FILES = [
    'js/micromodal.min.js',
    'css/micromodal.css',
]

ASSETS_FILES = HOVERXREF_ASSETS_FILES + TOOLTIP_ASSETS_FILES + MODAL_ASSETS_FILES

def copy_asset_files(app, exception):
    """
    Copy all assets after build finished successfully.

    Assets that are templates (ends with ``_t``) are previously rendered using
    using all the configs starting with ``hoverxref_`` as a context.
    """
    if exception is None:  # build succeeded

        context = {}
        for attr in app.config.values:
            if attr.startswith('hoverxref_'):
                # First, add the default values to the context
                context[attr] = app.config.values[attr][0]

        for attr in dir(app.config):
            if attr.startswith('hoverxref_'):
                # Then, add the values that the user overrides
                context[attr] = getattr(app.config, attr)

        context['http_hoverxref_version'] = __version__

        # Finally, add some non-hoverxref extra configs
        configs = ['html_theme']
        for attr in configs:
            context[attr] = getattr(app.config, attr)

        for f in ASSETS_FILES:
            path = os.path.join(os.path.dirname(__file__), '_static', f)
            copy_asset(
                path,
                os.path.join(app.outdir, '_static', f.split('.')[-1].replace('js_t', 'js')),
                context=context,
            )


def setup_domains(app, config):
    """
    Override domains respecting the one defined (if any).

    We create a new class by inheriting the Sphinx Domain already defined
    and our own ``HoverXRef...DomainMixin`` that includes the logic for
    ``_hoverxref`` attributes.
    """
    # Add ``hoverxref`` role replicating the behavior of ``ref``
    for role in HoverXRefBaseDomain.hoverxref_types:
        app.add_role_to_domain(
            'std',
            role,
            XRefRole(
                lowercase=True,
                innernodeclass=nodes.inline,
                warn_dangling=True,
            ),
        )

    domain = types.new_class(
        'HoverXRefStandardDomain',
        (
            HoverXRefStandardDomainMixin,
            app.registry.domains.get('std'),
        ),
        {}
    )
    app.add_domain(domain, override=True)

    if 'py' in app.config.hoverxref_domains:
        domain = types.new_class(
            'HoverXRefPythonDomain',
            (
                HoverXRefPythonDomainMixin,
                app.registry.domains.get('py'),
            ),
            {}
        )
        app.add_domain(domain, override=True)

    if 'cite' in app.config.hoverxref_domains:
        domain = types.new_class(
            'HoverXRefBibtexDomain',
            (
                HoverXRefBibtexDomainMixin,
                app.registry.domains.get('cite'),
            ),
            {}
        )
        app.add_domain(domain, override=True)


def setup_sphinx_tabs(app, config):
    """
    Disconnect ``update_context`` function from ``sphinx-tabs``.

    Sphinx Tabs removes the CSS/JS from pages that does not use the directive.
    Although, we need them to use inside the tooltip.
    """
    if sphinx.version_info < (3, 0, 0):
        listeners = list(app.events.listeners.get('html-page-context').items())
    else:
        listeners = [
            (listener.id, listener.handler)
            for listener in app.events.listeners.get('html-page-context')
        ]
    for listener_id, function in listeners:
        module_name = inspect.getmodule(function).__name__
        if module_name == 'sphinx_tabs.tabs':
            app.disconnect(listener_id)


def setup_intersphinx(app, config):
    """
    Disconnect ``missing-reference`` from ``sphinx.ext.intershinx``.

    As there is no way to hook into the ``missing_referece`` function to add
    some extra data to the docutils node returned by this function, we
    disconnect the original listener and add our custom one.

    https://github.com/sphinx-doc/sphinx/blob/53c1dff/sphinx/ext/intersphinx.py
    """
    if not app.config.hoverxref_intersphinx:
        # Do not disconnect original intersphinx missing-reference if the user
        # does not have hoverxref intersphinx enabled
        return

    if sphinx.version_info < (3, 0, 0):
        listeners = list(app.events.listeners.get('missing-reference').items())
    else:
        listeners = [
            (listener.id, listener.handler)
            for listener in app.events.listeners.get('missing-reference')
        ]
    for listener_id, function in listeners:
        module_name = inspect.getmodule(function).__name__
        if module_name == 'sphinx.ext.intersphinx':
            app.disconnect(listener_id)


def missing_reference(app, env, node, contnode):
    """
    Override original ``missing_referece`` to add data into the node.

    We call the original intersphinx extension and add hoverxref CSS classes
    plus the ``data-url`` to the node returned from it.

    Sphinx intersphinx downloads all the ``objects.inv`` and load each of them
    into a "named inventory" and also updates the "main inventory". We check if
    reference is part of any of the "named invetories" the user defined in
    ``hoverxref_intersphinx`` and we add hoverxref to the node **only if** the
    reference is on those inventories.

    See https://github.com/sphinx-doc/sphinx/blob/4d90277c/sphinx/ext/intersphinx.py#L244-L250
    """
    if not app.config.hoverxref_intersphinx or 'sphinx.ext.intersphinx' not in app.config.extensions:
        # Do nothing if the user doesn't have hoverxref intersphinx enabled
        return

    # We need to grab all the attributes before calling
    # ``sphinx_missing_reference`` because it modifies the node in-place
    domain = node.get('refdomain')  # ``std`` if used on ``:ref:``
    target = node['reftarget']
    reftype = node['reftype']

    # By default we skip adding hoverxref to the node to avoid possible
    # problems. We want to be sure we have to add hoverxref on it
    skip_node = True
    inventory_name_matched = None

    if domain == 'std':
        # Using ``:ref:`` manually, we could write intersphinx like:
        # :ref:`datetime <python:datetime.datetime>`
        # and the node will have these attribues:
        #   refdomain: std
        #   reftype: ref
        #   reftarget: python:datetime.datetime
        #   refexplicit: True
        if ':' in target:
            inventory_name, _ = target.split(':', 1)
            if inventory_name in app.config.hoverxref_intersphinx:
                skip_node = False
                inventory_name_matched = inventory_name
    else:
        # Using intersphinx via ``sphinx.ext.autodoc`` generates links for docstrings like:
        # :py:class:`float`
        # and the node will have these attribues:
        #   refdomain: py
        #   reftype: class
        #   reftarget: float
        #   refexplicit: False
        inventories = InventoryAdapter(env)

        for inventory_name in app.config.hoverxref_intersphinx:
            inventory = inventories.named_inventory.get(inventory_name, {})
            # Logic of `.objtypes_for_role` stolen from
            # https://github.com/sphinx-doc/sphinx/blob/b8789b4c/sphinx/ext/intersphinx.py#L397
            objtypes_for_role = env.get_domain(domain).objtypes_for_role(reftype)

            # If the reftype is not defined on the domain, we skip it
            if not objtypes_for_role:
                continue

            for objtype in objtypes_for_role:
                inventory_member = inventory.get(f'{domain}:{objtype}')

                if inventory_member and inventory_member.get(target) is not None:
                    # The object **does** exist on the inventories defined by the
                    # user: enable hoverxref on this node
                    skip_node = False
                    inventory_name_matched = inventory_name
                    break

    newnode = sphinx_missing_reference(app, env, node, contnode)
    if newnode is not None and not skip_node:
        hoverxref_type = app.config.hoverxref_intersphinx_types.get(inventory_name_matched)
        if isinstance(hoverxref_type, dict):
            # Specific style for a particular reftype
            hoverxref_type = hoverxref_type.get(reftype)
        hoverxref_type = hoverxref_type or app.config.hoverxref_default_type

        classes = newnode.get('classes')
        classes.extend(['hoverxref', hoverxref_type])
        newnode.replace_attr('classes', classes)

    return newnode


def setup_theme(app, exception):
    """
    Auto-configure default settings for known themes.

    Add a small custom CSS file for a specific theme and set hoverxref configs
    (if not overwritten by the user) with better defaults for these themes.
    """
    css_file = None
    theme = app.config.html_theme
    default, rebuild, types = app.config.values.get('hoverxref_modal_class')
    if theme == 'sphinx_material':
        if app.config.hoverxref_modal_class == default:
            app.config.hoverxref_modal_class = 'md-typeset'
            css_file = 'css/sphinx_material.css'
    elif theme == 'alabaster':
        if app.config.hoverxref_modal_class == default:
            app.config.hoverxref_modal_class = 'body'
            css_file = 'css/alabaster.css'
    elif theme == 'sphinx_rtd_theme':
        if app.config.hoverxref_modal_class == default:
            css_file = 'css/sphinx_rtd_theme.css'

    if css_file:
        app.add_css_file(css_file)
        path = os.path.join(os.path.dirname(__file__), '_static', css_file)
        copy_asset(
            path,
            os.path.join(app.outdir, '_static', 'css'),
        )


def setup_assets_policy(app, exception):
    """Tell Sphinx to always include assets in all HTML pages."""
    if hasattr(app, 'set_html_assets_policy'):
        # ``app.set_html_assets_policy`` was introduced in Sphinx 4.1.0
        # https://github.com/sphinx-doc/sphinx/pull/9174
        app.set_html_assets_policy('always')


def deprecated_configs_warning(app, exception):
    """Log warning message if old configs are used."""
    default, rebuild, types = app.config.values.get('hoverxref_tooltip_api_host')
    if app.config.hoverxref_tooltip_api_host != default:
        message = '"hoverxref_tooltip_api_host" is deprecated and replaced by "hoverxref_api_host".'
        logger.warning(message)
        app.config.hoverxref_api_host = app.config.hoverxref_tooltip_api_host



def setup(app):
    """Setup ``hoverxref`` Sphinx extension."""

    # ``override`` was introduced in 1.8
    app.require_sphinx('1.8')

    app.add_config_value('hoverxref_auto_ref', False, 'env')
    app.add_config_value('hoverxref_mathjax', False, 'env')
    app.add_config_value('hoverxref_sphinxtabs', False, 'env')
    app.add_config_value('hoverxref_roles', [], 'env')
    app.add_config_value('hoverxref_domains', [], 'env')
    app.add_config_value('hoverxref_ignore_refs', ['genindex', 'modindex', 'search'], 'env')
    app.add_config_value('hoverxref_role_types', {}, 'env')
    app.add_config_value('hoverxref_default_type', 'tooltip', 'env')
    app.add_config_value('hoverxref_intersphinx', [], 'env')
    app.add_config_value('hoverxref_intersphinx_types', {}, 'env')
    app.add_config_value('hoverxref_api_host', 'https://readthedocs.org', 'env')
    app.add_config_value('hoverxref_sphinx_version', sphinx.__version__, 'env')

    # Tooltipster settings
    # Deprecated in favor of ``hoverxref_api_host``
    app.add_config_value('hoverxref_tooltip_api_host', 'https://readthedocs.org', 'env')
    app.add_config_value('hoverxref_tooltip_theme', ['tooltipster-shadow', 'tooltipster-shadow-custom'], 'env')
    app.add_config_value('hoverxref_tooltip_interactive', True, 'env')
    app.add_config_value('hoverxref_tooltip_maxwidth', 450, 'env')
    app.add_config_value('hoverxref_tooltip_side', 'right', 'env')
    app.add_config_value('hoverxref_tooltip_animation', 'fade', 'env')
    app.add_config_value('hoverxref_tooltip_animation_duration', 0, 'env')
    app.add_config_value('hoverxref_tooltip_content', 'Loading...', 'env')
    app.add_config_value('hoverxref_tooltip_class', 'rst-content', 'env')

    # MicroModal settings
    app.add_config_value('hoverxref_modal_hover_delay', 350, 'env')
    app.add_config_value('hoverxref_modal_class', 'rst-content', 'env')
    app.add_config_value('hoverxref_modal_onshow_function', None, 'env')
    app.add_config_value('hoverxref_modal_openclass', 'is-open', 'env')
    app.add_config_value('hoverxref_modal_disable_focus', True, 'env')
    app.add_config_value('hoverxref_modal_disable_scroll', False, 'env')
    app.add_config_value('hoverxref_modal_awaitopenanimation', False, 'env')
    app.add_config_value('hoverxref_modal_awaitcloseanimation', False, 'env')
    app.add_config_value('hoverxref_modal_debugmode', False, 'env')
    app.add_config_value('hoverxref_modal_default_title', 'Note', 'env')
    app.add_config_value('hoverxref_modal_prefix_title', '📝 ', 'env')

    app.connect('config-inited', deprecated_configs_warning)

    app.connect('config-inited', setup_domains)
    app.connect('config-inited', setup_sphinx_tabs)
    app.connect('config-inited', setup_intersphinx)
    app.connect('config-inited', setup_theme)
    app.connect('config-inited', setup_assets_policy)
    app.connect('build-finished', copy_asset_files)

    app.connect('missing-reference', missing_reference)

    for f in ASSETS_FILES:
        if f.endswith('.js') or f.endswith('.js_t'):
            app.add_js_file(f.replace('.js_t', '.js'))
        if f.endswith('.css'):
            app.add_css_file(f)

    return {
        'version': __version__,
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
