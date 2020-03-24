#Module reference is scrapy.utils.reqser
#https://stackoverflow.com/questions/6234586/we-need-to-pickle-any-sort-of-callable
#https://stackoverflow.com/questions/1396668/get-object-by-id
#https://stackoverflow.com/questions/15011674/is-it-possible-to-dereference-variable-ids
"""
Helper functions for serializing (and deserializing) requests.
"""
from scrapy.utils.python import to_unicode
#import marshal
import pickle
from scrapy.http import Request
#import objgraph
import gc 

def get_self_name(func):
    #print("self", func.__self__)
    #print(globals())
    #print(locals())
    for items in globals():
        if globals().get(items)==func.__self__:
            return items

def obj_from_id(id_):
    for items in gc.get_objects():
        if id(items)==id_:
            return items
        else :
            return None

def serialize_req(req):
    #function to serialize Request for redis memory
    d=dict()
    d["id_"]=id(req.callback.__self__.crawler)
    req.callback.__self__.crawler = None
    d["req"] =req
    return d

def unserialize_req(d):
    #function to unserialize Request from redis memory
    req=d["req"]
    crawler_=obj_from_id(d["id_"])
    req.callback.__self__.crawler=crawler_
    return req

def get_self(string):
    a= globals().get(string,None)
    if a:
        return a
    else :
        pass

def serialize_func(func):
    #code_bytecode = marshal.dumps(func.__code__)
    #name_bytecode=pickle.dumps(func.__name__)
    #print(func.__closure__)
    #print(func.__defaults__)
    #print(func.__dict__)
    #print(func.__globals__)
    #print(func.__kwdefaults__)
    #print(func.__annotations__)
    #print(func)
    #objgraph.show_refs(func, filename='sample-graph.png')
    #objgraph.show_refs(func.__self__, filename='sample-graph.png')
    #print(func.__self__.__mro__)
    #print(func.__self__.__class__.__mro__)
    #print(gc.get_referents(func))
    #print(gc.get_objects())
    return func.__func__

def request_to_dict(request, spider=None):
    """Convert Request object to a dict.

    Without a spider is given
    """
    #print(get_self_name(request.callback))
    serialize_func(request.callback)

    d = {
        'url': to_unicode(request.url),  # urls should be safe (safe_string_url)
        'callback': request.callback.__name__,
        'errback': request.errback,
        'method': request.method,
        'headers': dict(request.headers),
        'body': request.body,
        'cookies': request.cookies,
        'meta': request.meta,
        '_encoding': request._encoding,
        'priority': request.priority,
        'dont_filter': request.dont_filter,
        'flags': request.flags,
        'cb_kwargs': request.cb_kwargs,
        "self": get_self_name(request.callback),
        "id_": id(request.callback.__self__)
    }
    return d


def serial_output(item):
    #item=request_to_dict(item,item)
    #print(item.callback.__self__.__dict__)
    item=serialize_req(item)
    return pickle.dumps(item,protocol=2)


def request_from_dict(d, spider=None):
    """Create Request object from a dict.

    If a spider is  not given.
    """
    #print(d["self"])
    #self_=get_self(d["id_"])
    self_=obj_from_id(d["id_"])
    #print("self is ",self_)
    cb = d['callback']
    cb=getattr(self_,cb)
    request_cls = load_object(d['_class']) if '_class' in d else Request
    return request_cls(
        url=to_unicode(d['url']),
        callback=cb,
        errback=d['errback'],
        method=d['method'],
        headers=d['headers'],
        body=d['body'],
        cookies=d['cookies'],
        meta=d['meta'],
        encoding=d['_encoding'],
        priority=d['priority'],
        dont_filter=d['dont_filter'],
        flags=d.get('flags'),
        cb_kwargs=d.get('cb_kwargs'),
    )

def get_object(item):
    item=pickle.loads(item)
    #item=request_from_dict(item,item)
    item=unserialize_req(item)
    return item