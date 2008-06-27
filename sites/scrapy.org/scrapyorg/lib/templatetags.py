from django import template


is_string    = lambda val: val[0] in ("'", '"') and val[0] == val[-1]
unquoute     = lambda val: val[1:-1]

def raise_syntax(msg):
   raise template.TemplateSyntaxError, msg
