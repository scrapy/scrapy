import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse

# Function to save content to a markdown file within a specific folder
def save_content(folder, filename, content):
    if not os.path.exists(folder):
        os.makedirs(folder)
    filepath = os.path.join(folder, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)

# Function to scrape a single page and return its content and links
def scrape_page(url, base_url, output_folder):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        # Extract the title for the folder name
        title = soup.title.string if soup.title else 'untitled'
        title = title.replace('/', '_').replace('\\', '_').replace(' ', '_')  # Sanitize folder name
        # Save the page content as markdown in a folder named after the title
        page_content = f"# {title}\n\nURL: {url}\n\n{soup.get_text()}"
        save_content(os.path.join(output_folder, title), f"{title}.md", page_content)
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

# Main script
def main():
    start_url = input("Enter the URL to start scraping: ").strip()
    base_url = '/'.join(start_url.split('/')[:3])  # Extract base URL
    domain = urlparse(base_url).netloc.replace('.', '_')
    output_folder = f"scraped_content_{domain}"
    crawl_and_scrape(start_url, base_url, output_folder)

if __name__ == "__main__":
    main()