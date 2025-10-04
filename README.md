A Python automation tool that fetches blog posts from RSS feeds (default: Google Research Blog), scrapes full article content, stores them in a local SQLite database, and generates JSON reports + daily summaries.

** Features**

   Fetch latest posts from RSS feed (last 30 days by default)

   Scrape full blog content with BeautifulSoup
   Store posts in SQLite database (avoids duplicates)

   Export all posts to blog_posts.json

   Generate today’s summaries in todays_summaries.json

   Easily extendable to other RSS feeds

** Requirements
**
  Install dependencies with:

  pip install -r requirements.txt


requirements.txt

  feedparser
  requests
  beautifulsoup4
  lxml
  sqlite3-binary ; only needed if not included in Python

**Usage**

  Clone the repo and run:

  git clone https://github.com/josephodera/rss-blog-scraper.git
  cd rss-blog-scraper
  python scraper.py


Output files:

  blog_posts.json → All scraped posts

todays_summaries.json → Summaries of today’s posts

blog_posts.db → Persistent SQLite database
