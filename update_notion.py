#!/usr/bin/env python3
import requests
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
month_str = f"{now.year}년 {now.month}월"
day_str = f"{now.month}월 {now.day}일"

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

CONFIGS = {
    "ev": {
        "topic": "전기차",
        "rss_urls": [
            "https://www.autoview.co.kr/RSS.asp",
            "https://rss.etnews.com/Section901.xml",
            "https://www.electimes.com/rss/allArticle.xml",
        ],
        "keywords": ["전기차", "EV", "전기", "배터리", "충전", "전동"],
        "trends_page_id": "32be0cfc-038d-8168-bb19-f26d76b21a1e",
        "march_page_id": "32be0cfc-038d-8137-9adc-e0b4f6d5618a",
        "toggle_prefix": "🔋",
    },
    "parts": {
        "topic": "차량부품",
        "rss_urls": [
            "https://www.autoview.co.kr/RSS.asp",
            "https://rss.etnews.com/Section901.xml",
            "https://www.autotimes.co.kr/rss/allArticle.xml",
        ],
        "keywords": ["부품", "반도체", "모터", "부품사", "공급망", "자동차 부품", "OEM"],
        "trends_page_id": "32be0cfc-038d-8153-a1d2-ffb7bce86340",
        "march_page_id": "32be0cfc-038d-81f1-b481-e95744eb1498",
        "toggle_prefix": "⚙️",
    },
}


def fetch_rss_news(rss_urls, keywords, max_items=7):
    news_items = []
    seen = set()
    for url in rss_urls:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                desc = (item.findtext("description", "") or "").strip()
                link = (item.findtext("link", "") or "").strip()
                pub_date = (item.findtext("pubDate", "") or "").strip()

                # HTML 태그 제거
                import re
                desc = re.sub(r"<[^>]+>", "", desc)[:120]

                if title in seen:
                    continue
                text = f"{title} {desc}".lower()
                if any(kw.lower() in text for kw in keywords):
                    seen.add(title)
                    news_items.append({
                        "title": title,
                        "desc": desc,
                        "link": link,
                        "date": pub_date,
                    })
                if len(news_items) >= max_items:
                    break
        except Exception as e:
            print(f"RSS 수집 실패 ({url}): {e}")
        if len(news_items) >= max_items:
            break
    return news_items


def get_or_create_month_page(config):
    if now.month == 3 and now.year == 2026:
        return config["march_page_id"]
    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS,
        json={
            "parent": {"type": "page_id", "page_id": config["trends_page_id"]},
            "icon": {"type": "emoji", "emoji": "📅"},
            "properties": {"title": [{"type": "text", "text": {"content": month_str}}]},
        },
    )
    return res.json()["id"]


def add_toggle_to_notion(page_id, topic, news_items, toggle_prefix):
    if not news_items:
        children = [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": "오늘 수집된 뉴스가 없습니다."}}]},
            }
        ]
    else:
        children = [
            {
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": f"📰 오늘의 {topic} 뉴스 ({len(news_items)}건)"}, "annotations": {"bold": True, "color": "blue"}}]
                },
            }
        ]
        for item in news_items:
            # 제목 + 링크
            rich = [{"type": "text", "text": {"content": f"• {item['title']}"}, "annotations": {"bold": True}}]
            if item["desc"]:
                rich.append({"type": "text", "text": {"content": f"\n   {item['desc']}"}})
            children.append({
                "type": "paragraph",
                "paragraph": {"rich_text": rich},
            })
            # 구분선 역할 빈 줄
            children.append({
                "type": "paragraph",
                "paragraph": {"rich_text": []},
            })

    res = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=HEADERS,
        json={
            "children": [
                {
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": f"{toggle_prefix} {day_str} {topic} 동향"}, "annotations": {"bold": True}}],
                        "children": children,
                    },
                }
            ]
        },
    )
    return res.json()


def main(mode):
    config = CONFIGS[mode]
    print(f"[{day_str}] {config['topic']} 동향 수집 시작...")

    month_page_id = get_or_create_month_page(config)

    print("RSS 뉴스 수집 중...")
    news_items = fetch_rss_news(config["rss_urls"], config["keywords"])
    print(f"  → {len(news_items)}개 뉴스 수집됨")

    print("Notion에 저장 중...")
    result = add_toggle_to_notion(
        month_page_id,
        config["topic"],
        news_items,
        config["toggle_prefix"],
    )

    if result.get("object") == "error":
        print(f"오류: {result.get('message')}")
        sys.exit(1)
    else:
        print(f"✅ {config['topic']} 동향 저장 완료!")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ev"
    main(mode)
