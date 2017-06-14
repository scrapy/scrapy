from docutils import nodes
from sphinx.util.compat import Directive
from sphinx.search import SkipNode


class xpath_demo_node(nodes.Element):
    pass


class XPathDemoDirective(Directive):
    has_content = True
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True

    def run(self):
        demo_node = xpath_demo_node()
        document = self.state.document
        env = document.settings.env

        _, demo_node.form_template = env.relfn2path('/_static/html/xpathdemo.html')
        demo_node.xpath_expression = self.arguments[0]
        demo_node.html_input = '\n'.join(self.content)
        return [demo_node]


def setup(app):
    app.add_node(
        xpath_demo_node,
        html=(
            visit_xpath_demo_node,
            depart_xpath_demo_node,
        ),
        # latex build are failing, so let's skip the xpath nodes
        latex=(skip_node, None),
    )
    app.add_directive('xpathdemo', XPathDemoDirective)


def skip_node(self, node):
    raise SkipNode


def visit_xpath_demo_node(self, node):
    try:
        with open(node.form_template) as fp:
            s = fp.read().format(
                xpath_expression=node.xpath_expression,
                html_input=node.html_input,
                id=id(node),
            )
        self.body.append(s)
    except AttributeError as e:
        print('Error: {}'.format(str(e)))


def depart_xpath_demo_node(self, node):
    pass
