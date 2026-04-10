import scrapy
import json
import re

class FacebookSpider(scrapy.Spider):
    name = "fb_spider"
    
    def start_requests(self):
        urls = [
            "https://mbasic.facebook.com/tarifii.mariam",
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        for url in urls:
            yield scrapy.Request(url, headers=headers, callback=self.parse)

    def parse(self, response):
        page_type = "main"
        if "/about" in response.url:
            page_type = "about"
        elif "/photos" in response.url:
            page_type = "photos"
            
        data = {
            "url": response.url,
            "page_type": page_type,
            "title": response.css('title::text').get(),
            "meta_description": response.css('meta[name="description"]::attr(content)').get(),
            "og_title": response.css('meta[property="og:title"]::attr(content)').get(),
            "og_description": response.css('meta[property="og:description"]::attr(content)').get(),
            "og_image": response.css('meta[property="og:image"]::attr(content)').get(),
        }
        
        # Look for JSON data in script tags
        scripts = response.css('script::text').getall()
        json_blobs = []
        for script in scripts:
            # Facebook often puts data in JSON objects
            if '{"require":[[' in script or '{"define":[[' in script:
                try:
                    # Try to extract the JSON part (this is tricky with regex)
                    matches = re.findall(r'(\{.*\})', script)
                    for m in matches:
                        if len(m) > 100: # only interested in big chunks
                            json_blobs.append(m[:500] + "...") # just a preview
                except:
                    pass
        
        data['json_previews'] = json_blobs
        
        # Try to find visible stats
        stats_text = response.css('div ::text').getall()
        relevant_stats = [t.strip() for t in stats_text if any(x in t for x in ["likes", "followers", "متابع", "إعجاب"])]
        data['potential_stats'] = list(set(relevant_stats))[:10]
        
        yield data
