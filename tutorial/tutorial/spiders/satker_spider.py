"""
DAP RRI Satker Spider - Scrapes analytics data for all 100 satkers

This spider authenticates with DAP RRI and scrapes weblytic data
for each satker, then exports to Excel format matching the template.

Usage:
    scrapy crawl satker_scraper -a email=EMAIL -a password=PASSWORD
    
    # With custom date range:
    scrapy crawl satker_scraper -a email=EMAIL -a password=PASSWORD \
        -a start_date=01/01/2026 -a end_date=31/01/2026
"""

import json
from datetime import datetime
from urllib.parse import urlencode

import scrapy


class SatkerSpider(scrapy.Spider):
    name = "satker_scraper"
    allowed_domains = ["dap.rri.go.id"]

    # Base URL
    base_url = "https://dap.rri.go.id"
    login_url = "https://dap.rri.go.id/"

    # API endpoint for page view data (contains all needed metrics)
    page_view_endpoint = "api/weblytic/get_page_view_total"

    # All 100 satkers from the Excel file
    SATKERS = [
        "Aceh Singkil",
        "Alor",
        "Ambon",
        "Ampana",
        "Atambua",
        "Banda Aceh",
        "Bandar Lampung",
        "Bandung",
        "Banjarmasin",
        "Banten",
        "Batam",
        "Baubau",
        "Belitung",
        "Bengkalis",
        "Bengkulu",
        "Biak",
        "Bima",
        "Bintuhan",
        "Bogor",
        "Bone",
        "Bovendigoel",
        "Bukittinggi",
        "Bula",
        "Cirebon",
        "Denpasar",
        "Ende",
        "Entikong",
        "Fak Fak",
        "Gorontalo",
        "Gunung Sitoli",
        "Jakarta",
        "Jambi",
        "Jayapura",
        "Jember",
        "Kaimana",
        "Kediri",
        "Kendari",
        "Kupang",
        "Labuan Bajo",
        "Lhokseumawe",
        "Madiun",
        "Makassar",
        "Malang",
        "Malinau",
        "Mamuju",
        "Manado",
        "Manokwari",
        "Mataram",
        "Medan",
        "Merauke",
        "Meulaboh",
        "Nabire",
        "Nias Selatan",
        "Nunukan",
        "Padang",
        "Palangkaraya",
        "Palembang",
        "Palu",
        "Pekanbaru",
        "Pontianak",
        "Purwokerto",
        "Pusat Pemberitaan",
        "Ranai",
        "Rimba Raya",
        "Rote",
        "Sabang",
        "Samarinda",
        "Sambas",
        "Sampang",
        "Sanggau",
        "Saumlaki",
        "Semarang",
        "Sendawar",
        "Serui",
        "Sibolga",
        "Singaraja",
        "Sintang",
        "Skouw",
        "Sorong",
        "Sumba",
        "Sumenep",
        "Sungailiat",
        "Sungaipenuh",
        "Surabaya",
        "Surakarta",
        "Tahuna",
        "Takengon",
        "Talaud",
        "Tanjung Balai",
        "Tanjungpinang",
        "Tarakan",
        "Teluk Bintuni",
        "Ternate",
        "Toli Toli",
        "Tual",
        "Tuban",
        "Voice of Indonesia",
        "Wamena",
        "Waykanan",
        "Yogyakarta",
    ]

    # Custom settings
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": True,
        "DOWNLOAD_DELAY": 0.5,  # Faster for 100 requests
        "CONCURRENT_REQUESTS": 1,  # Sequential to avoid rate limiting
        "HTTPERROR_ALLOWED_CODES": [302, 303, 401, 403],
        "LOG_LEVEL": "INFO",
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
        },
    }

    def __init__(
        self, email=None, password=None, start_date=None, end_date=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.email = email
        self.password = password

        # Default to January 2026 to match Excel file
        self.start_date = start_date or "01/01/2026"
        self.end_date = end_date or "31/01/2026"

        # Storage for all satker data (used for ranking calculation)
        self.satker_data = []

        if not self.email or not self.password:
            self.logger.warning("No credentials provided!")

    def start_requests(self):
        """Start by fetching the login page."""
        self.logger.info("🔐 Starting authentication...")
        yield scrapy.Request(
            url=self.login_url,
            callback=self.parse_login_page,
            dont_filter=True,
        )

    def parse_login_page(self, response):
        """Parse login page and submit credentials."""
        csrf_token = response.css('meta[name="csrf-token"]::attr(content)').get()

        if not csrf_token:
            csrf_token = response.css('input[name="_token"]::attr(value)').get()

        if not csrf_token:
            self.logger.error("❌ Could not find CSRF token")
            return

        self.logger.info(f"✓ Found CSRF token: {csrf_token[:20]}...")

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
            },
            callback=self.after_login,
            dont_filter=True,
        )

    def after_login(self, response):
        """After login, start scraping data for each satker."""
        if "dashboard" in response.url or response.status == 200:
            self.logger.info("✓ Login successful!")

        # Generate date range string
        date_range = f"{self.start_date} 00:00 - {self.end_date} 23:59"
        self.logger.info(f"📅 Date range: {date_range}")
        self.logger.info(f"📊 Scraping data for {len(self.SATKERS)} satkers...")

        # Request data for each satker
        for idx, satker in enumerate(self.SATKERS):
            params = {
                "date_range": date_range,
                "time_span": "auto",
                "satker": satker,
            }
            url = f"{self.base_url}/{self.page_view_endpoint}?{urlencode(params)}"

            yield scrapy.Request(
                url=url,
                callback=self.parse_satker_data,
                meta={
                    "satker": satker,
                    "satker_index": idx + 1,
                },
                headers={
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                dont_filter=True,
            )

    def parse_satker_data(self, response):
        """Parse API response for each satker."""
        satker = response.meta["satker"]
        idx = response.meta["satker_index"]

        try:
            data = json.loads(response.text)

            item = {
                "SATKER": satker,
                "PAGEVIEW": data.get("total", 0),
                "SESSION": data.get("total_session", 0),
                "NEW USERS": data.get("total_new_user", 0),
                "RETURNING USERS": data.get("total_returning_user", 0),
                "scraped_at": datetime.now().isoformat(),
                "status_code": response.status,
            }

            self.satker_data.append(item)
            self.logger.info(
                f"[{idx}/{len(self.SATKERS)}] {satker}: PV={item['PAGEVIEW']}, Session={item['SESSION']}"
            )

        except json.JSONDecodeError:
            self.logger.warning(f"❌ Failed to parse JSON for {satker}")
            item = {
                "SATKER": satker,
                "PAGEVIEW": 0,
                "SESSION": 0,
                "NEW USERS": 0,
                "RETURNING USERS": 0,
                "error": "JSON parse error",
            }
            self.satker_data.append(item)

        yield item

    def closed(self, reason):
        """Calculate rankings and export to Excel when spider closes."""
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Total satkers scraped: {len(self.satker_data)}")

        if len(self.satker_data) == 0:
            return

        # Sort by pageview descending for ranking
        sorted_by_pv = sorted(
            self.satker_data, key=lambda x: x.get("PAGEVIEW", 0), reverse=True
        )
        sorted_by_session = sorted(
            self.satker_data, key=lambda x: x.get("SESSION", 0), reverse=True
        )

        # Assign ranks
        pv_ranks = {item["SATKER"]: idx + 1 for idx, item in enumerate(sorted_by_pv)}
        session_ranks = {
            item["SATKER"]: idx + 1 for idx, item in enumerate(sorted_by_session)
        }

        for item in self.satker_data:
            item["RANK (PAGEVIEWS)"] = pv_ranks.get(item["SATKER"], 0)
            item["RANK (SESSION)"] = session_ranks.get(item["SATKER"], 0)

        # Export to Excel
        try:
            import pandas as pd

            df = pd.DataFrame(self.satker_data)

            # Reorder columns to match Excel template
            columns = [
                "SATKER",
                "PAGEVIEW",
                "SESSION",
                "NEW USERS",
                "RETURNING USERS",
                "RANK (PAGEVIEWS)",
                "RANK (SESSION)",
            ]
            df = df[[c for c in columns if c in df.columns]]

            # Sort by SATKER name for consistency
            df = df.sort_values("SATKER")

            output_file = f"satkers_scraped_{self.start_date.replace('/', '')}-{self.end_date.replace('/', '')}.xlsx"
            df.to_excel(output_file, index=False)
            self.logger.info(f"✅ Exported to: {output_file}")

            # Also show summary
            self.logger.info(f"\n📊 Summary:")
            self.logger.info(f"   Total Pageviews: {df['PAGEVIEW'].sum():,}")
            self.logger.info(f"   Total Sessions: {df['SESSION'].sum():,}")
            self.logger.info(f"   Total New Users: {df['NEW USERS'].sum():,}")

        except ImportError:
            self.logger.warning("⚠️ pandas not installed, cannot export to Excel")
        except Exception as e:
            self.logger.error(f"❌ Export error: {e}")
