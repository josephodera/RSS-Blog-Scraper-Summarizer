import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import json
import re
import time
import sqlite3

# Configuration
RSS_URL = 'https://research.google/blog/rss/'
OUTPUT_FILE = 'blog_posts.json'
SUMMARY_FILE = 'todays_summaries.json'
DB_FILE = 'blog_posts.db'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            title TEXT,
            url TEXT UNIQUE,
            author TEXT,
            date TEXT,
            content TEXT
        )
    ''')
    conn.commit()
    conn.close()

def store_post_in_db(title, url, author, date, content):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO posts (title, url, author, date, content)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, url, author, date, content))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

def get_todays_posts():
    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT title, url, author, date, content FROM posts WHERE date = ?', (today,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "title": row[0],
            "url": row[1],
            "author": row[2],
            "date": row[3],
            "content": row[4]
        }
        for row in rows
    ]

def summarize_post(content, max_length=200):
    """Generate a summary of the content (simple truncation-based summary)."""
    if not content or content == "Content unavailable." or content == "Scraping error.":
        return "No summary available."
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', content.strip())
    summary = []
    char_count = 0
    
    # Add sentences until we reach max_length
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if char_count + len(sentence) <= max_length:
            summary.append(sentence)
            char_count += len(sentence) + 1  # +1 for space
        else:
            break
    
    summary_text = ' '.join(summary).strip()
    if not summary_text:
        return "No summary available."
    
    # Ensure the summary ends with a period
    if len(summary_text) > max_length - 10 and not summary_text.endswith('.'):
        summary_text = summary_text[:max_length-3] + '...'
    
    return summary_text

def save_todays_summaries(posts):
    """Save summaries of today's posts to a JSON file."""
    summaries = []
    for post in posts:
        summary = summarize_post(post['content'])
        summaries.append({
            "title": post['title'],
            "url": post['url'],
            "author": post['author'],
            "date": post['date'],
            "summary": summary
        })
    
    with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, indent=2, ensure_ascii=False)
    
    return summaries

def fetch_daily_posts():
    feed = feedparser.parse(RSS_URL)
    now = datetime.now(timezone.utc)
    last_month = now - timedelta(days=30)  # Fetch posts from the last 30 days
    daily_posts = []
    for entry in feed.entries:
        pub_date = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %z')
        if pub_date >= last_month:
            daily_posts.append({
                'title': entry.title,
                'url': entry.link,
                'pub_date': pub_date,
                'rss_author': entry.get('author', 'Unknown'),
                'rss_description': entry.summary if hasattr(entry, 'summary') else entry.get('description', '').strip()
            })
    return daily_posts

def scrape_post_details(url, rss_description):
    try:
        time.sleep(1)
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch {url}: Status {response.status_code}")
            return "Unknown", rss_description or "Content unavailable."
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title_selectors = ['h1.post-title', 'h3.post-title', 'h1.entry-title', 'title']
        page_title = None
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem:
                page_title = elem.get_text(strip=True)
                break
        if page_title and page_title != rss_description[:len(page_title)]:
            print(f"Scraping: {page_title[:50]}...")
        else:
            print(f"Scraping {url.split('/')[-1]}...")
        
        author_selectors = [
            'span.post-author.vcard',
            'div.post-author',
            'a[rel="author"]',
            '.post-author',
            'span.fn',
            '.author-name',
            'meta[name="author"]'
        ]
        author = None
        for selector in author_selectors:
            elem = soup.select_one(selector)
            if elem:
                author = elem.get_text(strip=True)
                break
        if not author:
            author_meta = soup.find('meta', {'name': 'author'})
            author = author_meta['content'] if author_meta else None
        
        content = None
        content_selectors = [
            'div.post-body.entry-content',
            'div.post-body',
            '.entry-content',
            '#post-body-1234567890',
            'main',
            'article'
        ]
        article = None
        for selector in content_selectors:
            article = soup.select_one(selector)
            if article and article.get_text(strip=True):
                break
        
        if article:
            for unwanted in article.find_all(['script', 'style', 'nav', 'footer', 'aside']):
                unwanted.decompose()
            text_elements = article.find_all(text=True, recursive=True)
            content_parts = []
            for text in text_elements:
                text = text.strip()
                if text and len(text) > 15 and not re.match(r'^\d+$', text) and 'http' not in text:
                    content_parts.append(text)
            content = re.sub(r'\s+', ' ', ' '.join(content_parts)).strip()
        
        if not content or len(content) < 200:
            full_text = soup.get_text(separator=' ', strip=True)
            noise_patterns = [
                r'https?://\S+',
                r'\s*Share:\s*',
                r'\s*Posted by\s*',
                r'\s*at\s*\d{1,2}:\d{2} [AP]M\s*',
                r'\s*Labels:\s*',
                r'\s*0 comments?\s*',
                r'\s*Subscribe to:\s*'
            ]
            for pattern in noise_patterns:
                full_text = re.sub(pattern, '', full_text, flags=re.IGNORECASE)
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            sentences = re.split(r'[.!?]+', full_text)
            content = ' '.join(sentences[2:10]) if len(sentences) > 10 else full_text
        
        if not content or len(content) < 100:
            content = rss_description or "Content unavailable."
        
        return author or "Unknown", content
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return "Unknown", rss_description or "Scraping error."

if __name__ == "__main__":
    init_database()
    
    posts = fetch_daily_posts()
    blog_data = []
    for post in posts:
        author, content = scrape_post_details(post['url'], post['rss_description'])
        date_str = post['pub_date'].date().isoformat()
        
        store_post_in_db(post['title'], post['url'], author, date_str, content)
        
        blog_entry = {
            "title": post['title'],
            "url": post['url'],
            "author": author,
            "date": date_str,
            "content": content
        }
        blog_data.append(blog_entry)
    
    if not blog_data:
        print("No new posts in the last 30 days.")
    else:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(blog_data, f, indent=2, ensure_ascii=False)
        
        if blog_data:
            preview = blog_data[0].copy()
            preview['content'] = preview['content'][:500] + '...' if len(preview['content']) > 500 else preview['content']
            print(json.dumps(preview, indent=2, ensure_ascii=False))
            print(f"\n... (full content for all {len(blog_data)} posts saved to {OUTPUT_FILE})")
        
        todays_posts = get_todays_posts()
        if todays_posts:
            print("\nToday's blog posts:")
            for post in todays_posts:
                print(json.dumps(post, indent=2, ensure_ascii=False))
            
            summaries = save_todays_summaries(todays_posts)
            print(f"\nSummaries of today's posts saved to {SUMMARY_FILE}:")
            for summary in summaries:
                print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print("\nNo new posts today.")