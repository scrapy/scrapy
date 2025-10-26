#!/usr/bin/env python3
"""
Simple test for Memory Leak Fix in Scraper Slot

This test verifies that the memory leak fix works correctly without complex imports.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scrapy'))

# Mock the required classes to avoid import issues
class MockRequest:
    def __init__(self, url: str):
        self.url = url
        self.meta = {}

class MockResponse:
    def __init__(self, url: str, body: bytes):
        self.url = url
        self.body = body

class MockFailure:
    def __init__(self, value):
        self.value = value

# Import the Slot class directly
from scrapy.core.scraper import Slot

def test_memory_leak_fix():
    """Test that the memory leak fix works correctly"""
    print("Testing Memory Leak Fix in Scraper Slot")
    print("=" * 50)
    
    # Create a slot
    slot = Slot(max_active_size=1000000)
    
    # Test 1: Basic add/finish cycle
    print("\nTest 1: Basic add/finish cycle")
    request1 = MockRequest("http://example.com/test1")
    response1 = MockResponse("http://example.com/test1", b"x" * 500)
    
    # Add response
    deferred1 = slot.add_response_request(response1, request1)
    print(f"After add: active_size = {slot.active_size}")
    print(f"Request meta: {request1.meta}")
    
    # Simulate processing (move from queue to active)
    result, req, deferred = slot.next_response_request_deferred()
    print(f"After processing: active_size = {slot.active_size}")
    
    # Finish response
    slot.finish_response(response1, request1)
    print(f"After finish: active_size = {slot.active_size}")
    print(f"Request meta after finish: {request1.meta}")
    
    # Verify active_size is 0
    assert slot.active_size == 0, f"Expected active_size to be 0, got {slot.active_size}"
    print("✅ Test 1 passed: Basic add/finish cycle works correctly")
    
    # Test 2: Multiple requests with different sizes
    print("\nTest 2: Multiple requests with different sizes")
    requests = []
    responses = []
    
    for i in range(5):
        request = MockRequest(f"http://example.com/test{i}")
        body_size = 500 + (i * 200)  # 500, 700, 900, 1100, 1300
        response = MockResponse(f"http://example.com/test{i}", b"x" * body_size)
        
        requests.append(request)
        responses.append(response)
        
        # Add to slot
        slot.add_response_request(response, request)
        print(f"Added request {i}: body_size={body_size}, active_size={slot.active_size}")
    
    print(f"Total active_size after adding all: {slot.active_size}")
    
    # Process all requests
    while slot.queue:
        result, req, deferred = slot.next_response_request_deferred()
        print(f"Processing: {req.url}")
    
    # Finish all responses
    for i, (request, response) in enumerate(zip(requests, responses)):
        slot.finish_response(response, request)
        print(f"Finished request {i}: active_size={slot.active_size}")
    
    print(f"Final active_size: {slot.active_size}")
    assert slot.active_size == 0, f"Expected active_size to be 0, got {slot.active_size}"
    print("✅ Test 2 passed: Multiple requests handled correctly")
    
    # Test 3: Failure handling
    print("\nTest 3: Failure handling")
    request_fail = MockRequest("http://example.com/fail")
    failure = MockFailure(Exception("Test failure"))
    
    # Add failure
    slot.add_response_request(failure, request_fail)
    print(f"After add failure: active_size = {slot.active_size}")
    print(f"Request meta: {request_fail.meta}")
    
    # Process failure
    result, req, deferred = slot.next_response_request_deferred()
    print(f"After processing failure: active_size = {slot.active_size}")
    
    # Finish failure
    slot.finish_response(failure, request_fail)
    print(f"After finish failure: active_size = {slot.active_size}")
    print(f"Request meta after finish: {request_fail.meta}")
    
    assert slot.active_size == 0, f"Expected active_size to be 0, got {slot.active_size}"
    print("✅ Test 3 passed: Failure handling works correctly")
    
    # Test 4: Race condition simulation
    print("\nTest 4: Race condition simulation")
    request_race = MockRequest("http://example.com/race")
    response_race = MockResponse("http://example.com/race", b"x" * 500)
    
    # Add response
    slot.add_response_request(response_race, request_race)
    print(f"After add: active_size = {slot.active_size}")
    print(f"Stored size: {request_race.meta.get('_response_size')}")
    
    # Simulate race condition: response body changes
    response_race.body = b"x" * 1500  # Different size
    
    # Process
    result, req, deferred = slot.next_response_request_deferred()
    print(f"After processing: active_size = {slot.active_size}")
    
    # Finish with different body size (should use stored size)
    slot.finish_response(response_race, request_race)
    print(f"After finish: active_size = {slot.active_size}")
    
    assert slot.active_size == 0, f"Expected active_size to be 0, got {slot.active_size}"
    print("✅ Test 4 passed: Race condition handled correctly")
    
    print("\n🎉 All tests passed! Memory leak fix is working correctly.")

if __name__ == "__main__":
    test_memory_leak_fix()
