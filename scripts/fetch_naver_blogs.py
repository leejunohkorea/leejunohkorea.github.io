#!/usr/bin/env python3
"""Fetch three posts per supplied Naver Blog address, including thumbnails when available."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

# Three distinct Naver Blog feeds supplied by the user.
BLOGS = [
    {"id": "hr_jasonlee", "name": "출강 후기 블로그", "url": "https://blog.naver.com/hr_jasonlee"},
    {"id": "ljohrd", "name": "조직변화관리연구소 블로그", "url": "https://blog.naver.com/ljohrd"},
    {"id": "creatents", "name": "HR뮤지엄(인문학) 블로그", "url": "https://blog.naver.com/creatents"},
]

USER_AGENT = "Mozilla/5.0 (compatible; GoodInsightBlogFeed/1.0)"


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
            image = attrs.get("src") or attrs.get("data-src") or attrs.get("data-lazy-src")
            if image:
                self.images.append(image)


class MetaImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        attrs = {key.lower(): value for key, value in attrs}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        value = attrs.get("content") or ""
        if key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src") and value:
            self.images.append(value)


def normalize_image(value):
    value = html.unescape((value or "").strip())
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("http://"):
        value = "https://" + value[len("http://"):]
    return value if value.startswith("https://") else ""


def parse_content(value):
    parser = ContentParser()
    parser.feed(value or "")
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    image = normalize_image(parser.images[0]) if parser.images else ""
    return text[:360], image


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(item, key):
    for child in item:
        if local_name(child.tag) == key.lower():
            return "".join(child.itertext()).strip()
    return ""


def rss_image(item):
    # RSS feeds may expose a thumbnail or enclosure separately from description HTML.
    for node in item.iter():
        if local_name(node.tag) in ("thumbnail", "content", "enclosure"):
            candidate = node.attrib.get("url") or node.attrib.get("href")
            if candidate:
                image = normalize_image(candidate)
                if image:
                    return image
    return ""


def page_thumbnail(post_url):
    if not post_url.startswith("https://"):
        return ""
    request = urllib.request.Request(post_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            page = response.read(1_500_000).decode("utf-8", errors="replace")
        parser = MetaImageParser()
        parser.feed(page)
        return normalize_image(parser.images[0]) if parser.images else ""
    except Exception:
        # Naver may block article HTML requests; keep the title/link card regardless.
        return ""


def fetch(blog):
    rss_url = f"https://rss.blog.naver.com/{blog['id']}.xml"
    request = urllib.request.Request(rss_url, headers={"User-Agent": USER_AGENT})
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
        image = image or rss_image(item) or page_thumbnail(link)
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
thumbnail_count = sum(bool(post["image"]) for post in posts)
print(f"Wrote {len(posts)} cards from {len(BLOGS)} supplied blog addresses; found {thumbnail_count} thumbnails")
