"""Narx ma'lumotlarini olish moduli."""
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SYMBOLS = {
    "XAUUSD": {"name": "Oltin/Dollar", "emoji": "рџҐ‡"},
    "DXY":    {"name": "Dollar Indeksi", "emoji": "рџ’µ"},
    "NAS100": {"name": "Nasdaq 100", "emoji": "рџ“Љ"},
    "EURUSD": {"name": "Euro/Dollar", "emoji": "рџ‡Єрџ‡є"},
}

# Twelvedata orqali narx olish
def fetch_prices_twelvedata(api_key: str) -> dict:
    """Twelvedata API orqali narxlarni olish."""
    if not api_key or api_key == "your_twelvedata_key_here":
        return _fetch_prices_fallback()

    # Simbollar mosligi
    td_symbols = {
        "XAUUSD": "XAU/USD",
        "DXY":    "DX-Y.NYB",
        "NAS100": "NDX",
        "EURUSD": "EUR/USD",
    }

    prices = {}
    for sym, td_sym in td_symbols.items():
        try:
            url = "https://api.twelvedata.com/quote"
            params = {"symbol": td_sym, "apikey": api_key}
            resp = requests.get(url, params=params, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            if "close" in data:
                prices[sym] = {
                    "price": float(data.get("close", 0)),
                    "change": float(data.get("change", 0)),
                    "change_pct": float(data.get("percent_change", 0)),
                    "high": float(data.get("high", 0)),
                    "low": float(data.get("low", 0)),
                    "open": float(data.get("open", 0)),
                }
        except Exception as e:
            logger.debug(f"Twelvedata {sym} xatosi: {e}")
            prices[sym] = None
    return prices


def _fetch_prices_fallback() -> dict:
    """Bepul Yahoo Finance ga o'xshash manbadan narx olish."""
    yahoo_symbols = {
        "XAUUSD": "XAUUSD=X",
        "DXY":    "DX-Y.NYB",
        "NAS100": "^NDX",
        "EURUSD": "EURUSD=X",
    }
    prices = {}
    for sym, yahoo_sym in yahoo_symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            meta = data["chart"]["result"][0]["meta"]
            current = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", current))
            change = current - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            prices[sym] = {
                "price": round(current, 4),
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
                "high": round(meta.get("regularMarketDayHigh", 0), 4),
                "low": round(meta.get("regularMarketDayLow", 0), 4),
                "open": round(meta.get("regularMarketOpen", 0), 4),
            }
        except Exception as e:
            logger.debug(f"Yahoo {sym} xatosi: {e}")
            prices[sym] = None
    return prices


def fetch_prices(twelvedata_key: str = "") -> dict:
    """Narxlarni olish - Twelvedata yo'q bo'lsa Yahoo fallback."""
    if twelvedata_key and twelvedata_key != "your_twelvedata_key_here":
        return fetch_prices_twelvedata(twelvedata_key)
    return _fetch_prices_fallback()


def format_price_line(sym: str, data: Optional[dict]) -> str:
    """Narx qatorini formatlash."""
    info = SYMBOLS.get(sym, {"name": sym, "emoji": "рџ“€"})
    if not data:
        return f"{info['emoji']} {sym} вЂ” ma'lumot yo'q"

    price = data["price"]
    change = data["change"]
    change_pct = data["change_pct"]

    # Narx formati
    if sym in ("XAUUSD",):
        price_str = f"{price:,.2f}"
    elif sym == "DXY":
        price_str = f"{price:.3f}"
    elif sym == "NAS100":
        price_str = f"{price:,.1f}"
    else:
        price_str = f"{price:.5f}"

    arrow = "рџ”є" if change >= 0 else "рџ”»"
    sign = "+" if change >= 0 else ""

    return (
        f"{info['emoji']} {sym} `{price_str}`  "
        f"{arrow} {sign}{change_pct:.2f}%"
    )

