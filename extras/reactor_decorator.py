from functools import wraps
from twisted.internet import reactor, error
import traceback
import logging 


''' 
The reactor_process decorator is used to isolate the decorated 
function in a separate process, so as to allow the twisted reactor
to be started and stopped multiple times. 
This normally isn't possible (and is known problem with using scrapy
in a library capacity: https://stackoverflow.com/questions/35289054/scrapy-crawl-multiple-times-in-long-running-process )
but by using the multiprocessing library and some hacky runtime code
swapping, we can abstract the whole thing into a single decorator.

--- The one remaining issue is that the decorated function needs to import 
--- all necessary modules _within_ that function. It's an unfortunate side 
--- effect of having _helper_process defined here, as it won't contain the 
--- same context as the actual function being called. 
--- There should be a way to fix this; hopefully there's a way to do it with
--- a multiprocessing manager, but it may come down to manually importing 
--- the same modules as the base fuction via global inspection.  
'''
f_code = {} # Global function code dictionary

def placeholder(*args, **kwargs): 
	''' Placeholder function which takes on the code of the wrapped function '''
	pass 


def _helper_process(f_name, args, kwargs):
	''' Wrapper that reactor_process uses, as it needs to 
		exist on the top level to be pickleable '''
	try:
		placeholder.__code__ = f_code[f_name]
		placeholder(*args, **kwargs)
		reactor.run()
	except Exception as e: 
		logging.getLogger(__name__).error(
			'%s: \n%s'%(e, traceback.format_exc()))


def reactor_process(timeout=10):
	def wrapper_factory(f):
		''' This is very wrong as far as twisted is concerned, but
			it's the only way I've found to allow more than one 
			task to be run (and thus allow restarting the reactor).		

			We need to return the original function, and apparently 
			can't modify anything except __code__ without getting a 
			pickling error (i.e. '<function> is not the same object 
			as <function>'). __code__ variables aren't pickleable, 
			so we double wrap the replacement function (to allow a 
			few variables to be stored in a local context within the 
			wrapper) and store the __code__ object inside a global 
			variable to be accessed by a separate process. 
		'''
		@wraps(f)
		def ctx_wrapper(f_name, timeout):
			def wrap(*args, **kwargs):
				''' Imports need to be defined here, due to being called from 
					whatever class reactor_process is imported to '''
				from multiprocessing import Process
				from reactor_decorator import _helper_process

				p = Process(target=_helper_process, args=(f_name, args, kwargs))
				p.start()
				p.join(timeout=timeout)
			return wrap 

		f_code[f.__name__] = f.__code__
		f.__code__ = ctx_wrapper.__code__
		return f(f.__name__, timeout)
	return wrapper_factory




''' Example usage: '''
from twisted.internet import reactor
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging

class Spider(scrapy.Spider):
	name = "DecoratorTest"
	start_urls = ['https://www.google.com']

	def parse(self, response):
		print('Retrieved', response.url)


def without_decorator():
	runner = CrawlerRunner()
	d = runner.crawl(Spider)
	d.addBoth(lambda _: reactor.stop())
	reactor.run()


@reactor_process(timeout=1)
def with_decorator():
	''' Function needs to be defined either at the top level, or 
		within a class which is defined at the top level '''
	runner = CrawlerRunner()
	d = runner.crawl(Spider)
	d.addBoth(lambda _: reactor.stop())


def test(func):
	func()
	try:	
		func()
	except error.ReactorNotRestartable:
		return 'Failed to run second time'
	return 'Successfully ran second time'


if __name__ == '__main__':
	print('Testing without decorator:')
	print( test(without_decorator) )

	print('\nTesting with decorator:')
	print( test(with_decorator) )