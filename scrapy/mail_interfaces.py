"""
Mail sender interfaces for pluggable email sending

This module defines the interfaces for pluggable mail senders that allow
users to implement custom email sending logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


class MailSenderInterface(Protocol):
    """Protocol for mail sender implementations.
    
    This protocol defines the interface that all mail sender implementations
    must follow. It uses coroutines for async email sending.
    """
    
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Create mail sender instance from crawler.
        
        Args:
            crawler: The Scrapy crawler instance
            
        Returns:
            Mail sender instance
        """
        ...
    
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
        """Send an email message.
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            cc: CC recipient email address(es)
            attachs: Email attachments as (name, mimetype, file) tuples
            mimetype: MIME type for the email body
            charset: Character encoding for the email
        """
        ...


class BaseMailSender(ABC):
    """Abstract base class for mail sender implementations.
    
    This class provides a common base for mail sender implementations
    and defines the interface that subclasses must implement.
    """
    
    def __init__(self) -> None:
        """Initialize the mail sender."""
        pass
    
    @classmethod
    @abstractmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Create mail sender instance from crawler.
        
        Args:
            crawler: The Scrapy crawler instance
            
        Returns:
            Mail sender instance
        """
        pass
    
    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        """Create mail sender instance from settings.
        
        Args:
            settings: The Scrapy settings
            
        Returns:
            Mail sender instance
            
        Note:
            This method is deprecated. Use from_crawler() instead.
        """
        # Provide a default implementation for backward compatibility
        # Subclasses can override this if needed
        raise NotImplementedError(
            f"{cls.__name__}.from_settings() is not implemented. "
            "Use from_crawler() instead."
        )
    
    @abstractmethod
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
        """Send an email message.
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body content
            cc: CC recipient email address(es)
            attachs: Email attachments as (name, mimetype, file) tuples
            mimetype: MIME type for the email body
            charset: Character encoding for the email
        """
        pass