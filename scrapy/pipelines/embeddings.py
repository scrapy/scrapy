"""
Embeddings Pipeline

Adds vector embeddings to scraped items.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter

from scrapy.exceptions import NotConfigured

# Optional dependency
try:
    import litellm
except ImportError:
    litellm = None

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class EmbeddingsLiteLLMPipeline:
    """Add vector embeddings to Pinecone-formatted items using LiteLLM.

    Input item format:
        {
            'id': 'unique_id',
            'page_content': 'text to embed',
            'metadata': {'source': 'file.pdf', ...}
        }

    Output item format:
        {
            'id': 'unique_id',
            'values': [0.1, 0.2, 0.3, ...],      # Created by pipeline
            'metadata': {
                'page_content': 'text to embed', # Moved by pipeline
                'source': 'file.pdf',
                ...
            }
        }

    Settings:
        LITELLM_API_KEY: API key for the embedding provider (required)
        LITELLM_EMBEDDING_MODEL: Model to use (default: openai's "text-embedding-3-small")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
    ):
        if not api_key:
            raise NotConfigured("LITELLM_API_KEY setting is required")
        if litellm is None:
            raise NotConfigured("litellm package not installed")

        litellm.api_key = api_key
        self.model = model

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        return cls(
            api_key=settings.get("LITELLM_API_KEY"),
            model=settings.get("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small"),
        )

    def process_item(self, item: Any, spider: Spider) -> Any:
        adapter = ItemAdapter(item)

        page_content = adapter.get("page_content")
        if not page_content or not isinstance(page_content, str):
            logger.debug(
                f"Skipping item - invalid page_content: {page_content!r} "
                f"({type(page_content).__name__})",
                extra={"spider": spider},
            )
            return item

        response = litellm.embedding(
            model=self.model, input=page_content, num_retries=3
        )
        embedding = response["data"][0]["embedding"]

        adapter["id"] = str(adapter["id"])
        adapter["values"] = embedding
        adapter["metadata"] = {
            **adapter.get("metadata", {}),
            "page_content": page_content,
        }
        del adapter["page_content"]

        logger.debug(
            f"Added embedding vector (length={len(embedding)}) "
            f"to item {adapter.get('id', 'unknown')} via {self.model}",
            extra={"spider": spider},
        )
        return item
