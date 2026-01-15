"""
DAP RRI Streaming Satker Spider - Scrapes streaming analytics with PRO 1-4 breakdown

This spider authenticates with DAP RRI and scrapes streaming data
for each satker with breakdown by programa (PRO 1, 2, 3, 4).

Output format matches template: SATKER, PRO 1, PRO 2, PRO 3, PRO 4, ALL PRO,
TOTAL HITS *DAP VER., TOTAL USER

Usage:
    scrapy crawl streaming_scraper -a email=EMAIL -a password=PASSWORD
"""

import json
from datetime import datetime
from urllib.parse import urlencode

import scrapy


class StreamingSatkerSpider(scrapy.Spider):
    name = "streaming_scraper"
    allowed_domains = ["dap.rri.go.id"]

    base_url = "https://dap.rri.go.id"
    login_url = "https://dap.rri.go.id/"
    hits_endpoint = "api/streaming/get_hits_total"

    # Port/Programa names to query
    PROGRAMAS = ["Pro 1", "Pro 2", "Pro 3", "Pro 4"]

    # All satkers (104 from template)
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
        "Channel 5",
        "Cirebon",
        "Dangdut",
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

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": True,
        "DOWNLOAD_DELAY": 0.3,
        "CONCURRENT_REQUESTS": 1,
        "HTTPERROR_ALLOWED_CODES": [302, 303, 401, 403],
        "LOG_LEVEL": "INFO",
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
            "X-Requested-With": "XMLHttpRequest",
        },
    }

    def __init__(
        self, email=None, password=None, start_date=None, end_date=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.email = email
        self.password = password
        self.start_date = start_date or "01/01/2026"
        self.end_date = end_date or "31/01/2026"

        # Storage: {satker: {pro1: X, pro2: X, ...}}
        self.satker_data = {}

        if not self.email or not self.password:
            self.logger.warning("No credentials provided!")

    def start_requests(self):
        self.logger.info("🔐 Starting authentication...")
        yield scrapy.Request(
            url=self.login_url,
            callback=self.parse_login_page,
            dont_filter=True,
        )

    def parse_login_page(self, response):
        csrf_token = response.css('meta[name="csrf-token"]::attr(content)').get()
        if not csrf_token:
            csrf_token = response.css('input[name="_token"]::attr(value)').get()
        if not csrf_token:
            self.logger.error("❌ Could not find CSRF token")
            return

        self.logger.info(f"✓ Found CSRF token")
        yield scrapy.FormRequest(
            url=self.login_url,
            formdata={
                "_token": csrf_token,
                "email": self.email,
                "password": self.password,
            },
            headers={"X-CSRF-TOKEN": csrf_token, "Referer": self.login_url},
            callback=self.after_login,
            dont_filter=True,
        )

    def after_login(self, response):
        self.logger.info("✓ Login successful!")
        date_range = f"{self.start_date} 00:00 - {self.end_date} 23:59"
        self.logger.info(f"📅 Date range: {date_range}")

        total_requests = len(self.SATKERS) * (len(self.PROGRAMAS) + 1)  # +1 for ALL PRO
        self.logger.info(
            f"🎵 Scraping {total_requests} requests ({len(self.SATKERS)} satkers × {len(self.PROGRAMAS) + 1} programas)..."
        )

        request_idx = 0
        for satker in self.SATKERS:
            # Initialize satker data
            self.satker_data[satker] = {
                "PRO 1": 0,
                "PRO 2": 0,
                "PRO 3": 0,
                "PRO 4": 0,
                "ALL PRO": 0,
                "TOTAL USER": 0,
            }

            # Request for each programa (PRO 1-4)
            for programa in self.PROGRAMAS:
                request_idx += 1
                params = {
                    "date_range": date_range,
                    "time_span": "auto",
                    "satker": satker,
                    "port": programa,  # Filter by programa/port
                }
                url = f"{self.base_url}/{self.hits_endpoint}?{urlencode(params)}"

                yield scrapy.Request(
                    url=url,
                    callback=self.parse_programa_data,
                    meta={
                        "satker": satker,
                        "programa": programa,
                        "request_idx": request_idx,
                        "total_requests": total_requests,
                    },
                    headers={"Accept": "application/json"},
                    dont_filter=True,
                )

            # Request for ALL PRO (no port filter)
            request_idx += 1
            params = {
                "date_range": date_range,
                "time_span": "auto",
                "satker": satker,
            }
            url = f"{self.base_url}/{self.hits_endpoint}?{urlencode(params)}"

            yield scrapy.Request(
                url=url,
                callback=self.parse_all_pro_data,
                meta={
                    "satker": satker,
                    "request_idx": request_idx,
                    "total_requests": total_requests,
                },
                headers={"Accept": "application/json"},
                dont_filter=True,
            )

    def parse_programa_data(self, response):
        """Parse API response for specific programa (PRO 1-4)."""
        satker = response.meta["satker"]
        programa = response.meta["programa"]
        idx = response.meta["request_idx"]
        total = response.meta["total_requests"]

        try:
            data = json.loads(response.text)
            hits = data.get("total", 0)

            # Map "Pro 1" to "PRO 1" etc.
            col_name = programa.upper()
            self.satker_data[satker][col_name] = hits

            if idx % 50 == 0:
                self.logger.info(f"[{idx}/{total}] Processing...")

        except json.JSONDecodeError:
            self.logger.warning(f"❌ JSON parse error for {satker} {programa}")

    def parse_all_pro_data(self, response):
        """Parse API response for all programas combined."""
        satker = response.meta["satker"]
        idx = response.meta["request_idx"]
        total = response.meta["total_requests"]

        try:
            data = json.loads(response.text)
            hits = data.get("total", 0)
            users = data.get("total_user", 0)

            self.satker_data[satker]["ALL PRO"] = hits
            self.satker_data[satker]["TOTAL USER"] = users

            if idx % 20 == 0:
                self.logger.info(
                    f"[{idx}/{total}] {satker}: ALL PRO={hits}, Users={users}"
                )

        except json.JSONDecodeError:
            self.logger.warning(f"❌ JSON parse error for {satker}")

    def closed(self, reason):
        """Export to Excel with exact template format."""
        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Total satkers scraped: {len(self.satker_data)}")

        if len(self.satker_data) == 0:
            return

        try:
            import pandas as pd

            # Build rows matching template format
            rows = []
            for satker in sorted(self.satker_data.keys()):
                data = self.satker_data[satker]
                rows.append(
                    {
                        "SATKER": satker,
                        "PRO 1": data.get("PRO 1", 0),
                        "PRO 2": data.get("PRO 2", 0),
                        "PRO 3": data.get("PRO 3", 0),
                        "PRO 4": data.get("PRO 4", 0),
                        "ALL PRO": data.get("ALL PRO", 0),
                        "TOTAL HITS *DAP VER.": data.get(
                            "ALL PRO", 0
                        ),  # Same as ALL PRO
                        "TOTAL USER": data.get("TOTAL USER", 0),
                    }
                )

            df = pd.DataFrame(rows)

            # Reorder columns to match template
            columns = [
                "SATKER",
                "PRO 1",
                "PRO 2",
                "PRO 3",
                "PRO 4",
                "ALL PRO",
                "TOTAL HITS *DAP VER.",
                "TOTAL USER",
            ]
            df = df[columns]

            output_file = f"streaming_scraped_{self.start_date.replace('/', '')}-{self.end_date.replace('/', '')}.xlsx"

            # Write with header matching template format
            with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
                df.to_excel(
                    writer, sheet_name="Sheet1", startrow=2, index=False, header=False
                )

                # Get worksheet and add headers
                worksheet = writer.sheets["Sheet1"]

                # Row 1: Main headers
                worksheet.cell(row=1, column=1, value="SATKER")
                worksheet.cell(row=1, column=2, value="HITS")
                worksheet.cell(row=1, column=7, value="TOTAL HITS *DAP VER.")
                worksheet.cell(row=1, column=8, value="TOTAL USER")

                # Row 2: Sub headers for HITS breakdown
                worksheet.cell(row=2, column=2, value="PRO 1")
                worksheet.cell(row=2, column=3, value="PRO 2")
                worksheet.cell(row=2, column=4, value="PRO 3")
                worksheet.cell(row=2, column=5, value="PRO 4")
                worksheet.cell(row=2, column=6, value="ALL PRO")

            self.logger.info(f"✅ Exported to: {output_file}")

            # Summary
            total_hits = df["ALL PRO"].sum()
            total_users = df["TOTAL USER"].sum()
            satkers_with_data = (df["ALL PRO"] > 0).sum()

            self.logger.info(f"\n📊 Summary:")
            self.logger.info(f"   Total Hits: {total_hits:,}")
            self.logger.info(f"   Total Users: {total_users:,}")
            self.logger.info(f"   Satkers with data: {satkers_with_data}")

        except ImportError:
            self.logger.warning("⚠️ pandas not installed")
        except Exception as e:
            self.logger.error(f"❌ Export error: {e}")
            import traceback

            traceback.print_exc()
