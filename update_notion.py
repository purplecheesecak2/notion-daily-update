#!/usr/bin/env python3
import requests
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from google import genai

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
month_str = f"{now.year}년 {now.month}월"
day_str = f"{now.month}월 {now.day}일"

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

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
        ],
        "keywords": ["전기차", "EV", "배터리", "전기", "충전"],
        "trends_page_id": "32be0cfc-038d-8168-bb19-f26d76b21a1e",
        "march_page_id": "32be0cfc-038d-8137-9adc-e0b4f6d5618a",
        "toggle_prefix": "🔋",
        "news_icon": "🔋",
    },
    "parts": {
        "topic": "차량부품",
        "rss_urls": [
            "https://www.autoview.co.kr/RSS.asp",
            "https://rss.etnews.com/Section901.xml",
        ],
        "keywords": ["부품", "반도체", "모터", "배터리", "자동차", "부품사"],
        "trends_page_id": "32be0cfc-038d-8153-a1d2-ffb7bce86340",
        "march_page_id": "32be0cfc-038d-81f1-b481-e95744eb1498",
        "toggle_prefix": "⚙️",
        "news_icon": "🔩",
    },
}


def fetch_rss_news(rss_urls, keywords, max_items=10):
    """RSS에서 키워드 관련 뉴스 가져오기"""
    news_items = []
    for url in rss_urls:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                desc = item.findtext("description", "").strip()
                text = f"{title} {desc}".lower()
                if any(kw.lower() in text for kw in keywords):
                    news_items.append({"title": title, "desc": desc[:100]})
                if len(news_items) >= max_items:
                    break
        except Exception as e:
            print(f"RSS 수집 실패 ({url}): {e}")
    return news_items


def summarize_with_gemini(topic, news_items):
    """Gemini로 뉴스 요약 및 동향 정리"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    if news_items:
        news_text = "\n".join([f"- {n['title']}: {n['desc']}" for n in news_items[:8]])
        prompt = f"""다음은 오늘({day_str}) {topic} 관련 뉴스 헤드라인이야:

{news_text}

위 내용을 바탕으로 다음 JSON 형식으로만 반환해줘 (마크다운, 코드블록 없이):
{{
  "news": [
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}}
  ],
  "trends": ["주요 트렌드 1", "주요 트렌드 2", "주요 트렌드 3"],
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""
    else:
        prompt = f"""오늘({day_str}) {topic} 산업의 최신 기술 동향과 주요 이슈를 다음 JSON 형식으로만 반환해줘 (마크다운, 코드블록 없이):
{{
  "news": [
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}},
    {{"title": "뉴스 제목", "summary": "한 줄 요약"}}
  ],
  "trends": ["주요 트렌드 1", "주요 트렌드 2", "주요 트렌드 3"],
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
    )

    text = response.text.strip()
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"JSON 파싱 실패: {e}\n응답: {text[:200]}")
        return {
            "news": [{"title": f"{topic} 동향", "summary": text[:100]}],
            "trends": ["정보 없음"],
            "keywords": [topic],
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

    print("RSS 뉴스 수집 중...")
    news_items = fetch_rss_news(config["rss_urls"], config["keywords"])
    print(f"  → {len(news_items)}개 뉴스 수집됨")

    print("Gemini로 요약 중...")
    data = summarize_with_gemini(config["topic"], news_items)

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
