# Slovenian Tax Knowledge Scraper

A modular web scraper for collecting tax-related content from Slovenian websites. Designed for building AI training datasets for tax advisory applications.

## Features

- **Modular architecture**: Easy to add new websites
- **Slovenian tax keywords**: Auto-classification into individual, s.p., d.o.o. categories
- **AI-ready output**: JSONL/JSON format optimized for training
- **Polite crawling**: Respects robots.txt, rate limiting, retries
- **Dual interface**: CLI for testing + Python API for integration

## Quick Start

### Installation

```bash
# Copy the tax_scraper folder to your project
cp -r tax_scraper /path/to/your/project/

# Install dependencies
pip install scrapy w3lib itemloaders
```

### CLI Usage

```bash
# List available spiders
python -m tax_scraper list

# Scrape a specific site
python -m tax_scraper scrape --site simic

# Scrape all sites
python -m tax_scraper scrape --all

# Custom output directory
python -m tax_scraper scrape --site furs --output-dir ./data --format json

# View results
python -m tax_scraper results --dir ./output
```

### Python API Usage

```python
from tax_scraper import TaxScraper, get_available_spiders

# Check available spiders
print(get_available_spiders())  # ['simic', 'furs', 'finance']

# Initialize scraper
scraper = TaxScraper(
    output_dir="./data",
    output_format="jsonl",  # or "json"
    filter_non_tax=False,   # Set True to only keep tax content
)

# Scrape one site
results = scraper.scrape("simic")
print(f"Scraped {len(results)} articles")

# Scrape all sites
all_results = scraper.scrape_all()
```

## Output Schema

Each scraped article has this structure:

```json
{
    "id": "a1b2c3d4e5f6",
    "source": "simic-partnerji.si",
    "url": "https://simic-partnerji.si/blog/davki-za-sp/",
    "title": "Davki za samostojne podjetnike v letu 2026",
    "content": "Full article text...",
    "summary": "First 500 characters...",
    "category": "s.p.",
    "tax_topics": ["samostojni podjetnik", "dohodnina", "prispevki"],
    "author": "Jože Novak",
    "published_date": "2026-01-15",
    "scraped_at": "2026-01-24T10:30:00",
    "language": "sl"
}
```

### Categories

- `individual`: Personal income tax (dohodnina)
- `s.p.`: Sole proprietor taxation
- `d.o.o.`: LLC/company taxation
- `general`: General tax topics

## Adding New Sites

1. Copy `spiders/template.py` to `spiders/mysite.py`
2. Rename the class and update:
   - `name`: Unique spider identifier
   - `allowed_domains`: Domains to crawl
   - `start_urls`: Starting URL(s)
3. Implement `parse_article_list()` and `parse_article()`
4. Uncomment `@SpiderRegistry.register`

Example:

```python
from ..core.base_spider import BaseTaxSpider
from .registry import SpiderRegistry

@SpiderRegistry.register
class MySiteSpider(BaseTaxSpider):
    name = "mysite"
    allowed_domains = ["mysite.si"]
    start_urls = ["https://mysite.si/davki/"]

    def parse_article_list(self, response):
        for link in response.css("article a::attr(href)").getall():
            yield scrapy.Request(response.urljoin(link), self.parse_article)

    def parse_article(self, response):
        loader = self.create_loader(response)
        loader.add_css("title", "h1::text")
        loader.add_css("content", ".article-body *::text")
        yield self.finalize_item(loader)
```

## Integration with Your App

### Flask Example

```python
from flask import Flask, jsonify
from tax_scraper import TaxScraper

app = Flask(__name__)
scraper = TaxScraper(output_dir="./scraped_data")

@app.route("/scrape/<site>")
def scrape_site(site):
    try:
        results = scraper.scrape(site)
        return jsonify({"status": "ok", "items": len(results)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
```

### Background Scraping

```python
# For long-running scrapes, use subprocess
output_file = scraper.scrape_async("furs")
print(f"Scraping in background, output: {output_file}")
```

### Loading Results

```python
# Load previously scraped data
scraper = TaxScraper(output_dir="./data")
files = scraper.get_output_files()

for filepath in files:
    items = scraper.load_results(filepath)
    for item in items:
        # Process for AI training
        training_text = f"{item['title']}\n\n{item['content']}"
        category = item['category']
```

## Configuration

Settings in `settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DOWNLOAD_DELAY` | 1 | Seconds between requests |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 2 | Max parallel requests per site |
| `ROBOTSTXT_OBEY` | True | Respect robots.txt |
| `AUTOTHROTTLE_ENABLED` | True | Auto-adjust crawl speed |
| `MIN_CONTENT_LENGTH` | 100 | Min chars to keep article |
| `FILTER_NON_TAX` | False | Only keep tax-related content |

## Available Spiders

| Name | Domain | Description |
|------|--------|-------------|
| `simic` | simic-partnerji.si | Tax advisory blog |
| `furs` | fu.gov.si | Official tax authority |
| `finance` | finance.si | Financial news |

## Troubleshooting

### Site blocks requests
- Increase `DOWNLOAD_DELAY` in settings
- Add cookies if needed: `COOKIES_ENABLED = True`
- Some sites need specific headers

### No content extracted
- Check spider's CSS selectors match site structure
- Run with `--log-level DEBUG` to see details
- Site structure may have changed

### Rate limiting (429 errors)
- Increase delays in spider's `custom_settings`
- Enable `AUTOTHROTTLE_ENABLED`
