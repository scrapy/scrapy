"""
DAP RRI Spider - Scrapes portal and streaming detail pages from dap.rri.go.id

This spider authenticates with the DAP RRI platform and scrapes data from:
- Portal detail page: /portal/detail?page=6
- Streaming detail page: /streaming/detail?page=2

Usage:
    scrapy crawl dap -a email=YOUR_EMAIL -a password=YOUR_PASSWORD

    # Save output to JSON:
    scrapy crawl dap -a email=YOUR_EMAIL -a password=YOUR_PASSWORD -o output.json
"""

import json
import re
from datetime import datetime, timedelta

import scrapy


class DapSpider(scrapy.Spider):
    name = "dap"
    allowed_domains = ["dap.rri.go.id"]

    # Base URL
    base_url = "https://dap.rri.go.id"
    login_url = "https://dap.rri.go.id/"

    # Target pages to scrape (HTML pages)
    target_pages = [
        "/portal/detail?page=6",
        "/streaming/detail?page=2",
    ]

    # API endpoints for actual data (these return JSON)
    WEBLYTIC_ENDPOINTS = {
        "page_view_total": "api/weblytic/get_page_view_total",
        "session_total": "api/weblytic/get_session_total",
        "user_total": "api/weblytic/get_user_total",
        "new_user_total": "api/weblytic/get_new_user_total",
        "traffic_hour_day": "api/weblytic/get_traffic_hour_day",
        "traffic_utm_source": "api/weblytic/get_traffic_utm_source_nested_source",
        "traffic_url_path": "api/weblytic/get_traffic_url_path",
    }

    STREAMING_ENDPOINTS = {
        "hits_hour_day": "api/streaming/get_hits_hour_day",
        "hits_city": "api/streaming/get_hits_city",
        "hits_country": "api/streaming/get_hits_country",
        "hits_programa": "api/streaming/get_hits_programa",
        "hits_total": "api/streaming/get_hits_total",
    }

    # Custom settings for this spider
    custom_settings = {
        "ROBOTSTXT_OBEY": False,  # Need to bypass for authenticated scraping
        "COOKIES_ENABLED": True,
        "DOWNLOAD_DELAY": 1,
        "HTTPERROR_ALLOWED_CODES": [
            302,
            303,
            401,
            403,
        ],  # Handle redirects and auth errors
        "LOG_LEVEL": "DEBUG",  # More verbose logging
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        },
    }

    def __init__(self, email=None, password=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email = email
        self.password = password

        if not self.email or not self.password:
            self.logger.warning(
                "No credentials provided. Use: scrapy crawl dap -a email=EMAIL -a password=PASSWORD"
            )

    def start_requests(self):
        """Start by fetching the login page to get CSRF token."""
        self.logger.info("🔐 Starting authentication process...")
        yield scrapy.Request(
            url=self.login_url,
            callback=self.parse_login_page,
            dont_filter=True,
        )

    def parse_login_page(self, response):
        """Parse login page to extract CSRF token and submit login form."""
        self.logger.info(
            f"📄 Got login page: {response.url} (status: {response.status})"
        )

        # Save login page for debugging
        with open("login_page_debug.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        self.logger.info("📄 Saved login page HTML to login_page_debug.html")

        # Extract CSRF token from meta tag
        csrf_token = response.css('meta[name="csrf-token"]::attr(content)').get()

        if not csrf_token:
            # Try finding it in a hidden input field
            csrf_token = response.css('input[name="_token"]::attr(value)').get()

        if not csrf_token:
            self.logger.error("❌ Could not find CSRF token on login page")
            self.logger.debug(f"Page content preview: {response.text[:500]}")
            return

        self.logger.info(f"✓ Found CSRF token: {csrf_token[:20]}...")

        # Submit login form using direct POST (like dap_scraper.py)
        yield scrapy.FormRequest(
            url=self.login_url,
            formdata={
                "_token": csrf_token,
                "email": self.email,
                "password": self.password,
            },
            headers={
                "X-CSRF-TOKEN": csrf_token,
                "Referer": self.login_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            callback=self.after_login,
            dont_filter=True,
        )

    def after_login(self, response):
        """Check login success and start scraping target pages and API endpoints."""
        # Check if login was successful by looking at the URL or page content
        if "login" in response.url.lower() and response.status == 200:
            # Check for error messages
            error_msg = response.css(".alert-danger::text").get()
            if error_msg:
                self.logger.error(f"❌ Login failed: {error_msg.strip()}")
                return

        # Check for dashboard or home indicators
        if "dashboard" in response.url or "portal" in response.text.lower():
            self.logger.info(f"✓ Login successful! Redirected to: {response.url}")
        else:
            self.logger.info(f"➡️ Post-login URL: {response.url}")

        # Generate date range for API calls (last 7 days)

        end = datetime.now()
        start = end - timedelta(days=7)
        date_range = (
            f"{start.strftime('%d/%m/%Y')} 00:00 - {end.strftime('%d/%m/%Y')} 23:59"
        )

        # Scrape weblytic API endpoints
        for name, endpoint in self.WEBLYTIC_ENDPOINTS.items():
            url = f"{self.base_url}/{endpoint}"
            self.logger.info(f"📊 Queuing weblytic API: {name}")
            yield scrapy.Request(
                url=url,
                callback=self.parse_api_response,
                meta={
                    "api_type": "weblytic",
                    "endpoint_name": name,
                    "date_range": date_range,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
                dont_filter=True,
                cb_kwargs={"date_range": date_range, "time_span": "auto"},
            )

        # Scrape streaming API endpoints
        for name, endpoint in self.STREAMING_ENDPOINTS.items():
            url = f"{self.base_url}/{endpoint}"
            self.logger.info(f"📊 Queuing streaming API: {name}")
            yield scrapy.Request(
                url=url,
                callback=self.parse_api_response,
                meta={
                    "api_type": "streaming",
                    "endpoint_name": name,
                    "date_range": date_range,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
                dont_filter=True,
                cb_kwargs={"date_range": date_range, "time_span": "auto"},
            )

        # Also scrape the HTML target pages
        for page_path in self.target_pages:
            url = f"{self.base_url}{page_path}"
            self.logger.info(f"📄 Queuing target page: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse_detail_page,
                meta={"page_type": self._get_page_type(page_path)},
                dont_filter=True,
            )

    def parse_api_response(self, response, date_range=None, time_span=None):
        """Parse JSON response from API endpoints."""
        api_type = response.meta.get("api_type", "unknown")
        endpoint_name = response.meta.get("endpoint_name", "unknown")

        self.logger.info(f"📈 Parsing {api_type} API response: {endpoint_name}")

        item = {
            "url": response.url,
            "api_type": api_type,
            "endpoint_name": endpoint_name,
            "date_range": date_range,
            "scraped_at": datetime.now().isoformat(),
            "status_code": response.status,
        }

        try:
            data = json.loads(response.text)
            item["data"] = data
            self.logger.info(f"   ✓ Got JSON data for {endpoint_name}")
        except json.JSONDecodeError:
            item["error"] = "Failed to parse JSON"
            item["raw_response"] = response.text[:500]
            self.logger.warning(f"   ⚠️ Failed to parse JSON for {endpoint_name}")

        yield item

    def _get_page_type(self, path):
        """Determine page type from path."""
        if "/portal/" in path:
            return "portal"
        elif "/streaming/" in path:
            return "streaming"
        return "unknown"

    def parse_detail_page(self, response):
        """Parse the detail page and extract data."""
        page_type = response.meta.get("page_type", "unknown")
        self.logger.info(f"📈 Parsing {page_type} detail page: {response.url}")

        # Create base item
        item = {
            "url": response.url,
            "page_type": page_type,
            "scraped_at": datetime.now().isoformat(),
            "status_code": response.status,
        }

        # Extract page title
        item["title"] = response.css("title::text").get("").strip()

        # Try to extract data tables
        tables = self._extract_tables(response)
        if tables:
            item["tables"] = tables

        # Try to extract card data (common in dashboard layouts)
        cards = self._extract_cards(response)
        if cards:
            item["cards"] = cards

        # Extract any JSON data embedded in the page (common in SPAs)
        json_data = self._extract_embedded_json(response)
        if json_data:
            item["embedded_data"] = json_data

        # Extract pagination info
        pagination = self._extract_pagination(response)
        if pagination:
            item["pagination"] = pagination

        # Extract list items (common format for detail pages)
        list_items = self._extract_list_items(response)
        if list_items:
            item["list_items"] = list_items

        yield item

    def _extract_tables(self, response):
        """Extract data from HTML tables."""
        tables = []
        for table in response.css("table"):
            table_data = {
                "headers": [],
                "rows": [],
            }

            # Extract headers
            headers = table.css("thead th::text, thead td::text").getall()
            table_data["headers"] = [h.strip() for h in headers if h.strip()]

            # Extract rows
            for row in table.css("tbody tr"):
                cells = row.css("td::text, td a::text").getall()
                cells = [c.strip() for c in cells if c.strip()]
                if cells:
                    table_data["rows"].append(cells)

            if table_data["headers"] or table_data["rows"]:
                tables.append(table_data)

        return tables if tables else None

    def _extract_cards(self, response):
        """Extract data from card components."""
        cards = []
        for card in response.css(".card, .panel, .box"):
            card_data = {}

            # Card title/header
            title = card.css(
                ".card-header::text, .card-title::text, .panel-heading::text, h4::text, h5::text"
            ).get()
            if title:
                card_data["title"] = title.strip()

            # Card body content
            body = card.css(".card-body::text, .panel-body::text").get()
            if body:
                card_data["content"] = body.strip()

            # Look for metric values (common in analytics dashboards)
            value = card.css(
                ".metric-value::text, .stat-value::text, h2::text, h3::text"
            ).get()
            if value:
                card_data["value"] = value.strip()

            if card_data:
                cards.append(card_data)

        return cards if cards else None

    def _extract_embedded_json(self, response):
        """Extract JSON data embedded in script tags."""
        json_data = []

        # Look for inline JSON data
        scripts = response.css("script:not([src])::text").getall()
        for script in scripts:
            # Look for common patterns like var data = {...}
            patterns = [
                r"var\s+data\s*=\s*(\{.*?\});",
                r"var\s+config\s*=\s*(\{.*?\});",
                r'JSON\.parse\([\'"](.+?)[\'"]\)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, script, re.DOTALL)
                for match in matches:
                    try:
                        parsed = json.loads(match)
                        json_data.append(parsed)
                    except json.JSONDecodeError:
                        pass

        return json_data if json_data else None

    def _extract_pagination(self, response):
        """Extract pagination information."""
        pagination = {}

        # Current page
        current = response.css(
            ".pagination .active::text, .page-item.active .page-link::text"
        ).get()
        if current:
            pagination["current_page"] = current.strip()

        # Total pages (look for last page link)
        page_links = response.css(".pagination a::text, .page-link::text").getall()
        page_numbers = [int(p) for p in page_links if p.strip().isdigit()]
        if page_numbers:
            pagination["total_pages"] = max(page_numbers)

        # Next/Previous links
        next_link = response.css(
            ".pagination .next a::attr(href), a[rel='next']::attr(href)"
        ).get()
        if next_link:
            pagination["next_url"] = response.urljoin(next_link)

        prev_link = response.css(
            ".pagination .prev a::attr(href), a[rel='prev']::attr(href)"
        ).get()
        if prev_link:
            pagination["prev_url"] = response.urljoin(prev_link)

        return pagination if pagination else None

    def _extract_list_items(self, response):
        """Extract list items from the page."""
        items = []

        # Look for common list structures
        for li in response.css(".list-group-item, .media, .item"):
            item_data = {}

            # Title
            title = li.css("h4::text, h5::text, .title::text, a::text").get()
            if title:
                item_data["title"] = title.strip()

            # Description/content
            desc = li.css("p::text, .description::text, .content::text").get()
            if desc:
                item_data["description"] = desc.strip()

            # Link
            link = li.css("a::attr(href)").get()
            if link:
                item_data["link"] = response.urljoin(link)

            if item_data:
                items.append(item_data)

        return items if items else None
