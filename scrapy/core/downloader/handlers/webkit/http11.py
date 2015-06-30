'''
Created on 21 May, 2015

@author: wangyi
'''
import re
import logging
# scrapy asynchroneous framework dependency 
from twisted.internet import defer, reactor, protocol

from selenium import webdriver as wd
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities 
from selenium.webdriver.support.wait import WebDriverWait

from scrapy.utils.decorator import inthread

# this may cause some problem if the scrapy is updated to Py3k version
# I have some problems in using six module 
# from six.moves.urllib.parse import urldefrag
# see urllib.parse module
from urlparse import urldefrag
import time

logger = logging.getLogger(__name__)

class HTTP11DownloadHandler(object):
    
    def __init__(self, settings):
        
        pass
    
    def download_request(self, request, spider):
        """Return a deffered for HTTP download"""
        logger.info('enter into downloader')
        print('enter into downloader')
        agent = SeleniumAgent()
        return agent.download_request(request)

from scrapy.http import TextResponse

class WebDriverRep(TextResponse):
    
    def __init__(self, url, webdriver, body="", bodyText="", **kwargs):
        super(WebDriverRep, self).__init__(url, **kwargs)
        self._body = body
        self.bodyText = bodyText
        self.webdriver = webdriver
        
    # this function is needed, otherwise an error will be fired
    def replace(self, *args, **kwargs):
        kwargs.setdefault('body', self._body)
        return super(WebDriverRep, self).replace(*args, **kwargs)

class WebDriver(object):
    
    def __init__(self, webdriver):
        self._webdriver = webdriver
        self._flag = False
       
       
    def get2(self, url):
        # may take few secondes
        print("enter into webdriver get")
        logger.info("enter into webdriver get")
        self._webdriver.get(url)
        return self        
     
    @inthread 
    def get(self, url):
        # may take few secondes
        print("enter into webdriver get")
        logger.info("enter into webdriver get")
        self._webdriver.get(url)
        agent = self.agent
        print(agent)
        body = self.get_page()
        # need further debug
        #body, bodyText = self.get_body(), self.get_bodyText()
        rep = WebDriverRep(url, self, body)
        return \
            rep
    
    def execute(self, script):
        return self._webdriver.execute_script(script)
    
    def get_body(self):
        flag = self._renderedBody()
        if flag is "success":
            return self.execute("return body")
    
    def get_bodyText(self):
        flag = self._renderedBody()
        if flag is "success":
            return self.execute("return bodyText") 
    
    def get_page(self):
        return self.execute("return document.body.innerText")
    
    def get_xml(self):
        return self.execute("return document.body.innerHTML")
    
    def _renderedBody(self):
        # execute once controller
        flag = self._flag
        
        if flag:
            return
        with open("tutorial/js/lib/dom_filter.js", "r") as f:
            script = f.read()
        result = self.execute("""
function walk_dom(node, _IsExec){
    if (node === null){
        return;
    }
     
    var queue = [node], _curr = undefined;
     
    while(queue.length){
        _curr = queue.shift();
        var _array = dom_Array(_curr.children);
        queue.extend(_IsExec(_curr, _array));
    }
    
    return node;
}

// helper libs
function dom_Array(elements){
    var _array = [];
    Array.prototype.push.apply(_array, elements);
    return _array;
}

function extend(_array){
    Array.prototype.push.apply(this, _array);
    return this;
}
Array.prototype.extend = extend;


var node = walk_dom(document, function(parent, children) {
     
    var selected = [];
     
    for (child of children) {
        if (child.nodeName === "SCRIPT" || child.nodeName === "STYLE") {
            parent.removeChild(child);
        }
        else {
            selected.push(child);
        }
    }   
   return selected;
})
// for interprocess communication 
console.log(node);

bodyText = node.body.innerText, 
body = node.body.innerHTML;

bodyText = bodyText.split('\n').filter(function(node){
    if (node === "" ){return 0} return 1}) ; 

return {'status':"success"};
        """)
        self.flag = True
        return result
    
    @property      
    def agent(self):
        return self.execute("return navigator.userAgent")
    
    @property
    def length(self):
        return self.execute("return body.length")
    
    @property
    def current_url(self):
        return self._webdriver.current_url
    
    def close(self):
        # close current session
        pass
    
class SeleniumAgent(object):
    # contextFactory : SSL, I am not sure whether it is useful
    def __init__(self, connTimeout=10, bindAddress=None, pool=None):
        self._connTimeout = connTimeout
    
    def _get_driver(self):
        profile = dict(DesiredCapabilities.PHANTOMJS)
        
        profile["phantomjs.page.settings.userAgent"] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/53 " + 
        "(KHTML, like Gecko) Chrome/15.0.87")
        
        executable_path = '/usr/local/bin/phantomjs'
        driver = wd.PhantomJS(executable_path=executable_path, desired_capabilities=profile, 
                              service_args=['--ignore-ssl-errors=true'])
        # this could be wrapped, 
        return WebDriver(driver)
    
    # the second approach
    def download_request2(self, request):
        logger.info("enter into agent!")
        print("enter into agent!")
        timeout = request.meta.get('downlaod_timeout') or self._connTimeout
        
        # get driver, to get rendered response by webkit engine like phantom
        webdriver = self._get_driver()
        # parse url bind to request
        # consider using urllib.urldefrag
        url = urldefrag(request.url)[0]
        # inspect time start 
        start_time = time.time()
        # return a deffered object
        # a scapy agent will return a deferred object which host result of http connection over TCP connection
        d = defer.Deferred()
        # add asynchroneous callback,
        # we need to return a deffered according to
        # scrapy handler protocol, see downloader module
        d.addCallback(lambda url:webdriver.get2(url), url)
        d.addCallback(self._cb_timeout, request, url, timeout)
        d.addCallback(self._cb_latency, request, start_time)
        d.addCallback(self._cb_bodyready, request)
        d.addCallback(self._cb_bodydone, request, url)
        # set a schedual timout event, I cannot do this in my computer,
        self._timeout_cl = None
        d.addBoth(self._cb_timeout, request, url, timeout)
        return d
    
    # the first approach  
    def download_request(self, request):
        logger.info("enter into agent!")
        print("enter into agent!")
        timeout = request.meta.get('downlaod_timeout') or self._connTimeout
        
        # get driver, to get rendered response by webkit engine like phantom
        webdriver = self._get_driver()
        # parse url bind to request
        # consider using urllib.urldefrag
        url = urldefrag(request.url)[0]
        # return a deffered object
        # a scapy agent will return a deferred object which host result of http connection over TCP connection
        return webdriver.get(url)

    
    # callbacks
    def _cb_timeout(self, result, request, url, timeout):
        # this part will raise error if timeout achieves
        # this will call self._timeout_cl
        print("_cb_timeOut event triggered") 
        logger.info("_cb_timeOut event triggered")
        return result
    
    def _cb_latency(self, result, request, start_time):
        print("latency: %s" % request.meta['download_latency'])
        request.meta['download_latency'] = time.time() - start_time
        logger.info("latency: %s" % request.meta['download_latency'])
        return result
    
    def _cb_bodyready(self, result, request):
        # check rendered body size implementation
        print("enter into _cb_bodyready")
        # ...
        def _cancel(webdriver):
            # I am not sure whether there is a need to do this
            return webdriver
        # second level deferred object
        d = defer.Deferred(_cancel, result)    
        # deliver body: result.deliverBody?
        return d
    
    def _cb_bodydone(self, result, request, url):
        # return response if result isinstance of webdriver
        print("enter bodydone!")
        body = self.get_page()
        #body, bodyText = result.get_body(), result.get_bodyText()
        rep = WebDriverRep(url, result, body)
        return rep

     
    
    