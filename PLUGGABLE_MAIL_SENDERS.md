# Pluggable Mail Senders

This document describes the new pluggable mail sender system in Scrapy that allows you to customize email sending behavior.

## Overview

Starting with Scrapy 2.14, the mail sending functionality has been made pluggable, allowing you to:

- Use alternative email services (like Amazon SES, SendGrid, etc.)
- Implement custom authentication mechanisms
- Use different transport protocols
- Add custom logging or monitoring
- Avoid dependency on Twisted for email sending

## Basic Usage

### Using the Default Mail Sender

The default behavior remains unchanged. The original `MailSender` continues to work as before:

```python
from scrapy.mail import MailSender

# Create mail sender (traditional way)
mail_sender = MailSender(
    smtphost='smtp.gmail.com',
    mailfrom='your@email.com',
    smtpuser='your@email.com',
    smtppass='your_password',
    smtpport=587,
    smtptls=True
)

# Send email (traditional sync way)
mail_sender.send(
    to='recipient@example.com',
    subject='Test Subject',
    body='Test message body'
)
```

### Using a Custom Mail Sender

To use a custom mail sender, set the `MAIL_SENDER_CLASS` setting:

```python
# In settings.py
MAIL_SENDER_CLASS = 'myproject.mail.CustomMailSender'
```

Or configure it in your spider:

```python
custom_settings = {
    'MAIL_SENDER_CLASS': 'scrapy.mail_senders.DummyMailSender'
}
```

## Creating Custom Mail Senders

### Method 1: Inherit from BaseMailSender

```python
from scrapy.mail_interfaces import BaseMailSender
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO, Any
    from scrapy.crawler import Crawler

class CustomMailSender(BaseMailSender):
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
    
    @classmethod
    def from_crawler(cls, crawler):
        api_key = crawler.settings.get('CUSTOM_MAIL_API_KEY')
        return cls(api_key=api_key)
    
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
        # Your custom email sending logic here
        print(f"Sending email via custom API: {subject}")
        # e.g., make HTTP request to email service API
```

### Method 2: Implement the Protocol

```python
from scrapy.mail_interfaces import MailSenderInterface

class MyMailSender:
    """Mail sender that implements the MailSenderInterface protocol."""
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls()
    
    async def send(self, to, subject, body, **kwargs):
        # Your implementation
        pass
```

## Built-in Alternative Mail Senders

### DummyMailSender

For testing and development, use the `DummyMailSender` which logs emails instead of sending them:

```python
# In settings.py
MAIL_SENDER_CLASS = 'scrapy.mail_senders.DummyMailSender'
DUMMY_MAIL_LOG_LEVEL = 'INFO'  # Optional: Set log level
```

### SESMailSender (Placeholder)

A placeholder for Amazon SES integration:

```python
# In settings.py
MAIL_SENDER_CLASS = 'scrapy.mail_senders.SESMailSender'
AWS_SES_REGION = 'us-east-1'
AWS_SES_SOURCE_EMAIL = 'verified@yourdomain.com'
```

## Integration with Extensions

The mail sender is automatically used by Scrapy's built-in extensions:

### StatsMailer Extension

```python
# In settings.py
STATSMAILER_RCPTS = ['admin@yourcompany.com']
MAIL_SENDER_CLASS = 'scrapy.mail_senders.DummyMailSender'  # Will use custom sender
```

### MemoryUsage Extension

```python
# In settings.py
MEMUSAGE_ENABLED = True
MEMUSAGE_NOTIFY_MAIL = ['admin@yourcompany.com']
MAIL_SENDER_CLASS = 'myproject.mail.CustomMailSender'  # Will use custom sender
```

## Advanced Examples

### SendGrid Integration

```python
import sendgrid
from sendgrid.helpers.mail import Mail
from scrapy.mail_interfaces import BaseMailSender

class SendGridMailSender(BaseMailSender):
    def __init__(self, api_key: str, from_email: str):
        super().__init__()
        self.sg = sendgrid.SendGridAPIClient(api_key=api_key)
        self.from_email = from_email
    
    @classmethod
    def from_crawler(cls, crawler):
        api_key = crawler.settings.get('SENDGRID_API_KEY')
        from_email = crawler.settings.get('SENDGRID_FROM_EMAIL')
        return cls(api_key=api_key, from_email=from_email)
    
    async def send(self, to, subject, body, **kwargs):
        to_list = to if isinstance(to, list) else [to]
        
        message = Mail(
            from_email=self.from_email,
            to_emails=to_list,
            subject=subject,
            html_content=body
        )
        
        try:
            response = self.sg.send(message)
            print(f"Email sent successfully: {response.status_code}")
        except Exception as e:
            print(f"Error sending email: {e}")
```

### Gmail API Integration

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from scrapy.mail_interfaces import BaseMailSender
import base64
from email.mime.text import MIMEText

class GmailAPIMailSender(BaseMailSender):
    def __init__(self, credentials_path: str):
        super().__init__()
        self.creds = Credentials.from_authorized_user_file(credentials_path)
        self.service = build('gmail', 'v1', credentials=self.creds)
    
    @classmethod
    def from_crawler(cls, crawler):
        creds_path = crawler.settings.get('GMAIL_CREDENTIALS_PATH')
        return cls(credentials_path=creds_path)
    
    async def send(self, to, subject, body, **kwargs):
        message = MIMEText(body)
        message['to'] = to if isinstance(to, str) else ', '.join(to)
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        try:
            self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            print(f"Email sent via Gmail API: {subject}")
        except Exception as e:
            print(f"Error sending email via Gmail API: {e}")
```

## Migration Guide

### From Old MailSender

If you were using `MailSender.from_settings()`:

```python
# Old way (deprecated)
from scrapy.mail import MailSender
sender = MailSender.from_settings(settings)

# New way
from scrapy.mail import get_mail_sender_from_crawler
sender = get_mail_sender_from_crawler(crawler)
```

### Async vs Sync

The new interface is async-first, but the old sync interface is still supported:

```python
# New async way (recommended)
await mail_sender.send_async(to='user@example.com', subject='Hello', body='World')

# Old sync way (still works)
mail_sender.send(to='user@example.com', subject='Hello', body='World')
```

## Configuration Reference

| Setting | Description | Default |
|---------|-------------|---------|
| `MAIL_SENDER_CLASS` | Full Python path to mail sender class | `'scrapy.mail.MailSender'` |
| `DUMMY_MAIL_LOG_LEVEL` | Log level for DummyMailSender | `'INFO'` |
| `AWS_SES_REGION` | AWS region for SES | `'us-east-1'` |
| `AWS_SES_SOURCE_EMAIL` | Verified source email for SES | `''` |

## Best Practices

1. **Testing**: Use `DummyMailSender` during development
2. **Error Handling**: Always implement proper error handling in custom senders
3. **Async/Await**: Use async methods for better performance
4. **Configuration**: Use settings for all configuration options
5. **Logging**: Add appropriate logging to custom mail senders

## Troubleshooting

### Import Errors
Make sure your custom mail sender class is importable:
```python
# Test import
from myproject.mail import CustomMailSender
```

### Interface Errors
Ensure your custom class implements the required methods:
```python
# Check if class implements interface
from scrapy.mail_interfaces import BaseMailSender
assert issubclass(CustomMailSender, BaseMailSender)
```

### Async Issues
If you're having issues with async methods, ensure you're using proper async/await syntax:
```python
# Correct
await mail_sender.send_async(...)

# Incorrect
mail_sender.send_async(...)  # Missing await
```