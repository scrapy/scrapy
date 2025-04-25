import time
from scrapy.crawler import Crawler
from scrapy import Spider
from scrapy.settings import Settings

# Define a simple spider class
class MySpider(Spider):
    name = 'myspider'

# Define an extension class to look for
class MyExtension:
    pass

def run_benchmark():
    # Create a crawler and initialize it
    settings = Settings()
    crawler = Crawler(MySpider, settings)
    
    # Set up manually since we're not using the regular crawling process
    crawler.extensions = type('MockExtensionManager', (), {'middlewares': []})()
    
    # Add our extension to the middlewares
    extension_instance = MyExtension()
    crawler.extensions.middlewares.append(extension_instance)
    
    # First call - should populate cache
    print("First call (not cached):")
    start = time.time()
    result1 = crawler.get_extension(MyExtension)
    first_call_time = time.time() - start
    print(f"  Time: {first_call_time:.6f} seconds")
    print(f"  Result: {result1}")
    
    # Second call - should use cache
    print("\nSecond call (should be cached):")
    start = time.time()
    result2 = crawler.get_extension(MyExtension)
    second_call_time = time.time() - start
    print(f"  Time: {second_call_time:.6f} seconds")
    print(f"  Result: {result2}")
    
    # Multiple cached calls
    print("\nRunning 1000 cached calls:")
    start = time.time()
    for _ in range(1000):
        crawler.get_extension(MyExtension)
    many_calls_time = time.time() - start
    print(f"  Total time: {many_calls_time:.6f} seconds")
    print(f"  Average time per call: {many_calls_time/1000:.9f} seconds")
    
    # Compare performance
    if second_call_time > 0:  # Avoid division by zero
        speedup = first_call_time / second_call_time
        print(f"\nCache speedup: {speedup:.2f}x faster")

if __name__ == "__main__":
    run_benchmark()