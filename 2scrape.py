import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse
import time
import random

# Function to save content to a markdown file within a specific folder
def save_content(folder, filename, content):
    if not os.path.exists(folder):
        os.makedirs(folder)
    filepath = os.path.join(folder, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)

# Function to scrape a single page and return its content and links
def scrape_page(url, base_url, output_folder):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        # Extract the title for the file name
        title = soup.title.string if soup.title else 'untitled'
        title = title.replace('/', '_').replace('\\', '_').replace(' ', '_')  # Sanitize file name
        # Save the page content as markdown in the output folder
        page_content = f"# {title}\n\nURL: {url}\n\n{soup.get_text()}"
        save_content(output_folder, f"{title}.md", page_content)
        # Extract and return all links
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Normalize and filter URLs
            href = urljoin(base_url, href)
            parsed_href = urlparse(href)
            if parsed_href.scheme in ['http', 'https']:
                href = parsed_href._replace(fragment='').geturl()  # Remove fragment
                links.append(href)
        return links
    else:
        print(f"Failed to retrieve the webpage. Status code: {response.status_code}")
        return []

# Function to crawl links and scrape each page
def crawl_and_scrape(start_url, base_url, output_folder, max_depth=4):
    visited = set()
    to_visit = [(start_url, 0)]

    while to_visit:
        current_url, depth = to_visit.pop(0)
        if current_url not in visited and depth <= max_depth:
            visited.add(current_url)
            links = scrape_page(current_url, base_url, output_folder)
            for link in links:
                if base_url in link and link not in visited:
                    to_visit.append((link, depth + 1))
            # Introduce a random delay between 1 to 3 seconds to mimic human behavior
            time.sleep(random.uniform(1, 3))

# Main script
def main():
    url_file = input("Enter the path to the text file with URLs: ").strip()
    
    try:
        with open(url_file, 'r') as file:
            urls = [line.strip() for line in file.readlines()]
    except FileNotFoundError:
        print(f"File not found: {url_file}")
        return

    global_output_folder = "scraped_content"
    if not os.path.exists(global_output_folder):
        os.makedirs(global_output_folder)

    for url in urls:
        base_url = '/'.join(url.split('/')[:3])  # Extract base URL
        domain = urlparse(base_url).netloc.replace('.', '_')
        output_folder = os.path.join(global_output_folder, domain)
        crawl_and_scrape(url, base_url, output_folder)

if __name__ == "__main__":
    main()