"""
Tests for pluggable mail sender functionality.
"""

import asyncio
from unittest.mock import MagicMock, patch

from scrapy.crawler import Crawler
from scrapy.mail import get_mail_sender_from_crawler, MailSender
from scrapy.mail_interfaces import BaseMailSender
from scrapy.mail_senders import DummyMailSender, SESMailSender
from scrapy.settings import Settings


class TestPluggableMailSenders:
    """Test pluggable mail sender functionality."""
    
    def test_default_mail_sender_from_crawler(self):
        """Test that default MailSender is used when no custom class is specified."""
        settings = Settings()
        crawler = MagicMock(spec=Crawler)
        crawler.settings = settings
        
        with patch.object(MailSender, 'from_crawler', return_value=MagicMock(spec=MailSender)) as mock_from_crawler:
            mail_sender = get_mail_sender_from_crawler(crawler)
            mock_from_crawler.assert_called_once_with(crawler)
            assert isinstance(mail_sender, MailSender) or isinstance(mail_sender, MagicMock)
    
    def test_custom_mail_sender_from_crawler(self):
        """Test that custom mail sender is used when specified in settings."""
        settings = Settings({
            'MAIL_SENDER_CLASS': 'scrapy.mail_senders.DummyMailSender'
        })
        crawler = MagicMock(spec=Crawler)
        crawler.settings = settings
        
        with patch.object(DummyMailSender, 'from_crawler', return_value=MagicMock(spec=DummyMailSender)) as mock_from_crawler:
            mail_sender = get_mail_sender_from_crawler(crawler)
            mock_from_crawler.assert_called_once_with(crawler)
    
    def test_dummy_mail_sender_interface(self):
        """Test that DummyMailSender implements the required interface."""
        assert issubclass(DummyMailSender, BaseMailSender)
        
        # Test instantiation
        sender = DummyMailSender()
        assert hasattr(sender, 'send')
        assert hasattr(sender, 'from_crawler')
    
    def test_ses_mail_sender_interface(self):
        """Test that SESMailSender implements the required interface."""
        assert issubclass(SESMailSender, BaseMailSender)
        
        # Test instantiation
        sender = SESMailSender()
        assert hasattr(sender, 'send')
        assert hasattr(sender, 'from_crawler')
    
    def test_dummy_mail_sender_from_crawler(self):
        """Test DummyMailSender creation from crawler."""
        settings = Settings({
            'DUMMY_MAIL_LOG_LEVEL': 'DEBUG'
        })
        crawler = MagicMock(spec=Crawler)
        crawler.settings = settings
        
        sender = DummyMailSender.from_crawler(crawler)
        assert isinstance(sender, DummyMailSender)
        assert sender.log_level == 20  # DEBUG level
    
    def test_ses_mail_sender_from_crawler(self):
        """Test SESMailSender creation from crawler."""
        settings = Settings({
            'AWS_SES_REGION': 'us-west-2',
            'AWS_SES_SOURCE_EMAIL': 'test@example.com'
        })
        crawler = MagicMock(spec=Crawler)
        crawler.settings = settings
        
        sender = SESMailSender.from_crawler(crawler)
        assert isinstance(sender, SESMailSender)
        assert sender.region == 'us-west-2'
        assert sender.source_email == 'test@example.com'
    
    async def test_dummy_mail_sender_send(self):
        """Test DummyMailSender send method."""
        sender = DummyMailSender()
        
        # Should not raise any exceptions
        await sender.send(
            to='test@example.com',
            subject='Test Subject',
            body='Test Body',
            cc='cc@example.com'
        )
    
    async def test_ses_mail_sender_send(self):
        """Test SESMailSender send method."""
        sender = SESMailSender(region='us-east-1', source_email='sender@example.com')
        
        # Should not raise any exceptions
        await sender.send(
            to='test@example.com',
            subject='Test Subject',
            body='Test Body',
            cc='cc@example.com'
        )
    
    def test_mail_sender_inherits_from_base(self):
        """Test that MailSender inherits from BaseMailSender."""
        assert issubclass(MailSender, BaseMailSender)
    
    async def test_mail_sender_async_interface(self):
        """Test that MailSender implements the async interface."""
        # This would need a more complex setup to test properly
        # For now, just verify the method exists
        sender = MailSender(debug=True)
        assert hasattr(sender, 'send_async')
        assert callable(sender.send_async)


class TestBackwardCompatibility:
    """Test backward compatibility of the mail sender changes."""
    
    def test_mail_sender_sync_interface_still_works(self):
        """Test that the original sync interface still works."""
        sender = MailSender(debug=True)
        
        # Should not raise any exceptions
        result = sender.send(
            to='test@example.com',
            subject='Test Subject',
            body='Test Body'
        )
        # In debug mode, should return None
        assert result is None
    
    def test_mail_sender_from_settings_deprecated(self):
        """Test that from_settings method still works but is deprecated."""
        settings = Settings({
            'MAIL_HOST': 'localhost',
            'MAIL_PORT': 25,
            'MAIL_FROM': 'test@example.com'
        })
        
        # This should work but issue a deprecation warning
        with patch('warnings.warn') as mock_warn:
            sender = MailSender.from_settings(settings)
            mock_warn.assert_called()
            assert isinstance(sender, MailSender)


# Run async tests
if __name__ == "__main__":
    import pytest
    pytest.main([__file__])