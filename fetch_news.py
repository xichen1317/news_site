import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import mktime

import feedparser
import requests

RSS_FEEDS = [
    {
        "website": "Google News",
        "rss_url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    },
    {
        "website": "Yahoo News",
        "rss_url": "https://news.yahoo.com/rss/topstories",
    },
    {
        "website": "华尔街见闻",
        "rss_url": "https://feed.wallstreetcn.com/wallstreetcn/news/global",
    },
]

ITEMS_PER_SITE = 10
OUTPUT_FILE = "news.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PersonalNewsReader/1.0)"
}


def get_published(entry):
    """尽可能将 RSS 发布时间转为 ISO 8601；无法解析时返回 None。"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(
                mktime(parsed), tz=timezone.utc
            ).isoformat()
        except (ValueError, OverflowError, OSError):
            pass

    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def get_timestamp(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return mktime(parsed)
        except (ValueError, OverflowError, OSError):
            pass
    return 0


def clean_text(value):
    from bs4 import BeautifulSoup
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def fetch_source(source):
    print(f"Fetching {source['website']} ...")
    response = requests.get(
        source["rss_url"], headers=HEADERS, timeout=25
    )
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    if not feed.entries:
        raise RuntimeError(
            f"No RSS entries found. HTTP {response.status_code}; "
            f"parse error: {getattr(feed, 'bozo_exception', None)}"
        )

    entries = sorted(feed.entries, key=get_timestamp, reverse=True)
    articles = []
    seen = set()

    for entry in entries:
        title = clean_text(entry.get("title", "")).strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        key = (title.casefold(), link)
        if key in seen:
            continue
        seen.add(key)

        summary = clean_text(
            entry.get("summary", "")
            or entry.get("description", "")
        )

        articles.append({
            "title": title,
            "link": link,
            "published_at": get_published(entry),
            "summary": summary,
            "author": entry.get("author"),
        })

        if len(articles) >= ITEMS_PER_SITE:
            break

    return {
        "website": source["website"],
        "rss_url": source["rss_url"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": articles,
    }


def main():
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "sources": [],
        "errors": [],
    }

    for source in RSS_FEEDS:
        try:
            output["sources"].append(fetch_source(source))
        except Exception as exc:
            print(f"Failed: {source['website']}: {exc}")
            output["errors"].append({
                "website": source["website"],
                "rss_url": source["rss_url"],
                "error": str(exc),
            })
            output["sources"].append({
                "website": source["website"],
                "rss_url": source["rss_url"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": 0,
                "articles": [],
            })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved: {OUTPUT_FILE}")
    for source in output["sources"]:
        print(f"- {source['website']}: {source['count']} articles")
    if output["errors"]:
        print("Some sources failed. See the 'errors' field in news.json.")


if __name__ == "__main__":
    main()
