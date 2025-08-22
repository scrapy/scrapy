"""Tests for the Embeddings LiteLLM pipeline."""

from __future__ import annotations

import pytest

from scrapy.pipelines.embeddings import EmbeddingsLiteLLMPipeline
from scrapy.utils.test import get_crawler


@pytest.fixture
def pipeline(monkeypatch):
    def mock_embedding(*args, **kwargs):
        return {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "model": "text-embedding-3-small",
            "object": "list",
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        }

    mock_litellm_obj = type(
        "MockLiteLLM", (), {"api_key": None, "embedding": mock_embedding}
    )
    monkeypatch.setattr("scrapy.pipelines.embeddings.litellm", mock_litellm_obj)
    return EmbeddingsLiteLLMPipeline(api_key="test-key")


@pytest.mark.requires_litellm
class TestEmbeddingsLiteLLMPipeline:
    def test_from_crawler_with_default_settings(self, pipeline):
        settings = {"LITELLM_API_KEY": "test-api-key"}
        crawler = get_crawler(None, settings)
        pipeline = EmbeddingsLiteLLMPipeline.from_crawler(crawler)
        assert pipeline.model == "text-embedding-3-small"

    def test_from_crawler_with_custom_settings(self, pipeline):
        settings = {
            "LITELLM_API_KEY": "test-api-key",
            "LITELLM_EMBEDDING_MODEL": "cohere/embed-english-v3.0",
        }
        crawler = get_crawler(None, settings)
        pipeline = EmbeddingsLiteLLMPipeline.from_crawler(crawler)
        assert pipeline.model == "cohere/embed-english-v3.0"

    def test_process_item(self, pipeline):
        item = {
            "id": "123",
            "page_content": "Hello world",
            "metadata": {"title": "Test Item", "source": "test.pdf"},
            "url": "https://example.com",  # Extra field - should be ignored
            "timestamp": "2024-01-01",  # Extra field - should be ignored
        }
        result = pipeline.process_item(item, None)

        # Verify Pinecone format
        assert result["id"] == "123"
        assert result["values"] == [0.1, 0.2, 0.3]
        assert result["metadata"]["page_content"] == "Hello world"
        assert result["metadata"]["title"] == "Test Item"
        assert result["metadata"]["source"] == "test.pdf"

        # Extra fields should be preserved (JsonLines exporter handles final format)
        assert result["url"] == "https://example.com"
        assert result["timestamp"] == "2024-01-01"

    @pytest.mark.parametrize(
        ("item", "description"),
        [
            ({"id": "123", "metadata": {"title": "Test"}}, "missing page_content"),
            (
                {"id": "123", "page_content": "", "metadata": {"title": "Test"}},
                "empty page_content",
            ),
            (
                {"id": "123", "page_content": None, "metadata": {"title": "Test"}},
                "None page_content",
            ),
            (
                {"id": "123", "page_content": 12345, "metadata": {"title": "Test"}},
                "invalid type page_content",
            ),
        ],
    )
    def test_skip_invalid_items(self, pipeline, item, description):
        original_item = item.copy()
        result = pipeline.process_item(item, None)

        assert "values" not in result, f"Should skip item with {description}"
        assert result == original_item, f"Item should be unchanged with {description}"
