import docutils
import re
import sphinx

# Sphinx <2 Compatibility
if sphinx.version_info >= (2, 0):
    from sphinx.builders.dirhtml import DirectoryHTMLBuilder
else:
    from sphinx.builders.html import DirectoryHTMLBuilder


def replace_uris(app, doctree, nodetype, nodeattr):
    """
    Replace ``nodetype`` URIs from ``doctree`` to the proper one.

    If ``nodetype`` is an image (``docutils.nodes.image``), the URL is prefixed
    with ``Builder.imagedir`` and the original image path is added to
    ``Builder.images`` so it's copied using Sphinx's internals before
    finalizing the building.

    :param app: Sphinx Application
    :type app: sphinx.application.Sphinx

    :param doctree: doctree representing the document
    :type doctree: docutils.nodes.document

    :param nodetype: type of node to replace URIs
    :type nodetype: docutils.nodes.Node

    :param nodeattr: node attribute to be replaced
    :type nodeattr: str
    """
    # https://github.com/sphinx-doc/sphinx/blob/2adeb68af1763be46359d5e808dae59d708661b1/sphinx/environment/adapters/toctree.py#L260-L266
    for node in doctree.traverse(nodetype):
        uri = olduri = node.attributes.get(nodeattr)  # somepage.html (or ../sompage.html)

        if isinstance(app.builder, DirectoryHTMLBuilder):
            # When the builder is ``DirectoryHTMLBuilder``, refuri will be
            # ``../somepage.html``. In that case, we want to remove the
            # initial ``../`` to make valid links
            if uri.startswith('../'):
                uri = uri.replace('../', '')

        if re.match('^https?://', uri):
            # allow non-local URLs for resources
            continue

        imagedir = ''
        if nodetype is docutils.nodes.image:
            # Prefix the URL with ``Builder.imagedir`` to use the internal's
            # Sphinx image handling if the node is an image
            imagedir = '{imagedir}/'.format(
                imagedir=app.builder.imagedir,
            )

            # The image is copied into ``app.builder.imagedir`` without keeping
            # the directory structure, so we need only the filename for the
            # correct link
            uri = olduri.split('/')[-1]

        if app.config.notfound_no_urls_prefix:
            uri = '/{imagedir}{filename}'.format(
                filename=uri,
                imagedir=imagedir,
            )
        else:
            uri = '{prefix}{imagedir}{filename}'.format(
                prefix=app.config.notfound_urls_prefix or '/',
                imagedir=imagedir,
                filename=uri,
            )
        node.replace_attr(nodeattr, uri)

        # Force adding the image to the builder so it's copied at ``Builder.copy_image_files``
        # https://github.com/sphinx-doc/sphinx/blob/5ce5c2c3156c53c1f1b758c38150e48080138b15/sphinx/builders/html.py#L721
        # We need to do this at this point because ``Builder.post_process_images``
        # does not add it automatically as the path does not match.
        # https://github.com/sphinx-doc/sphinx/blob/5ce5c2c3156c53c1f1b758c38150e48080138b15/sphinx/builders/__init__.py#L189
        if nodetype is docutils.nodes.image:
            if all([
                    not olduri.startswith('data:'),
                    '://' not in olduri,
            ]):
                app.builder.images[olduri] = olduri.split('/')[-1]
