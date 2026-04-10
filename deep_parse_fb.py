import json
import re
import html

def extract_all_json_from_html(file_path):
    try:
        with open(file_path, "r", encoding="utf-16") as f:
            content = f.read()
    except:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

    print(f"Analyzing {file_path}...")
    
    # 1. Look for script tags with JSON
    all_data = {}
    
    # Extract meta tags first
    meta_tags = re.findall(r'<meta property="([^"]+)" content="([^"]+)"', content)
    for prop, val in meta_tags:
        all_data[f"meta_{prop}"] = html.unescape(val)
        
    # 2. Find all potential JSON blobs in scripts
    # Facebook uses a specific format for its data: {"require":[[...]]} or {"define":[[...]]}
    json_patterns = [
        r'\{"require":\[\[.*?\]\]\}',
        r'\{"define":\[\[.*?\]\]\}',
        r'\{"__bbox":.*?\}'
    ]
    
    found_count = 0
    for pattern in json_patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                # Clean up if needed
                data = json.loads(match)
                found_count += 1
                # We want to find keys like 'name', 'profile', 'follower_count', etc.
                # Since the JSON is nested, we'll do a recursive search for interesting keys
                extract_interesting_keys(data, all_data)
            except:
                continue
                
    print(f"Found and analyzed {found_count} JSON blobs.")
    
    # Save the consolidated data
    with open("fb_comprehensive_data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
    
    return all_data

def extract_interesting_keys(obj, results):
    interesting_keys = [
        "name", "text", "description", "label", "caption", 
        "follower_count", "subscriber_count", "friend_count",
        "profile_plus_id", "id", "url", "uri", "image", "src",
        "category_name", "biography", "short_name",
        "city", "hometown", "gender", "birthday", "education", "work",
        "school", "employer", "position", "start_date", "end_date",
        "body", "message", "creation_time", "feedback",
        "headline", "current_city", "relationship_status"
    ]
    
    if isinstance(obj, dict):
        # Specific check for posts in Facebook JSON structure
        if 'message' in obj and 'text' in obj['message']:
            if 'posts' not in results: results['posts'] = []
            if obj['message']['text'] not in results['posts']:
                results['posts'].append(obj['message']['text'])
        
        # Look for education/work specifically in 'timeline_context_item_wrapper'
        if 'text' in obj and isinstance(obj['text'], str):
            if any(x in obj['text'] for x in ["Studied", "Works at", "Lives in", "From"]):
                if 'about_details' not in results: results['about_details'] = []
                if obj['text'] not in results['about_details']:
                    results['about_details'].append(obj['text'])

        for k, v in obj.items():
            if k in interesting_keys and isinstance(v, (str, int, float)):
                # If key already exists, don't overwrite unless it's a better value
                if k not in results or (isinstance(v, str) and len(str(v)) > len(str(results.get(k, "")))):
                    results[k] = v
            extract_interesting_keys(v, results)
    elif isinstance(obj, list):
        for item in obj:
            extract_interesting_keys(item, results)

if __name__ == "__main__":
    extract_all_json_from_html("fb_response.html")
