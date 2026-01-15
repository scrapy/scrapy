"""
DAP RRI Streaming Scraper - Browser-based with Playwright

This script uses Playwright to:
1. Login to DAP RRI
2. Navigate to streaming detail page
3. For each satker: select it, set date range, click apply, extract PRO 1-4 data
4. Export to Excel matching the template format

Usage:
    python streaming_browser_scraper.py

    # With custom date range:
    python streaming_browser_scraper.py --start-date 01/01/2026 --end-date 31/01/2026
"""

import asyncio
import argparse
from datetime import datetime
from playwright.async_api import async_playwright
import pandas as pd


# Configuration
EMAIL = "admin@rri.go.id"
PASSWORD = "!@#$ADMIN4daprri!@#$"
BASE_URL = "https://dap.rri.go.id"
STREAMING_URL = f"{BASE_URL}/streaming/detail?page=2"


async def scrape_streaming_data(start_date="01/01/2026", end_date="31/01/2026"):
    """Main scraping function using Playwright."""

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("🔐 Logging in...")
        await page.goto(BASE_URL)
        await page.wait_for_load_state("networkidle")

        # Fill login form
        await page.fill('input[name="email"]', EMAIL)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click("#kt_sign_in_submit")

        # Wait for login to complete
        await page.wait_for_timeout(3000)
        print("✓ Login successful!")

        # Navigate to streaming detail page
        print("📊 Navigating to streaming detail page...")
        await page.goto(STREAMING_URL)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        # Get all satker options from dropdown
        satker_options = await page.evaluate("""
            () => {
                const select = document.querySelector('#kt_dash_satker');
                if (select) {
                    return Array.from(select.options).map(opt => ({
                        value: opt.value,
                        text: opt.text.trim()
                    })).filter(opt => opt.value && opt.value !== '');
                }
                return [];
            }
        """)

        print(f"📋 Found {len(satker_options)} satkers to scrape")

        # Set date range
        date_range = f"{start_date} 00:00 - {end_date} 23:59"
        await page.evaluate(f'''
            () => {{
                const dateInput = document.querySelector('#kt_dash_daterangepicker');
                if (dateInput) {{
                    dateInput.value = "{date_range}";
                    dateInput.dispatchEvent(new Event('change'));
                }}
            }}
        ''')

        print(f"📅 Date range set: {date_range}")

        # Scrape each satker
        for idx, satker in enumerate(satker_options):
            satker_name = satker["text"]
            satker_value = satker["value"]

            print(f"[{idx + 1}/{len(satker_options)}] Scraping {satker_name}...")

            # Select satker
            await page.select_option("#kt_dash_satker", value=satker_value)

            # Click apply filter
            await page.click("#kt_apply_filter")

            # Wait for data to load
            await page.wait_for_timeout(2000)

            # Extract PRO 1-4 values and totals
            data = await page.evaluate("""
                () => {
                    const result = {
                        pro1: 0, pro2: 0, pro3: 0, pro4: 0,
                        total_hits: 0, total_users: 0
                    };
                    
                    // Extract PRO 1-4 values
                    ['pro1', 'pro2', 'pro3', 'pro4'].forEach(pro => {
                        const card = document.querySelector(`#${pro}_total_card_chart_line`);
                        if (card) {
                            const hitsEl = card.querySelector('.fs-4.text-gray-900.fw-bold');
                            if (hitsEl) {
                                let value = hitsEl.innerText.trim();
                                // Parse value (could be like "55.5K", "1.2M", etc.)
                                value = value.replace(/,/g, '');
                                if (value.endsWith('K')) {
                                    result[pro] = parseFloat(value) * 1000;
                                } else if (value.endsWith('M')) {
                                    result[pro] = parseFloat(value) * 1000000;
                                } else {
                                    result[pro] = parseFloat(value) || 0;
                                }
                            }
                        }
                    });
                    
                    // Get total hits
                    const totalHitsCard = document.querySelector('#total_hits_card_idle');
                    if (totalHitsCard) {
                        const hitsEl = totalHitsCard.querySelector('.fs-4.text-gray-900.fw-bold, .fw-bold');
                        if (hitsEl) {
                            let value = hitsEl.innerText.trim().replace(/,/g, '');
                            if (value.endsWith('K')) {
                                result.total_hits = parseFloat(value) * 1000;
                            } else if (value.endsWith('M')) {
                                result.total_hits = parseFloat(value) * 1000000;
                            } else {
                                result.total_hits = parseFloat(value) || 0;
                            }
                        }
                    }
                    
                    // Get total users
                    const totalUsersCard = document.querySelector('#total_users_card_idle');
                    if (totalUsersCard) {
                        const usersEl = totalUsersCard.querySelector('.fs-4.text-gray-900.fw-bold, .fw-bold');
                        if (usersEl) {
                            let value = usersEl.innerText.trim().replace(/,/g, '');
                            if (value.endsWith('K')) {
                                result.total_users = parseFloat(value) * 1000;
                            } else if (value.endsWith('M')) {
                                result.total_users = parseFloat(value) * 1000000;
                            } else {
                                result.total_users = parseFloat(value) || 0;
                            }
                        }
                    }
                    
                    return result;
                }
            """)

            # Calculate ALL PRO (sum of pro1-4)
            all_pro = data["pro1"] + data["pro2"] + data["pro3"] + data["pro4"]

            results.append(
                {
                    "SATKER": satker_name,
                    "PRO 1": int(data["pro1"]),
                    "PRO 2": int(data["pro2"]),
                    "PRO 3": int(data["pro3"]),
                    "PRO 4": int(data["pro4"]),
                    "ALL PRO": int(all_pro),
                    "TOTAL HITS *DAP VER.": int(data["total_hits"]),
                    "TOTAL USER": int(data["total_users"]),
                }
            )

            if (idx + 1) % 10 == 0:
                print(f"   Progress: {idx + 1}/{len(satker_options)} satkers done")

        await browser.close()

    return results


def export_to_excel(data, start_date, end_date):
    """Export data to Excel matching template format."""
    df = pd.DataFrame(data)

    # Sort by SATKER
    df = df.sort_values("SATKER")

    output_file = f"streaming_scraped_{start_date.replace('/', '')}-{end_date.replace('/', '')}.xlsx"

    # Write with headers matching template format
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", startrow=2, index=False, header=False)

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

    print(f"\n✅ Exported to: {output_file}")
    print(f"📊 Summary:")
    print(f"   Total satkers: {len(df)}")
    print(f"   Satkers with data: {(df['ALL PRO'] > 0).sum()}")
    print(f"   Total ALL PRO hits: {df['ALL PRO'].sum():,}")
    print(f"   Total users: {df['TOTAL USER'].sum():,}")

    return output_file


async def main():
    parser = argparse.ArgumentParser(description="DAP RRI Streaming Scraper")
    parser.add_argument(
        "--start-date", default="01/01/2026", help="Start date (DD/MM/YYYY)"
    )
    parser.add_argument(
        "--end-date", default="31/01/2026", help="End date (DD/MM/YYYY)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🎵 DAP RRI Streaming Scraper (Browser-based)")
    print("=" * 60)
    print(f"📅 Date range: {args.start_date} - {args.end_date}")
    print()

    data = await scrape_streaming_data(args.start_date, args.end_date)

    if data:
        export_to_excel(data, args.start_date, args.end_date)
    else:
        print("❌ No data scraped")


if __name__ == "__main__":
    asyncio.run(main())
