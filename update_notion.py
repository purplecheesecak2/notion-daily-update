#!/usr/bin/env python3
import anthropic
import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
month_str = f"{now.year}년 {now.month}월"
day_str = f"{now.month}월 {now.day}일"

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

CONFIGS = {
    "ev": {
        "topic": "전기차",
        "trends_page_id": "32be0cfc-038d-8168-bb19-f26d76b21a1e",
        "march_page_id": "32be0cfc-038d-8137-9adc-e0b4f6d5618a",
        "toggle_prefix": "🔋",
        "news_icon": "🔋",
    },
    "parts": {
        "topic": "차량부품",
        "trends_page_id": "32be0cfc-038d-8153-a1d2-ffb7bce86340",
        "march_page_id": "32be0cfc-038d-81f1-b481-e95744eb1498",
        "toggle_prefix": "⚙️",
        "news_icon": "🔩",
    },
}


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


def search_news_with_claude(topic):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[
            {
                "role": "user",
                "content": f"""오늘({day_str}) {topic} 관련 최신 뉴스와 기술 동향을 웹에서 검색해서 다음 JSON 형식으로만 반환해줘 (마크다운 없이):
{{
  "news": [
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}}
  ],
  "trends": [
    "기술 트렌드 1",
    "기술 트렌드 2",
    "기술 트렌드 3"
  ],
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}""",
            }
        ],
    )
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            try:
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception:
                pass
    return {
        "news": [{"title": f"{topic} 뉴스 수집 실패", "summary": "다음에 다시 시도해주세요"}],
        "trends": ["정보 없음"],
        "keywords": [topic],
    }


def add_toggle_to_notion(page_id, topic, data, toggle_prefix, news_icon):
    children = [
        {
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": f"{news_icon} 주요 뉴스"}, "annotations": {"bold": True, "color": "blue"}}]
            },
        }
    ]
    for item in data.get("news", []):
        children.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"{item['title']} — {item['summary']}"}}]},
        })

    children.append({
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "💡 기술 동향"}, "annotations": {"bold": True, "color": "green"}}]
        },
    })
    for trend in data.get("trends", []):
        children.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": trend}}]},
        })

    children.append({
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "📌 핵심 키워드"}, "annotations": {"bold": True, "color": "orange"}}]
        },
    })
    for kw in data.get("keywords", []):
        children.append({
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": kw}}]},
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
    print("Claude API로 최신 뉴스 검색 중...")
    data = search_news_with_claude(config["topic"])

    print("Notion에 저장 중...")
    result = add_toggle_to_notion(
        month_page_id,
        config["topic"],
        data,
        config["toggle_prefix"],
        config["news_icon"],
    )

    if result.get("object") == "error":
        print(f"오류: {result.get('message')}")
        sys.exit(1)
    else:
        print(f"✅ {config['topic']} 동향 저장 완료!")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ev"
    main(mode)
