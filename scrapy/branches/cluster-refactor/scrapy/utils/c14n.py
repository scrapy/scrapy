"""
Canonicalization routine for URLs
"""
import re
import urlparse

_hexmatcher = re.compile("\%[0-9A-Fa-f]{2}")

def get_canonized_port(port):
    if port and port != 80:
        cport = ":" + str(port)
    else:
        cport = ""
    return cport

def create_params_dict(params):
    param_dict = {}
    for param in params.split("&"):
        nvpair = param.split("=")
        if len(nvpair) >= 2:
            param_dict[nvpair[0]] = '='.join(nvpair[1:])
        else:
            param_dict[nvpair[0]] = None
    return param_dict
    
def create_unique_params_list(params):
    """
    This function build a query string from unique params only.
    Unique params are params with unique key=>value pair. So param=qwe and param=123
    are diffrent and a query string will be param=qwe&param=123.
    If input params will contain pairs like this param=123 and param=123 a query
    string will be just param=123
    We have to do this because some ASP sites uses the same parameters names in the URLs,
    but with diffrent values. Such queries are interpreted as arrays in the ASP framework.
    """
    param_list = []
    if params:
        for param in params.split("&"):
            nvpair = param.split("=", 1)
            if len(nvpair) >= 2:
                param_list.append(nvpair[0] + '=' + nvpair[1])
            else:
                param_list.append(nvpair[0] + '=')
        if param_list:
            p_list = []
            # select only unique pairs, it is possible to use set() for this but change order of pairs...
            for param in param_list:
                if param not in p_list:
                    p_list.append(param)
            return '&'.join(p_list)
    return ''

def convert_escaped(string_to_convert):
    hexvalues = _hexmatcher.findall(string_to_convert)
    for hexvalue in hexvalues:
        string_to_convert = string_to_convert.replace(
                hexvalue, chr(int(hexvalue[1:len(hexvalue)],16)))
    return string_to_convert

def remove_dirs(path):
    dirs = path.split("/")
    dirs.reverse()
    stripped_dirs = []
    ellipsis = 0
    for dir in dirs:
        if dir == ".." :
            ellipsis += 1
        elif dir == "." :
            pass
        else:
            if ellipsis > 0 :
                ellipsis -= 1
            else:
                stripped_dirs.append(dir)
    stripped_dirs.reverse()
    return "/".join(stripped_dirs)

def canonicalize(url):
    """
    This method c14ns the url we are passed by doing the following
    1) lowercasing the hostname and scheme
    2) removing the port if it is 80
    3) making the query params unique and alphabetized
    4) removing url encoding
    5) Removing any ./
    6) Removing and ../ and their preceding directories
    """

    # Remove the fragment marker, even if it's url encoded
    defragmented_url = urlparse.urldefrag(url)[0]

    # This automatically converts the scheme and hostname to lower case 
    parsed = urlparse.urlparse(defragmented_url)

    # Get the port in the correct format 
    cport = get_canonized_port(parsed.port)
    
    query = create_unique_params_list(parsed.query)

    # Remove the url encoded params from the path and query string
    query = convert_escaped(query)
    if query :
        query = "?" + query
    path = convert_escaped(parsed.path)

    # Remove the ../ and the previous directories and remove the ./
    path = remove_dirs(path)

    # Now put it all back together
    return "%s://%s%s%s%s" % (parsed.scheme, parsed.hostname, cport, path, query)
