#!/usr/bin/env python3
"""Fetch three posts from each supplied Naver Blog RSS URL."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

# Keep all three submitted entries, including the repeated creatents URL.
BLOGS = [
    {"id": "hr_jasonlee", "name": "이준오 블로그", "url": "https://blog.naver.com/hr_jasonlee"},
    {"id": "creatents", "name": "creatents 블로그", "url": "https://blog.naver.com/creatents"},
    {"id": "creatents", "name": "creatents 블로그", "url": "https://blog.naver.com/creatents"},
]

class ContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.images = []
    def handle_data(self, data):
        self.text_parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            attrs = dict(attrs)
            image = attrs.get("src") or attrs.get("data-src")
            if image:
                self.images.append(image)

def parse_content(value):
    parser = ContentParser()
    parser.feed(value or "")
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    image = parser.images[0] if parser.images else ""
    if image.startswith("//"):
        image = "https:" + image
    if image and not image.startswith("https://"):
        image = ""
    return text[:360], image

def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()

def child_text(item, key):
    for child in item:
        if local_name(child.tag) == key.lower():
            return "".join(child.itertext()).strip()
    return ""

def fetch(blog):
    rss_url = f"https://rss.blog.naver.com/{blog['id']}.xml"
    request = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0 (compatible; GoodInsightBlogFeed/1.0)"})
    with urllib.request.urlopen(request, timeout=25) as response:
        root = ET.fromstring(response.read())
    posts = []
    for item in root.iter():
        if local_name(item.tag) != "item":
            continue
        title = child_text(item, "title")
        link = child_text(item, "link") or blog["url"]
        raw_date = child_text(item, "pubdate")
        try:
            published = parsedate_to_datetime(raw_date)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            date_label = published.astimezone().strftime("%Y. %m. %d.")
        except (TypeError, ValueError, OverflowError):
            published = datetime.min.replace(tzinfo=timezone.utc)
            date_label = ""
        description = child_text(item, "description") or child_text(item, "encoded")
        excerpt, image = parse_content(description)
        posts.append({"title": title, "url": link, "source": blog["name"], "dateLabel": date_label,
                      "published": published.isoformat(), "excerpt": excerpt, "image": image})
        if len(posts) == 3:
            break
    return posts

posts = []
for blog in BLOGS:
    posts.extend(fetch(blog))
result = {"updatedAt": datetime.now(timezone.utc).isoformat(), "blogs": BLOGS, "posts": posts}
Path("blog-posts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(posts)} cards from {len(BLOGS)} supplied blog addresses")
