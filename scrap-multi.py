import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse

# Function to save content to a file
def save_content(folder, filename, content):
    if not os.path.exists(folder):
        os.makedirs(folder)
    filepath = os.path.join(folder, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)

# Function to save consolidated content to a markdown file
def save_consolidated_content(filename, content):
    with open(filename, 'a', encoding='utf-8') as file:
        file.write(content + "\n\n")

# Function to scrape a single page and return its content and links
def scrape_page(url, base_url, output_folder, consolidated_file):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        # Extract the title for the folder name
        title = soup.title.string if soup.title else 'untitled'
        title = title.replace('/', '_').replace('\\', '_')  # Sanitize folder name
        # Save the page content as text in a folder named after the title
        page_content = f"Title: {title}\nURL: {url}\n\n{soup.get_text()}"
        # Save individual page content
        save_content(output_folder, f"{title}.txt", page_content)
        # Save consolidated content
        save_consolidated_content(consolidated_file, page_content)
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
def crawl_and_scrape(start_url, base_url, output_folder, consolidated_file, max_depth=2):
    visited = set()
    to_visit = [(start_url, 0)]

    while to_visit:
        current_url, depth = to_visit.pop(0)
        if current_url not in visited and depth <= max_depth:
            visited.add(current_url)
            links = scrape_page(current_url, base_url, output_folder, consolidated_file)
            for link in links:
                if base_url in link and link not in visited:
                    to_visit.append((link, depth + 1))

# Main script
def main():
    input_choice = input("Enter '1' to input a URL or '2' to provide a text file with URLs: ").strip()
    
    if input_choice == '1':
        start_url = input("Enter the URL to start scraping: ").strip()
        urls = [start_url]
    elif input_choice == '2':
        url_file = input("Enter the path to the text file with URLs: ").strip()
        try:
            with open(url_file, 'r') as file:
                urls = [line.strip() for line in file.readlines()]
        except FileNotFoundError:
            print(f"File not found: {url_file}")
            return
    else:
        print("Invalid choice. Please enter '1' or '2'.")
        return

    output_folder = "scraped_content"
    consolidated_file = "consolidated_content.md"
    # Clear the consolidated file before starting
    open(consolidated_file, 'w').close()

    for url in urls:
        base_url = '/'.join(url.split('/')[:3])  # Extract base URL
        crawl_and_scrape(url, base_url, output_folder, consolidated_file)

if __name__ == "__main__":
    main()