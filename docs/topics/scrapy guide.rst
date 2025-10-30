🕸️ Scrapy Tutorial: A Complete Beginner's Guide to Web Scraping with Python [Blog]

Web scraping is one of the most powerful techniques for gathering data from websites 
and Scrapy is the ultimate Python framework for doing it efficiently and at scale.
In this guide, we'll walk you step-by-step through building your first Scrapy project, 
creating spiders, extracting data, and exporting it — all in a simple, beginner-friendly way.


🧰 What is Scrapy?
Scrapy is an open-source and fast web crawling and data extraction framework written in Python.
It helps you automatically navigate web pages, extract specific data (like quotes, prices, images, etc.), and store it in a structured format such as JSON or CSV.


💡 Why Use Scrapy?

Fast and asynchronous (built on Twisted networking engine)
Handles thousands of pages efficiently
Built-in support for exporting data
Easy link-following and pagination
Designed for large-scale crawlers

⚙️ Installation

Before getting started, make sure you have Python 3.8+ installed.
Then open your terminal and install Scrapy with:
'pip install scrapy'

You can check if Scrapy was installed correctly by running:
'scrapy version'



🚀 Step 1: Create a New Scrapy Project
To start your first Scrapy project, open your terminal and move to the folder where you want to create it. Then run:

"scrapy startproject tutorial"

This command initializes a new Scrapy project named tutorial and automatically
 sets up the necessary files and folders.


Your project will include important components such as:
-scrapy.cfg - The main configuration file used for deploying and managing your Scrapy project.
-items.py - Defines the data structures (models) that describe the fields you want to scrape.
-middlewares.py - Contains custom middleware to process requests and responses.
-pipelines.py - Handles data after it's scraped (e.g., cleaning, storing in databases, exporting).
-settings.py - Stores all project-wide settings such as user agents, delays, and concurrency limits.
-spiders/ - A folder that contains your spiders, which are the actual crawlers that visit websites and extract data.

🕷️ Each spider acts as a mini bot that knows where to crawl, what to extract, and how to follow links. You can create multiple spiders inside one Scrapy project — each one dedicated to a specific website or section.


🕷️ Step 2: Create Your First Spider
Let's scrape quotes from "quotes.toscrape.com"
 — a website made for practicing web scraping.
Inside the spiders folder, create a new file called quotes_spider.py and paste this code:

"from pathlib import Path"
"import scrapy"


class QuotesSpider(scrapy.Spider):
    name = "quotes"

    start_urls = [
        "https://quotes.toscrape.com/page/1/",
        "https://quotes.toscrape.com/page/2/",
    ]

    def parse(self, response):
        page = response.url.split("/")[-2]
        filename = f"quotes-{page}.html"
        Path(filename).write_bytes(response.body)
        self.log(f"Saved file {filename}")

🔍 What's Happening Here:
name: The spider's unique name.
start_urls: Initial URLs where scraping begins.
parse(): The main function that handles each webpage's response.


▶️ Step 3: Run Your Spider
In your terminal, navigate to the top-level tutorial directory and run:

"scrapy crawl quotes"


You should see logs showing your spider crawling pages.
After it finishes, you'll have two new files:
quotes-1.html and quotes-2.html saved in your folder.


🧠 Step 4: Extracting Data
Now let's extract meaningful content — the actual quotes, authors, and tags.
We'll modify our spider like this:

import scrapy

class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/page/1/"]

    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
            }

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)


🧩 Explanation:
We loop through each <div class="quote">.
Extract text, author, and tags using CSS selectors.
Find the “Next” link and follow it recursively to scrape all pages.


💾 Step 5: Saving the Data:
You can save scraped data to a file using Scrapy's Feed Export feature.
For example, to save data in JSON format, run:
scrapy crawl quotes -O quotes.json
Or, to append data in JSON Lines format:

scrapy crawl quotes -o quotes.jsonl

Output Example:
{
  "text": "“It is our choices, Harry, that show what we truly are...”",
  "author": "J.K. Rowling",
  "tags": ["choices", "life"]
}


🔗 Step 6: Following Links Automatically
Scrapy makes following pagination or internal links simple.
Here's how you can follow “Next” links:

next_page = response.css("li.next a::attr(href)").get()
if next_page:
    yield response.follow(next_page, callback=self.parse)


You can also follow all links on a page using:

"yield from response.follow_all(css="ul.pager a", callback=self.parse)""


🧩 Step 7: Using Spider Arguments
Scrapy allows you to customize spider behavior using command-line arguments.
For example, run this:

scrapy crawl quotes -a tag=humor -O humor_quotes.json

Then modify your spider to handle the argument:

import scrapy

class QuotesSpider(scrapy.Spider):
    name = "quotes"

    async def start(self):
        tag = getattr(self, "tag", None)
        url = "https://quotes.toscrape.com/"
        if tag:
            url += f"tag/{tag}"
        yield scrapy.Request(url, callback=self.parse)


Now your spider scrapes only “humor” quotes dynamically.


🧭 Step 8: Next Steps
You've just built a fully functional Scrapy crawler! 🎉
Here's what you can explore next:
Item Pipelines: Clean and process scraped data.
Middlewares: Modify requests/responses dynamically.
CrawlSpider: Advanced spiders for complex sites.


💬 Final Thoughts
Scrapy is like a Swiss army knife for web scraping : simple enough for beginners but powerful
enough for enterprise-level crawlers.
Start small, play with different selectors, and soon you'll be scraping and analyzing data like a pro. 🚀

