#!/usr/bin/env python3
import requests
import os
import sys
import re
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


def clean_text(text):
    """HTML 태그 제거 및 공백 정리"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_summary(desc, max_len=200):
    """RSS 설명에서 요약 추출 — 문장 단위로 자르고 말줄임표 추가"""
    text = clean_text(desc)
    if len(text) <= max_len:
        return text
    # 문장 끝(. ! ?) 기준으로 자르기
    truncated = text[:max_len]
    for end_char in ["다.", "다!", "다?", ". ", "! ", "? "]:
        idx = truncated.rfind(end_char)
        if idx > max_len // 2:
            return truncated[:idx + (2 if end_char.endswith(" ") else 1)]
    return truncated.rstrip() + "…"


def fetch_rss_news(rss_urls, keywords, max_items=7):
    news_items = []
    seen = set()
    for url in rss_urls:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.iter("item"):
                title = clean_text(item.findtext("title", ""))
                desc  = item.findtext("description", "") or ""
                link  = clean_text(item.findtext("link", "") or "")

                summary = make_summary(desc)

                if title in seen:
                    continue
                text = f"{title} {summary}".lower()
                if any(kw.lower() in text for kw in keywords):
                    seen.add(title)
                    news_items.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
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
        "https://api.notion.com/v1/search",
        headers=HEADERS,
        json={"query": month_str, "filter": {"property": "object", "value": "page"}},
    )
    for page in res.json().get("results", []):
        title = page.get("properties", {}).get("title", {}).get("title", [])
        parent = page.get("parent", {})
        if (
            title and title[0].get("plain_text") == month_str
            and parent.get("page_id", "").replace("-", "") == config["trends_page_id"].replace("-", "")
        ):
            print(f"  → 기존 '{month_str}' 페이지 재사용")
            return page["id"]

    print(f"  → '{month_str}' 페이지 새로 생성")
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


def build_news_blocks(topic, news_items):
    if not news_items:
        return [{
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": "오늘 수집된 뉴스가 없습니다."}}]},
        }]

    blocks = [{
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"📰 오늘의 {topic} 뉴스 ({len(news_items)}건)"},
                "annotations": {"bold": True, "color": "blue"},
            }]
        },
    }]

    for item in news_items:
        rich = []

        # 제목 (굵게)
        rich.append({
            "type": "text",
            "text": {"content": f"• {item['title']}\n"},
            "annotations": {"bold": True},
        })

        # 요약
        if item["summary"]:
            rich.append({
                "type": "text",
                "text": {"content": f"   {item['summary']}\n"},
            })

        # 원문 링크
        if item["link"]:
            rich.append({
                "type": "text",
                "text": {"content": "   "},
            })
            rich.append({
                "type": "text",
                "text": {"content": "🔗 원문 보기", "link": {"url": item["link"]}},
                "annotations": {"color": "blue"},
            })

        blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
        blocks.append({"type": "paragraph", "paragraph": {"rich_text": []}})  # 빈 줄

    return blocks


def add_toggle_to_notion(page_id, topic, news_items, toggle_prefix):
    children = build_news_blocks(topic, news_items)

    res = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=HEADERS,
        json={
            "children": [{
                "type": "toggle",
                "toggle": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": f"{toggle_prefix} {day_str} {topic} 동향"},
                        "annotations": {"bold": True},
                    }],
                    "children": children,
                },
            }]
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
