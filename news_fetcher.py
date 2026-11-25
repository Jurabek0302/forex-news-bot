"""Yangiliklar olish va filtrlash moduli."""
import feedparser
import requests
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# RSS manbalar - bepul, real vaqt
RSS_FEEDS = {
    "Reuters FX":     "https://feeds.reuters.com/reuters/businessNews",
    "ForexFactory":   "https://www.forexfactory.com/ff_calendar_thisweek.xml",
    "Investing.com":  "https://www.investing.com/rss/news.rss",
    "FXStreet":       "https://www.fxstreet.com/rss/news",
    "DailyFX":        "https://www.dailyfx.com/feeds/all",
    "MarketWatch FX": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "BBC Business":   "https://feeds.bbci.co.uk/news/business/rss.xml",
    "Bloomberg":      "https://feeds.bloomberg.com/markets/news.rss",
}

# Muhim kalit so'zlar - bu so'zlar bo'lsa darhol xabar berish
HIGH_PRIORITY_KEYWORDS = [
    "fed", "federal reserve", "fomc", "interest rate", "rate hike", "rate cut",
    "powell", "inflation", "cpi", "pce", "nonfarm payroll", "nfp",
    "unemployment", "gdp", "recession",
    "war", "conflict", "attack", "military", "geopolit",
    "gold", "xauusd", "dollar", "dxy", "dollar index",
    "nasdaq", "s&p", "risk off", "safe haven",
    "china", "russia", "ukraine", "middle east", "iran", "israel",
    "opec", "oil", "crude",
    "ecb", "boe", "boj", "central bank",
    "tariff", "trade war", "sanctions",
    "emergency", "crisis", "crash", "collapse",
]

# Bozorga ta'sir kalit so'zlari (toifalar bo'yicha)
IMPACT_KEYWORDS = {
    "xauusd_bullish": [
        "war", "conflict", "attack", "military strike", "geopolit",
        "risk off", "safe haven", "recession", "rate cut", "dovish",
        "dollar weakness", "inflation surge", "crisis", "emergency",
        "gold rally", "flight to safety",
    ],
    "xauusd_bearish": [
        "rate hike", "hawkish", "dollar strength", "risk on",
        "gold falls", "gold drop", "gold selloff",
        "ceasefire", "peace deal", "de-escalation",
    ],
    "dxy_bullish": [
        "rate hike", "hawkish fed", "strong dollar", "dollar surges",
        "risk off", "safe haven demand", "us economy strong",
        "nfp beat", "inflation hot", "powell hawkish",
    ],
    "dxy_bearish": [
        "rate cut", "dovish fed", "dollar weakens", "dollar falls",
        "us recession", "weak jobs", "inflation cools", "powell dovish",
    ],
    "nas100_bullish": [
        "rate cut", "dovish", "tech rally", "risk on", "ai boom",
        "earnings beat", "gdp strong", "soft landing",
    ],
    "nas100_bearish": [
        "rate hike", "hawkish", "recession", "risk off", "tech selloff",
        "earnings miss", "gdp weak", "layoffs",
    ],
}


def _score_impact(text: str) -> dict:
    """Matn bo'yicha bozor ta'sirini baholash."""
    text_lower = text.lower()
    scores = {k: 0 for k in IMPACT_KEYWORDS}
    for category, keywords in IMPACT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[category] += 1
    return scores


def _priority_level(text: str) -> str:
    """Yangilik muhimligini aniqlash: HIGH / MEDIUM / LOW."""
    text_lower = text.lower()
    matches = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text_lower)
    if matches >= 3:
        return "HIGH"
    if matches >= 1:
        return "MEDIUM"
    return "LOW"


def _fetch_rss(url: str, name: str) -> list[dict]:
    """RSS feedddan yangiliklar olish."""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        feed = feedparser.parse(resp.text)
        items = []
        for entry in feed.entries[:5]:  # Har manbadan oxirgi 5 ta
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")
            items.append({
                "source": name,
                "title": title,
                "summary": summary[:300],
                "link": link,
                "published": published,
                "text": f"{title} {summary}",
            })
        return items
    except Exception as e:
        logger.debug(f"RSS xatosi {name}: {e}")
        return []


def fetch_all_news() -> list[dict]:
    """Barcha manbalardan yangilik olish va filtrlash."""
    all_items = []
    for name, url in RSS_FEEDS.items():
        all_items.extend(_fetch_rss(url, name))

    # Muhimlik darajasini va ta'sirini qo'shish
    result = []
    for item in all_items:
        priority = _priority_level(item["text"])
        item["priority"] = priority
        item["impact"] = _score_impact(item["text"])
        result.append(item)

    # HIGH birinchi, keyin MEDIUM
    result.sort(key=lambda x: 0 if x["priority"] == "HIGH" else 1)
    return result


def fetch_newsapi(api_key: str) -> list[dict]:
    """NewsAPI orqali yangiliklar olish (agar kalit bo'lsa)."""
    if not api_key or api_key == "your_newsapi_key_here":
        return []
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "gold OR forex OR federal reserve OR dollar OR XAUUSD OR DXY",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        result = []
        for a in articles:
            text = f"{a.get('title','')} {a.get('description','')}"
            priority = _priority_level(text)
            result.append({
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "title": a.get("title", ""),
                "summary": (a.get("description") or "")[:300],
                "link": a.get("url", ""),
                "published": a.get("publishedAt", ""),
                "text": text,
                "priority": priority,
                "impact": _score_impact(text),
            })
        return result
    except Exception as e:
        logger.warning(f"NewsAPI xatosi: {e}")
        return []
