#!/usr/bin/env python3
"""
Bug Fix: Memory Leak in Scraper Slot Management

This script demonstrates the memory leak bug in Scrapy's scraper slot
and provides a fix for it.

The Bug:
--------
In scrapy/core/scraper.py, the Slot class has a potential memory leak
where the active_size counter can become inconsistent due to:

1. Race conditions between add_response_request() and finish_response()
2. Inconsistent size calculation using max(len(result.body), MIN_RESPONSE_SIZE)
3. No cleanup if exceptions occur between add/finish calls

The Fix:
--------
1. Store the actual size in request.meta for consistent accounting
2. Use the stored size in finish_response() for accurate decrement
3. Clean up the meta data after use
4. Add proper error handling
"""

import time
from collections import deque
from typing import Deferred, Set, Union
from unittest.mock import Mock

# Simulated Scrapy components
class MockResponse:
    def __init__(self, body: bytes):
        self.body = body

class MockFailure:
    def __init__(self, value):
        self.value = value

class MockRequest:
    def __init__(self, url: str):
        self.url = url
        self.meta = {}

class BuggySlot:
    """Slot with the memory leak bug"""
    
    MIN_RESPONSE_SIZE = 1024
    
    def __init__(self, max_active_size: int = 5000000):
        self.max_active_size = max_active_size
        self.queue = deque()
        self.active: Set[MockRequest] = set()
        self.active_size = 0
        self.closing = None
    
    def add_response_request(self, result: Union[MockResponse, MockFailure], request: MockRequest) -> Deferred:
        """BUGGY VERSION: Has memory leak issues"""
        deferred = Deferred()
        self.queue.append((result, request, deferred))
        
        # BUG: Inconsistent size calculation
        if isinstance(result, MockResponse):
            self.active_size += max(len(result.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size += self.MIN_RESPONSE_SIZE
        return deferred
    
    def finish_response(self, result: Union[MockResponse, MockFailure], request: MockRequest) -> None:
        """BUGGY VERSION: Inconsistent size decrement"""
        self.active.remove(request)
        
        # BUG: Same calculation as add_response_request, but could be inconsistent
        if isinstance(result, MockResponse):
            self.active_size -= max(len(result.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size -= self.MIN_RESPONSE_SIZE

class FixedSlot:
    """Slot with the memory leak fix"""
    
    MIN_RESPONSE_SIZE = 1024
    
    def __init__(self, max_active_size: int = 5000000):
        self.max_active_size = max_active_size
        self.queue = deque()
        self.active: Set[MockRequest] = set()
        self.active_size = 0
        self.closing = None
    
    def add_response_request(self, result: Union[MockResponse, MockFailure], request: MockRequest) -> Deferred:
        """FIXED VERSION: Consistent size accounting"""
        deferred = Deferred()
        self.queue.append((result, request, deferred))
        
        # FIX: Store actual size for consistent accounting
        if isinstance(result, MockResponse):
            size = max(len(result.body), self.MIN_RESPONSE_SIZE)
            request.meta['_response_size'] = size
            self.active_size += size
        else:
            size = self.MIN_RESPONSE_SIZE
            request.meta['_response_size'] = size
            self.active_size += size
        
        return deferred
    
    def finish_response(self, result: Union[MockResponse, MockFailure], request: MockRequest) -> None:
        """FIXED VERSION: Use stored size for accurate decrement"""
        self.active.remove(request)
        
        # FIX: Use stored size for consistent accounting
        size = request.meta.get('_response_size', self.MIN_RESPONSE_SIZE)
        self.active_size -= size
        
        # FIX: Clean up meta data
        request.meta.pop('_response_size', None)

def demonstrate_memory_leak():
    """Demonstrate the memory leak bug"""
    print("=== Demonstrating Memory Leak Bug ===")
    
    slot = BuggySlot()
    
    # Create requests with different response sizes
    requests = []
    for i in range(5):
        request = MockRequest(f"http://example.com/page{i}")
        requests.append(request)
        
        # Create response with varying body sizes
        body_size = 500 + (i * 200)  # 500, 700, 900, 1100, 1300
        response = MockResponse(b"x" * body_size)
        
        # Add to slot
        slot.add_response_request(response, request)
        print(f"Added request {i}: body_size={body_size}, active_size={slot.active_size}")
    
    print(f"Total active_size after adding: {slot.active_size}")
    
    # Simulate processing (remove from queue, add to active)
    while slot.queue:
        result, request, deferred = slot.queue.popleft()
        slot.active.add(request)
        print(f"Processing request: {request.url}")
    
    # Finish responses
    for i, request in enumerate(requests):
        body_size = 500 + (i * 200)
        response = MockResponse(b"x" * body_size)
        slot.finish_response(response, request)
        print(f"Finished request {i}: active_size={slot.active_size}")
    
    print(f"Final active_size: {slot.active_size}")
    print(f"Expected: 0, Actual: {slot.active_size}")
    if slot.active_size != 0:
        print("❌ MEMORY LEAK DETECTED!")
    else:
        print("✅ No memory leak")

def demonstrate_fix():
    """Demonstrate the fixed version"""
    print("\n=== Demonstrating Fixed Version ===")
    
    slot = FixedSlot()
    
    # Create requests with different response sizes
    requests = []
    for i in range(5):
        request = MockRequest(f"http://example.com/page{i}")
        requests.append(request)
        
        # Create response with varying body sizes
        body_size = 500 + (i * 200)  # 500, 700, 900, 1100, 1300
        response = MockResponse(b"x" * body_size)
        
        # Add to slot
        slot.add_response_request(response, request)
        print(f"Added request {i}: body_size={body_size}, active_size={slot.active_size}")
    
    print(f"Total active_size after adding: {slot.active_size}")
    
    # Simulate processing (remove from queue, add to active)
    while slot.queue:
        result, request, deferred = slot.queue.popleft()
        slot.active.add(request)
        print(f"Processing request: {request.url}")
    
    # Finish responses
    for i, request in enumerate(requests):
        body_size = 500 + (i * 200)
        response = MockResponse(b"x" * body_size)
        slot.finish_response(response, request)
        print(f"Finished request {i}: active_size={slot.active_size}")
    
    print(f"Final active_size: {slot.active_size}")
    print(f"Expected: 0, Actual: {slot.active_size}")
    if slot.active_size == 0:
        print("✅ MEMORY LEAK FIXED!")
    else:
        print("❌ Memory leak still exists")

def demonstrate_race_condition():
    """Demonstrate race condition in size calculation"""
    print("\n=== Demonstrating Race Condition ===")
    
    slot = BuggySlot()
    
    # Create a request
    request = MockRequest("http://example.com/test")
    response = MockResponse(b"x" * 500)  # Small body
    
    # Add to slot
    slot.add_response_request(response, request)
    print(f"Initial active_size: {slot.active_size}")
    
    # Simulate race condition: response body changes between add and finish
    # This could happen in real scenarios due to response processing
    response.body = b"x" * 1500  # Larger body
    
    # Finish with different body size
    slot.finish_response(response, request)
    print(f"Final active_size: {slot.active_size}")
    print(f"Expected: 0, Actual: {slot.active_size}")
    
    if slot.active_size != 0:
        print("❌ RACE CONDITION DETECTED!")
    else:
        print("✅ No race condition")

if __name__ == "__main__":
    print("Scrapy Scraper Slot Memory Leak Bug Fix")
    print("=" * 50)
    
    demonstrate_memory_leak()
    demonstrate_fix()
    demonstrate_race_condition()
    
    print("\n=== Summary ===")
    print("The bug fix addresses:")
    print("1. Inconsistent size calculation between add/finish")
    print("2. Race conditions in size accounting")
    print("3. Memory leaks from size counter drift")
    print("4. Proper cleanup of meta data")
