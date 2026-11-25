"""Yangilik ta'sirini tahlil qilish va xabar shakllantirish."""
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


_UZ_TERMS = {
    "gold": "oltin", "dollar": "dollar", "federal reserve": "Federal Rezerv",
    "interest rate": "foiz stavkasi", "rate hike": "stavka oshirish",
    "rate cut": "stavka kamaytirish", "inflation": "inflyatsiya",
    "recession": "tanazzul", "war": "urush", "conflict": "mojarо",
    "oil": "neft", "market": "bozor", "stock": "aksiya",
    "economy": "iqtisodiyot", "bank": "bank", "trade": "savdo",
    "gdp": "YaIM", "unemployment": "ishsizlik", "bond": "obligatsiya",
    "rally": "oshish", "selloff": "tushish", "crash": "inqiroz",
    "sanctions": "sanksiyalar", "tariff": "tarif", "china": "Xitoy",
    "russia": "Rossiya", "ukraine": "Ukraina", "europe": "Yevropa",
    "bullish": "o'sish", "bearish": "tushish", "safe haven": "xavfsiz aktiv",
    "risk off": "xavfdan qochish", "risk on": "xavf olish",
}

def _translate_to_uzbek(text: str) -> str:
    """Moliyaviy atamalarni o'zbek tiliga almashtirish."""
    if not text:
        return text
    result = text
    text_lower = text.lower()
    for en, uz in _UZ_TERMS.items():
        if en in text_lower:
            import re
            result = re.sub(re.escape(en), uz, result, flags=re.IGNORECASE)
    return result


def _impact_summary(impact: dict) -> str:
    lines = []
    xau_bull = impact.get("xauusd_bullish", 0)
    xau_bear = impact.get("xauusd_bearish", 0)
    if xau_bull > xau_bear and xau_bull:
        lines.append("🥇 XAUUSD: Yuqoriga bosim (BULLISH)")
    elif xau_bear > xau_bull and xau_bear:
        lines.append("🥇 XAUUSD: Pastga bosim (BEARISH)")

    dxy_bull = impact.get("dxy_bullish", 0)
    dxy_bear = impact.get("dxy_bearish", 0)
    if dxy_bull > dxy_bear and dxy_bull:
        lines.append("💵 DXY: Kuchayish (BULLISH)")
    elif dxy_bear > dxy_bull and dxy_bear:
        lines.append("💵 DXY: Zaiflashish (BEARISH)")

    nas_bull = impact.get("nas100_bullish", 0)
    nas_bear = impact.get("nas100_bearish", 0)
    if nas_bull > nas_bear and nas_bull:
        lines.append("📊 NAS100: Osish kutilmoqda (BULLISH)")
    elif nas_bear > nas_bull and nas_bear:
        lines.append("📊 NAS100: Tushish xavfi (BEARISH)")

    if dxy_bull > dxy_bear and dxy_bull:
        lines.append("🇪🇺 EURUSD: Tushish mumkin (DXY kuchayishi)")
    elif dxy_bear > dxy_bull and dxy_bear:
        lines.append("🇪🇺 EURUSD: Kostarilishi mumkin (DXY zaiflanishi)")

    return "\n".join(lines) if lines else "⚪ Tasir aniqlanmadi"


def _xauusd_analysis(impact: dict) -> tuple:
    """Oltin (XAUUSD) ga ta'sir tahlili va xulosa.

    Oltin: dollar kuchaysa/stavka oshsa tushadi; dollar zaiflashsa,
    risk-off (urush/inqiroz) bo'lsa ko'tariladi.
    """
    xau_bull = impact.get("xauusd_bullish", 0)
    xau_bear = impact.get("xauusd_bearish", 0)
    dxy_bull = impact.get("dxy_bullish", 0)   # kuchli dollar -> oltin tushadi
    dxy_bear = impact.get("dxy_bearish", 0)   # zaif dollar  -> oltin ko'tariladi

    bull = xau_bull + dxy_bear
    bear = xau_bear + dxy_bull

    if bull > bear:
        reasons = []
        if xau_bull:
            reasons.append("xavfsiz aktivga talab / geosiyosiy keskinlik")
        if dxy_bear:
            reasons.append("dollarning zaiflashishi")
        detail = "🥇 Oltinga ta'siri: IJOBIY — ko'tarilishi mumkin."
        if reasons:
            detail += "\nSabab: " + ", ".join(reasons[:2]) + "."
        xulosa = "📝 XULOSA: Oltin (XAUUSD) ko'tarilishi ehtimoli yuqori. 🟢"
    elif bear > bull:
        reasons = []
        if xau_bear:
            reasons.append("risk-on kayfiyat / tinchlik signali")
        if dxy_bull:
            reasons.append("dollarning kuchayishi / hawkish Fed")
        detail = "🥇 Oltinga ta'siri: SALBIY — tushishi mumkin."
        if reasons:
            detail += "\nSabab: " + ", ".join(reasons[:2]) + "."
        xulosa = "📝 XULOSA: Oltin (XAUUSD) tushishi ehtimoli yuqori. 🔴"
    else:
        detail = "🥇 Oltinga ta'siri: Neytral — kuchli signal yo'q."
        xulosa = "📝 XULOSA: Oltin (XAUUSD) uchun sezilarli harakat kutilmaydi. ⚪"

    return detail, xulosa


def format_news_alert(news_item: dict, title_uz: str = None, summary_uz: str = None) -> str:
    priority = news_item.get("priority", "MEDIUM")
    header = "🚨 TEZKOR XABAR" if priority == "HIGH" else "📰 BOZOR YANGILIGI"
    source = news_item.get("source", "Noma'lum")
    title = news_item.get("title", "")
    summary = news_item.get("summary", "")
    link = news_item.get("link", "")
    impact = news_item.get("impact", {})
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    impact_text = _impact_summary(impact)
    xau_detail, xulosa = _xauusd_analysis(impact)

    if title_uz is None:
        title_uz = _translate_to_uzbek(title)
    if summary_uz is None:
        summary_uz = _translate_to_uzbek(summary) if summary and summary != title else ""

    msg = f"{header}\n⏰ {now} | 📡 {source}\n\n📌 {title_uz}"
    if summary_uz:
        msg += f"\n\n{summary_uz[:300]}"
    msg += f"\n\n---\n📊 BOZORGA TA'SIRI:\n{impact_text}\n\n{xau_detail}\n\n{xulosa}\n---"
    if link:
        msg += f"\n🔗 {link}"
    return msg


def format_price_update(prices: dict) -> str:
    from price_fetcher import format_price_line, SYMBOLS
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"📈 BOZOR NARXLARI | {now}\n"]
    for sym in SYMBOLS:
        lines.append(format_price_line(sym, prices.get(sym)))
    return "\n".join(lines)


def format_daily_summary(prices: dict, top_news: list, titles_uz: list = None) -> str:
    from price_fetcher import format_price_line, SYMBOLS
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    lines = [
        f"🌅 KUNLIK BOZOR SHARHI",
        f"📅 {now}",
        "",
        "💹 JORIY NARXLAR:",
        "",
    ]
    for sym in SYMBOLS:
        lines.append(format_price_line(sym, prices.get(sym)))
    lines += ["", "---", "🔥 BUGUNGI ASOSIY YANGILIKLAR:", ""]
    if top_news:
        for i, news in enumerate(top_news[:5], 1):
            icon = "🚨" if news.get("priority") == "HIGH" else "📌"
            if titles_uz and i - 1 < len(titles_uz):
                title_uz = titles_uz[i - 1]
            else:
                title_uz = _translate_to_uzbek(news.get('title', '')[:150])
            lines.append(f"{icon} {i}. {title_uz}")
            lines.append(f"   📡 {news.get('source', '')}")
            lines.append("")
    else:
        lines.append("Muhim yangilik topilmadi")
    lines += ["---", "Faqat malumot maqsadida. Moliyaviy maslahat emas.", "", "🤖 Avtomatik tahlil boti"]
    return "\n".join(lines)


def format_market_context() -> str:
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    sessions = []
    if 22 <= hour or hour < 7:
        sessions.append("🇯🇵 Tokio (22:00-07:00 UTC)")
    if 7 <= hour < 16:
        sessions.append("🇬🇧 London (07:00-16:00 UTC)")
    if 13 <= hour < 22:
        sessions.append("🇺🇸 Nyu-York (13:00-22:00 UTC)")
    if 7 <= hour < 22:
        sessions.append("⚡ Faol vaqt!")
    if not sessions:
        sessions.append("😴 Past faollik davri")
    return "🕐 Ochiq sessiyalar:\n" + "\n".join(f"  {s}" for s in sessions)
