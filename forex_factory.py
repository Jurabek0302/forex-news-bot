"""ForexFactory iqtisodiy kalendar moduli — foiz stavka va muhim hodisalar tahlili."""
import requests
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# Foiz stavka / markaziy bank kalit so'zlari
RATE_KEYWORDS = [
    "rate statement", "cash rate", "official bank rate", "federal funds",
    "main refinancing", "interest rate", "monetary policy", "rate decision",
    "fomc", "ecb press", "boe", "boj", "rba", "snb", "rate", "monetary",
]

IMPACT_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "Holiday": "⚪"}

FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CAD": "🇨🇦",
    "AUD": "🇦🇺", "NZD": "🇳🇿", "CHF": "🇨🇭", "CNY": "🇨🇳",
}


def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def fetch_ff_calendar() -> list[dict]:
    """ForexFactory haftalik kalendarini olish."""
    try:
        r = requests.get(FF_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        events = []
        for e in root.findall("event"):
            events.append({
                "title": _text(e, "title"),
                "country": _text(e, "country"),
                "date": _text(e, "date"),
                "time": _text(e, "time"),
                "impact": _text(e, "impact"),
                "forecast": _text(e, "forecast"),
                "previous": _text(e, "previous"),
                "url": _text(e, "url"),
            })
        return events
    except Exception as ex:
        logger.warning(f"ForexFactory kalendar xatosi: {ex}")
        return []


def _is_rate_event(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in RATE_KEYWORDS)


def _is_clock(t: str) -> bool:
    t = t.strip().lower()
    return bool(t) and t[0].isdigit() and ("am" in t or "pm" in t)


def _event_dt(ev: dict):
    """Hodisa sanasini UTC datetime ga aylantirish (saralash uchun)."""
    try:
        d = datetime.strptime(ev["date"], "%m-%d-%Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    if _is_clock(ev["time"]):
        try:
            tt = datetime.strptime(ev["time"].strip().lower(), "%I:%M%p")
            return d.replace(hour=tt.hour, minute=tt.minute)
        except Exception:
            pass
    return d.replace(hour=23, minute=59)  # All Day / Tentative -> kun oxiri


def _parse_num(val: str):
    """'0.8%' -> 0.8, '1.2K' -> 1200, '' -> None"""
    if not val:
        return None
    s = val.strip().replace("%", "").replace(",", "").replace("<", "").replace(">", "")
    mult = 1
    if s and s[-1] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[s[-1].lower()]
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return None


def _analysis(ev: dict) -> str:
    """Hodisa uchun bozor ta'siri tahlili (o'zbekcha)."""
    title = ev["title"].lower()
    cur = ev["country"]
    f = _parse_num(ev["forecast"])
    p = _parse_num(ev["previous"])
    is_rate = _is_rate_event(ev["title"])
    is_infl = any(k in title for k in ["cpi", "pce", "ppi", "inflation", "price index"])

    if f is None or p is None:
        if is_rate:
            return "🏦 Markaziy bank hodisasi — foiz stavka siyosati bo'yicha signal berishi mumkin."
        return ""

    fc, pv = ev["forecast"], ev["previous"]
    if is_rate:
        if f > p:
            return f"📈 Stavka oshishi kutilmoqda ({pv} → {fc}). {cur} kuchayadi, oltinga bosim."
        if f < p:
            return f"📉 Stavka pasayishi kutilmoqda ({pv} → {fc}). {cur} zaiflashadi, oltin ko'tariladi."
        return f"➖ Stavka o'zgarmas kutilmoqda ({fc}). Bayonot ohangiga e'tibor bering."

    if is_infl:
        if f > p:
            return f"📈 Inflyatsiya oshishi kutilmoqda ({pv} → {fc}). Hawkish → {cur} kuchayishi, oltinga bosim."
        if f < p:
            return f"📉 Inflyatsiya pasayishi kutilmoqda ({pv} → {fc}). Dovish → {cur} zaiflashishi, oltin uchun ijobiy."
        return f"➖ Inflyatsiya o'zgarmas kutilmoqda ({fc})."

    if f > p:
        return f"📈 Bashorat o'tgandan yuqori ({pv} → {fc}). {cur} uchun ijobiy bo'lishi mumkin."
    if f < p:
        return f"📉 Bashorat o'tgandan past ({pv} → {fc}). {cur} uchun salbiy bo'lishi mumkin."
    return f"➖ Bashorat o'tgan bilan bir xil ({fc})."


def _format_event(ev: dict) -> str:
    dt = _event_dt(ev)
    if dt is None:
        when = f"{ev['date']} {ev['time']}"
    elif _is_clock(ev["time"]):
        when = dt.strftime("%d.%m %H:%M") + " UTC"
    else:
        when = dt.strftime("%d.%m") + f" {ev['time'] or '—'}"

    flag = FLAGS.get(ev["country"], "")
    imp = IMPACT_EMOJI.get(ev["impact"], "")
    s = f"{imp} {when} | {flag} {ev['country']}\n   {ev['title']}"
    if ev["forecast"] or ev["previous"]:
        s += f"\n   Bashorat: {ev['forecast'] or '—'} | Oldingi: {ev['previous'] or '—'}"
    a = _analysis(ev)
    if a:
        s += f"\n   {a}"
    return s


def format_ff_calendar(events: list[dict]) -> str:
    """Kalendarni o'zbekcha xabar ko'rinishida formatlash."""
    if not events:
        return ("📅 FOREX FACTORY\n\n"
                "⚠️ Hozircha kalendar ma'lumotini olishning imkoni bo'lmadi. "
                "Birozdan keyin qayta urinib ko'ring.")

    now = datetime.now(timezone.utc)
    upcoming = [e for e in events if (_event_dt(e) or now) >= now - timedelta(hours=2)]
    upcoming.sort(key=lambda e: _event_dt(e) or now)

    important = [e for e in upcoming if e["impact"] in ("High", "Medium")]
    rate = [e for e in upcoming if _is_rate_event(e["title"])]

    lines = ["📅 FOREX FACTORY — IQTISODIY KALENDAR", ""]

    if important:
        lines.append("🔴 MUHIM HODISALAR (bozorni kuchli harakatlantiradi):")
        lines.append("")
        for e in important[:8]:
            lines.append(_format_event(e))
            lines.append("")
    else:
        lines.append("ℹ️ Yaqin kunlarda yuqori ta'sirli hodisa yo'q.")
        lines.append("")

    if rate:
        lines.append("🏦 FOIZ STAVKA / MARKAZIY BANK:")
        lines.append("")
        seen = {id(e) for e in important[:8]}
        shown = 0
        for e in rate:
            if id(e) in seen:
                continue
            lines.append(_format_event(e))
            lines.append("")
            shown += 1
            if shown >= 5:
                break
        if shown == 0:
            lines.append("Bu hafta alohida stavka qarori yo'q (yuqoridagilarga qarang).")
            lines.append("")

    lines.append("---")
    lines.append("🔴 Yuqori | 🟠 O'rta | 🟡 Past ta'sir · Vaqtlar UTC")
    lines.append("Faqat ma'lumot maqsadida. Moliyaviy maslahat emas.")
    return "\n".join(lines)
