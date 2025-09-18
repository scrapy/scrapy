"""
Simple test script to verify pluggable mail sender functionality
"""

import asyncio
import sys
from scrapy.settings import Settings
from scrapy.mail_senders import DummyMailSender
from scrapy.mail_interfaces import BaseMailSender
from unittest.mock import MagicMock

def test_basic_functionality():
    """Test basic pluggable mail sender functionality."""
    print("Testing pluggable mail sender...")
    
    # Test 1: Check that DummyMailSender inherits from BaseMailSender
    assert issubclass(DummyMailSender, BaseMailSender), "DummyMailSender should inherit from BaseMailSender"
    print("✓ DummyMailSender inherits from BaseMailSender")
    
    # Test 2: Create a DummyMailSender instance
    sender = DummyMailSender()
    print("✓ DummyMailSender instance created")
    
    # Test 3: Test from_crawler method
    mock_crawler = MagicMock()
    mock_crawler.settings = Settings({'DUMMY_MAIL_LOG_LEVEL': 'INFO'})
    
    sender_from_crawler = DummyMailSender.from_crawler(mock_crawler)
    assert isinstance(sender_from_crawler, DummyMailSender), "from_crawler should return DummyMailSender instance"
    print("✓ from_crawler method works")
    
    # Test 4: Test async send method
    async def test_send():
        await sender.send(
            to='test@example.com',
            subject='Test Subject',
            body='Test Body'
        )
        print("✓ Async send method works")
    
    # Run async test
    asyncio.run(test_send())
    
    print("\nAll tests passed! ✓")
    print("The pluggable mail sender system is working correctly.")


if __name__ == "__main__":
    test_basic_functionality()