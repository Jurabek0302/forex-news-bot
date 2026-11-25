"""Asosiy Telegram bot - Forex/Oltin bozor tahlilchisi."""
import asyncio
import logging
import os
import hashlib
import html as _html
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import requests as _requests

from news_fetcher import fetch_all_news, fetch_newsapi
from price_fetcher import fetch_prices, format_price_line, SYMBOLS
from forex_factory import fetch_ff_calendar, format_ff_calendar
from analyzer import (
    format_news_alert,
    format_price_update,
    format_daily_summary,
    format_market_context,
    _translate_to_uzbek,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY  = os.getenv("NEWS_API_KEY", "")
TD_API_KEY    = os.getenv("TWELVEDATA_API_KEY", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))
DAILY_TIME    = os.getenv("DAILY_SUMMARY_TIME", "05:00")

# Ko'rilgan yangiliklar - takrorlanmaslik uchun
_seen_news: set[str] = set()


async def _translate_uz(text: str) -> str:
    """Matnni o'zbek tiliga tarjima qilish (async, bloklamas)."""
    if not text or len(text) < 5:
        return text

    def _do():
        # 1-usul: Google (tez, cheksiz — agar IP bloklanmagan bo'lsa)
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "en", "tl": "uz", "dt": "t", "q": text[:450]}
            resp = _requests.get(url, params=params, timeout=5)
            data = resp.json()
            out = "".join(p[0] for p in data[0] if p[0])
            if out:
                return out
        except Exception:
            pass
        # 2-usul: MyMemory (datacenter uchun ishonchli)
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {"q": text[:450], "langpair": "en|uz"}
            resp = _requests.get(url, params=params, timeout=5)
            data = resp.json()
            out = data.get("responseData", {}).get("translatedText", "")
            if out:
                return _html.unescape(out)
        except Exception:
            pass
        return None

    try:
        result = await asyncio.to_thread(_do)
        return result or _translate_to_uzbek(text)
    except Exception:
        return _translate_to_uzbek(text)


def _news_hash(item: dict) -> str:
    """Yangilik uchun unikal hash."""
    key = f"{item.get('source','')}-{item.get('title','')[:60]}"
    return hashlib.md5(key.encode()).hexdigest()


async def send_message_safe(bot: Bot, text: str, disable_preview: bool = True):
    """Telegram ga xabar yuborish, xatolarni ushlab olish."""
    try:
        # 4096 belgi chegarasi
        if len(text) > 4000:
            text = text[:3997] + "..."
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            disable_web_page_preview=disable_preview,
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xato: {e}")


# ─── Scheduled joblar ────────────────────────────────────────────────────────

async def job_check_news(bot: Bot):
    """Har CHECK_INTERVAL soniyada yangiliklar tekshirish."""
    global _seen_news
    logger.info("Yangiliklar tekshirilmoqda...")

    try:
        items = await asyncio.to_thread(fetch_all_news)
        if NEWS_API_KEY:
            extra = await asyncio.to_thread(fetch_newsapi, NEWS_API_KEY)
            items = extra + items
    except Exception as e:
        logger.error(f"Yangilik olishda xato: {e}")
        return

    new_count = 0
    for item in items:
        if new_count >= 15:
            _seen_news.add(_news_hash(item))
            continue

        h = _news_hash(item)
        if h in _seen_news:
            continue
        _seen_news.add(h)

        if len(_seen_news) > 500:
            _seen_news = set(list(_seen_news)[-300:])

        try:
            title_uz = await _translate_uz(item.get("title", ""))
            raw_summary = item.get("summary", "")
            summary_uz = await _translate_uz(raw_summary) if raw_summary else ""
            msg = format_news_alert(item, title_uz=title_uz, summary_uz=summary_uz)
            await send_message_safe(bot, msg)
            new_count += 1
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Yangilik yuborishda xato: {e}")

    if new_count:
        logger.info(f"{new_count} ta yangi yangilik yuborildi")
    else:
        logger.info("Yangi muhim yangilik yo'q")


async def job_price_update(bot: Bot):
    """Har 15 daqiqada narx yangilanishi."""
    try:
        prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
        msg = format_price_update(prices)
        ctx = format_market_context()
        await send_message_safe(bot, msg + "\n\n" + ctx)
    except Exception as e:
        logger.error(f"Narx yangilanishida xato: {e}")


async def job_daily_summary(bot: Bot):
    """Kunlik bozor sharhi."""
    try:
        prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
        items = await asyncio.to_thread(fetch_all_news)
        high_news = [n for n in items if n.get("priority") == "HIGH"][:5]
        titles_uz = [await _translate_uz(n.get("title", "")[:150]) for n in high_news]
        msg = format_daily_summary(prices, high_news, titles_uz=titles_uz)
        await send_message_safe(bot, msg)
    except Exception as e:
        logger.error(f"Kunlik sharh yuborishda xato: {e}")


# ─── Telegram komandalar ──────────────────────────────────────────────────────

def _main_keyboard() -> InlineKeyboardMarkup:
    """Asosiy tugmalar paneli."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Narxlar", callback_data="prices"),
            InlineKeyboardButton("📰 Yangiliklar", callback_data="news"),
        ],
        [
            InlineKeyboardButton("🌅 Bozor sharhi", callback_data="summary"),
            InlineKeyboardButton("🤖 Bot holati", callback_data="status"),
        ],
        [
            InlineKeyboardButton("📅 Forex Factory kalendar", callback_data="ff"),
        ],
        [
            InlineKeyboardButton("❓ Yordam", callback_data="help"),
        ],
    ])


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/start - Chat ID va salomlashish."""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "foydalanuvchi"

    await update.message.reply_text(
        f"👋 Salom, @{username}!\n\n"
        f"🤖 Forex Tahlil Boti ishga tushdi!\n\n"
        f"Chat ID: {chat_id}\n\n"
        f"Quyidagi tugmalardan foydalaning 👇",
        reply_markup=_main_keyboard(),
    )


async def cmd_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/prices — Joriy narxlar."""
    await update.message.reply_text("⏳ Narxlar olinmoqda...")
    prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
    msg = format_price_update(prices)
    ctx_msg = format_market_context()
    await update.message.reply_text(msg + "\n\n" + ctx_msg)


async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/news — So'nggi muhim yangiliklar."""
    await update.message.reply_text("⏳ Yangiliklar izlanmoqda...")
    items = await asyncio.to_thread(fetch_all_news)

    if not items:
        await update.message.reply_text("ℹ️ Hozircha muhim yangilik yoq.")
        return

    for item in items[:3]:
        title_uz = await _translate_uz(item.get("title", ""))
        msg = format_news_alert(item, title_uz=title_uz)
        await update.message.reply_text(msg, disable_web_page_preview=True)
        await asyncio.sleep(1)


async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/summary — To'liq bozor sharhi."""
    await update.message.reply_text("⏳ Sharh tayyorlanmoqda...")
    prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
    items = await asyncio.to_thread(fetch_all_news)
    high_news = [n for n in items if n.get("priority") == "HIGH"][:5]
    titles_uz = [await _translate_uz(n.get("title", "")[:150]) for n in high_news]
    msg = format_daily_summary(prices, high_news, titles_uz=titles_uz)
    await update.message.reply_text(msg, disable_web_page_preview=True)


async def cmd_calendar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/kalendar — ForexFactory iqtisodiy kalendar."""
    await update.message.reply_text("⏳ Forex Factory kalendari yuklanmoqda...")
    events = await asyncio.to_thread(fetch_ff_calendar)
    msg = format_ff_calendar(events)[:4000]
    await update.message.reply_text(msg, disable_web_page_preview=True)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/status — Bot holati va sozlamalari."""
    now = datetime.now(timezone.utc).strftime("%H:%M UTC, %d.%m.%Y")
    td_status = "✅ Ulangan" if (TD_API_KEY and TD_API_KEY != "your_twelvedata_key_here") else "⚠️ Yoq (Yahoo fallback)"
    news_status = "✅ Ulangan" if (NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here") else "⚠️ Yoq (RSS only)"

    await update.message.reply_text(
        f"🤖 BOT HOLATI\n"
        f"⏰ Vaqt: {now}\n\n"
        f"API holatlar:\n"
        f"• TwelveData: {td_status}\n"
        f"• NewsAPI: {news_status}\n\n"
        f"Sozlamalar:\n"
        f"• Yangilik tekshirish: har {CHECK_INTERVAL//60} daqiqa\n"
        f"• Kunlik sharh: {DAILY_TIME} UTC\n"
        f"• Korilgan yangiliklar: {len(_seen_news)} ta\n\n"
        f"Kuzatiladigan juftliklar:\n"
        f"🥇 XAUUSD | 💵 DXY | 📊 NAS100 | 🇪🇺 EURUSD",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/help — Yordam."""
    text = (
        "📖 YORDAM\n\n"
        "Bu bot quyidagi bozorlarni kuzatadi:\n"
        "🥇 XAUUSD — Oltin/Dollar\n"
        "💵 DXY — Dollar Indeksi\n"
        "📊 NAS100 — Nasdaq 100\n"
        "🇪🇺 EURUSD — Euro/Dollar\n\n"
        "Avtomatik xabarlar:\n"
        "• 🚨 Tezkor yangiliklar — darhol\n"
        "• 📰 Muhim yangiliklar — doimiy kuzatuv\n"
        "• 📈 Narx yangilanishi — har 15 daqiqa\n"
        f"• 🌅 Kunlik sharh — har kuni {DAILY_TIME} UTC\n\n"
        "📅 Forex Factory kalendar tugmasi:\n"
        "Haftalik iqtisodiy hodisalar, foiz stavka qarorlari va\n"
        "ularning bozorga ta'siri tahlili (/kalendar).\n\n"
        "Faqat malumot maqsadida. Moliyaviy maslahat emas."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=_main_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=_main_keyboard())


async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tugma bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "prices":
        await query.edit_message_text("⏳ Narxlar olinmoqda...")
        prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
        msg = format_price_update(prices)
        ctx_msg = format_market_context()
        await query.edit_message_text(msg + "\n\n" + ctx_msg, reply_markup=_main_keyboard())

    elif data == "news":
        await query.edit_message_text("⏳ Yangiliklar izlanmoqda...")
        items = await asyncio.to_thread(fetch_all_news)
        if not items:
            await query.edit_message_text("ℹ️ Hozircha muhim yangilik yoq.", reply_markup=_main_keyboard())
            return
        for item in items[:3]:
            title_uz = await _translate_uz(item.get("title", ""))
            msg = format_news_alert(item, title_uz=title_uz)
            await query.message.reply_text(msg, disable_web_page_preview=True)
            await asyncio.sleep(1)
        await query.message.reply_text("📋 Asosiy menyu:", reply_markup=_main_keyboard())

    elif data == "summary":
        await query.edit_message_text("⏳ Sharh tayyorlanmoqda...")
        prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
        items = await asyncio.to_thread(fetch_all_news)
        high_news = [n for n in items if n.get("priority") == "HIGH"][:5]
        titles_uz = [await _translate_uz(n.get("title", "")[:150]) for n in high_news]
        msg = format_daily_summary(prices, high_news, titles_uz=titles_uz)
        await query.edit_message_text(msg, reply_markup=_main_keyboard())

    elif data == "ff":
        await query.edit_message_text("⏳ Forex Factory kalendari yuklanmoqda...")
        events = await asyncio.to_thread(fetch_ff_calendar)
        msg = format_ff_calendar(events)[:4000]
        await query.edit_message_text(msg, reply_markup=_main_keyboard())

    elif data == "status":
        now = datetime.now(timezone.utc).strftime("%H:%M UTC, %d.%m.%Y")
        td_status = "✅ Ulangan" if (TD_API_KEY and TD_API_KEY != "your_twelvedata_key_here") else "⚠️ Yoq (Yahoo fallback)"
        news_status = "✅ Ulangan" if (NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here") else "⚠️ Yoq (RSS only)"
        text = (
            f"🤖 BOT HOLATI\n"
            f"⏰ Vaqt: {now}\n\n"
            f"API holatlar:\n"
            f"• TwelveData: {td_status}\n"
            f"• NewsAPI: {news_status}\n\n"
            f"Sozlamalar:\n"
            f"• Yangilik tekshirish: har {CHECK_INTERVAL//60} daqiqa\n"
            f"• Kunlik sharh: {DAILY_TIME} UTC\n"
            f"• Korilgan yangiliklar: {len(_seen_news)} ta\n\n"
            f"Kuzatiladigan juftliklar:\n"
            f"🥇 XAUUSD | 💵 DXY | 📊 NAS100 | 🇪🇺 EURUSD"
        )
        await query.edit_message_text(text, reply_markup=_main_keyboard())

    elif data == "help":
        text = (
            "📖 YORDAM\n\n"
            "Bu bot quyidagi bozorlarni kuzatadi:\n"
            "🥇 XAUUSD — Oltin/Dollar\n"
            "💵 DXY — Dollar Indeksi\n"
            "📊 NAS100 — Nasdaq 100\n"
            "🇪🇺 EURUSD — Euro/Dollar\n\n"
            "Avtomatik xabarlar:\n"
            "• 🚨 Tezkor yangiliklar — darhol\n"
            "• 📰 Muhim yangiliklar — doimiy kuzatuv\n"
            "• 📈 Narx yangilanishi — har 15 daqiqa\n"
            f"• 🌅 Kunlik sharh — har kuni {DAILY_TIME} UTC\n\n"
            "📅 Forex Factory kalendar tugmasi:\n"
            "Haftalik iqtisodiy hodisalar, foiz stavka qarorlari va\n"
            "ularning bozorga ta'siri tahlili (/kalendar).\n\n"
            "Faqat malumot maqsadida. Moliyaviy maslahat emas."
        )
        await query.edit_message_text(text, reply_markup=_main_keyboard())


# ─── Asosiy ishga tushirish ───────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        logger.error("❌ TELEGRAM_BOT_TOKEN .env faylda yo'q!")
        print("\n⚠️  Avval .env faylni to'ldiring:")
        print("   1. .env.example → .env ga nusxalang")
        print("   2. TELEGRAM_BOT_TOKEN ni to'ldiring")
        print("   3. TELEGRAM_CHAT_ID ni to'ldiring")
        return

    if not CHAT_ID or CHAT_ID == "your_chat_id_here":
        logger.warning("⚠️ TELEGRAM_CHAT_ID yo'q — faqat komanda rejimida ishlaydi")
        print("\n⚠️  Chat ID kerak: botga /start yuboring, ID ni ko'rasiz")

    logger.info("🤖 Bot ishga tushmoqda...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Komandalarni ro'yxatdan o'tkazish
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("prices",  cmd_prices))
    app.add_handler(CommandHandler("news",    cmd_news))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("kalendar", cmd_calendar))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CallbackQueryHandler(callback_handler))

    bot = app.bot

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Yangilik tekshirish - har CHECK_INTERVAL soniya
    scheduler.add_job(
        job_check_news,
        "interval",
        seconds=CHECK_INTERVAL,
        args=[bot],
        id="news_check",
    )

    # Narx yangilanishi - har 15 daqiqa
    scheduler.add_job(
        job_price_update,
        "interval",
        minutes=15,
        args=[bot],
        id="price_update",
    )

    # Kunlik sharh
    hour, minute = map(int, DAILY_TIME.split(":"))
    scheduler.add_job(
        job_daily_summary,
        "cron",
        hour=hour,
        minute=minute,
        args=[bot],
        id="daily_summary",
    )

    scheduler.start()
    logger.info(f"✅ Scheduler ishga tushdi: yangilik={CHECK_INTERVAL}s, narx=15min, sharh={DAILY_TIME} UTC")

    # Ishga tushish xabari
    if CHAT_ID and CHAT_ID != "your_chat_id_here":
        try:
            prices = await asyncio.to_thread(fetch_prices, TD_API_KEY)
            startup_msg = (
                "🤖 BOT ISHGA TUSHDI!\n\n"
                + format_price_update(prices)
                + "\n\n"
                + format_market_context()
                + "\n\n"
                f"⚙️ Sozlamalar:\n"
                f"• Yangilik: har {CHECK_INTERVAL//60} daqiqa\n"
                f"• Narx: har 15 daqiqa\n"
                f"• Sharh: {DAILY_TIME} UTC"
            )
            await send_message_safe(bot, startup_msg)
        except Exception as e:
            logger.warning(f"Ishga tushish xabari yuborilmadi: {e}")

    logger.info("✅ Bot ishga tushdi. To'xtatish uchun Ctrl+C")

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        try:
            await asyncio.Event().wait()  # Cheksiz kutish
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            logger.info("Bot to'xtatilmoqda...")
        finally:
            scheduler.shutdown()
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
