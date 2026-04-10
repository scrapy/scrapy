from facebook_scraper import get_profile, get_posts
import json
import sys

def scrape_fb_profile(username):
    print(f"Scraping profile for: {username}...")
    try:
        # Get profile info
        profile = get_profile(username)
        
        # Get posts (let's limit to 5 for speed)
        print("Scraping posts...")
        posts = []
        for post in get_posts(username, pages=3):
            posts.append(post)
            if len(posts) >= 10:
                break
                
        data = {
            "profile": profile,
            "posts": posts
        }
        
        with open("fb_comprehensive_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, default=str)
            
        print("Data saved to fb_comprehensive_data.json")
        return data
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    scrape_fb_profile("tarifii.mariam")
