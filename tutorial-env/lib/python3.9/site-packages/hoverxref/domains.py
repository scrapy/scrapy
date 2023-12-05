import docutils

from sphinx.util import logging

logger = logging.getLogger(__name__)


class HoverXRefBaseDomain:

    hoverxref_types = (
        'hoverxref',
        'hoverxreftooltip',
        'hoverxrefmodal',
    )

    def _inject_hoverxref_data(self, env, refnode, typ):
        classes = ['hoverxref']
        type_class = None
        if typ == 'hoverxreftooltip':
            type_class = 'tooltip'
            classes.append(type_class)
        elif typ == 'hoverxrefmodal':
            type_class = 'modal'
            classes.append(type_class)
        if not type_class:
            type_class = env.config.hoverxref_role_types.get(typ)
            if not type_class:
                default = env.config.hoverxref_default_type
                type_class = default
                logger.info(
                    'Using default style (%s) for unknown typ (%s). '
                    'Define it in hoverxref_role_types.',
                    default,
                    typ,
                )
            classes.append(type_class)

        refnode.replace_attr('classes', classes)
        # TODO: log something else here, so we can unique identify this node
        logger.debug(
            ':%s: _hoverxref injected. classes=%s',
            typ,
            classes,
        )

    def _is_ignored_ref(self, env, target):
        # HACK: skip all references if the builder is non-html. We shouldn't
        # have overridden the Domain in first instance at ``setup_domains``
        # function, but at that time ``app.builder`` is not yet initialized. If
        # we suscribe ourselves to ``builder-initied`` it's too late and our
        # override does not take effect. Other builders (e.g. LatexBuilder) may
        # fail with internal functions we use (e.g. builder.get_outfilename).
        # So, we are skipping it here :(
        if env.app.builder.format != 'html':
            return True

        if target in env.config.hoverxref_ignore_refs:
            logger.info(
                'Ignoring reference in hoverxref_ignore_refs. target=%s',
                target,
            )
            return True
        return False


class HoverXRefPythonDomainMixin(HoverXRefBaseDomain):

    def resolve_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        refnode = super().resolve_xref(env, fromdocname, builder, typ, target, node, contnode)
        if refnode is None:
            return refnode

        if self._is_ignored_ref(env, target):
            return refnode

        self._inject_hoverxref_data(env, refnode, typ)
        return refnode


class HoverXRefStandardDomainMixin(HoverXRefBaseDomain):
    """
    Mixin for ``StandardDomain`` to save the values after the xref resolution.

    ``:ref:`` are treating as a different node in Sphinx
    (``sphinx.addnodes.pending_xref``). These nodes are translated to regular
    ``docsutils.nodes.reference`` for this domain class.

    This class add the required ``hoverxref`` and ``modal``/``tooltip`` to tell
    the frontend to show a modal/tooltip on this element.
    """

    def resolve_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        if typ in self.hoverxref_types:
            resolver = self._resolve_ref_xref
            return resolver(env, fromdocname, builder, typ, target, node, contnode)

        return super().resolve_xref(env, fromdocname, builder, typ, target, node, contnode)

    # NOTE: We could override more ``_resolve_xref`` method apply hover in more places
    def _resolve_ref_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        refnode = super()._resolve_ref_xref(env, fromdocname, builder, typ, target, node, contnode)
        if refnode is None:
            return refnode

        if any([
                self._is_ignored_ref(env, target),
                not (env.config.hoverxref_auto_ref or typ in self.hoverxref_types)
        ]):
            return refnode


        self._inject_hoverxref_data(env, refnode, typ)
        return refnode

    def _resolve_obj_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        refnode = super()._resolve_obj_xref(env, fromdocname, builder, typ, target, node, contnode)
        if refnode is None:
            return refnode

        if any([
                self._is_ignored_ref(env, target),
                typ not in env.config.hoverxref_roles,
        ]):
            return refnode

        self._inject_hoverxref_data(env, refnode, typ)
        return refnode

    # TODO: combine this method with ``_resolve_obj_xref``
    def _resolve_numref_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        refnode = super()._resolve_numref_xref(env, fromdocname, builder, typ, target, node, contnode)
        if refnode is None:
            return refnode

        if any([
                self._is_ignored_ref(env, target),
                typ not in env.config.hoverxref_roles,
        ]):
            return refnode

        self._inject_hoverxref_data(env, refnode, typ)
        return refnode


class HoverXRefBibtexDomainMixin(HoverXRefBaseDomain):
    """
    Mixin for ``BibtexDomain`` to save the values after the xref resolution.

    This class add the required ``hoverxref`` and ``modal``/``tooltip`` to tell
    the frontend to show a modal/tooltip on this element.

    https://github.com/mcmtroffaes/sphinxcontrib-bibtex/blob/2.4.1/src/sphinxcontrib/bibtex/domain.py#L281
    """

    def resolve_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        textnode = super().resolve_xref(env, fromdocname, builder, typ, target, node, contnode)
        if textnode is None:
            return textnode

        if any([
                self._is_ignored_ref(env, target),
                not (env.config.hoverxref_auto_ref or typ in self.hoverxref_types or 'cite' in env.config.hoverxref_domains)
        ]):
            return textnode

        # The structure of the node generated by bibtex is between two
        # ``#text`` nodes and we need to add the classes into the ``reference``
        # node to get the ``href=`` attribute from it
        #
        # (Pdb++) textnode.children
        # [<#text: 'Nelson ['>, <reference: <#text: 'Nel87'>>, <#text: ']'>]
        refnode_index = textnode.first_child_matching_class(docutils.nodes.reference)
        if refnode_index:
            refnode = textnode.children[refnode_index]
            self._inject_hoverxref_data(env, refnode, typ)

        return textnode
