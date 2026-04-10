import json
import re

def parse_comprehensive_fb(file_path):
    try:
        with open(file_path, "r", encoding="utf-16") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    
    data = {}
    
    # Extract meta tags (og:title, og:description, etc.)
    data['name'] = re.search(r'property="og:title" content="([^"]+)"', content)
    data['name'] = data['name'].group(1) if data['name'] else "Unknown"
    
    data['description'] = re.search(r'property="og:description" content="([^"]+)"', content)
    data['description'] = data['description'].group(1) if data['description'] else "No description"
    
    data['url'] = re.search(r'property="og:url" content="([^"]+)"', content)
    data['url'] = data['url'].group(1) if data['url'] else "No URL"
    
    data['image'] = re.search(r'property="og:image" content="([^"]+)"', content)
    data['image'] = data['image'].group(1) if data['image'] else "No Image"
    
    # Try to find likes and talking about this
    stats = re.search(r'([\d,]+) likes · ([\d,]+) talking about this', content)
    if stats:
        data['likes'] = stats.group(1)
        data['talking_about'] = stats.group(2)
    else:
        # Try finding separately
        likes = re.search(r'([\d,]+) likes', content)
        data['likes'] = likes.group(1) if likes else "N/A"
        
        followers = re.search(r'([\d,]+) followers', content)
        data['followers'] = followers.group(1) if followers else "N/A"

    # Extract some info from the bio/intro
    bio_match = re.search(r'News reporter', content)
    if bio_match:
        data['category'] = "News reporter"

    # Save to JSON
    with open("fb_comprehensive_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    return data

if __name__ == "__main__":
    parse_comprehensive_fb("fb_response.html")
