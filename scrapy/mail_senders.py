"""
Example mail sender implementations for demonstration purposes.

This module shows how to implement custom mail senders using the
pluggable mail sender interface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.mail_interfaces import BaseMailSender

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class DummyMailSender(BaseMailSender):
    """A dummy mail sender for testing and demonstration.
    
    This mail sender doesn't actually send emails but logs them instead.
    Useful for testing and development environments.
    """
    
    def __init__(self, log_level: str = "INFO") -> None:
        """Initialize the dummy mail sender.
        
        Args:
            log_level: The log level to use for email messages
        """
        super().__init__()
        self.log_level = getattr(logging, log_level.upper())
    
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Create dummy mail sender instance from crawler.
        
        Args:
            crawler: The Scrapy crawler instance
            
        Returns:
            DummyMailSender instance
        """
        log_level = crawler.settings.get("DUMMY_MAIL_LOG_LEVEL", "INFO")
        return cls(log_level=log_level)
    
    async def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        attachs: Sequence[tuple[str, str, IO[Any]]] = (),
        mimetype: str = "text/plain",
        charset: str | None = None,
    ) -> None:
        """Log an email message instead of sending it.
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            cc: CC recipient email address(es)
            attachs: Email attachments as (name, mimetype, file) tuples
            mimetype: MIME type for the email body
            charset: Character encoding for the email
        """
        to_list = to if isinstance(to, list) else [to]
        cc_list = cc if isinstance(cc, list) else ([cc] if cc else [])
        
        logger.log(
            self.log_level,
            "DUMMY EMAIL - To: %s, CC: %s, Subject: %s, Body: %s, "
            "Attachments: %d, MIME: %s, Charset: %s",
            to_list,
            cc_list,
            subject,
            body[:100] + "..." if len(body) > 100 else body,
            len(attachs),
            mimetype,
            charset,
        )


class SESMailSender(BaseMailSender):
    """Amazon SES mail sender implementation (placeholder).
    
    This is a placeholder implementation showing how one would implement
    an SES-based mail sender. The actual implementation would require
    the boto3 library and proper AWS credentials.
    """
    
    def __init__(self, region: str = "us-east-1", source_email: str = "") -> None:
        """Initialize the SES mail sender.
        
        Args:
            region: AWS region for SES
            source_email: The verified sender email address
        """
        super().__init__()
        self.region = region
        self.source_email = source_email
    
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Create SES mail sender instance from crawler.
        
        Args:
            crawler: The Scrapy crawler instance
            
        Returns:
            SESMailSender instance
        """
        region = crawler.settings.get("AWS_SES_REGION", "us-east-1")
        source_email = crawler.settings.get("AWS_SES_SOURCE_EMAIL", "")
        return cls(region=region, source_email=source_email)
    
    async def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        attachs: Sequence[tuple[str, str, IO[Any]]] = (),
        mimetype: str = "text/plain",
        charset: str | None = None,
    ) -> None:
        """Send an email via Amazon SES.
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            cc: CC recipient email address(es)
            attachs: Email attachments as (name, mimetype, file) tuples
            mimetype: MIME type for the email body
            charset: Character encoding for the email
        """
        # This would be the actual SES implementation
        # For now, we'll just log a message indicating what would happen
        to_list = to if isinstance(to, list) else [to]
        cc_list = cc if isinstance(cc, list) else ([cc] if cc else [])
        
        logger.info(
            "Would send via SES - Region: %s, From: %s, To: %s, CC: %s, "
            "Subject: %s, Body length: %d, Attachments: %d",
            self.region,
            self.source_email,
            to_list,
            cc_list,
            subject,
            len(body),
            len(attachs),
        )
        
        # Actual implementation would use boto3:
        # try:
        #     import boto3
        #     client = boto3.client('ses', region_name=self.region)
        #     # Send email using SES API
        # except ImportError:
        #     raise ImportError("boto3 is required for SESMailSender")