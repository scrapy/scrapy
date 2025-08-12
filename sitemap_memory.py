from scrapy.utils.sitemap import Sitemap

with open("/mnt/d/Downloads/albertcz_sitemap_products-0.xml/albertcz_sitemap_products-0.xml", 'rb') as f:
    content = f.read()

import memray

with memray.Tracker(f"{__file__}_memray.bin"):
    Sitemap(content)