# Agent Instructions

This file provides guidance for AI coding agents (Claude Code, GitHub Copilot, Cursor, Gemini CLI) working in this repository.

## Development Guidelines
- Read the README and CONTRIBUTING docs before making changes
- Follow the coding style and test conventions already in use
- Check open issues and PRs to avoid duplicate work
- Run existing tests before submitting

## AI Agent Usage (MAI-1)

Machine-readable contract for this library. AI agents can use this block to discover how to install and invoke the library without parsing the full README. This block is self-contained — no external services are queried.

```json
{
  "aid": "scrapy-v1",
  "logic": {
    "input_schema": {
      "type": "url",
      "description": "A URL or list of URLs to scrape structured data from"
    },
    "output_schema": {
      "type": "json",
      "description": "Structured data extracted from the target website"
    }
  },
  "trust": {
    "reliability_score": 0.95,
    "latency_ms": 100
  },
  "action": {
    "install_cmd": "pip install scrapy",
    "execute_cmd": "scrapy crawl <spider_name>"
  }
}
```
