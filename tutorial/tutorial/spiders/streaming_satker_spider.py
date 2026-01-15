"""
DAP RRI Streaming Satker Spider - Scrapes streaming analytics with PRO 1-4 breakdown via API

Uses:
- api/get_cards?ids=6 for TOTAL HITS *DAP VER. (id=total_hits_card_idle)
- api/get_cards?ids=7 for TOTAL USER (id=total_users_card_idle)
- api/streaming/get_hits_total with port filter for PRO 1-4 breakdown

Usage:
    scrapy crawl streaming_scraper -a email=EMAIL -a password=PASSWORD
"""

import json
import re
from datetime import datetime
from urllib.parse import urlencode

import scrapy


class StreamingSatkerSpider(scrapy.Spider):
    name = "streaming_scraper"
    allowed_domains = ["dap.rri.go.id"]

    base_url = "https://dap.rri.go.id"
    login_url = "https://dap.rri.go.id/"

    # API endpoints
    hits_endpoint = "api/streaming/get_hits_total"
    cards_endpoint = "api/get_cards"

    # Port names for PRO 1-4 breakdown
    PORTS = {
        "Pro 1": "PRO 1",
        "Pro 2": "PRO 2",
        "Pro 3": "PRO 3",
        "Pro 4": "PRO 4",
    }

    # All satkers (from dropdown)
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
        "IKN",
        "Jakarta",
        "Jambi",
        "Jayapura",
        "Jazz Channel",
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
        "Memori",
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
        "Pro3",
        "Purwokerto",
        "Ranai",
        "Rote",
        "Rimba Raya",
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
        "Terminabuan",
        "Ternate",
        "Toli Toli",
        "Tual",
        "Tuban",
        "Voice of Indonesia",
        "Wamena",
        "Way kanan",
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

        # Storage: {satker: {PRO 1: X, PRO 2: X, ..., TOTAL HITS: X, TOTAL USER: X}}
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

        self.logger.info("✓ Found CSRF token")
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

        # For each satker, we need:
        # - 1 request to get_cards?ids=6,7 (total_hits and total_users)
        # - 4 requests to get_hits_total with port filter (PRO 1-4)
        total_requests = len(self.SATKERS) * 5
        self.logger.info(
            f"🎵 Making {total_requests} API requests for {len(self.SATKERS)} satkers..."
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
                "TOTAL HITS": 0,
                "TOTAL USER": 0,
            }

            # Request 1: Get TOTAL HITS and TOTAL USER from get_cards API
            request_idx += 1
            params = {
                "ids": "6,7",  # 6=total_hits_card_idle, 7=total_users_card_idle
                "date_range": date_range,
                "satker": satker,
            }
            url = f"{self.base_url}/{self.cards_endpoint}?{urlencode(params)}"

            yield scrapy.Request(
                url=url,
                callback=self.parse_cards_data,
                meta={
                    "satker": satker,
                    "request_idx": request_idx,
                    "total_requests": total_requests,
                },
                headers={"Accept": "application/json"},
                dont_filter=True,
            )

            # Requests 2-5: Get PRO 1-4 with port filter from get_hits_total
            for port_api, port_col in self.PORTS.items():
                request_idx += 1
                params = {
                    "date_range": date_range,
                    "time_span": "auto",
                    "satker": satker,
                    "port": port_api,
                }
                url = f"{self.base_url}/{self.hits_endpoint}?{urlencode(params)}"

                yield scrapy.Request(
                    url=url,
                    callback=self.parse_port_data,
                    meta={
                        "satker": satker,
                        "port_col": port_col,
                        "request_idx": request_idx,
                        "total_requests": total_requests,
                    },
                    headers={"Accept": "application/json"},
                    dont_filter=True,
                )

    def parse_cards_data(self, response):
        """Parse get_cards API response for TOTAL HITS and TOTAL USER."""
        satker = response.meta["satker"]
        idx = response.meta["request_idx"]
        total = response.meta["total_requests"]

        try:
            data = json.loads(response.text)

            # The response contains content with HTML that has the data
            # We need to extract the values from data-tag_type="total" elements
            if data.get("status") and data.get("result"):
                content = data["result"].get("content", {})

                # Card 6 = total_hits_card_idle
                # Card 7 = total_users_card_idle
                for card_id, card_content in content.items():
                    if card_id == "6":
                        # Extract total hits value from HTML
                        match = re.search(
                            r'data-tag_type="total"[^>]*>([^<]+)<', card_content
                        )
                        if match:
                            value_str = match.group(1).strip().replace(",", "")
                            if value_str.endswith("K"):
                                self.satker_data[satker]["TOTAL HITS"] = int(
                                    float(value_str[:-1]) * 1000
                                )
                            elif value_str.endswith("M"):
                                self.satker_data[satker]["TOTAL HITS"] = int(
                                    float(value_str[:-1]) * 1000000
                                )
                            else:
                                self.satker_data[satker]["TOTAL HITS"] = (
                                    int(float(value_str)) if value_str else 0
                                )

                    elif card_id == "7":
                        # Extract total users value from HTML
                        match = re.search(
                            r'data-tag_type="total"[^>]*>([^<]+)<', card_content
                        )
                        if match:
                            value_str = match.group(1).strip().replace(",", "")
                            if value_str.endswith("K"):
                                self.satker_data[satker]["TOTAL USER"] = int(
                                    float(value_str[:-1]) * 1000
                                )
                            elif value_str.endswith("M"):
                                self.satker_data[satker]["TOTAL USER"] = int(
                                    float(value_str[:-1]) * 1000000
                                )
                            else:
                                self.satker_data[satker]["TOTAL USER"] = (
                                    int(float(value_str)) if value_str else 0
                                )

                if idx % 20 == 0:
                    self.logger.info(
                        f"[{idx}/{total}] {satker}: "
                        f"HITS={self.satker_data[satker]['TOTAL HITS']}, "
                        f"USER={self.satker_data[satker]['TOTAL USER']}"
                    )

        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"❌ Error parsing cards for {satker}: {e}")

    def parse_port_data(self, response):
        """Parse API response for specific PRO (port) hits."""
        satker = response.meta["satker"]
        port_col = response.meta["port_col"]
        idx = response.meta["request_idx"]
        total = response.meta["total_requests"]

        try:
            data = json.loads(response.text)
            hits = data.get("total", 0) or 0

            self.satker_data[satker][port_col] = hits

            if idx % 100 == 0:
                self.logger.info(f"[{idx}/{total}] Processing ports...")

        except json.JSONDecodeError:
            self.logger.warning(f"❌ JSON parse error for {satker} {port_col}")

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
                # Calculate ALL PRO as sum of PRO 1-4
                all_pro = (
                    data.get("PRO 1", 0)
                    + data.get("PRO 2", 0)
                    + data.get("PRO 3", 0)
                    + data.get("PRO 4", 0)
                )

                rows.append(
                    {
                        "SATKER": satker,
                        "PRO 1": data.get("PRO 1", 0),
                        "PRO 2": data.get("PRO 2", 0),
                        "PRO 3": data.get("PRO 3", 0),
                        "PRO 4": data.get("PRO 4", 0),
                        "ALL PRO": all_pro,
                        "TOTAL HITS *DAP VER.": data.get("TOTAL HITS", 0),
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

            output_file = f"streaming_{self.start_date.replace('/', '')}-{self.end_date.replace('/', '')}.xlsx"

            # Write with header matching template format
            with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
                df.to_excel(
                    writer, sheet_name="Sheet1", startrow=2, index=False, header=False
                )

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
            total_all_pro = df["ALL PRO"].sum()
            total_hits = df["TOTAL HITS *DAP VER."].sum()
            total_users = df["TOTAL USER"].sum()
            satkers_with_data = (df["ALL PRO"] > 0).sum()

            self.logger.info(f"\n📊 Summary:")
            self.logger.info(f"   Total satkers: {len(df)}")
            self.logger.info(f"   Satkers with data: {satkers_with_data}")
            self.logger.info(f"   Total ALL PRO: {total_all_pro:,}")
            self.logger.info(f"   Total HITS (DAP VER.): {total_hits:,}")
            self.logger.info(f"   Total USERS: {total_users:,}")

        except ImportError:
            self.logger.warning("⚠️ pandas not installed")
        except Exception as e:
            self.logger.error(f"❌ Export error: {e}")
            import traceback

            traceback.print_exc()
