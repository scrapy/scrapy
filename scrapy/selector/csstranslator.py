from cssselect import GenericTranslator, HTMLTranslator
from cssselect.xpath import _unicode, _unicode_safe_getattr, XPathExpr, ExpressionError
from cssselect.parser import FunctionalPseudoElement, parse_series


class ScrapyXPathExpr(XPathExpr):

    textnode = False
    attribute = None

    @classmethod
    def from_xpath(cls, xpath, textnode=False, attribute=None):
        x = cls(path=xpath.path, element=xpath.element, condition=xpath.condition)
        x.textnode = textnode
        x.attribute = attribute
        x.post_condition = None
        return x

    def add_post_condition(self, post_condition):
        if self.post_condition:
            self.post_condition = '%s and (%s)' % (self.post_condition,
                                                   post_condition)
        else:
            self.post_condition = post_condition
        return self

    def __str__(self):
        path = super(ScrapyXPathExpr, self).__str__()
        if self.post_condition:
            path = '%s[%s]' % (path, self.post_condition)
        if self.textnode:
            if path == '*':
                path = 'text()'
            elif path.endswith('::*/*'):
                path = path[:-3] + 'text()'
            else:
                path += '/text()'

        if self.attribute is not None:
            if path.endswith('::*/*'):
                path = path[:-2]
            path += '/@%s' % self.attribute
        return path

    def join(self, combiner, other):
        super(ScrapyXPathExpr, self).join(combiner, other)
        self.textnode = other.textnode
        self.attribute = other.attribute
        self.post_condition = other.post_condition
        return self


class TranslatorMixin(object):

    def xpath_element(self, selector):
        xpath = super(TranslatorMixin, self).xpath_element(selector)
        return ScrapyXPathExpr.from_xpath(xpath)

    def xpath_pseudo_element(self, xpath, pseudo_element):
        if isinstance(pseudo_element, FunctionalPseudoElement):
            method = 'xpath_%s_functional_pseudo_element' % (
                pseudo_element.name.replace('-', '_'))
            method = _unicode_safe_getattr(self, method, None)
            if not method:
                raise ExpressionError(
                    "The functional pseudo-element ::%s() is unknown"
                % pseudo_element.name)
            xpath = method(xpath, pseudo_element)
        else:
            method = 'xpath_%s_simple_pseudo_element' % (
                pseudo_element.replace('-', '_'))
            method = _unicode_safe_getattr(self, method, None)
            if not method:
                raise ExpressionError(
                    "The pseudo-element ::%s is unknown"
                    % pseudo_element)
            xpath = method(xpath)
        return xpath

    def xpath_attr_functional_pseudo_element(self, xpath, function):
        if function.argument_types() not in (['STRING'], ['IDENT']):
            raise ExpressionError(
                "Expected a single string or ident for ::attr(), got %r"
                % function.arguments)
        return ScrapyXPathExpr.from_xpath(xpath,
            attribute=function.arguments[0].value)

    def xpath_text_simple_pseudo_element(self, xpath):
        """Support selecting text nodes using ::text pseudo-element"""
        return ScrapyXPathExpr.from_xpath(xpath, textnode=True)

    def xpath_first_pseudo(self, xpath):
        """Support selecting first child nodes using :first pseudo-class"""
        xpath.add_star_prefix()
        return xpath.add_post_condition("position() = 1")

    def xpath_last_pseudo(self, xpath):
        """Support selecting last child nodes using :last pseudo-class"""
        xpath.add_star_prefix()
        return xpath.add_post_condition("position() = last()")

    def xpath_anb_condition(self, function, last=False):
        try:
            a, b = parse_series(function.arguments)
        except ValueError:
            raise ExpressionError("Invalid series: '%r'" % function.arguments)
        # non-last
        # --------
        #    position() = an+b
        # -> position() - b = an
        #
        # if a < 0:
        #    position() - b <= 0
        # -> position() <= b
        #
        # last
        # ----
        #    last() - position() = an+b -1
        # -> last() - position() - b +1 = an
        #
        # if a < 0:
        #    last() - position() - b +1 <= 0
        # -> position() >= last() - b +1
        #
        # -b +1 = -(b-1)
        if last:
            b = b - 1
        if b > 0:
            b_neg = str(-b)
        else:
            b_neg = '+%s' % (-b)
        if a == 0:
            if last:
                # http://www.w3.org/TR/selectors/#nth-last-child-pseudo
                # The :nth-last-child(an+b) pseudo-class notation represents
                # an element that has an+b-1 siblings after it in the document tree
                #
                #    last() - position() = an+b-1
                # -> position() = last() -b +1 (for a==0)
                #
                if b == 0:
                    b = 'last()'
                else:
                    b = 'last() %s' % b_neg
            return 'position() = %s' % b
        if a != 1:
            # last() - position() - b +1 = an
            if last:
                left = '(last() - position())'
            # position() - b = an
            else:
                left = 'position()'
            if b != 0:
                left = '(%s %s)' % (left, b_neg)
            expr = ['%s mod %s = 0' % (left, a)]
        else:
            expr = []
        if last:
            if b == 0:
                right = 'last()'
            else:
                right = 'last() %s' % b_neg
            if a > 0:
                expr.append('(position() <= %s)' % right)
            else:
                expr.append('(position() >= %s)' % right)
        else:
            # position() > 0 so if b < 0, then position() > b
            # also, position() >= 1 always
            if b > 1:
                if a > 0:
                    expr.append('position() >= %s' % b)
                else:
                    expr.append('position() <= %s' % b)

        expr = ' and '.join(expr)
        if expr:
            return expr

    def xpath_nth_function(self, xpath, function):
        """Support selecting n-th child nodes using :nth(an+b) pseudo-class"""
        xpath.add_star_prefix()
        cond = self.xpath_anb_condition(function, last=False)
        if cond:
            return xpath.add_post_condition(cond)
        else:
            return xpath

    def xpath_nth_last_function(self, xpath, function):
        """Support selecting n-th child nodes using :nth-last(an+b) pseudo-class"""
        xpath.add_star_prefix()
        cond = self.xpath_anb_condition(function, last=True)
        if cond:
            return xpath.add_post_condition(cond)
        else:
            return xpath


class ScrapyGenericTranslator(TranslatorMixin, GenericTranslator):
    pass


class ScrapyHTMLTranslator(TranslatorMixin, HTMLTranslator):
    pass

