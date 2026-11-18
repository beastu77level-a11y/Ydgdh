import asyncio
import html
import json
import logging
import math
import os
import re
import sqlite3
import unicodedata
import uuid
from contextvars import ContextVar
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    MessageEntity,
    CallbackQuery,
    ChatMemberUpdated,
    PreCheckoutQuery,
    LabeledPrice,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.methods import (SendMessage, EditMessageText, SendPhoto, SendAnimation,
                             SendVideo, EditMessageCaption, ForwardMessage, DeleteMessage)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============================================================
# CONFIG (RAILWAY / ENVIRONMENT VARIABLES READY)
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Two default admins (can also be overridden via ADMIN_IDS env var, e.g. "12345,67890")
_env_admins = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
}
ADMIN_IDS = _env_admins or {
    6261736889,
    8199495967,
}

# Optional: set DB_FILE=/data/gift_bot.db if you attach a Railway Volume at /data
DB_FILE = os.getenv("DB_FILE", "gift_bot.db").strip() or "gift_bot.db"
_db_dir = os.path.dirname(DB_FILE)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

_env_log_cid = os.getenv("LOG_CHANNEL_ID", "").strip()
LOG_CHANNEL_ID = int(_env_log_cid) if _env_log_cid.lstrip("-").isdigit() else -1003907607524


# ============================================================
# MONEY / BALANCE
# ============================================================
#
# Internally:
#
# 1 Star = 2 balance units
# 0.5 Star = 1 balance unit
#
# Internal balance units support half-Star amounts without floats
# without using floating-point numbers.
#
# ============================================================

UNITS_PER_STAR = 2

MIN_DEPOSIT_STARS = 2
MAX_DEPOSIT_STARS = 100000

GIFT_PRICE_STARS = 15

# Gift transaction fee is disabled. Users pay only the Telegram gift price.
GIFT_FEE_PERCENT = 0


# ============================================================
# REFERRAL
# ============================================================

REFERRAL_REWARD_UNITS = UNITS_PER_STAR  # 1 full \u2b50


# ============================================================
# CUSTOM EMOJI IDS
# ============================================================
#
# Leave as None if you don't have custom emoji IDs.
#
# Example:
#
# EMOJI_GIFT = "5368324170671202286"
#
# ============================================================

EMOJI_GIFT = "5357356688213046902"
EMOJI_DEPOSIT = "4967518033061872209"
EMOJI_BALANCE = "6082667069826931768"
EMOJI_PROMOTE = "6213253673561103336"
EMOJI_REFERRAL = "5260730055880876557"
EMOJI_REDEEM = "5262682895905989734"
EMOJI_STAR = "5954135079662916434"
EMOJI_USER = "5258362837411045098"
EMOJI_TEDDY = "5397915559037785261"
EMOJI_LOVE = "5465263910414195580"
EMOJI_CONFIRM = "5260416304224936047"
EMOJI_CANCEL = "5260342697075416641"
EMOJI_BACK = "5960671702059848143"
EMOJI_ADMIN = "6154278103230194209"
EMOJI_STATS = "5028746137645876535"
EMOJI_SECURITY = "6030445631921721471"
EMOJI_SETTINGS = "5258096772776991776"
EMOJI_VIP = "5471952986970267163"
EMOJI_LOGS = "6323096332579899122"
EMOJI_FORCE = "6008220984346152956"
EMOJI_VERIFY = "5260416304224936047"
EMOJI_LOCK = "5258476306152038031"
EMOJI_SUCCESS = "5461151367559141950"
EMOJI_WARNING = "6195140911710608839"
EMOJI_STOP = "5861680368108704195"
EMOJI_MAINTENANCE = "6226259397174109685"
EMOJI_INVOICE = "5444856076954520455"
EMOJI_HISTORY = EMOJI_INVOICE
EMOJI_NOTE = "5334882760735598374"
EMOJI_ID = "5014902839575577394"
EMOJI_USERS = "5256143829672672750"
EMOJI_SEARCH = "5472214816766577537"
EMOJI_ADD = "5298954496016138169"
EMOJI_REMOVE = "5301240299085906131"

# Additional emojis used across the bot (None by default; configurable in Admin -> Change Variables -> Change Emoji ID)
EMOJI_TARGET = None
EMOJI_PIN = None
EMOJI_PICTURE = None
EMOJI_MONEY_WINGS = None
EMOJI_CALENDAR = None
EMOJI_NAME_BADGE = None
EMOJI_EMPTY_MAILBOX = None
EMOJI_NEW = None
EMOJI_QUESTION = None
EMOJI_STOP_BTN = None
EMOJI_GREEN_DOT = None
EMOJI_WHITE_DOT = None
EMOJI_TROPHY = None
EMOJI_MEDAL = None

# Level & rank number emojis (1 to 10, medals)
EMOJI_NUM_1 = None
EMOJI_NUM_2 = None
EMOJI_NUM_3 = None
EMOJI_NUM_4 = None
EMOJI_NUM_5 = None
EMOJI_NUM_6 = None
EMOJI_NUM_7 = None
EMOJI_NUM_8 = None
EMOJI_NUM_9 = None
EMOJI_NUM_10 = None
EMOJI_FIRST = None
EMOJI_SECOND = None
EMOJI_THIRD = None
EMOJI_RIBBON = None
EMOJI_HEART_RIBBON = None
EMOJI_NEXT = None
EMOJI_REFRESH = None
EMOJI_ROSE = None
EMOJI_CAKE = None
EMOJI_BOUQUET = None
EMOJI_CHAMPAGNE = None
EMOJI_ROCKET = None
EMOJI_RING = None
EMOJI_SPARKLING_HEART = None
EMOJI_TWO_HEARTS = None
EMOJI_GROWING_HEART = None
EMOJI_BEATING_HEART = None
EMOJI_REVOLVING_HEARTS = None
EMOJI_CUPID = None
EMOJI_HEART_DECORATION = None

CUSTOM_EMOJI_IDS = {
    "🎁": EMOJI_GIFT, "💳": EMOJI_DEPOSIT, "💰": EMOJI_BALANCE,
    "📢": EMOJI_PROMOTE, "🔗": EMOJI_REFERRAL, "🎟️": EMOJI_REDEEM,
    "⭐": EMOJI_STAR, "👤": EMOJI_USER, "🧸": EMOJI_TEDDY,
    "❤️": EMOJI_LOVE, "✅": EMOJI_CONFIRM, "❌": EMOJI_CANCEL,
    "⬅️": EMOJI_BACK, "👑": EMOJI_ADMIN, "📊": EMOJI_STATS,
    "🛡️": EMOJI_SECURITY, "⚙️": EMOJI_SETTINGS, "💎": EMOJI_VIP,
    "📜": EMOJI_LOGS, "📣": EMOJI_FORCE, "🔒": EMOJI_LOCK,
    "🎉": EMOJI_SUCCESS, "⚠️": EMOJI_WARNING, "⛔": EMOJI_STOP,
    "🔧": EMOJI_MAINTENANCE, "🧾": EMOJI_INVOICE, "📝": EMOJI_NOTE,
    "🆔": EMOJI_ID, "👥": EMOJI_USERS, "🔎": EMOJI_SEARCH,
    "➕": EMOJI_ADD, "➖": EMOJI_REMOVE,
}
CUSTOM_EMOJI_IDS = {k: v for k, v in CUSTOM_EMOJI_IDS.items() if v}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("giftbot")


# ============================================================
# BOT
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not configured. Please set BOT_TOKEN in Railway Variables."
    )

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def premiumize_text(value):
    """Convert supplied emoji IDs into Telegram HTML custom-emoji entities.

    Also handles numeric HTML entities (for example &#127873;) used by older
    dashboard strings. Only known emoji entities are decoded, so HTML escaping
    such as &lt; and &amp; remains untouched.
    """
    if not isinstance(value, str):
        return value

    numeric_emoji = {
        127873: "🎁", 128176: "💰", 11088: "⭐", 128187: "💳",
        128226: "📢", 128279: "🔗", 127903: "🎟️", 128100: "👤",
    }
    # Keep the lookup above simple and valid Python; replace numeric entities
    # for every custom emoji by their actual codepoint(s).
    for emoji in CUSTOM_EMOJI_IDS:
        cps = [ord(ch) for ch in emoji if ord(ch) not in (0xFE0F, 0xFE0E)]
        if len(cps) == 1:
            numeric_emoji[cps[0]] = emoji
    value = re.sub(
        r"&#(?:x([0-9a-fA-F]+)|(\d+));?",
        lambda m: numeric_emoji.get(int(m.group(1), 16) if m.group(1) else int(m.group(2)), m.group(0)),
        value,
    )
    # Preserve any already-wrapped <tg-emoji>...</tg-emoji> spans while converting other emojis.
    parts = re.split(r"(<tg-emoji\b[^>]*>.*?</tg-emoji>)", value, flags=re.DOTALL)
    sorted_emojis = sorted(CUSTOM_EMOJI_IDS.items(), key=lambda item: len(item[0]), reverse=True)
    for idx in range(0, len(parts), 2):
        chunk = parts[idx]
        for emoji, custom_id in sorted_emojis:
            chunk = chunk.replace(emoji, f'<tg-emoji emoji-id="{custom_id}">{emoji}</tg-emoji>')
        parts[idx] = chunk
    return "".join(parts)

# Apply premium custom emoji conversion at the Bot API call layer.
# Supports Photo, GIF (Animation), and Video banners attached to messages.
_original_bot_call = Bot.__call__
_BANNER_MEDIA = None  # Tuple of (media_type, file_id) where media_type in ("photo", "animation", "video")
_SKIP_BANNER: ContextVar[bool] = ContextVar("_SKIP_BANNER", default=False)
DEFAULT_BANNER_SOURCE = "https://t.me/metahelpline/28"


def get_banner_source() -> str:
    try:
        val = get_setting("banner_source", DEFAULT_BANNER_SOURCE).strip()
        return val if val else DEFAULT_BANNER_SOURCE
    except Exception:
        return DEFAULT_BANNER_SOURCE


def get_log_channel_id() -> str:
    try:
        val = get_setting("log_channel_id", str(LOG_CHANNEL_ID)).strip()
        return val if val else str(LOG_CHANNEL_ID)
    except Exception:
        return str(LOG_CHANNEL_ID)


def get_vouch_channel_id() -> str:
    try:
        return get_setting("vouch_channel_id", "").strip()
    except Exception:
        return ""


def _parse_telegram_post_link(source: str):
    m_pub = re.match(r"^https?://(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,32})/(\d+)/?$", source)
    if m_pub:
        return f"@{m_pub.group(1)}", int(m_pub.group(2))
    m_priv = re.match(r"^https?://(?:t\.me|telegram\.me)/c/(\d+)/(\d+)/?$", source)
    if m_priv:
        return int(f"-100{m_priv.group(1)}"), int(m_priv.group(2))
    return None, None


def _detect_direct_media_type(source: str):
    lower = source.lower()
    if lower.startswith("gif:"):
        return "animation", source[4:].strip()
    if lower.startswith("video:"):
        return "video", source[6:].strip()
    if lower.startswith("photo:"):
        return "photo", source[6:].strip()

    clean_path = lower.split("?", 1)[0].split("#", 1)[0]
    if clean_path.endswith(".gif"):
        return "animation", source
    if clean_path.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v")):
        return "video", source
    return "photo", source


async def _get_banner_media(self, target_chat, request_timeout=None):
    global _BANNER_MEDIA
    if _BANNER_MEDIA:
        return _BANNER_MEDIA

    source = get_banner_source()
    if not source or source.lower() in ("none", "off"):
        return None

    from_chat, msg_id = _parse_telegram_post_link(source)
    if from_chat is not None and msg_id is not None:
        forwarded = None
        try:
            forwarded = await _original_bot_call(
                self,
                ForwardMessage(
                    chat_id=target_chat,
                    from_chat_id=from_chat,
                    message_id=msg_id,
                ),
                request_timeout=request_timeout,
            )
            anim = getattr(forwarded, "animation", None)
            if anim:
                _BANNER_MEDIA = ("animation", anim.file_id)
                return _BANNER_MEDIA

            vid = getattr(forwarded, "video", None)
            if vid:
                _BANNER_MEDIA = ("video", vid.file_id)
                return _BANNER_MEDIA

            photos = getattr(forwarded, "photo", None) or []
            if photos:
                _BANNER_MEDIA = ("photo", photos[-1].file_id)
                return _BANNER_MEDIA

            doc = getattr(forwarded, "document", None)
            if doc:
                mime = str(getattr(doc, "mime_type", "") or "").lower()
                if mime == "image/gif":
                    _BANNER_MEDIA = ("animation", doc.file_id)
                    return _BANNER_MEDIA
                if mime.startswith("video/"):
                    _BANNER_MEDIA = ("video", doc.file_id)
                    return _BANNER_MEDIA

            logger.warning("Configured banner post %s does not contain a photo, GIF, or video", source)
        except Exception:
            logger.warning("Could not read banner media from %s", source, exc_info=True)
        finally:
            if forwarded is not None:
                try:
                    await _original_bot_call(
                        self,
                        DeleteMessage(chat_id=target_chat, message_id=forwarded.message_id),
                        request_timeout=request_timeout,
                    )
                except Exception:
                    logger.warning("Could not remove temporary banner forward", exc_info=True)
        return None

    # Direct URL (photo/gif/video) or Telegram file_id
    _BANNER_MEDIA = _detect_direct_media_type(source)
    return _BANNER_MEDIA


async def send_text_only(chat_id, text: str, **kwargs):
    token = _SKIP_BANNER.set(True)
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    finally:
        _SKIP_BANNER.reset(token)


async def _premium_bot_call(self, method, request_timeout=None):
    if isinstance(method, (SendMessage, EditMessageText)):
        if isinstance(method.text, str):
            method.text = premiumize_text(method.text)
            if "<tg-emoji" in method.text:
                method.parse_mode = "HTML"

    elif isinstance(method, (SendPhoto, SendAnimation, SendVideo)):
        if isinstance(method.caption, str):
            method.caption = premiumize_text(method.caption)
            if "<tg-emoji" in method.caption:
                method.parse_mode = "HTML"

    elif isinstance(method, EditMessageCaption):
        if isinstance(method.caption, str):
            method.caption = premiumize_text(method.caption)
            if "<tg-emoji" in method.caption:
                method.parse_mode = "HTML"

    log_cid = get_log_channel_id()
    vouch_cid = get_vouch_channel_id()

    # Convert EditMessageText into EditMessageCaption when editing banner media messages (photo, GIF, video).
    if isinstance(method, EditMessageText) and str(method.chat_id) not in (log_cid, vouch_cid):
        caption_method = EditMessageCaption(
            chat_id=method.chat_id,
            message_id=method.message_id,
            inline_message_id=method.inline_message_id,
            caption=method.text,
            parse_mode=method.parse_mode,
            caption_entities=method.entities,
            reply_markup=method.reply_markup,
        )
        try:
            return await _original_bot_call(self, caption_method, request_timeout=request_timeout)
        except TelegramBadRequest as e:
            err_lower = str(e).lower()
            if "no caption" in err_lower:
                return await _original_bot_call(self, method, request_timeout=request_timeout)
            if "caption is too long" in err_lower and method.chat_id and method.message_id:
                try:
                    await _original_bot_call(
                        self,
                        DeleteMessage(chat_id=method.chat_id, message_id=method.message_id),
                        request_timeout=request_timeout,
                    )
                except Exception:
                    pass
                fallback_send = SendMessage(
                    chat_id=method.chat_id,
                    text=method.text,
                    parse_mode=method.parse_mode,
                    entities=method.entities,
                    reply_markup=method.reply_markup,
                )
                return await _original_bot_call(self, fallback_send, request_timeout=request_timeout)
            raise

    # Convert outgoing user-facing text messages into photo/GIF/video messages, retaining
    # the caption and inline keyboard. Logs, vouches, and plain alerts remain text-only.
    if (
        isinstance(method, SendMessage)
        and not _SKIP_BANNER.get()
        and str(method.chat_id) not in (log_cid, vouch_cid)
        and len(method.text or "") <= 1024
    ):
        media_info = await _get_banner_media(self, method.chat_id, request_timeout)
        if media_info:
            media_type, media_id = media_info
            try:
                payload = method.model_dump(exclude_none=True)
                payload.pop("text", None)
                payload.pop("disable_web_page_preview", None)
                payload.pop("link_preview_options", None)

                if media_type == "animation":
                    method_cls = SendAnimation
                    media_field = "animation"
                elif media_type == "video":
                    method_cls = SendVideo
                    media_field = "video"
                else:
                    method_cls = SendPhoto
                    media_field = "photo"

                allowed = set(method_cls.model_fields.keys())
                media_payload = {k: v for k, v in payload.items() if k in allowed}
                media_payload["chat_id"] = method.chat_id
                media_payload[media_field] = media_id
                media_payload["caption"] = method.text
                if method.parse_mode:
                    media_payload["parse_mode"] = method.parse_mode
                media_method = method_cls(**media_payload)
                return await _original_bot_call(self, media_method, request_timeout=request_timeout)
            except Exception:
                logger.exception("Could not attach banner media (%s); sending text fallback", media_type)

    return await _original_bot_call(self, method, request_timeout=request_timeout)

Bot.__call__ = _premium_bot_call


async def send_activity_log(text: str):
    log_cid = get_log_channel_id()
    if not log_cid or log_cid.lower() in ("0", "off", "none"):
        return
    try:
        target = int(log_cid) if log_cid.lstrip("-").isdigit() else log_cid
        await send_text_only(target, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        logger.exception("Could not post activity log to configured log channel")


async def send_vouch_message(text: str):
    vouch_cid = get_vouch_channel_id()
    if not vouch_cid or vouch_cid.lower() in ("0", "off", "none"):
        return
    try:
        target = int(vouch_cid) if vouch_cid.lstrip("-").isdigit() else vouch_cid
        await send_text_only(target, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        logger.exception("Could not post vouch message to configured vouch channel")


async def notify_new_user(user, source: str, referrer_id=None):
    mention = f'<a href="tg://user?id={user.id}">Open user profile</a>'
    username = f'@{esc(user.username)}' if user.username else '<i>not set</i>'
    source_text = f'Referral (from <code>{referrer_id}</code>)' if source == 'refer' else 'Search / direct start'
    kb = InlineKeyboardBuilder()
    kb.button(
        text=user.full_name or "Open User",
        url=f"tg://user?id={user.id}",
        style="success",
        icon_custom_emoji_id=EMOJI_USER,
    )
    kb.adjust(1)
    body = ("<b>New user started the bot</b>\n\n"
            f"ID: <code>{user.id}</code>\nName: {esc(user.full_name)}\n"
            f"Username: {username}\nSource: {source_text}\n\n{mention}")
    for admin_id in ADMIN_IDS:
        try:
            await send_text_only(admin_id, body, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception:
            logger.exception("Could not notify admin about new user")
    await send_activity_log(body)



# ============================================================
# SQLITE
# ============================================================

db = sqlite3.connect(
    DB_FILE,
    check_same_thread=False,
    timeout=30,
)

db.row_factory = sqlite3.Row

db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA foreign_keys=ON")
db.execute("PRAGMA busy_timeout=30000")


# ============================================================
# DATABASE SCHEMA
# ============================================================

db.executescript(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        currency TEXT NOT NULL,
        payload TEXT NOT NULL,
        telegram_charge_id TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS gifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        receiver_username TEXT,
        receiver_name TEXT,
        gift_type TEXT NOT NULL,
        telegram_gift_id TEXT NOT NULL,
        telegram_price INTEGER NOT NULL,
        balance_price INTEGER NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS force_join (
        chat_id INTEGER PRIMARY KEY,
        chat_type TEXT NOT NULL,
        title TEXT NOT NULL,
        invite_link TEXT,
        added_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS referrals (
        referred_user_id INTEGER PRIMARY KEY,
        referrer_user_id INTEGER NOT NULL,
        rewarded INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """
)

db.commit()

# Extended admin features
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS blocked_users (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward_units INTEGER NOT NULL,
        max_uses INTEGER NOT NULL DEFAULT 1,
        used_count INTEGER NOT NULL DEFAULT 0,
        expires_at TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS promo_uses (
        code TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        used_at TEXT NOT NULL,
        PRIMARY KEY(code, user_id)
    );
    CREATE TABLE IF NOT EXISTS vip_users (
        user_id INTEGER PRIMARY KEY,
        expires_at TEXT,
        added_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS channel_promotions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        channel_title TEXT NOT NULL,
        channel_username TEXT NOT NULL,
        description TEXT NOT NULL,
        credits INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS promo_wallets (
        user_id INTEGER PRIMARY KEY,
        stars INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS promo_verifications (
        promotion_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        verified_at TEXT NOT NULL,
        PRIMARY KEY (promotion_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS promo_gate_eligibility (
        promotion_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        eligible INTEGER NOT NULL DEFAULT 0,
        checked_at TEXT NOT NULL,
        PRIMARY KEY (promotion_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS user_sources (
        user_id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        referrer_id INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bot_admins (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS channel_task_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        promotion_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        rewarded_at TEXT,
        penalized INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, channel_id)
    );
    CREATE TABLE IF NOT EXISTS task_eligibility (
        user_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        promotion_id INTEGER NOT NULL,
        was_member INTEGER NOT NULL DEFAULT 0,
        shown_at TEXT NOT NULL,
        PRIMARY KEY (user_id, channel_id)
    );
    CREATE TABLE IF NOT EXISTS promo_link_joins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promotion_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        invite_link TEXT,
        joined_at TEXT NOT NULL,
        left_at TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        source TEXT NOT NULL DEFAULT 'bot_link',
        UNIQUE(promotion_id, user_id)
    );
    """
)
db.commit()


def migrate_channel_promotions_schema():
    cols = {
        row["name"]
        for row in db.execute("PRAGMA table_info(channel_promotions)").fetchall()
    }
    alterations = [
        ("invite_link", "TEXT"),
        ("initial_member_count", "INTEGER NOT NULL DEFAULT 0"),
        ("verified_joins", "INTEGER NOT NULL DEFAULT 0"),
        ("total_credits", "INTEGER NOT NULL DEFAULT 0"),
        ("chat_type", "TEXT NOT NULL DEFAULT 'channel'"),
    ]
    for col_name, col_def in alterations:
        if col_name not in cols:
            db.execute(f"ALTER TABLE channel_promotions ADD COLUMN {col_name} {col_def}")
    db.execute(
        "UPDATE channel_promotions SET total_credits = credits WHERE total_credits = 0 AND credits > 0"
    )
    db.commit()


migrate_channel_promotions_schema()


def admin_log(admin_id, action, details=""):
    db.execute(
        "INSERT INTO admin_logs (admin_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (admin_id, action, str(details)[:500], now()),
    )
    db.commit()


def get_setting(key, default=""):
    row = db.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db.execute("INSERT INTO bot_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    db.commit()


# Persisted operational settings override code defaults after restart.
GIFT_PRICE_STARS = int(get_setting("gift_price_stars", str(GIFT_PRICE_STARS)))
REFERRAL_REWARD_UNITS = int(get_setting("referral_reward_units", str(REFERRAL_REWARD_UNITS)))

EMOJI_VAR_REGISTRY = {
    "GIFT": ("🎁", "EMOJI_GIFT", EMOJI_GIFT),
    "DEPOSIT": ("💳", "EMOJI_DEPOSIT", EMOJI_DEPOSIT),
    "BALANCE": ("💰", "EMOJI_BALANCE", EMOJI_BALANCE),
    "PROMOTE": ("📢", "EMOJI_PROMOTE", EMOJI_PROMOTE),
    "REFERRAL": ("🔗", "EMOJI_REFERRAL", EMOJI_REFERRAL),
    "REDEEM": ("🎟️", "EMOJI_REDEEM", EMOJI_REDEEM),
    "STAR": ("⭐", "EMOJI_STAR", EMOJI_STAR),
    "USER": ("👤", "EMOJI_USER", EMOJI_USER),
    "TEDDY": ("🧸", "EMOJI_TEDDY", EMOJI_TEDDY),
    "LOVE": ("❤️", "EMOJI_LOVE", EMOJI_LOVE),
    "CONFIRM": ("✅", "EMOJI_CONFIRM", EMOJI_CONFIRM),
    "CANCEL": ("❌", "EMOJI_CANCEL", EMOJI_CANCEL),
    "BACK": ("⬅️", "EMOJI_BACK", EMOJI_BACK),
    "ADMIN": ("👑", "EMOJI_ADMIN", EMOJI_ADMIN),
    "STATS": ("📊", "EMOJI_STATS", EMOJI_STATS),
    "SECURITY": ("🛡️", "EMOJI_SECURITY", EMOJI_SECURITY),
    "SETTINGS": ("⚙️", "EMOJI_SETTINGS", EMOJI_SETTINGS),
    "VIP": ("💎", "EMOJI_VIP", EMOJI_VIP),
    "LOGS": ("📜", "EMOJI_LOGS", EMOJI_LOGS),
    "FORCE": ("📣", "EMOJI_FORCE", EMOJI_FORCE),
    "VERIFY": ("✅", "EMOJI_VERIFY", EMOJI_VERIFY),
    "LOCK": ("🔒", "EMOJI_LOCK", EMOJI_LOCK),
    "SUCCESS": ("🎉", "EMOJI_SUCCESS", EMOJI_SUCCESS),
    "WARNING": ("⚠️", "EMOJI_WARNING", EMOJI_WARNING),
    "STOP": ("⛔", "EMOJI_STOP", EMOJI_STOP),
    "MAINTENANCE": ("🔧", "EMOJI_MAINTENANCE", EMOJI_MAINTENANCE),
    "INVOICE": ("🧾", "EMOJI_INVOICE", EMOJI_INVOICE),
    "NOTE": ("📝", "EMOJI_NOTE", EMOJI_NOTE),
    "ID": ("🆔", "EMOJI_ID", EMOJI_ID),
    "USERS": ("👥", "EMOJI_USERS", EMOJI_USERS),
    "SEARCH": ("🔎", "EMOJI_SEARCH", EMOJI_SEARCH),
    "ADD": ("➕", "EMOJI_ADD", EMOJI_ADD),
    "REMOVE": ("➖", "EMOJI_REMOVE", EMOJI_REMOVE),
    "TARGET": ("🎯", "EMOJI_TARGET", None),
    "PIN": ("📌", "EMOJI_PIN", None),
    "PICTURE": ("🖼️", "EMOJI_PICTURE", None),
    "MONEY_WINGS": ("💸", "EMOJI_MONEY_WINGS", None),
    "CALENDAR": ("📅", "EMOJI_CALENDAR", None),
    "NAME_BADGE": ("📛", "EMOJI_NAME_BADGE", None),
    "EMPTY_MAILBOX": ("📭", "EMOJI_EMPTY_MAILBOX", None),
    "NEW": ("🆕", "EMOJI_NEW", None),
    "QUESTION": ("❓", "EMOJI_QUESTION", None),
    "STOP_BTN": ("⏹", "EMOJI_STOP_BTN", None),
    "GREEN_DOT": ("🟢", "EMOJI_GREEN_DOT", None),
    "WHITE_DOT": ("⚪", "EMOJI_WHITE_DOT", None),
    "TROPHY": ("🏆", "EMOJI_TROPHY", None),
    "MEDAL": ("🏅", "EMOJI_MEDAL", None),
    "1": ("1️⃣", "EMOJI_NUM_1", None),
    "2": ("2️⃣", "EMOJI_NUM_2", None),
    "3": ("3️⃣", "EMOJI_NUM_3", None),
    "4": ("4️⃣", "EMOJI_NUM_4", None),
    "5": ("5️⃣", "EMOJI_NUM_5", None),
    "6": ("6️⃣", "EMOJI_NUM_6", None),
    "7": ("7️⃣", "EMOJI_NUM_7", None),
    "8": ("8️⃣", "EMOJI_NUM_8", None),
    "9": ("9️⃣", "EMOJI_NUM_9", None),
    "10": ("🔟", "EMOJI_NUM_10", None),
    "FIRST": ("🥇", "EMOJI_FIRST", None),
    "SECOND": ("🥈", "EMOJI_SECOND", None),
    "THIRD": ("🥉", "EMOJI_THIRD", None),
    "RIBBON": ("🎀", "EMOJI_RIBBON", None),
    "HEART_RIBBON": ("💝", "EMOJI_HEART_RIBBON", None),
    "NEXT": ("➡️", "EMOJI_NEXT", None),
    "REFRESH": ("🔄", "EMOJI_REFRESH", None),
    "ROSE": ("🌹", "EMOJI_ROSE", None),
    "CAKE": ("🎂", "EMOJI_CAKE", None),
    "BOUQUET": ("💐", "EMOJI_BOUQUET", None),
    "CHAMPAGNE": ("🍾", "EMOJI_CHAMPAGNE", None),
    "ROCKET": ("🚀", "EMOJI_ROCKET", None),
    "RING": ("💍", "EMOJI_RING", None),
    "SPARKLING_HEART": ("💖", "EMOJI_SPARKLING_HEART", None),
    "TWO_HEARTS": ("💕", "EMOJI_TWO_HEARTS", None),
    "GROWING_HEART": ("💗", "EMOJI_GROWING_HEART", None),
    "BEATING_HEART": ("💓", "EMOJI_BEATING_HEART", None),
    "REVOLVING_HEARTS": ("💞", "EMOJI_REVOLVING_HEARTS", None),
    "CUPID": ("💘", "EMOJI_CUPID", None),
    "HEART_DECORATION": ("💟", "EMOJI_HEART_DECORATION", None),
}


def reload_custom_emojis():
    global EMOJI_HISTORY
    for key, (unicode_char, global_var, default_id) in EMOJI_VAR_REGISTRY.items():
        saved = get_setting(f"emoji_id_{key}", default_id or "").strip()
        if saved.lower() in ("off", "none") or not saved:
            globals()[global_var] = None
            CUSTOM_EMOJI_IDS.pop(unicode_char, None)
        else:
            globals()[global_var] = saved
            CUSTOM_EMOJI_IDS[unicode_char] = saved
    EMOJI_HISTORY = EMOJI_INVOICE


reload_custom_emojis()


# ============================================================
# USER TIER / LEVEL & EXP SYSTEM (LEVELS 1 TO 9)
# ============================================================
#
# EXP = Total Stars Incoming (deposits, referrals, tasks, promos) + Outgoing (gifts, channel promos)
# Level 1 -> 2 requires 32 Stars EXP.
# Each next level requires 2x the previous step:
#   L1: 0
#   L2: 32
#   L3: 32 + 64 = 96
#   L4: 96 + 128 = 224
#   L5: 224 + 256 = 480
#   L6: 480 + 512 = 992
#   L7: 992 + 1024 = 2016
#   L8: 2016 + 2048 = 4064
#   L9: 4064 + 4096 = 8160 (MAX)
# ============================================================

MAX_USER_LEVEL = 9
BASE_LEVEL_EXP_UNITS = 32 * UNITS_PER_STAR  # 32 Stars = 64 half-Star units

LEVEL_EMOJIS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}


def level_to_emoji(level: int) -> str:
    lvl = max(1, min(MAX_USER_LEVEL, int(level)))
    return LEVEL_EMOJIS[lvl]


def level_step_units(level: int) -> int:
    if level < 1:
        level = 1
    return BASE_LEVEL_EXP_UNITS * (2 ** (level - 1))


def level_min_exp_units(level: int) -> int:
    if level <= 1:
        return 0
    return BASE_LEVEL_EXP_UNITS * ((2 ** (level - 1)) - 1)


def compute_level_from_exp_units(exp_units: int) -> int:
    exp_units = max(0, int(exp_units))
    lvl = 1
    while lvl < MAX_USER_LEVEL and exp_units >= level_min_exp_units(lvl + 1):
        lvl += 1
    return lvl


def get_user_exp_units(user_id: int) -> int:
    tx_row = db.execute(
        """
        SELECT COALESCE(SUM(ABS(amount)), 0) AS total_units
        FROM transactions
        WHERE user_id = ?
          AND type IN ('deposit', 'gift', 'channel_gift', 'referral', 'task_reward', 'promo_reward')
        """,
        (user_id,),
    ).fetchone()
    tx_units = int(tx_row["total_units"]) if tx_row else 0

    promo_pay_row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS stars
        FROM payments
        WHERE user_id = ? AND payload LIKE 'promowallet:%'
        """,
        (user_id,),
    ).fetchone()
    promo_in_units = int(promo_pay_row["stars"]) * UNITS_PER_STAR if promo_pay_row else 0

    promo_spend_row = db.execute(
        """
        SELECT COALESCE(SUM(credits), 0) AS stars
        FROM channel_promotions
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    promo_out_units = int(promo_spend_row["stars"]) * UNITS_PER_STAR if promo_spend_row else 0

    return tx_units + promo_in_units + promo_out_units


def get_user_level(user_id: int) -> int:
    exp_units = get_user_exp_units(user_id)
    computed = compute_level_from_exp_units(exp_units)
    saved_raw = get_setting(f"user_level_{user_id}", "")
    if saved_raw.isdigit():
        return max(int(saved_raw), computed)
    set_setting(f"user_level_{user_id}", computed)
    return computed


async def check_and_notify_level_up(user_id: int):
    exp_units = get_user_exp_units(user_id)
    new_level = compute_level_from_exp_units(exp_units)
    saved_raw = get_setting(f"user_level_{user_id}", "")
    if not saved_raw.isdigit():
        set_setting(f"user_level_{user_id}", new_level)
        return
    old_level = int(saved_raw)
    if new_level > old_level:
        set_setting(f"user_level_{user_id}", new_level)
        lvl_emoji = level_to_emoji(new_level)
        exp_text = units_to_text(exp_units)
        if new_level < MAX_USER_LEVEL:
            next_req_text = units_to_text(level_min_exp_units(new_level + 1))
            next_line = f"🎯 Next Level ({level_to_emoji(new_level + 1)}): <b>{next_req_text} ⭐ EXP</b>"
        else:
            next_line = "🏆 <b>Maximum Tier Level Reached!</b>"

        congo_text = (
            f"🎉 <b>Congratulations! Level Up!</b>\n\n"
            f"⭐ You reached <b>Tier: {lvl_emoji} level</b>!\n"
            f"📊 Total EXP: <b>{exp_text} ⭐</b>\n"
            f"{next_line}"
        )
        try:
            await send_text_only(user_id, congo_text, parse_mode="HTML")
        except Exception:
            logger.exception("Could not send level up congrats message to %s", user_id)

DEFAULT_BOT_HEADING = "Telegram Gift Store"


def get_bot_heading() -> str:
    try:
        val = get_setting("bot_heading", DEFAULT_BOT_HEADING).strip()
        return val if val else DEFAULT_BOT_HEADING
    except Exception:
        return DEFAULT_BOT_HEADING


COLOR_TO_STYLE = {
    "blue": "primary",
    "green": "success",
    "red": "danger",
}
STYLE_TO_COLOR = {
    "primary": "blue",
    "success": "green",
    "danger": "red",
}

# key -> (display_name, default_style)
BUTTON_STYLE_REGISTRY = {
    "SEND_GIFT": ("Send Gift", "primary"),
    "DEPOSIT": ("Deposit", "success"),
    "BALANCE": ("Balance", "primary"),
    "TASKS": ("Tasks", "success"),
    "PROMOTE_CHANNEL": ("Promote Channel", "success"),
    "REFERRAL": ("Referral", "primary"),
    "REDEEM_CODE": ("Redeem Code", "primary"),
    "BACK_MENU": ("Back to Menu", "danger"),
    "SEND_USER": ("Send to User", "primary"),
    "SEND_SELF": ("Send to Myself", "primary"),
    "SEND_CHANNEL": ("Send to Channel", "primary"),
    "PROMOTE_MY_CHANNEL": ("Promote My Channel", "success"),
    "ADD_PROMO_STARS": ("Add Promo Stars", "primary"),
    "PROMO_BALANCE": ("Promo Balance", "primary"),
    "VERIFY": ("Verify", "success"),
    "CONFIRM_SEND": ("Confirm & Send", "success"),
    "CANCEL": ("Cancel", "danger"),
    "LEADERBOARD": ("Leaderboard", "success"),
    "HISTORY": ("History", "primary"),
}

BUTTON_NAME_ALIASES = {
    "main menu": "BACK_MENU",
    "back": "BACK_MENU",
    "task": "TASKS",
    "promote": "PROMOTE_CHANNEL",
    "redeem": "REDEEM_CODE",
    "gift": "SEND_GIFT",
    "confirm": "CONFIRM_SEND",
    "transaction history": "HISTORY",
}


def resolve_button_style_key(raw_name: str):
    cleaned = re.sub(r"\s+", " ", (raw_name or "").strip()).lower()
    if not cleaned:
        return None
    if cleaned in BUTTON_NAME_ALIASES:
        return BUTTON_NAME_ALIASES[cleaned]
    for key, (disp_name, _) in BUTTON_STYLE_REGISTRY.items():
        if cleaned == disp_name.lower() or cleaned == key.lower() or cleaned == key.lower().replace("_", " "):
            return key
    return None


def get_button_style(key: str) -> str:
    _, default_style = BUTTON_STYLE_REGISTRY[key]
    try:
        saved = get_setting(f"btn_style_{key}", default_style).strip().lower()
    except Exception:
        return default_style
    if saved in COLOR_TO_STYLE:
        return COLOR_TO_STYLE[saved]
    if saved in STYLE_TO_COLOR:
        return saved
    return default_style


def get_button_color_name(key: str) -> str:
    return STYLE_TO_COLOR.get(get_button_style(key), "blue")


# Main menu button definitions:
# key -> (display_name, button_text_with_emoji, callback_data, emoji_global_var_name)
DASHBOARD_BUTTONS = {
    "SEND_GIFT": ("Send Gift", "\U0001f381 Send Gift", "dashboard_gift", "EMOJI_GIFT"),
    "DEPOSIT": ("Deposit", "\U0001f4b3 Deposit", "dashboard_deposit", "EMOJI_DEPOSIT"),
    "BALANCE": ("Balance", "\U0001f4b0 Balance", "dashboard_balance", "EMOJI_BALANCE"),
    "TASKS": ("Tasks", "\U0001f4dd Tasks", "dashboard_tasks", "EMOJI_NOTE"),
    "PROMOTE_CHANNEL": ("Promote Channel", "\U0001f4e2 Promote Channel", "channelpromo_start", "EMOJI_PROMOTE"),
    "REFERRAL": ("Referral", "\U0001f517 Referral", "dashboard_referral", "EMOJI_REFERRAL"),
    "REDEEM_CODE": ("Redeem Code", "\U0001f39f\ufe0f Redeem Code", "dashboard_redeem_promo", "EMOJI_REDEEM"),
    "LEADERBOARD": ("Leaderboard", "\U0001f3c6 Leaderboard", "dashboard_leaderboard", "EMOJI_TROPHY"),
}

DEFAULT_DASHBOARD_LAYOUT = (
    "Send Gift\n"
    "Deposit - Balance\n"
    "Tasks - Promote Channel\n"
    "Referral - Redeem Code\n"
    "Leaderboard"
)


def parse_dashboard_layout(layout_text: str):
    rows = []
    for raw_line in (layout_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"\s*-\s*|\s*\|\s*", line) if p.strip()]
        if not parts:
            continue
        row_keys = []
        for part in parts:
            key = resolve_button_style_key(part)
            if not key or key not in DASHBOARD_BUTTONS:
                raise ValueError(f"Unknown main menu button: '{part}'")
            row_keys.append(key)
        rows.append(row_keys)
    if not rows:
        raise ValueError("Layout cannot be empty.")
    return rows


def get_dashboard_layout_text() -> str:
    try:
        val = get_setting("dashboard_layout", DEFAULT_DASHBOARD_LAYOUT).strip()
        return val if val else DEFAULT_DASHBOARD_LAYOUT
    except Exception:
        return DEFAULT_DASHBOARD_LAYOUT


def get_parsed_dashboard_layout():
    raw = get_dashboard_layout_text()
    try:
        return parse_dashboard_layout(raw)
    except Exception:
        return parse_dashboard_layout(DEFAULT_DASHBOARD_LAYOUT)


def feature_enabled(name):
    return get_setting(f"gift_enabled_{name}", "1") == "1"


def is_banned(user_id):
    return db.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,)).fetchone() is not None


# ============================================================
# DATABASE MIGRATION
# ============================================================
#
# Older versions used:
#
#     balance INTEGER
#
# New version still keeps that column but interprets it as
# half-Star units.
#
# Existing old balances were whole Stars. Therefore we migrate
# them once by multiplying by 2.
#
# ============================================================

def ensure_default_admins():
    for aid in ADMIN_IDS:
        db.execute(
            "INSERT OR IGNORE INTO bot_admins(user_id, added_by, created_at) VALUES(?, ?, ?)",
            (aid, 0, now()),
        )
    db.commit()


def get_all_admin_ids():
    rows = db.execute("SELECT user_id FROM bot_admins").fetchall()
    admins = {int(r["user_id"]) for r in rows}
    return admins.union(ADMIN_IDS)


def is_admin(user_id: int):
    return user_id in get_all_admin_ids()


def migrate_old_balances():
    marker_exists = db.execute(
        """
        SELECT 1
        FROM transactions
        WHERE type = 'system_migration'
        LIMIT 1
        """
    ).fetchone()

    if marker_exists:
        return

    rows = db.execute(
        """
        SELECT user_id, balance
        FROM users
        """
    ).fetchall()

    if not rows:
        return

    try:
        db.execute("BEGIN IMMEDIATE")

        for row in rows:
            old_balance = int(row["balance"])

            db.execute(
                """
                UPDATE users
                SET balance = ?
                WHERE user_id = ?
                """,
                (
                    old_balance * UNITS_PER_STAR,
                    row["user_id"],
                ),
            )

        db.execute(
            """
            INSERT INTO transactions (
                user_id,
                amount,
                type,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                0,
                0,
                "system_migration",
                "Converted old whole-Star balances to half-Star units",
                now(),
            ),
        )

        db.commit()

        logger.info(
            "Old balance migration completed."
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Balance migration failed."
        )


# ============================================================
# FSM
# ============================================================

class GiftStates(StatesGroup):
    waiting_recipient = State()
    waiting_description = State()
    selecting_gift = State()
    confirmation = State()
    waiting_channel = State()
    waiting_channel_description = State()
    selecting_channel_gift = State()
    channel_confirmation = State()


class DepositStates(StatesGroup):
    waiting_amount = State()


class ForceStates(StatesGroup):
    waiting_chat_id = State()


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_user_id = State()
    waiting_balance_amount = State()
    waiting_promo_create = State()
    waiting_gift_price = State()
    waiting_referral_reward = State()
    waiting_var_banner = State()
    waiting_var_logs = State()
    waiting_var_vouch = State()
    waiting_var_emoji = State()
    waiting_var_heading = State()
    waiting_var_btn_color = State()
    waiting_var_btn_layout = State()
    waiting_admin_add = State()
    waiting_admin_remove = State()


class PromoStates(StatesGroup):
    waiting_code = State()


class ChannelPromoStates(StatesGroup):
    waiting_channel = State()
    waiting_description = State()
    waiting_credits = State()
    waiting_topup = State()


# ============================================================
# TIME
# ============================================================

def now():
    return datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ============================================================
# HTML
# ============================================================

def esc(value):
    return html.escape(str(value or ""))


# ============================================================
# BALANCE HELPERS
# ============================================================

def units_to_text(units: int) -> str:
    """
    Converts internal half-Star units into readable Stars.

    30 -> 15
    31 -> 15.5
    """

    units = int(units)

    if units < 0:
        return "-" + units_to_text(-units)

    if units % 2 == 0:
        return str(units // 2)

    return f"{units // 2}.5"


def stars_to_units(stars: int) -> int:
    return int(stars) * UNITS_PER_STAR


def get_balance_units(user_id: int) -> int:
    row = db.execute(
        """
        SELECT balance
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if not row:
        return 0

    return int(row["balance"])


def get_balance_stars(user_id: int) -> str:
    return units_to_text(
        get_balance_units(user_id)
    )


# ============================================================
# USER
# ============================================================

def ensure_user(user):
    if not user:
        return

    db.execute(
        """
        INSERT INTO users (
            user_id,
            username,
            first_name,
            balance,
            created_at
        )
        VALUES (?, ?, ?, 0, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
        """,
        (
            user.id,
            user.username or "",
            user.first_name or "",
            now(),
        ),
    )

    db.commit()


def user_has_started(user_id: int) -> bool:
    row = db.execute(
        """
        SELECT user_id
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    return row is not None


# ============================================================
# REFERRAL
# ============================================================

def create_referral(
    referred_user_id: int,
    referrer_user_id: int,
):
    if referred_user_id == referrer_user_id:
        return

    if not user_has_started(referrer_user_id):
        return

    existing = db.execute(
        """
        SELECT referred_user_id
        FROM referrals
        WHERE referred_user_id = ?
        """,
        (referred_user_id,),
    ).fetchone()

    if existing:
        return

    db.execute(
        """
        INSERT INTO referrals (
            referred_user_id,
            referrer_user_id,
            rewarded,
            created_at
        )
        VALUES (?, ?, 0, ?)
        """,
        (
            referred_user_id,
            referrer_user_id,
            now(),
        ),
    )

    db.commit()


def reward_referral_if_eligible(
    referred_user_id: int,
):
    """
    Referral is rewarded only after the referred user
    successfully passes force-join verification.
    """

    try:
        db.execute("BEGIN IMMEDIATE")

        referral = db.execute(
            """
            SELECT *
            FROM referrals
            WHERE referred_user_id = ?
              AND rewarded = 0
            """,
            (referred_user_id,),
        ).fetchone()

        if not referral:
            db.rollback()
            return None

        referrer_id = int(
            referral["referrer_user_id"]
        )

        if not user_has_started(referrer_id):
            db.rollback()
            return None

        db.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
            """,
            (
                REFERRAL_REWARD_UNITS,
                referrer_id,
            ),
        )

        db.execute(
            """
            INSERT INTO transactions (
                user_id,
                amount,
                type,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                referrer_id,
                REFERRAL_REWARD_UNITS,
                "referral",
                f"Referral reward: {units_to_text(REFERRAL_REWARD_UNITS)} \u2b50",
                now(),
            ),
        )

        db.execute(
            """
            UPDATE referrals
            SET rewarded = 1
            WHERE referred_user_id = ?
            """,
            (referred_user_id,),
        )

        db.commit()

        return referrer_id

    except Exception:
        db.rollback()
        logger.exception(
            "Referral reward failed."
        )
        return None


# ============================================================
# DEPOSIT PRICING
# ============================================================

def calculate_deposit_charge(
    credit_amount: int,
):
    """
    User enters how much they want credited.

    2-20:
        +1 \u2b50

    21-49:
        +2 \u2b50

    50+:
        +5%, rounded UP.

    Returns:
        invoice_amount, fee
    """

    if credit_amount < MIN_DEPOSIT_STARS:
        raise ValueError(
            f"Minimum deposit is {MIN_DEPOSIT_STARS} \u2b50."
        )

    if credit_amount <= 20:
        fee = 1

    elif credit_amount < 50:
        fee = 2

    else:
        fee = math.ceil(
            credit_amount * 0.05
        )

    return (
        credit_amount + fee,
        fee,
    )


# ============================================================
# GIFT PRICING
# ============================================================

def calculate_gift_fee(gift_price: int):
    # Kept as a compatibility helper for older calculation paths.
    # Gift transaction fees are fully disabled.
    return 0


def calculate_gift_total(
    gift_price: int,
):
    fee = calculate_gift_fee(
        gift_price
    )

    return (
        gift_price + fee,
        fee,
    )





# ============================================================
# GIFT HELPERS
# ============================================================

def safe_name(text):
    if not text:
        return "Telegram User"

    return str(text)[:100]


def get_gift_emoji(gift):
    try:
        return gift.sticker.emoji or ""
    except Exception:
        return ""


def is_teddy(gift):
    return "\U0001f9f8" in get_gift_emoji(gift)


def is_love(gift):
    emoji = get_gift_emoji(gift)

    love_emojis = (
        "\u2764\ufe0f",
        "\u2764",
        "\U0001f495",
        "\U0001f497",
        "\U0001f496",
        "\U0001f493",
        "\U0001f49e",
        "\U0001f498",
        "\U0001f49d",
        "\U0001f49f",
    )

    return any(
        x in emoji
        for x in love_emojis
    )


def extract_text_and_entities(message: Message):
    """Extract stripped text and UTF-16 offset-adjusted entities (including custom_emoji)."""
    raw_text = message.text or ""
    stripped = raw_text.strip()
    if not stripped:
        return "", []

    lstrip_chars = len(raw_text) - len(raw_text.lstrip())
    leading_utf16 = len(raw_text[:lstrip_chars].encode("utf-16-le")) // 2
    stripped_utf16_len = len(stripped.encode("utf-16-le")) // 2

    serialized = []
    for ent in (message.entities or []):
        new_offset = int(ent.offset) - leading_utf16
        length = int(ent.length)
        if new_offset < 0 or (new_offset + length) > stripped_utf16_len:
            continue
        item = {
            "type": str(ent.type),
            "offset": new_offset,
            "length": length,
        }
        if getattr(ent, "custom_emoji_id", None):
            item["custom_emoji_id"] = str(ent.custom_emoji_id)
        if getattr(ent, "url", None):
            item["url"] = str(ent.url)
        if getattr(ent, "language", None):
            item["language"] = str(ent.language)
        serialized.append(item)

    return stripped, serialized


def deserialize_entities(serialized_entities):
    if not serialized_entities:
        return []
    entities = []
    for item in serialized_entities:
        try:
            entities.append(MessageEntity(**item))
        except Exception:
            logger.warning("Skipping invalid entity payload: %s", item)
    return entities


def render_description_html(text: str, serialized_entities) -> str:
    """Render description HTML with <tg-emoji> tags for preview messages."""
    if not text:
        return ""
    custom_spans = [
        e for e in (serialized_entities or [])
        if e.get("type") == "custom_emoji" and e.get("custom_emoji_id")
    ]
    if not custom_spans:
        return esc(text)

    custom_spans.sort(key=lambda x: int(x["offset"]))
    utf16 = text.encode("utf-16-le")
    total_units = len(utf16) // 2
    cursor = 0
    out = []
    for span in custom_spans:
        off = int(span["offset"])
        ln = int(span["length"])
        if off < cursor or off + ln > total_units:
            continue
        if off > cursor:
            plain_chunk = utf16[cursor * 2 : off * 2].decode("utf-16-le", errors="ignore")
            out.append(esc(plain_chunk))
        emoji_chunk = utf16[off * 2 : (off + ln) * 2].decode("utf-16-le", errors="ignore")
        cid = esc(span["custom_emoji_id"])
        out.append(f'<tg-emoji emoji-id="{cid}">{esc(emoji_chunk)}</tg-emoji>')
        cursor = off + ln
    if cursor < total_units:
        tail = utf16[cursor * 2 :].decode("utf-16-le", errors="ignore")
        out.append(esc(tail))
    return "".join(out)


def is_gift_sold_out(gift) -> bool:
    if bool(getattr(gift, "is_limited", False)):
        rem = getattr(gift, "remaining_count", None)
        if rem is not None and int(rem) <= 0:
            return True
    return False


GIFT_EMOJI_NAME_MAP = {
    "🧸": "Teddy",
    "💝": "Love",
    "❤️": "Love",
    "❤": "Love",
    "💕": "Love",
    "💗": "Love",
    "💖": "Love",
    "💓": "Love",
    "💞": "Love",
    "💘": "Love",
    "💟": "Love",
    "💌": "Love Letter",
    "🌹": "Rose",
    "🎁": "Gift Box",
    "🎀": "Gift Box",
    "🎂": "Cake",
    "💐": "Bouquet",
    "🍾": "Champagne",
    "🚀": "Rocket",
    "🏆": "Trophy",
    "💍": "Ring",
    "💎": "Diamond",
    "🎩": "Top Hat",
    "👜": "Handbag",
    "👠": "High Heel",
    "👑": "Crown",
    "🔮": "Crystal Ball",
    "🧿": "Evil Eye",
    "🎃": "Pumpkin",
    "🎄": "Christmas Tree",
    "🎅": "Santa Hat",
    "⛄": "Snowman",
    "❄️": "Snowflake",
    "🍭": "Lollipop",
    "🍬": "Candy",
    "🍫": "Chocolate",
    "🍪": "Cookie",
    "🧁": "Cupcake",
    "🍰": "Shortcake",
    "🍦": "Ice Cream",
    "🥂": "Cheers",
    "🍷": "Wine",
    "🍸": "Cocktail",
    "☕": "Coffee",
    "🌸": "Cherry Blossom",
    "🌺": "Hibiscus",
    "🌻": "Sunflower",
    "🌷": "Tulip",
    "🍀": "Clover",
    "⭐": "Star",
    "🌟": "Star",
    "🔥": "Fire",
    "⚡": "Lightning",
    "🌈": "Rainbow",
    "🎈": "Balloon",
    "🎉": "Party Popper",
    "🎊": "Confetti Ball",
    "🕯️": "Candle",
    "🪔": "Diya Lamp",
    "🏮": "Lantern",
    "🎭": "Masks",
    "🎨": "Palette",
    "🎸": "Guitar",
    "🎧": "Headphones",
    "🎮": "Gamepad",
    "🎯": "Bullseye",
    "🏅": "Medal",
    "🥇": "Medal",
    "⌚": "Watch",
    "🕶️": "Sunglasses",
    "🧳": "Luggage",
    "🚗": "Car",
    "✈️": "Airplane",
    "🛸": "UFO",
    "🪐": "Planet",
    "🌙": "Moon",
    "☀️": "Sun",
    "🐱": "Cat",
    "🐶": "Dog",
    "🐰": "Rabbit",
    "🦊": "Fox",
    "🦁": "Lion",
    "🦄": "Unicorn",
    "🐉": "Dragon",
    "🦋": "Butterfly",
    "🕊️": "Dove",
    "🦅": "Eagle",
    "🦉": "Owl",
    "🐧": "Penguin",
    "🐸": "Frog",
    "🐍": "Snake",
    "🐢": "Turtle",
    "🐙": "Octopus",
    "🐳": "Whale",
    "🐬": "Dolphin",
    "🦈": "Shark",
    "🐝": "Bee",
    "🐞": "Ladybug",
    "💀": "Skull",
    "👻": "Ghost",
    "🤖": "Robot",
    "👽": "Alien",
    "🗿": "Moai",
    "🗽": "Statue",
    "🗼": "Tower",
    "🏰": "Castle",
    "🔑": "Key",
    "🗝️": "Old Key",
    "🔒": "Lock",
    "🛡️": "Shield",
    "⚔️": "Swords",
    "🪄": "Magic Wand",
    "💄": "Lipstick",
    "🧢": "Cap",
    "🎓": "Graduation Cap",
    "🎒": "Backpack",
    "💼": "Briefcase",
    "👛": "Purse",
    "🪩": "Disco Ball",
    "🪬": "Hamsa",
    "🪷": "Lotus",
    "🫧": "Bubbles",
}

GIFT_SLUG_DISPLAY_MAP = {
    "teddy": "🧸 Teddy",
    "love": "💝 Love",
    "rose": "🌹 Rose",
    "gift_box": "🎀 Gift Box",
    "cake": "🎂 Cake",
    "bouquet": "💐 Bouquet",
    "champagne": "🍾 Champagne",
    "rocket": "🚀 Rocket",
    "trophy": "🏆 Trophy",
    "ring": "💍 Ring",
    "diamond": "💎 Diamond",
}


def normalize_gift_display_emoji(raw_emoji: str) -> str:
    em = (raw_emoji or "").strip()
    if not em or em == "🎁":
        return "🎀"
    return em


def resolve_gift_name_from_emoji(raw_emoji: str) -> str:
    em = (raw_emoji or "").strip()
    if not em:
        return "Gift Box"
    if em in GIFT_EMOJI_NAME_MAP:
        return GIFT_EMOJI_NAME_MAP[em]
    stripped = em.replace("️", "")
    if stripped in GIFT_EMOJI_NAME_MAP:
        return GIFT_EMOJI_NAME_MAP[stripped]
    for ch in em:
        if ord(ch) > 127 and ch not in ("️", "‍"):
            try:
                uname = unicodedata.name(ch, "").strip()
                if uname:
                    return uname.title()
            except Exception:
                pass
    return "Gift"


def format_gift_display_name(gift) -> str:
    raw_emoji = get_gift_emoji(gift) or "🎁"
    disp_emoji = normalize_gift_display_emoji(raw_emoji)
    api_title = getattr(gift, "title", None) or getattr(gift, "name", None)
    if api_title and str(api_title).strip():
        return f"{disp_emoji} {str(api_title).strip()}"
    name = resolve_gift_name_from_emoji(raw_emoji)
    return f"{disp_emoji} {name}"


def get_gift_type_slug(gift) -> str:
    raw_emoji = get_gift_emoji(gift) or "🎁"
    name = resolve_gift_name_from_emoji(raw_emoji)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or f"gift_{gift.id}"


def format_stored_gift_type(gift_type_raw: str) -> str:
    gtype = gift_type_raw or ""
    is_ch = gtype.startswith("channel_")
    base = gtype.removeprefix("channel_")
    label = GIFT_SLUG_DISPLAY_MAP.get(base)
    if not label:
        pretty = base.replace("_", " ").strip().title() or "Gift"
        label = f"🎁 {pretty}"
    if is_ch:
        label += " (Channel)"
    return label


def is_gift_id_enabled(gift_id: str, emoji: str = "") -> bool:
    val = get_setting(f"gift_enabled_id_{gift_id}", "")
    if val in ("0", "1"):
        return val == "1"
    if "🧸" in (emoji or "") and get_setting("gift_enabled_teddy", "") in ("0", "1"):
        return get_setting("gift_enabled_teddy") == "1"
    if any(x in (emoji or "") for x in ("❤", "💕", "💗", "💖", "💓", "💞", "💘", "💝", "💟")):
        if get_setting("gift_enabled_love", "") in ("0", "1"):
            return get_setting("gift_enabled_love") == "1"
    return True


def get_cached_gifts():
    raw = get_setting("cached_available_gifts", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def get_available_real_gifts():
    result = await bot.get_available_gifts()
    return result.gifts


async def refresh_available_gifts_cache():
    gifts = await get_available_real_gifts()
    items = []
    for g in gifts:
        if is_gift_sold_out(g):
            continue
        gid = str(g.id)
        raw_emoji = get_gift_emoji(g) or "🎁"
        emoji = normalize_gift_display_emoji(raw_emoji)
        star_count = int(g.star_count)
        is_lim = bool(getattr(g, "is_limited", False))
        rem = getattr(g, "remaining_count", None)
        if get_setting(f"gift_enabled_id_{gid}", "") not in ("0", "1"):
            default_enabled = "1" if is_gift_id_enabled(gid, emoji) else "0"
            set_setting(f"gift_enabled_id_{gid}", default_enabled)
        items.append({
            "id": gid,
            "emoji": emoji,
            "star_count": star_count,
            "is_limited": is_lim,
            "remaining_count": int(rem) if rem is not None else None,
        })
    items.sort(key=lambda x: (x["star_count"], x["id"]))
    set_setting("cached_available_gifts", json.dumps(items, ensure_ascii=False))
    set_setting("cached_gifts_updated_at", now())
    return items


async def get_enabled_real_gifts(channel_only: bool = False):
    gifts = await get_available_real_gifts()
    enabled = []
    for g in gifts:
        if is_gift_sold_out(g):
            continue
        if channel_only and bool(getattr(g, "is_limited", False)):
            continue
        gid = str(g.id)
        emoji = get_gift_emoji(g) or ""
        if is_gift_id_enabled(gid, emoji):
            enabled.append(g)
    enabled.sort(key=lambda g: (int(g.star_count), str(g.id)))
    return enabled


async def find_gift_by_id(gift_id: str, channel_only: bool = False):
    gifts = await get_available_real_gifts()
    for g in gifts:
        if str(g.id) != str(gift_id):
            continue
        if is_gift_sold_out(g):
            return None
        if channel_only and bool(getattr(g, "is_limited", False)):
            return None
        if not is_gift_id_enabled(str(g.id), get_gift_emoji(g) or ""):
            return None
        return g
    return None


def dynamic_gift_keyboard(gifts, prefix: str = "gift_id"):
    kb = InlineKeyboardBuilder()
    for g in gifts:
        disp = format_gift_display_name(g)
        stars = int(g.star_count)
        add_inline_button(
            kb,
            f"{disp} • {stars} ⭐",
            f"{prefix}:{g.id}",
            "primary",
        )
    add_inline_button(kb, "❌ Cancel", "gift_cancel", "danger", EMOJI_CANCEL)
    if len(gifts) > 6:
        rows = [2] * (len(gifts) // 2)
        if len(gifts) % 2:
            rows.append(1)
        rows.append(1)
        kb.adjust(*rows)
    else:
        kb.adjust(1)
    return kb.as_markup()


# ============================================================
# BUTTON HELPER
# ============================================================

def add_inline_button(
    builder,
    text,
    callback_data,
    style="primary",
    emoji_id=None,
):
    kwargs = {
        "text": text,
        "callback_data": callback_data,
        "style": style,
    }

    for emoji, custom_id in CUSTOM_EMOJI_IDS.items():
        if text.startswith(emoji):
            if not emoji_id:
                emoji_id = custom_id
            # The custom emoji is rendered as the button icon, so remove
            # its plain Unicode copy from the button label to avoid duplicates.
            text = text[len(emoji):].lstrip()
            kwargs["text"] = text
            break

    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id

    builder.button(**kwargs)


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_keyboard(user_id=None):
    kb = InlineKeyboardBuilder()
    rows = get_parsed_dashboard_layout()
    row_sizes = []
    for row_keys in rows:
        count = 0
        for bkey in row_keys:
            if bkey not in DASHBOARD_BUTTONS:
                continue
            _, label, cb_data, emoji_var = DASHBOARD_BUTTONS[bkey]
            style = get_button_style(bkey)
            emoji_id = globals().get(emoji_var)
            add_inline_button(kb, label, cb_data, style, emoji_id)
            count += 1
        if count > 0:
            row_sizes.append(count)
    if row_sizes:
        kb.adjust(*row_sizes)
    return kb.as_markup()


def submenu_back_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(1)
    return kb.as_markup()


def wallet_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "📜 History", "wallet_history:0", get_button_style("HISTORY"), EMOJI_HISTORY)
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(1, 1)
    return kb.as_markup()


def promo_menu_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\U0001f4e2 Promote Channel / Group", "channelpromo_begin", get_button_style("PROMOTE_MY_CHANNEL"))
    add_inline_button(kb, "\U0001f4b3 Add Promo Stars", "channelpromo_topup", get_button_style("ADD_PROMO_STARS"))
    add_inline_button(kb, "\U0001f4b0 Promo Balance", "channelpromo_wallet", get_button_style("PROMO_BALANCE"))
    add_inline_button(kb, "\U0001f4ca My Promotions", "channelpromo_my", "primary", EMOJI_STATS)
    add_inline_button(kb, "\u2b05\ufe0f Main Menu", "dashboard_home", get_button_style("BACK_MENU"))
    kb.adjust(1, 2, 1, 1)
    return kb.as_markup()


def gift_menu_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\U0001f464 Send to User", "giftmenu_user", get_button_style("SEND_USER"))
    add_inline_button(kb, "\U0001f381 Send to Myself", "giftmenu_self", get_button_style("SEND_SELF"))
    add_inline_button(kb, "\U0001f4e2 Send to Channel", "giftmenu_channel", get_button_style("SEND_CHANNEL"))
    add_inline_button(kb, "\u2b05\ufe0f Main Menu", "dashboard_home", get_button_style("BACK_MENU"))
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def admin_keyboard():
    kb = InlineKeyboardBuilder()
    buttons = [
        ("\U0001f464 Users", "admin_users", "primary", EMOJI_ADMIN),
        ("\U0001f4b3 Payments", "admin_payments", "primary", EMOJI_HISTORY),
        ("\U0001f381 Gifts", "admin_gifts", "primary", EMOJI_GIFT),
        ("\U0001f381 Edit Gifts", "admin_edit_gifts", "success", EMOJI_GIFT),
        ("\U0001f4ca Statistics", "admin_stats", "success", EMOJI_STATS),
        ("\U0001f6e1\ufe0f Security", "admin_security", "primary", EMOJI_SECURITY),
        ("\U0001f39f\ufe0f Promo Codes", "admin_promos", "primary", EMOJI_REDEEM),
        ("\U0001f4e2 Broadcast", "admin_broadcast", "primary", EMOJI_PROMOTE),
        ("\u2699\ufe0f Settings", "admin_settings", "primary", EMOJI_SETTINGS),
        ("\U0001f527 Change Variables", "admin_variables", "primary", EMOJI_MAINTENANCE),
        ("\U0001f48e VIP Users", "admin_vip", "primary", EMOJI_VIP),
        ("\U0001f4dc Admin Logs", "admin_logs", "primary", EMOJI_LOGS),
        ("\U0001f4e2 Force Join", "admin_force", "success", EMOJI_FORCE),
        ("\U0001f451 Admins", "admin_manage_admins", "primary", EMOJI_ADMIN),
        ("\u2b05\ufe0f User Menu", "dashboard_home", "danger", EMOJI_BACK),
    ]
    for label, data, style, emoji in buttons:
        add_inline_button(kb, label, data, style, emoji)
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_submenu_back_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u2b05\ufe0f Back", "admin_home", "danger", EMOJI_BACK)
    kb.adjust(1)
    return kb.as_markup()


# ============================================================
# FORCE JOIN KEYBOARD
# ============================================================

def force_join_keyboard(rows):
    kb = InlineKeyboardBuilder()

    for row in rows:
        title = row["title"]

        if len(title) > 35:
            title = title[:35]

        add_inline_button(
            kb,
            f"\U0001f4e2 {title}",
            f"force_open:{row['chat_id']}",
            "primary",
        )

    add_inline_button(
        kb,
        "\u2705 Verify Join",
        "force_verify",
        "success",
        EMOJI_VERIFY,
    )

    kb.adjust(1)

    return kb.as_markup()


# ============================================================
# RECIPIENT KEYBOARD
# ============================================================

def recipient_keyboard():
    select_btn = KeyboardButton(
        text="\U0001f464 Select Telegram User",
        style="primary",
        request_user={
            "request_id": 1,
            "user_is_bot": False,
        },
    )
    cancel_btn = KeyboardButton(
        text="\u274c Cancel",
        style="danger",
    )

    return ReplyKeyboardMarkup(
        keyboard=[
            [select_btn],
            [cancel_btn],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=(
            "Select recipient..."
        ),
    )


# ============================================================
# GIFT KEYBOARD
# ============================================================

def gift_keyboard(
    teddy_available,
    love_available,
):
    kb = InlineKeyboardBuilder()

    if teddy_available:
        add_inline_button(
            kb,
            f"\U0001f9f8 Teddy \u2022 {GIFT_PRICE_STARS} \u2b50",
            "gift:teddy",
            "primary",
            EMOJI_TEDDY,
        )

    if love_available:
        add_inline_button(
            kb,
            f"\u2764\ufe0f Love \u2022 {GIFT_PRICE_STARS} \u2b50",
            "gift:love",
            "primary",
            EMOJI_LOVE,
        )

    add_inline_button(
        kb,
        "\u274c Cancel",
        "gift_cancel",
        "danger",
        EMOJI_CANCEL,
    )

    kb.adjust(1)

    return kb.as_markup()


# ============================================================
# CONFIRM KEYBOARD
# ============================================================

def confirm_keyboard():
    kb = InlineKeyboardBuilder()

    add_inline_button(
        kb,
        "\u2705 Confirm & Send",
        "gift_confirm",
        get_button_style("CONFIRM_SEND"),
        EMOJI_CONFIRM,
    )

    add_inline_button(
        kb,
        "\u274c Cancel",
        "gift_cancel",
        get_button_style("CANCEL"),
        EMOJI_CANCEL,
    )

    kb.adjust(1)

    return kb.as_markup()


# ============================================================
# FORCE JOIN DATABASE
# ============================================================

def get_force_channels():
    return db.execute(
        """
        SELECT *
        FROM force_join
        ORDER BY created_at ASC
        """
    ).fetchall()


def get_force_channel(chat_id):
    return db.execute(
        """
        SELECT *
        FROM force_join
        WHERE chat_id = ?
        """,
        (chat_id,),
    ).fetchone()


def remove_force_channel(chat_id):
    db.execute(
        """
        DELETE FROM force_join
        WHERE chat_id = ?
        """,
        (chat_id,),
    )

    db.commit()


# ============================================================
# FORCE JOIN CHECK
# ============================================================

async def get_missing_force_channels(
    user_id: int,
):
    rows = get_force_channels()
    if not rows:
        return []

    missing = []
    for row in rows:
        chat_id = int(row["chat_id"])

        try:
            member = await bot.get_chat_member(
                chat_id=chat_id,
                user_id=user_id,
            )

            status = member.status

            if status in (
                "creator",
                "administrator",
                "member",
            ):
                continue

            if (
                status == "restricted"
                and getattr(
                    member,
                    "is_member",
                    False,
                )
            ):
                continue

            missing.append(row)

        except Exception as e:
            logger.warning(
                "Force join check failed "
                "chat=%s user=%s error=%s",
                chat_id,
                user_id,
                e,
            )

            if await bot_can_manage_chat(
                chat_id
            ) is False:
                await remove_force_channel_with_log(
                    chat_id,
                    "Bot can no longer access/manage this chat.",
                )
            else:
                missing.append(row)

    return missing


async def user_joined_force_channels(
    user_id: int,
):
    if is_admin(user_id):
        return True
    missing = await get_missing_force_channels(user_id)
    return len(missing) == 0


def admin_force_only_keyboard(force_rows):
    kb = InlineKeyboardBuilder()
    for row in force_rows:
        label = (row["title"] or "Required Channel")[:35]
        link = row["invite_link"] or (
            f"https://t.me/{row['username']}"
            if "username" in row.keys() and row["username"]
            else None
        )
        if link:
            kb.button(text=label, url=link, icon_custom_emoji_id=EMOJI_FORCE)
        else:
            kb.button(
                text=label,
                callback_data=f"force_open:{row['chat_id']}",
                icon_custom_emoji_id=EMOJI_FORCE,
            )
    kb.button(
        text="Verify Join",
        callback_data="admin_force_verify",
        icon_custom_emoji_id=EMOJI_VERIFY,
    )
    kb.adjust(1)
    return kb.as_markup()


async def send_admin_force_gate(chat_id: int, user_id: int) -> bool:
    if is_admin(user_id):
        return False
    missing = await get_missing_force_channels(user_id)
    if not missing:
        return False
    lines = [
        "🔒 <b>Required Channel Join</b>",
        "",
        "You must join all required channels below before using this bot:",
        "",
        "After joining, tap <b>Verify Join</b> to continue.",
    ]
    await bot.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=admin_force_only_keyboard(missing),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return True


async def bot_can_manage_chat(
    chat_id: int,
):
    try:
        me = await bot.get_me()

        member = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=me.id,
        )

        if member.status == "creator":
            return True

        if member.status != "administrator":
            return False

        # For channels/groups, being administrator is enough
        # for this bot's force-join check.
        return True

    except Exception:
        return False


# ============================================================
# REMOVE FORCE JOIN + ADMIN LOG
# ============================================================

async def remove_force_channel_with_log(
    chat_id: int,
    reason: str,
):
    row = get_force_channel(
        chat_id
    )

    if not row:
        return

    title = row["title"]

    remove_force_channel(
        chat_id
    )

    logger.warning(
        "Force join removed: %s (%s) - %s",
        title,
        chat_id,
        reason,
    )

    text = (
        "\u26a0\ufe0f <b>Force Join Removed Automatically</b>\n\n"
        f"\U0001f4e2 Chat: <b>{esc(title)}</b>\n"
        f"\U0001f194 ID: <code>{chat_id}</code>\n"
        f"\U0001f4dd Reason: {esc(reason)}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Could not notify admin %s",
                admin_id,
            )


# ============================================================
# FORCE JOIN MONITOR
# ============================================================

async def force_join_monitor():
    while True:
        try:
            rows = get_force_channels()

            for row in rows:
                chat_id = int(row["chat_id"])

                try:
                    me = await bot.get_me()

                    member = await bot.get_chat_member(
                        chat_id=chat_id,
                        user_id=me.id,
                    )

                    if member.status not in (
                        "administrator",
                        "creator",
                    ):
                        await remove_force_channel_with_log(
                            chat_id,
                            "Bot was demoted or removed.",
                        )

                except Exception as e:
                    logger.warning(
                        "Force monitor error chat=%s: %s",
                        chat_id,
                        e,
                    )

                    # Verify if chat is still accessible.
                    try:
                        await bot.get_chat(
                            chat_id
                        )
                    except Exception:
                        await remove_force_channel_with_log(
                            chat_id,
                            "Bot lost access to the chat.",
                        )

        except Exception:
            logger.exception(
                "Force join monitor error."
            )

        await asyncio.sleep(60)


# ============================================================
# START GATE: ADMIN FORCE-JOIN + PAID CHANNEL PROMOTIONS
# ============================================================

async def get_start_gate_rows(user_id: int):
    force_rows = []
    for force_row in get_force_channels():
        try:
            member = await bot.get_chat_member(int(force_row['chat_id']), user_id)
            is_member = member.status in ("creator", "administrator", "member") or (member.status == "restricted" and getattr(member, "is_member", False))
            if not is_member:
                force_rows.append(force_row)
        except Exception:
            force_rows.append(force_row)
    campaigns = db.execute("SELECT * FROM channel_promotions WHERE status='active' AND credits>0 ORDER BY created_at ASC LIMIT 20").fetchall()
    visible_promos = []
    for row in campaigns:
        seen = db.execute("SELECT 1 FROM promo_verifications WHERE promotion_id=? AND user_id=?", (row['id'], user_id)).fetchone()
        if seen:
            continue
        try:
            member = await bot.get_chat_member(int(row['channel_id']), user_id)
            already_member = member.status in ("creator", "administrator", "member") or (member.status == "restricted" and getattr(member, "is_member", False))
        except Exception:
            # If membership cannot be checked, do not count this user as an eligible impression.
            already_member = True
        db.execute("INSERT INTO promo_gate_eligibility(promotion_id,user_id,eligible,checked_at) VALUES(?,?,?,?) ON CONFLICT(promotion_id,user_id) DO UPDATE SET eligible=excluded.eligible, checked_at=excluded.checked_at", (row['id'], user_id, 0 if already_member else 1, now()))
        if not already_member:
            visible_promos.append(row)
    db.commit()
    return force_rows, visible_promos


def get_promo_join_url(promo):
    link = (promo["invite_link"] or "").strip() if "invite_link" in promo.keys() else ""
    if link:
        return link
    uname = (promo["channel_username"] or "").strip()
    if uname:
        return f"https://t.me/{uname}"
    return None


async def ensure_promo_invite_link(promo) -> str:
    existing = (promo["invite_link"] or "").strip() if "invite_link" in promo.keys() else ""
    if existing:
        return existing
    chat_id = int(promo["channel_id"])
    invite = await bot.create_chat_invite_link(
        chat_id=chat_id,
        name=f"Promo #{promo['id']}",
    )
    new_link = invite.invite_link
    db.execute(
        "UPDATE channel_promotions SET invite_link = ? WHERE id = ?",
        (new_link, int(promo["id"])),
    )
    db.commit()
    return new_link


def start_gate_keyboard(force_rows, promo_rows):
    kb = InlineKeyboardBuilder()
    for row in force_rows:
        label = (row['title'] or 'Required Channel')[:35]
        link = row['invite_link'] or (f"https://t.me/{row['username']}" if 'username' in row.keys() and row['username'] else None)
        if link:
            kb.button(text=label, url=link, icon_custom_emoji_id=EMOJI_FORCE)
        else:
            kb.button(text=label, callback_data=f"force_open:{row['chat_id']}", icon_custom_emoji_id=EMOJI_FORCE)
    for row in promo_rows:
        title = (row['channel_title'] or row['channel_username'] or 'Featured Chat')[:35]
        join_url = get_promo_join_url(row)
        if join_url:
            kb.button(text=title, url=join_url, icon_custom_emoji_id=EMOJI_FORCE)
    kb.button(text="Verify", callback_data="force_verify", icon_custom_emoji_id=EMOJI_VERIFY)
    kb.adjust(1)
    return kb.as_markup()


async def send_start_gate(message: Message):
    force_rows, promo_rows = await get_start_gate_rows(message.from_user.id)
    if not force_rows and not promo_rows:
        return False
    # Ensure every active promotion uses a bot-created invite link
    for row in promo_rows:
        if not (row["invite_link"] or "").strip():
            try:
                await ensure_promo_invite_link(row)
            except Exception:
                logger.warning("Could not lazily create promo invite link for #%s", row["id"])
    _, promo_rows = await get_start_gate_rows(message.from_user.id)
    lines = ["\U0001f512 <b>One quick step before entering</b>", ""]
    if force_rows:
        lines += ["<b>Required channels:</b>", "Join every channel below.", ""]
    if promo_rows:
        lines += ["<b>Featured channels &amp; groups:</b>", "Join via the links below and stay for at least 3 minutes.", ""]
        for row in promo_rows:
            lines.append(f"<b>{esc(row['channel_title'])}</b> — {esc(row['description'])}")
        lines.append("")
    lines.append("After joining, tap <b>Verify</b> to continue.")
    await message.answer("\n".join(lines), reply_markup=start_gate_keyboard(force_rows, promo_rows), parse_mode="HTML", disable_web_page_preview=True)
    return True


async def finalize_completed_promotions():
    candidate_rows = db.execute(
        "SELECT * FROM channel_promotions WHERE credits <= 0 AND status = 'active'"
    ).fetchall()
    if not candidate_rows:
        return

    for promo in candidate_rows:
        promo_id = int(promo["id"])
        pending_cnt = db.execute(
            "SELECT COUNT(*) AS c FROM promo_link_joins WHERE promotion_id = ? AND status = 'pending'",
            (promo_id,),
        ).fetchone()["c"]
        if int(pending_cnt) > 0:
            # Wait until all pending joins finish their 3-minute retention check
            continue

        db.execute(
            "UPDATE channel_promotions SET status = 'completed' WHERE id = ? AND status = 'active'",
            (promo_id,),
        )
        if db.execute("SELECT changes() AS c").fetchone()["c"] != 1:
            continue
        db.commit()

        chat_id = int(promo["channel_id"])
        inv_link = (promo["invite_link"] or "").strip()
        if inv_link:
            try:
                await bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=inv_link)
            except Exception:
                logger.warning("Could not revoke completed promo invite link for promo #%s", promo_id)

        try:
            final_count = int(await bot.get_chat_member_count(chat_id))
        except Exception:
            final_count = 0

        initial_count = int(promo["initial_member_count"] or 0)
        verified_joins = int(promo["verified_joins"] or 0)
        handle_text = f"@{esc(promo['channel_username'])}" if promo["channel_username"] else f"ID <code>{chat_id}</code>"

        vouch_text = (
            f"📢 <b>Promotion Completed!</b> • <b>{esc(promo['channel_title'])}</b> ({handle_text})\n"
            f"✅ <b>{verified_joins}</b> verified 3-min joins delivered via bot link! 🎉"
        )
        await send_vouch_message(vouch_text)

        try:
            owner_msg = (
                f"✅ <b>Your Promotion Is Completed!</b>\n\n"
                f"📢 <b>Chat:</b> {esc(promo['channel_title'])} ({handle_text})\n"
                f"👥 <b>Starting Count:</b> <b>{initial_count}</b>\n"
                f"📈 <b>Current Count:</b> <b>{final_count}</b>\n"
                f"🔗 <b>Verified Joins (3+ min via Bot Link):</b> <b>{verified_joins}</b>\n"
                f"🔒 Bot invite link has been closed."
            )
            await send_text_only(int(promo["user_id"]), owner_msg, parse_mode="HTML")
        except Exception:
            pass


async def complete_start_gate(callback: CallbackQuery):
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Please join all required channels first.", show_alert=True)
        return False
    _, promos = await get_start_gate_rows(callback.from_user.id)
    for promo in promos:
        eligible = db.execute("SELECT eligible FROM promo_gate_eligibility WHERE promotion_id=? AND user_id=?", (promo['id'], callback.from_user.id)).fetchone()
        if not eligible or int(eligible['eligible']) != 1:
            continue
        join_rec = db.execute(
            "SELECT status, source FROM promo_link_joins WHERE promotion_id=? AND user_id=?",
            (promo['id'], callback.from_user.id),
        ).fetchone()
        if join_rec and join_rec["source"] == "other_link":
            await callback.answer("Please join using the button link provided by this bot.", show_alert=True)
            return False
        try:
            member = await bot.get_chat_member(int(promo['channel_id']), callback.from_user.id)
            if member.status not in ("creator", "administrator", "member") and not (member.status == "restricted" and getattr(member, "is_member", False)):
                await callback.answer("Join the featured channels/groups first, then verify.", show_alert=True)
                return False
        except Exception:
            await callback.answer("Could not verify one of the featured chats. Please try again later.", show_alert=True)
            return False
    # Consume a credit only for users who were not members at the initial check.
    ts = now()
    for promo in promos:
        eligible = db.execute("SELECT eligible FROM promo_gate_eligibility WHERE promotion_id=? AND user_id=?", (promo['id'], callback.from_user.id)).fetchone()
        if not eligible or int(eligible['eligible']) != 1:
            continue
        db.execute("INSERT OR IGNORE INTO promo_verifications(promotion_id,user_id,verified_at) VALUES(?,?,?)", (promo['id'], callback.from_user.id, ts))
        if db.execute("SELECT changes() AS c").fetchone()['c'] == 1:
            db.execute("UPDATE channel_promotions SET credits=MAX(credits-1,0) WHERE id=?", (promo['id'],))
        db.execute(
            "INSERT OR IGNORE INTO promo_link_joins(promotion_id, channel_id, user_id, invite_link, joined_at, status, source) "
            "VALUES(?,?,?,?,?,'pending','start_gate')",
            (promo['id'], int(promo['channel_id']), callback.from_user.id, promo['invite_link'] or '', ts),
        )
    db.commit()
    await finalize_completed_promotions()
    referred_by = reward_referral_if_eligible(callback.from_user.id)
    if referred_by:
        await check_and_notify_level_up(referred_by)
        try:
            await bot.send_message(referred_by,
                "\U0001f389 <b>Referral Reward</b>\n\nYour referred user completed channel verification.\n"
                f"\u2b50 Reward: <b>{units_to_text(REFERRAL_REWARD_UNITS)} Stars</b>", parse_mode="HTML")
        except Exception:
            pass
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_main_menu(callback.bot, callback.from_user, callback.message.chat.id)
    await callback.answer("Verified successfully!")
    return True


def build_main_menu_text(user, include_tagline: bool = False) -> str:
    full_name = (
        getattr(user, "full_name", None)
        or getattr(user, "first_name", None)
        or "Telegram User"
    )
    safe_name_html = esc(full_name)
    username = getattr(user, "username", None)
    if username:
        username_line = f"🔗 Username: @{esc(username)}"
    else:
        username_line = f'🔗 Mention: <a href="tg://user?id={user.id}">{safe_name_html}</a>'

    tagline = (
        "\n\nSend real Telegram Gifts directly "
        "through the Bot API."
        if include_tagline
        else ""
    )

    heading_html = esc(get_bot_heading())
    return (
        f"🎁 <b>{heading_html}</b>\n\n"
        f"👤 Name: <b>{safe_name_html}</b>\n"
        f"{username_line}\n"
        f"🆔 ID: <code>{user.id}</code>"
        f"{tagline}\n\n"
        "Choose an option:"
    )


async def show_main_menu(bot_obj, user, chat_id):
    ensure_user(user)
    await bot_obj.send_message(
        chat_id,
        build_main_menu_text(user),
        reply_markup=dashboard_keyboard(user.id),
        parse_mode="HTML",
    )


# ============================================================
# FORCE JOIN MESSAGE
# ============================================================

async def require_force_join(message: Message):
    if is_banned(message.from_user.id):
        await message.answer("\u26d4 Your access to this bot has been restricted.")
        return False
    if get_setting("maintenance", "0") == "1" and not is_admin(message.from_user.id):
        await message.answer("\U0001f527 <b>Bot is under maintenance.</b> Please try again later.", parse_mode="HTML")
        return False
    return not await send_start_gate(message)


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start_handler(
    message: Message,
):
    if is_banned(message.from_user.id):
        await message.answer("\u26d4 Your access to this bot has been restricted.")
        return
    if get_setting("maintenance", "0") == "1" and not is_admin(message.from_user.id):
        await message.answer("\U0001f527 <b>Bot is under maintenance.</b> Please try again later.", parse_mode="HTML")
        return
    is_new_user = not user_has_started(message.from_user.id)
    ensure_user(message.from_user)

    # --------------------------------------------------------
    # Referral from /start ref_123
    # --------------------------------------------------------

    args = (
        message.text or ""
    ).split(maxsplit=1)

    if len(args) == 2:
        parameter = args[1].strip()

        if parameter.startswith("ref_"):
            try:
                referrer_id = int(
                    parameter[4:]
                )

                if (
                    referrer_id
                    != message.from_user.id
                ):
                    create_referral(
                        message.from_user.id,
                        referrer_id,
                    )

            except ValueError:
                pass

    if is_new_user:
        ref_row = db.execute("SELECT referrer_user_id FROM referrals WHERE referred_user_id=?", (message.from_user.id,)).fetchone()
        source = "refer" if ref_row else "search"
        referrer = int(ref_row['referrer_user_id']) if ref_row else None
        db.execute("INSERT OR IGNORE INTO user_sources(user_id,source,referrer_id,created_at) VALUES(?,?,?,?)", (message.from_user.id, source, referrer, now()))
        db.commit()
        await notify_new_user(message.from_user, source, referrer)

    # --------------------------------------------------------
    # Force join ALWAYS checked before normal usage.
    # --------------------------------------------------------

    if not await require_force_join(message):
        return

    # --------------------------------------------------------
    # Referral reward only after force join passes.
    # --------------------------------------------------------

    referrer_id = reward_referral_if_eligible(
        message.from_user.id
    )

    if referrer_id:
        await check_and_notify_level_up(referrer_id)
        try:
            await bot.send_message(
                referrer_id,
                "\U0001f389 <b>Referral Reward</b>\n\n"
                "A referred user completed the "
                "required join verification.\n\n"
                f"\u2b50 You received <b>{units_to_text(REFERRAL_REWARD_UNITS)} \u2b50</b>.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    if len(args) == 2 and args[1].strip().lower() == "tier":
        await message.answer(
            build_tier_info_text(message.from_user),
            reply_markup=submenu_back_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        build_main_menu_text(message.from_user, include_tagline=True),
        reply_markup=dashboard_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


# ============================================================
# FORCE VERIFY
# ============================================================

@dp.callback_query(F.data == "force_verify")
async def force_verify(callback: CallbackQuery):
    await complete_start_gate(callback)


@dp.callback_query(F.data == "admin_force_verify")
async def admin_force_verify(callback: CallbackQuery):
    missing = await get_missing_force_channels(callback.from_user.id)
    if missing:
        await callback.answer(
            "Please join all required channels first.",
            show_alert=True,
        )
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Verified! You can now continue using the bot.", show_alert=True)


@dp.message.outer_middleware()
async def force_join_message_middleware(handler, event: Message, data):
    user = getattr(event, "from_user", None)
    if not user or getattr(event, "successful_payment", None):
        return await handler(event, data)

    if is_banned(user.id):
        await event.answer("⛔ Your access to this bot has been restricted.")
        return

    if get_setting("maintenance", "0") == "1" and not is_admin(user.id):
        await event.answer(
            "🔧 <b>Bot is under maintenance.</b> Please try again later.",
            parse_mode="HTML",
        )
        return

    # Let /start pass through to start_handler so it enforces BOTH
    # admin force-join channels AND promoted channels.
    text = (event.text or "").strip()
    if text == "/start" or text.startswith("/start "):
        return await handler(event, data)

    if not is_admin(user.id):
        if await send_admin_force_gate(event.chat.id, user.id):
            return

    return await handler(event, data)


@dp.callback_query.outer_middleware()
async def force_join_callback_middleware(handler, event: CallbackQuery, data):
    user = getattr(event, "from_user", None)
    if not user:
        return await handler(event, data)

    if is_banned(user.id):
        await event.answer("⛔ Your access to this bot has been restricted.", show_alert=True)
        return

    if get_setting("maintenance", "0") == "1" and not is_admin(user.id):
        await event.answer("🔧 Bot is under maintenance. Please try again later.", show_alert=True)
        return

    cb_data = event.data or ""
    if cb_data in ("force_verify", "admin_force_verify") or cb_data.startswith("force_open:"):
        return await handler(event, data)

    if not is_admin(user.id):
        missing = await get_missing_force_channels(user.id)
        if missing:
            if event.message:
                await send_admin_force_gate(event.message.chat.id, user.id)
            await event.answer(
                "Please join all required channels first.",
                show_alert=True,
            )
            return

    return await handler(event, data)


# ============================================================
# FORCE OPEN
# ============================================================

@dp.callback_query(
    F.data.startswith("force_open:")
)
async def force_open(
    callback: CallbackQuery,
):
    try:
        chat_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except Exception:
        await callback.answer(
            "Invalid chat.",
            show_alert=True,
        )
        return

    row = get_force_channel(
        chat_id
    )

    if not row:
        await callback.answer(
            "This force-join chat no longer exists.",
            show_alert=True,
        )
        return

    link = row["invite_link"]

    if not link:
        await callback.answer(
            "No invite link is configured.",
            show_alert=True,
        )
        return

    # URL button isn't used because callback_data buttons
    # cannot directly open URLs. Send the link separately.
    await callback.message.answer(
        f"\U0001f4e2 <b>{esc(row['title'])}</b>\n\n"
        f"Join here:\n{esc(link)}",
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# BALANCE / WALLET & TIER EXP
# ============================================================

def build_tier_info_text(user) -> str:
    lvl = get_user_level(user.id)
    lvl_emoji = level_to_emoji(lvl)
    exp_units = get_user_exp_units(user.id)
    exp_text = units_to_text(exp_units)

    if lvl < MAX_USER_LEVEL:
        cur_floor = level_min_exp_units(lvl)
        next_target = level_min_exp_units(lvl + 1)
        step_need = level_step_units(lvl)
        in_level_exp = max(0, exp_units - cur_floor)
        remaining_units = max(0, next_target - exp_units)
        progress_block = (
            f"⭐ <b>Current EXP:</b> <b>{exp_text} ⭐</b>\n"
            f"🎯 <b>Next Level ({level_to_emoji(lvl + 1)}):</b> <b>{units_to_text(in_level_exp)} / {units_to_text(step_need)} ⭐</b> "
            f"(<b>{units_to_text(remaining_units)} ⭐</b> left)\n"
        )
    else:
        progress_block = (
            f"⭐ <b>Current EXP:</b> <b>{exp_text} ⭐</b>\n"
            f"🏆 <b>Status:</b> Max Level Reached ({level_to_emoji(MAX_USER_LEVEL)})\n"
        )

    return (
        f"👑 <b>Tier &amp; Level Progress</b>\n\n"
        f"👤 <b>User:</b> {esc(user.first_name or user.full_name or 'User')}\n"
        f"🏅 <b>Current Tier:</b> {lvl_emoji} level\n"
        f"{progress_block}\n"
        f"📌 <b>Level Up Rules:</b>\n"
        f"• Every incoming and outgoing Star activity (<b>Deposit + Spend + Referral + Tasks</b>) counts toward your EXP.\n"
        f"• {level_to_emoji(1)} → {level_to_emoji(2)} requires <b>32 ⭐</b> EXP.\n"
        f"• Each next level requires <b>2x</b> the EXP of the previous level:\n"
        f"  {level_to_emoji(1)}→{level_to_emoji(2)}: <b>32 ⭐</b> | "
        f"{level_to_emoji(2)}→{level_to_emoji(3)}: <b>64 ⭐</b> | "
        f"{level_to_emoji(3)}→{level_to_emoji(4)}: <b>128 ⭐</b>\n"
        f"  {level_to_emoji(4)}→{level_to_emoji(5)}: <b>256 ⭐</b> | "
        f"{level_to_emoji(5)}→{level_to_emoji(6)}: <b>512 ⭐</b> | "
        f"{level_to_emoji(6)}→{level_to_emoji(7)}: <b>1024 ⭐</b>\n"
        f"  {level_to_emoji(7)}→{level_to_emoji(8)}: <b>2048 ⭐</b> | "
        f"{level_to_emoji(8)}→{level_to_emoji(9)}: <b>4096 ⭐</b>"
    )


async def build_wallet_text(user) -> str:
    me = await bot.get_me()
    bot_username = me.username or ""
    lvl = get_user_level(user.id)
    lvl_emoji = level_to_emoji(lvl)
    gift_bal = get_balance_stars(user.id)
    promo_bal = get_promo_balance(user.id)
    display_name = esc(user.first_name or user.full_name or "User")

    if bot_username:
        tier_link = f'<a href="https://t.me/{bot_username}?start=tier">Tier:</a> {lvl_emoji} <a href="https://t.me/{bot_username}?start=tier">level</a>'
    else:
        tier_link = f"Tier: {lvl_emoji} level"

    return (
        "💰 <b>Your Wallet</b>\n"
        f"👤 <b>User:</b> {display_name} • {tier_link}\n"
        f"⭐ <b>Gift Balance:</b> {gift_bal} ⭐\n"
        f"📢 <b>Promo Balance:</b> {promo_bal} ⭐"
    )


@dp.message(Command("balance"))
async def balance_command(
    message: Message,
):
    ensure_user(
        message.from_user
    )

    if not await require_force_join(
        message
    ):
        return

    wallet_text = await build_wallet_text(message.from_user)

    await message.answer(
        wallet_text,
        reply_markup=wallet_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@dp.callback_query(
    F.data == "dashboard_balance"
)
async def dashboard_balance(
    callback: CallbackQuery,
):
    if not await user_joined_force_channels(
        callback.from_user.id
    ):
        await callback.answer(
            "Join required first.",
            show_alert=True,
        )
        return

    ensure_user(
        callback.from_user
    )

    wallet_text = await build_wallet_text(callback.from_user)

    await callback.message.edit_text(
        wallet_text,
        reply_markup=wallet_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


WALLET_HISTORY_PER_PAGE = 6

TX_TYPE_LABELS = {
    "deposit": "💳 Deposit",
    "gift": "🎁 Gift Sent",
    "channel_gift": "📢 Channel Gift",
    "referral": "🔗 Referral Reward",
    "task_reward": "📝 Task Reward",
    "task_penalty": "⚠️ Task Leave Penalty",
    "promo_reward": "🎟️ Promo Redeemed",
    "admin_credit": "👑 Admin Credit",
    "admin_debit": "👑 Admin Debit",
}


def format_user_tx_description(tx_type: str, desc: str) -> str:
    clean = (desc or "").strip()
    if tx_type == "admin_credit":
        return "Manual balance added by admin"
    if tx_type == "admin_debit":
        return "Manual balance deducted by admin"
    if tx_type == "deposit" and ";" in clean:
        clean = clean.split(";", 1)[0].strip()
    elif tx_type in ("gift", "channel_gift") and ";" in clean:
        clean = clean.split(";", 1)[0].strip()
    if len(clean) > 48:
        clean = clean[:45] + "..."
    return clean


def build_wallet_history_view(user_id: int, page: int = 0):
    total = db.execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE user_id = ? AND type != 'system_migration'",
        (user_id,),
    ).fetchone()["c"]
    total_pages = max(1, math.ceil(total / WALLET_HISTORY_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    offset = page * WALLET_HISTORY_PER_PAGE

    rows = db.execute(
        """
        SELECT id, amount, type, description, created_at
        FROM transactions
        WHERE user_id = ? AND type != 'system_migration'
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, WALLET_HISTORY_PER_PAGE, offset),
    ).fetchall()

    cur_bal = get_balance_stars(user_id)
    lines = [
        "📜 <b>Transaction History</b>",
        f"💰 <b>Current Balance:</b> <b>{cur_bal} ⭐</b>",
        "",
    ]

    if not rows:
        lines.append("📭 <i>No transactions found yet.</i>")
    else:
        for r in rows:
            amt = int(r["amount"])
            tx_type = r["type"] or ""
            label = TX_TYPE_LABELS.get(tx_type, f"🧾 {tx_type.replace('_', ' ').title()}")
            if amt > 0:
                amt_str = f"🟢 <b>+{units_to_text(amt)} ⭐</b>"
            elif amt < 0:
                amt_str = f"🔴 <b>-{units_to_text(-amt)} ⭐</b>"
            else:
                amt_str = "⚪ <b>0 ⭐</b>"
            detail = format_user_tx_description(tx_type, r["description"])
            ts = (r["created_at"] or "")[:16]
            detail_part = f"{esc(detail)} • " if detail else ""
            lines.append(
                f"{amt_str} • {label}\n"
                f"   {detail_part}<code>{esc(ts)}</code>"
            )

    kb = InlineKeyboardBuilder()
    row_sizes = []
    if total_pages > 1:
        prev_p = (page - 1) % total_pages
        next_p = (page + 1) % total_pages
        kb.button(text="⬅️ Prev", callback_data=f"wallet_history:{prev_p}", style="primary")
        kb.button(text=f"{page + 1}/{total_pages}", callback_data="wallet_history_noop", style="primary")
        kb.button(text="Next ➡️", callback_data=f"wallet_history:{next_p}", style="primary")
        row_sizes.append(3)

    add_inline_button(kb, "💰 Back to Wallet", "dashboard_balance", "primary", EMOJI_BALANCE)
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    row_sizes.append(2)
    kb.adjust(*row_sizes)

    return "\n".join(lines), kb.as_markup()


@dp.callback_query(F.data.startswith("wallet_history:"))
async def wallet_history_callback(callback: CallbackQuery):
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    ensure_user(callback.from_user)
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        page = 0
    body, markup = build_wallet_history_view(callback.from_user.id, page=page)
    try:
        await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(F.data == "wallet_history_noop")
async def wallet_history_noop(callback: CallbackQuery):
    await callback.answer()


# ============================================================
# REFERRAL
# ============================================================

@dp.callback_query(
    F.data == "dashboard_referral"
)
async def dashboard_referral(
    callback: CallbackQuery,
):
    if not await user_joined_force_channels(
        callback.from_user.id
    ):
        await callback.answer(
            "Join required first.",
            show_alert=True,
        )
        return

    me = await bot.get_me()

    link = (
        f"https://t.me/{me.username}"
        f"?start=ref_{callback.from_user.id}"
    )

    referral_count = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM referrals
        WHERE referrer_user_id = ? AND rewarded = 1
        """,
        (callback.from_user.id,),
    ).fetchone()["total"]

    await callback.message.edit_text(
        "\U0001f517 <b>Refer & Earn</b>\n\n"
        "Invite new users with your personal referral link.\n\n"
        f"\u2b50 Reward per successful referral: <b>{units_to_text(REFERRAL_REWARD_UNITS)} \u2b50</b>\n"
        f"\U0001f465 Successful referrals: <b>{referral_count}</b>\n\n"
        "The reward is credited after the referred user "
        "completes the required force-join verification. "
        "Each new Telegram user can reward only one referrer.\n\n"
        f"<code>{esc(link)}</code>",
        reply_markup=submenu_back_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# DEPOSIT COMMAND
# ============================================================

@dp.message(Command("deposit"))
async def deposit_command(
    message: Message,
    state: FSMContext,
):
    ensure_user(
        message.from_user
    )

    if not await require_force_join(
        message
    ):
        return

    await state.clear()

    await state.set_state(
        DepositStates.waiting_amount
    )

    await message.answer(
        "\U0001f4b3 <b>Deposit Balance</b>\n\n"
        "Enter how many Stars you want "
        "to receive in your internal balance.\n\n"
        f"Minimum: <b>{MIN_DEPOSIT_STARS} \u2b50</b>\n\n"
        "Fee structure:\n"
        "\u2022 2\u201320 \u2b50 \u2192 +1 \u2b50\n"
        "\u2022 21\u201349 \u2b50 \u2192 +2 \u2b50\n"
        "\u2022 50+ \u2b50 \u2192 +5%\n\n"
        "Example:\n"
        "<code>20</code>",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(
    F.data == "dashboard_deposit"
)
async def dashboard_deposit(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not await user_joined_force_channels(
        callback.from_user.id
    ):
        await callback.answer(
            "Join required first.",
            show_alert=True,
        )
        return

    await state.clear()

    await state.set_state(
        DepositStates.waiting_amount
    )

    await callback.message.edit_text(
        "\U0001f4b3 <b>Deposit Balance</b>\n\n"
        "Enter how many Stars you want "
        "to receive in your internal balance.\n\n"
        f"Minimum: <b>{MIN_DEPOSIT_STARS} \u2b50</b>\n\n"
        "Fee structure:\n"
        "\u2022 2\u201320 \u2b50 \u2192 +1 \u2b50\n"
        "\u2022 21\u201349 \u2b50 \u2192 +2 \u2b50\n"
        "\u2022 50+ \u2b50 \u2192 +5%\n\n"
        "Example:\n"
        "<code>20</code>",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# DEPOSIT AMOUNT
# ============================================================

@dp.message(
    DepositStates.waiting_amount
)
async def deposit_amount(
    message: Message,
    state: FSMContext,
):
    if not await require_force_join(
        message
    ):
        await state.clear()
        return

    raw = (
        message.text or ""
    ).strip()

    try:
        credit_amount = int(raw)
    except ValueError:
        await message.answer(
            "\u274c Enter a valid whole number."
        )
        return

    if credit_amount < MIN_DEPOSIT_STARS:
        await message.answer(
            f"\u274c Minimum deposit is "
            f"<b>{MIN_DEPOSIT_STARS} \u2b50</b>.",
            parse_mode="HTML",
        )
        return

    if credit_amount > MAX_DEPOSIT_STARS:
        await message.answer(
            f"\u274c Maximum deposit is "
            f"{MAX_DEPOSIT_STARS} \u2b50.",
        )
        return

    invoice_amount, fee = (
        calculate_deposit_charge(
            credit_amount
        )
    )

    ensure_user(
        message.from_user
    )

    unique_id = uuid.uuid4().hex

    payload = (
        f"deposit:"
        f"{message.from_user.id}:"
        f"{credit_amount}:"
        f"{invoice_amount}:"
        f"{unique_id}"
    )

    await state.clear()

    try:
        await bot.send_invoice(
            chat_id=message.chat.id,
            title="Gift Store Balance",
            description=(
                f"Add {credit_amount} \u2b50 "
                "to your Gift Store balance."
            ),
            payload=payload,
            currency="XTR",
            prices=[
                LabeledPrice(
                    label="Gift Store Balance",
                    amount=invoice_amount,
                )
            ],
        )

        await message.answer(
            "\U0001f4b3 <b>Deposit Invoice</b>\n\n"
            f"\U0001f4b0 Balance credit: "
            f"<b>{credit_amount} \u2b50</b>\n"
            f"\U0001f9fe Fee: <b>{fee} \u2b50</b>\n"
            f"\U0001f4b3 Total payment: "
            f"<b>{invoice_amount} \u2b50</b>",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception(
            "Invoice creation failed."
        )

        await message.answer(
            "\u274c <b>Could not create invoice.</b>\n\n"
            f"<code>{esc(e)}</code>",
            parse_mode="HTML",
        )


# ============================================================
# PRE-CHECKOUT
# ============================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery,
):
    payload = query.invoice_payload

    try:
        parts = payload.split(":")
        if parts[0] == "promowallet" and len(parts) == 4:
            user_id = int(parts[1]); credit_amount = int(parts[2]); invoice_amount = credit_amount
            payment_kind = "promowallet"
        elif parts[0] == "deposit" and len(parts) == 5:
            user_id = int(parts[1]); credit_amount = int(parts[2]); invoice_amount = int(parts[3])
            payment_kind = "deposit"
        else:
            raise ValueError
    except Exception:
        await query.answer(
            ok=False,
            error_message="Invalid payment invoice.",
        )
        return

    if user_id != query.from_user.id:
        await query.answer(
            ok=False,
            error_message=(
                "This invoice belongs to another user."
            ),
        )
        return

    if query.currency != "XTR":
        await query.answer(
            ok=False,
            error_message="Invalid currency.",
        )
        return

    if query.total_amount != invoice_amount:
        await query.answer(
            ok=False,
            error_message="Payment amount mismatch.",
        )
        return

    try:
        if payment_kind == "promowallet":
            if not 1 <= credit_amount <= 100000:
                raise ValueError
            expected_invoice = credit_amount
        else:
            expected_invoice, _ = calculate_deposit_charge(credit_amount)
    except ValueError:
        await query.answer(ok=False, error_message="Invalid payment amount.")
        return

    if expected_invoice != invoice_amount:
        await query.answer(
            ok=False,
            error_message="Invalid invoice.",
        )
        return

    await query.answer(
        ok=True
    )


# ============================================================
# SUCCESSFUL PAYMENT
# ============================================================

@dp.message(
    F.successful_payment
)
async def successful_payment(
    message: Message,
):
    payment = message.successful_payment

    if not payment:
        return

    payload = payment.invoice_payload

    if payload.startswith("promowallet:"):
        try:
            parts = payload.split(":")
            if len(parts) != 4: return
            user_id = int(parts[1]); amount = int(parts[2])
            if user_id != message.from_user.id or int(payment.total_amount) != amount: return
            charge_id = payment.telegram_payment_charge_id
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("SELECT 1 FROM payments WHERE telegram_charge_id=?", (charge_id,)).fetchone()
            if exists:
                db.rollback(); await message.answer("This payment was already credited."); return
            ensure_user(message.from_user)
            db.execute("INSERT INTO promo_wallets(user_id,stars) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET stars=stars+excluded.stars", (user_id, amount))
            db.execute("INSERT INTO payments(user_id,amount,currency,payload,telegram_charge_id,created_at) VALUES(?,?,?,?,?,?)", (user_id, amount, payment.currency, payload, charge_id, now()))
            db.commit()
            await check_and_notify_level_up(user_id)
            await send_activity_log(f"<b>Promo wallet payment received</b>\nUser: <code>{user_id}</code>\nAmount: <b>{amount} XTR Stars</b>")
            await message.answer(f"\u2705 <b>Promo Balance topped up!</b>\nAdded: <b>{amount} Promo Stars</b>\nAvailable Promo Balance: <b>{get_promo_balance(user_id)}</b>", reply_markup=promo_menu_keyboard(), parse_mode="HTML")
        except Exception:
            db.rollback(); logger.exception("Promo wallet credit failed")
            await message.answer("Payment received but Promo Balance could not be updated. Contact admin with your Telegram payment receipt.")
        return

    if not payload.startswith("deposit:"):
        return

    try:
        parts = payload.split(":")

        if len(parts) != 5:
            raise ValueError

        user_id = int(parts[1])
        credit_amount = int(parts[2])
        invoice_amount = int(parts[3])

    except Exception:
        logger.error(
            "Invalid payment payload."
        )
        return

    if user_id != message.from_user.id:
        return

    paid_amount = int(
        payment.total_amount
    )

    # Recalculate expected invoice.
    try:
        expected_invoice, expected_fee = (
            calculate_deposit_charge(
                credit_amount
            )
        )
    except ValueError:
        logger.error(
            "Invalid deposit amount."
        )
        return

    if paid_amount != expected_invoice:
        logger.error(
            "Payment amount mismatch. "
            "paid=%s expected=%s",
            paid_amount,
            expected_invoice,
        )
        return

    if invoice_amount != expected_invoice:
        logger.error(
            "Payload invoice mismatch."
        )
        return

    charge_id = (
        payment.telegram_payment_charge_id
    )

    ensure_user(
        message.from_user
    )

    # --------------------------------------------------------
    # Atomic duplicate protection + credit.
    #
    # IMPORTANT:
    # Only credit_amount goes into the user's balance.
    # The fee is NOT credited.
    # --------------------------------------------------------

    try:
        db.execute(
            "BEGIN IMMEDIATE"
        )

        existing = db.execute(
            """
            SELECT id
            FROM payments
            WHERE telegram_charge_id = ?
            """,
            (charge_id,),
        ).fetchone()

        if existing:
            db.rollback()

            await message.answer(
                "\u26a0\ufe0f This payment was already credited."
            )
            return

        user_row = db.execute(
            """
            SELECT user_id
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if not user_row:
            db.execute(
                """
                INSERT INTO users (
                    user_id,
                    username,
                    first_name,
                    balance,
                    created_at
                )
                VALUES (?, ?, ?, 0, ?)
                """,
                (
                    user_id,
                    message.from_user.username or "",
                    message.from_user.first_name or "",
                    now(),
                ),
            )

        credit_units = stars_to_units(
            credit_amount
        )

        db.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
            """,
            (
                credit_units,
                user_id,
            ),
        )

        db.execute(
            """
            INSERT INTO transactions (
                user_id,
                amount,
                type,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                credit_units,
                "deposit",
                (
                    f"Deposit credit {credit_amount} \u2b50; "
                    f"fee {expected_fee} \u2b50; "
                    f"paid {paid_amount} \u2b50"
                ),
                now(),
            ),
        )

        db.execute(
            """
            INSERT INTO payments (
                user_id,
                amount,
                currency,
                payload,
                telegram_charge_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                credit_amount,
                payment.currency,
                payload,
                charge_id,
                now(),
            ),
        )

        db.commit()
        await check_and_notify_level_up(user_id)
        await send_activity_log(f"<b>Deposit payment received</b>\nUser: <code>{user_id}</code>\nPaid: <b>{paid_amount} XTR Stars</b>\nCredited: <b>{credit_amount} Stars</b>")

    except Exception:
        logger.exception(
            "Payment credit error."
        )

        try:
            db.rollback()
        except Exception:
            pass

        await message.answer(
            "\u26a0\ufe0f <b>Payment received, but your "
            "balance could not be updated automatically.</b>\n\n"
            "Please contact an admin.\n\n"
            "Your payment was recorded by Telegram. "
            "An admin can verify the charge ID.",
            parse_mode="HTML",
        )

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    "\u26a0\ufe0f <b>Payment Credit Error</b>\n\n"
                    f"User: <code>{user_id}</code>\n"
                    f"Requested credit: <b>{credit_amount} \u2b50</b>\n"
                    f"Paid: <b>{paid_amount} \u2b50</b>\n"
                    f"Charge ID:\n"
                    f"<code>{esc(charge_id)}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        return

    balance = get_balance_stars(
        user_id
    )

    await message.answer(
        "\u2705 <b>Deposit Successful</b>\n\n"
        f"\U0001f4b0 Added to balance: "
        f"<b>{credit_amount} \u2b50</b>\n"
        f"\U0001f9fe Fee: <b>{expected_fee} \u2b50</b>\n"
        f"\U0001f4b3 Paid: <b>{paid_amount} \u2b50</b>\n"
        f"\U0001f4b0 New balance: <b>{balance} \u2b50</b>",
        reply_markup=dashboard_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


# ============================================================
# GIFT START
# ============================================================

async def start_gift_flow(
    user,
    state: FSMContext,
    message: Message,
    self_gift=False,
):
    ensure_user(user)

    if not await require_force_join(
        message
    ):
        return

    cached = get_cached_gifts()
    enabled_prices = [
        int(it["star_count"])
        for it in cached
        if is_gift_id_enabled(it["id"], it.get("emoji", ""))
    ]
    if cached and not enabled_prices:
        await message.answer(
            "\u274c <b>No Gifts Available</b>\n\n"
            "All gifts are currently disabled by the admin. Please try again later.",
            reply_markup=dashboard_keyboard(user.id),
            parse_mode="HTML",
        )
        return

    min_gift_price = min(enabled_prices) if enabled_prices else GIFT_PRICE_STARS
    balance_units = get_balance_units(
        user.id
    )

    required_units = stars_to_units(min_gift_price)

    if balance_units < required_units:
        await message.answer(
            "\u274c <b>Insufficient Balance</b>\n\n"
            f"\U0001f4b0 Balance: "
            f"<b>{units_to_text(balance_units)} \u2b50</b>\n"
            f"\U0001f381 Minimum gift price: "
            f"<b>{min_gift_price} \u2b50</b>\n"
            f"\U0001f4b3 Required total: "
            f"<b>{units_to_text(required_units)} \u2b50</b>\n\n"
            "Use Deposit to add balance.",
            reply_markup=dashboard_keyboard(user.id),
            parse_mode="HTML",
        )
        return

    await state.clear()

    if self_gift:
        await state.update_data(
            receiver_id=user.id,
            receiver_username=user.username,
            receiver_name=user.first_name
            or "Telegram User",
            self_gift=True,
        )

        await state.set_state(
            GiftStates.waiting_description
        )

        prompt_text = (
            "\U0001f381 <b>Gift To Myself</b>\n\n"
            "<b>Step 1/3</b>\n\n"
            "Send the message/description "
            "for your gift.\n\n"
            "Maximum: <b>128 characters</b>."
        )
        if getattr(message, "from_user", None) and message.from_user.is_bot:
            await message.edit_text(
                prompt_text,
                reply_markup=user_cancel_keyboard(),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                prompt_text,
                reply_markup=user_cancel_keyboard(),
                parse_mode="HTML",
            )

        return

    await state.set_state(
        GiftStates.waiting_recipient
    )

    await message.answer(
        "\U0001f381 <b>Send Gift</b>\n\n"
        "<b>Step 1/3</b>\n\n"
        "Tap <b>Select Telegram User</b> below to choose who should "
        "receive the gift.\n\n"
        "\u26a0\ufe0f The recipient must have started "
        "this bot at least once.",
        reply_markup=recipient_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# /GIFT
# ============================================================

@dp.message(Command("gift"))
async def gift_command(
    message: Message,
    state: FSMContext,
):
    await start_gift_flow(
        message.from_user,
        state,
        message,
        self_gift=False,
    )


@dp.callback_query(F.data == "dashboard_gift")
async def dashboard_gift_menu(callback: CallbackQuery, state: FSMContext):
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "\U0001f381 <b>Send a Telegram Gift</b>\n\nChoose who should receive your gift:",
        reply_markup=gift_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "giftmenu_user")
async def giftmenu_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_gift_flow(callback.from_user, state, callback.message, self_gift=False)


@dp.callback_query(F.data == "giftmenu_self")
async def giftmenu_self(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_gift_flow(callback.from_user, state, callback.message, self_gift=True)


@dp.callback_query(F.data == "giftmenu_channel")
async def giftmenu_channel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ensure_user(callback.from_user)
    await state.clear()
    await state.set_state(GiftStates.waiting_channel)
    await callback.message.answer(
        "\U0001f4e2 <b>Gift to Public Channel</b>\n\nSend the public channel username, e.g. <code>@mychannel</code>.",
        reply_markup=user_cancel_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "dashboard_home")
async def dashboard_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(callback.from_user)
    await callback.message.edit_text(
        build_main_menu_text(callback.from_user),
        reply_markup=dashboard_keyboard(callback.from_user.id),
        parse_mode="HTML",
    )
    await callback.answer()


# ============================================================
# SELF GIFT BUTTON
# ============================================================

@dp.callback_query(
    F.data == "dashboard_self_gift"
)
async def dashboard_self_gift(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not await user_joined_force_channels(
        callback.from_user.id
    ):
        await callback.answer(
            "Join required first.",
            show_alert=True,
        )
        return

    await start_gift_flow(
        callback.from_user,
        state,
        callback.message,
        self_gift=True,
    )

    await callback.answer()


# ============================================================
# GIFT TO PUBLIC CHANNEL
# ============================================================

async def start_channel_gift_flow(message: Message, state: FSMContext):
    await state.clear()
    if not await require_force_join(message):
        return
    await state.set_state(GiftStates.waiting_channel)
    await message.answer(
        "\U0001f4e2 <b>Gift to Public Channel</b>\n\n"
        "Send the public channel username, for example "
        "<code>@mychannel</code> or <code>t.me/mychannel</code>.\n\n"
        "Only public channels are supported.",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )


@dp.message(Command("giftchannel"))
async def gift_channel_command(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    await start_channel_gift_flow(message, state)


@dp.callback_query(F.data == "dashboard_channel_gift")
async def dashboard_channel_gift(callback: CallbackQuery, state: FSMContext):
    ensure_user(callback.from_user)
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    await state.clear()
    await state.set_state(GiftStates.waiting_channel)
    await callback.message.answer(
        "\U0001f4e2 <b>Gift to Public Channel</b>\n\n"
        "Send the public channel username, for example "
        "<code>@mychannel</code> or <code>t.me/mychannel</code>.\n\n"
        "Only public channels are supported.",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(GiftStates.waiting_channel)
async def channel_username_received(message: Message, state: FSMContext):
    if not await require_force_join(message):
        await state.clear()
        return
    raw = (message.text or "").strip()
    username = raw.replace("https://t.me/", "").replace("http://t.me/", "")
    username = username.replace("t.me/", "").strip().split("/")[0].lstrip("@")
    if not username or not username.replace("_", "").isalnum():
        await message.answer("\u274c Invalid public channel username. Try again, e.g. <code>@mychannel</code>.", parse_mode="HTML")
        return
    try:
        channel = await bot.get_chat(f"@{username}")
    except Exception as e:
        await message.answer(
            "\u274c I could not access this channel. Check that the username is correct and the channel is public.\n\n"
            f"<code>{esc(e)}</code>",
            parse_mode="HTML",
        )
        return
    if str(channel.type) != "channel" or not channel.username:
        await message.answer("\u274c This is not a public channel. Please send a public channel username.")
        return
    await state.update_data(
        channel_id=int(channel.id),
        channel_username=channel.username,
        channel_title=channel.title or channel.username,
    )
    await state.set_state(GiftStates.waiting_channel_description)
    await message.answer(
        "\U0001f4dd <b>Gift message</b>\n\n"
        "Send the message that will appear with the gift.\n"
        "Maximum: <b>128 characters</b>.",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )


@dp.message(GiftStates.waiting_channel_description)
async def channel_gift_description(message: Message, state: FSMContext):
    if not await require_force_join(message):
        await state.clear()
        return
    description, gift_entities = extract_text_and_entities(message)
    if not description:
        await message.answer("\u274c Gift message cannot be empty.")
        return
    if len(description) > 128:
        await message.answer("\u274c Maximum message length is 128 characters.")
        return
    data = await state.get_data()
    try:
        enabled_gifts = await get_enabled_real_gifts(channel_only=True)
    except Exception as e:
        await message.answer(f"\u274c Could not load Telegram gifts.\n<code>{esc(e)}</code>", parse_mode="HTML")
        await state.clear()
        return

    if not enabled_gifts:
        await message.answer(
            "\u274c No supported non-limited gifts are currently enabled or available for channels.",
            reply_markup=dashboard_keyboard(message.from_user.id),
        )
        await state.clear()
        return
    await state.update_data(description=description, gift_entities=gift_entities)
    await state.set_state(GiftStates.selecting_channel_gift)
    bal_stars = get_balance_stars(message.from_user.id)
    await message.answer(
        "\U0001f381 <b>Choose a channel gift</b>\n\n"
        f"\U0001f4e3 Channel: <b>{esc(data.get('channel_title'))}</b>\n"
        f"\U0001f4b0 <b>Your Balance:</b> <b>{bal_stars} \u2b50</b>\n\n"
        "Select one of the available gifts below:",
        reply_markup=dynamic_gift_keyboard(enabled_gifts, prefix="channelgift_id"),
        parse_mode="HTML",
    )


@dp.callback_query(GiftStates.selecting_channel_gift, F.data.startswith("channelgift_id:"))
async def channel_gift_select(callback: CallbackQuery, state: FSMContext):
    selected_id = callback.data.split(":", 1)[1]
    try:
        gift = await find_gift_by_id(selected_id, channel_only=True)
    except Exception:
        logger.exception("Channel gift lookup failed")
        await callback.answer("Could not load gifts.", show_alert=True)
        return
    if not gift:
        await callback.answer("This gift is unavailable or disabled.", show_alert=True)
        return

    data = await state.get_data()
    if not data.get("channel_id") or not data.get("description"):
        await callback.message.edit_text("\u274c Session expired. Use /giftchannel again.")
        await state.clear()
        return
    price = int(gift.star_count)
    fee = 0
    total = price
    balance_units = get_balance_units(callback.from_user.id)
    if balance_units < stars_to_units(total):
        await callback.message.edit_text(
            "\u274c <b>Insufficient Balance</b>\n\n"
            f"Required: <b>{total} \u2b50</b>\n"
            f"Your balance: <b>{units_to_text(balance_units)} \u2b50</b>",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )
        await state.clear()
        return

    gift_name = format_gift_display_name(gift)
    gift_type = get_gift_type_slug(gift)
    desc_preview = render_description_html(data.get("description"), data.get("gift_entities"))
    await state.update_data(
        channel_gift_id=str(gift.id),
        channel_gift_type=gift_type,
        channel_gift_name=gift_name,
        channel_gift_price=price,
        channel_fee=fee,
        channel_total=total,
    )
    await state.set_state(GiftStates.channel_confirmation)
    await callback.message.edit_text(
        "\U0001f4e2 <b>Confirm Channel Gift</b>\n\n"
        f"\U0001f4e3 Channel: <b>{esc(data.get('channel_title'))}</b>\n"
        f"\U0001f517 Username: <b>@{esc(data.get('channel_username'))}</b>\n"
        f"\U0001f381 Gift: <b>{esc(gift_name)}</b>\n"
        f"\u2b50 Gift price: <b>{price} \u2b50</b>\n"
        f"\U0001f4b3 Total: <b>{total} \u2b50</b>\n"
        f"\U0001f4b0 Balance: <b>{units_to_text(balance_units)} \u2b50</b>\n\n"
        f"\U0001f4dd Message: {desc_preview}\n\n"
        "Confirm to send this gift to the public channel.",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(GiftStates.channel_confirmation, F.data == "gift_confirm")
async def confirm_channel_gift(callback: CallbackQuery, state: FSMContext):
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    required = ("channel_id", "channel_username", "channel_title", "description", "channel_gift_id", "channel_gift_type", "channel_gift_name", "channel_gift_price", "channel_fee", "channel_total")
    if any(data.get(key) is None for key in required):
        await callback.message.edit_text("\u274c Session expired. Use /giftchannel again.")
        await state.clear()
        return

    sender_id = callback.from_user.id
    if get_balance_units(sender_id) < stars_to_units(int(data["channel_total"])):
        await callback.message.edit_text("\u274c Insufficient balance. No gift was sent.", reply_markup=dashboard_keyboard(callback.from_user.id))
        await state.clear()
        return

    await callback.answer("Sending gift to channel...")
    try:
        current_gift = await find_gift_by_id(str(data["channel_gift_id"]), channel_only=True)
        if not current_gift or int(current_gift.star_count) != int(data["channel_gift_price"]):
            raise RuntimeError("This channel-compatible gift is no longer available at the selected price.")
        gift_entities = deserialize_entities(data.get("gift_entities"))
        send_kwargs = {
            "chat_id": int(data["channel_id"]),
            "gift_id": str(current_gift.id),
            "text": data["description"],
        }
        if gift_entities:
            send_kwargs["text_entities"] = gift_entities
        result = await bot.send_gift(**send_kwargs)
        if result is not True:
            raise RuntimeError("Telegram did not confirm sendGift.")
    except Exception as e:
        logger.exception("Channel sendGift failed")
        await callback.message.edit_text(
            "\u274c <b>Channel Gift Failed</b>\n\n"
            f"Channel: <b>{esc(data['channel_title'])}</b>\n"
            f"Telegram error: <code>{esc(e)}</code>\n\n"
            "<b>Your balance was NOT deducted.</b>",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )
        await state.clear()
        return

    gift_price = int(current_gift.star_count)
    fee = 0
    final_total = gift_price
    total_units = stars_to_units(final_total)
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,)).fetchone()
        if not row or int(row["balance"]) < total_units:
            db.rollback()
            logger.critical("Channel gift sent but balance deduction failed for %s", sender_id)
            await callback.message.edit_text(
                "\u26a0\ufe0f <b>Gift was sent to the channel</b>, but the balance could not be deducted. Contact an admin.",
                reply_markup=dashboard_keyboard(callback.from_user.id),
                parse_mode="HTML",
            )
            await state.clear()
            return

        db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (total_units, sender_id, total_units),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("Atomic balance deduction failed.")

        db.execute(
            """
            INSERT INTO gifts (
                sender_id, receiver_id, receiver_username, receiver_name,
                gift_type, telegram_gift_id, telegram_price, balance_price,
                description, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sender_id, int(data["channel_id"]), data["channel_username"], data["channel_title"],
             f"channel_{data['channel_gift_type']}", str(current_gift.id), gift_price, final_total,
             data["description"], now()),
        )
        db.execute(
            """
            INSERT INTO transactions (user_id, amount, type, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sender_id, -total_units, "channel_gift",
             f"{data['channel_gift_name']} sent to @{data['channel_username']}; gift={gift_price} \u2b50; no transaction fee",
             now()),
        )
        db.commit()
        await check_and_notify_level_up(sender_id)
        await send_activity_log(f"<b>Channel gift sent</b>\nUser: <code>{sender_id}</code>\nChannel: @{esc(data['channel_username'])}\nGift: {esc(data['channel_gift_name'])}\nPrice: <b>{gift_price} Stars</b>")
        await send_vouch_message(
            f"🎁 <b>New Channel Gift Delivered!</b> • {esc(data['channel_gift_name'])} (<b>{gift_price} ⭐</b>)\n"
            f"📢 Sent to <b>@{esc(data['channel_username'])}</b> by <b>{esc(callback.from_user.full_name)}</b>! 🎉"
        )
    except Exception:
        logger.exception("Channel gift balance update failed after successful Telegram send")
        try:
            db.rollback()
        except Exception:
            pass
        await callback.message.edit_text(
            "\u26a0\ufe0f Gift was sent, but the balance record could not be updated. Contact an admin.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )
        await state.clear()
        return

    new_balance = get_balance_stars(sender_id)
    await callback.message.edit_text(
        "\u2705 <b>Channel Gift Sent Successfully</b>\n\n"
        f"\U0001f4e3 Channel: <b>{esc(data['channel_title'])}</b>\n"
        f"\U0001f517 Username: <b>@{esc(data['channel_username'])}</b>\n"
        f"\U0001f381 Gift: <b>{esc(data['channel_gift_name'])}</b>\n"
        f"\u2b50 Gift price: <b>{gift_price} \u2b50</b>\n"
        f"\U0001f4b3 Deducted: <b>{final_total} \u2b50</b>\n"
        f"\U0001f4b0 New balance: <b>{new_balance} \u2b50</b>",
        reply_markup=dashboard_keyboard(callback.from_user.id),
        parse_mode="HTML",
    )
    await state.clear()


# ============================================================
# RECIPIENT SELECTED
# ============================================================

@dp.message(
    GiftStates.waiting_recipient,
    F.text.in_({"❌ Cancel", "Cancel"}),
)
async def recipient_cancel_text(
    message: Message,
    state: FSMContext,
):
    await state.clear()
    rm_msg = await send_text_only(
        message.chat.id,
        "⏳",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await rm_msg.delete()
    except Exception:
        pass
    await message.answer(
        "❌ <b>Gift Cancelled</b>\n\nChoose an option:",
        reply_markup=dashboard_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.message(
    GiftStates.waiting_recipient,
    F.user_shared,
)
async def recipient_selected(
    message: Message,
    state: FSMContext,
):
    shared = message.user_shared

    receiver_id = shared.user_id

    if receiver_id == message.from_user.id:
        await message.answer(
            "\u274c You selected yourself.\n\n"
            "Use <b>Gift To Myself</b> from the "
            "dashboard if you want to gift yourself.",
            reply_markup=recipient_keyboard(),
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # IMPORTANT:
    # The recipient must have started this bot.
    # --------------------------------------------------------

    if not user_has_started(
        receiver_id
    ):
        await message.answer(
            "\u274c <b>Recipient has not started the bot.</b>\n\n"
            "The bot cannot send a gift to this user "
            "until they open the bot and press /start "
            "at least once.\n\n"
            f"Ask them to open:\n"
            f"https://t.me/{(await bot.get_me()).username}",
            reply_markup=recipient_keyboard(),
            parse_mode="HTML",
        )
        return

    receiver_username = None
    receiver_name = "Telegram User"

    try:
        receiver = await bot.get_chat(
            receiver_id
        )

        receiver_username = (
            receiver.username
        )

        receiver_name = (
            receiver.first_name
            or receiver.title
            or "Telegram User"
        )

    except Exception as e:
        logger.warning(
            "Could not get receiver info: %s",
            e,
        )

    await state.update_data(
        receiver_id=receiver_id,
        receiver_username=receiver_username,
        receiver_name=receiver_name,
        self_gift=False,
    )

    await state.set_state(
        GiftStates.waiting_description
    )

    rm_msg = await send_text_only(
        message.chat.id,
        "⏳",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await rm_msg.delete()
    except Exception:
        pass

    await message.answer(
        "\U0001f4dd <b>Step 2/3</b>\n\n"
        "Send the description/message that "
        "will appear with the gift.\n\n"
        "Maximum: <b>128 characters</b>.\n\n"
        "Example:\n"
        "<i>Happy Birthday \u2764\ufe0f</i>",
        reply_markup=user_cancel_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# DESCRIPTION
# ============================================================

@dp.message(
    GiftStates.waiting_description
)
async def gift_description(
    message: Message,
    state: FSMContext,
):
    if not await require_force_join(
        message
    ):
        await state.clear()
        return

    description, gift_entities = extract_text_and_entities(message)

    if not description:
        await message.answer(
            "\u274c Description cannot be empty."
        )
        return

    if len(description) > 128:
        await message.answer(
            "\u274c Description is too long.\n\n"
            "Maximum: 128 characters."
        )
        return

    data = await state.get_data()

    receiver_id = data.get(
        "receiver_id"
    )

    # Extra recipient verification.
    if not user_has_started(
        receiver_id
    ):
        await message.answer(
            "\u274c Recipient has not started the bot.\n\n"
            "The gift cannot be sent."
        )
        await state.clear()
        return

    await state.update_data(
        description=description,
        gift_entities=gift_entities,
    )

    try:
        enabled_gifts = await get_enabled_real_gifts(channel_only=False)

    except Exception as e:
        logger.exception(
            "getAvailableGifts failed."
        )

        await message.answer(
            "\u274c Could not load Telegram Gifts.\n\n"
            f"<code>{esc(e)}</code>",
            parse_mode="HTML",
        )

        await state.clear()
        return

    if not enabled_gifts:
        await message.answer(
            "\u274c No gifts are currently enabled or available.\n\n"
            "Please try again later.",
            reply_markup=dashboard_keyboard(message.from_user.id),
        )

        await state.clear()
        return

    await state.set_state(
        GiftStates.selecting_gift
    )

    bal_stars = get_balance_stars(message.from_user.id)
    await message.answer(
        "\U0001f381 <b>Choose Your Gift</b>\n\n"
        f"\U0001f4b0 <b>Your Balance:</b> <b>{bal_stars} \u2b50</b>\n\n"
        "Select one of the available gifts below:",
        reply_markup=dynamic_gift_keyboard(enabled_gifts, prefix="gift_id"),
        parse_mode="HTML",
    )


# ============================================================
# GIFT SELECT
# ============================================================

@dp.callback_query(
    GiftStates.selecting_gift,
    F.data.startswith("gift_id:"),
)
async def gift_select(
    callback: CallbackQuery,
    state: FSMContext,
):
    selected_id = callback.data.split(
        ":",
        1,
    )[1]

    try:
        gift = await find_gift_by_id(
            selected_id,
            channel_only=False,
        )
    except Exception:
        logger.exception(
            "Gift lookup failed."
        )

        await callback.answer(
            "Could not load gifts.",
            show_alert=True,
        )
        return

    if not gift:
        await callback.answer(
            "This gift is unavailable or disabled.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    receiver_id = data.get(
        "receiver_id"
    )

    receiver_name = data.get(
        "receiver_name",
        "Telegram User",
    )

    receiver_username = data.get(
        "receiver_username"
    )

    description = data.get(
        "description"
    )

    if not receiver_id or not description:
        await callback.message.edit_text(
            "\u274c Gift session expired.\n\n"
            "Use /gift again."
        )

        await state.clear()
        return

    # Recipient must still have started the bot.
    if not user_has_started(
        receiver_id
    ):
        await callback.message.edit_text(
            "\u274c <b>Recipient has not started the bot.</b>\n\n"
            "The gift cannot be sent.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    gift_price = int(
        gift.star_count
    )

    fee = 0
    total = gift_price

    balance_units = get_balance_units(
        callback.from_user.id
    )

    required_units = stars_to_units(
        total
    )

    if balance_units < required_units:
        await callback.message.edit_text(
            "\u274c <b>Insufficient Balance</b>\n\n"
            f"\U0001f4b0 Balance: "
            f"<b>{units_to_text(balance_units)} \u2b50</b>\n"
            f"\U0001f381 Gift: <b>{gift_price} \u2b50</b>\n"
            f"\U0001f4b3 Total: <b>{total} \u2b50</b>",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    gift_name = format_gift_display_name(gift)
    gift_type = get_gift_type_slug(gift)
    desc_preview = render_description_html(description, data.get("gift_entities"))

    await state.update_data(
        gift_type=gift_type,
        gift_name=gift_name,
        telegram_gift_id=str(
            gift.id
        ),
        telegram_price=gift_price,
        transaction_fee=fee,
        total_price=total,
    )

    await state.set_state(
        GiftStates.confirmation
    )

    username_text = (
        f"@{receiver_username}"
        if receiver_username
        else "No username"
    )

    self_text = (
        "\n\U0001f3af <b>Self gift:</b> Yes"
        if data.get("self_gift")
        else ""
    )

    await callback.message.edit_text(
        "\U0001f381 <b>Confirm Gift</b>\n\n"
        f"\U0001f464 <b>Recipient:</b> "
        f"{esc(receiver_name)}\n"
        f"\U0001f517 <b>Username:</b> "
        f"{esc(username_text)}\n"
        f"\U0001f194 <b>ID:</b> "
        f"<code>{receiver_id}</code>\n"
        f"{self_text}\n\n"
        f"\U0001f381 <b>Gift:</b> {esc(gift_name)}\n"
        f"\u2b50 <b>Gift price:</b> {gift_price} \u2b50\n"
        f"\U0001f4b3 <b>Total:</b> {total} \u2b50\n"
        f"\U0001f4b0 <b>Balance:</b> "
        f"{units_to_text(balance_units)} \u2b50\n\n"
        f"\U0001f4dd <b>Description:</b>\n"
        f"{desc_preview}\n\n"
        "Press <b>Confirm & Send</b>.",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# CONFIRM + SEND REAL TELEGRAM GIFT
# ============================================================

@dp.callback_query(
    GiftStates.confirmation,
    F.data == "gift_confirm",
)
async def confirm_gift(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not await user_joined_force_channels(
        callback.from_user.id
    ):
        await callback.answer(
            "Join required first.",
            show_alert=True,
        )
        await state.clear()
        return

    data = await state.get_data()

    receiver_id = data.get(
        "receiver_id"
    )

    receiver_username = data.get(
        "receiver_username"
    )

    receiver_name = data.get(
        "receiver_name",
        "Telegram User",
    )

    gift_type = data.get(
        "gift_type"
    )

    gift_name = data.get(
        "gift_name"
    )

    description = data.get(
        "description"
    )

    telegram_price = data.get(
        "telegram_price"
    )

    transaction_fee = data.get(
        "transaction_fee"
    )

    total_price = data.get(
        "total_price"
    )

    if not all(
        x is not None
        for x in (
            receiver_id,
            gift_type,
            gift_name,
            description,
            telegram_price,
            transaction_fee,
            total_price,
        )
    ):
        await callback.message.edit_text(
            "\u274c Gift session expired.\n\n"
            "Use /gift again.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )

        await state.clear()
        return

    sender_id = callback.from_user.id

    # --------------------------------------------------------
    # Recipient must have started bot.
    # --------------------------------------------------------

    if not user_has_started(
        receiver_id
    ):
        await callback.message.edit_text(
            "\u274c <b>Gift not sent</b>\n\n"
            "The recipient has not started the bot.\n\n"
            "Ask them to open the bot and press /start.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    # --------------------------------------------------------
    # Final balance check.
    # --------------------------------------------------------

    balance_units = get_balance_units(
        sender_id
    )

    required_units = stars_to_units(
        int(total_price)
    )

    if balance_units < required_units:
        await callback.message.edit_text(
            "\u274c <b>Insufficient Balance</b>\n\n"
            f"Required: <b>{total_price} \u2b50</b>\n"
            f"Balance: "
            f"<b>{units_to_text(balance_units)} \u2b50</b>",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    await callback.answer(
        "Sending real Telegram Gift..."
    )

    # --------------------------------------------------------
    # Get current real gift.
    # --------------------------------------------------------

    selected_gift_id = str(data.get("telegram_gift_id") or "")
    if not selected_gift_id:
        await callback.message.edit_text(
            "\u274c Gift session expired.\n\n"
            "Use /gift again.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )
        await state.clear()
        return

    try:
        current_gift = await find_gift_by_id(
            selected_gift_id,
            channel_only=False,
        )
    except Exception:
        logger.exception(
            "Current gift lookup failed."
        )

        await callback.message.edit_text(
            "\u274c Could not verify the Telegram Gift.\n\n"
            "No balance was deducted.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )

        await state.clear()
        return

    if not current_gift:
        await callback.message.edit_text(
            "\u274c This gift is no longer available or was disabled.\n\n"
            "No balance was deducted.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )

        await state.clear()
        return

    current_gift_id = str(
        current_gift.id
    )

    actual_gift_price = int(
        current_gift.star_count
    )

    actual_fee = 0
    actual_total = actual_gift_price

    if actual_gift_price != int(
        telegram_price
    ):
        await callback.message.edit_text(
            "\u274c Gift price changed.\n\n"
            "Please start the gift process again.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
        )

        await state.clear()
        return

    # --------------------------------------------------------
    # ACTUAL BOT API sendGift (with custom/premium emoji entities)
    # --------------------------------------------------------

    try:
        gift_entities = deserialize_entities(data.get("gift_entities"))
        send_kwargs = {
            "user_id": int(receiver_id),
            "gift_id": current_gift_id,
            "text": description,
        }
        if gift_entities:
            send_kwargs["text_entities"] = gift_entities
        result = await bot.send_gift(**send_kwargs)

        if result is not True:
            raise RuntimeError(
                "Telegram did not confirm sendGift."
            )

    except Exception as e:
        logger.exception(
            "sendGift failed."
        )

        await callback.message.edit_text(
            "\u274c <b>Gift Sending Failed</b>\n\n"
            f"\U0001f464 Recipient: "
            f"<b>{esc(receiver_name)}</b>\n"
            f"\U0001f381 Gift: <b>{gift_name}</b>\n\n"
            f"Telegram error:\n"
            f"<code>{esc(e)}</code>\n\n"
            "\U0001f4b0 <b>Your balance was NOT deducted.</b>",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Gift has already been sent.
    #
    # Now atomically deduct:
    #
    # exact Telegram gift price only (no transaction fee).
    # --------------------------------------------------------

    total_units = stars_to_units(
        actual_total
    )

    try:
        db.execute(
            "BEGIN IMMEDIATE"
        )

        row = db.execute(
            """
            SELECT balance
            FROM users
            WHERE user_id = ?
            """,
            (sender_id,),
        ).fetchone()

        if not row:
            db.rollback()

            logger.critical(
                "User missing after successful gift: %s",
                sender_id,
            )

            await callback.message.edit_text(
                "\u26a0\ufe0f <b>Gift Sent</b>\n\n"
                "The real Telegram Gift was sent, "
                "but the internal balance record "
                "could not be updated.\n\n"
                "Contact an admin immediately.",
                reply_markup=dashboard_keyboard(callback.from_user.id),
                parse_mode="HTML",
            )

            await state.clear()
            return

        current_balance = int(
            row["balance"]
        )

        if current_balance < total_units:
            db.rollback()

            logger.critical(
                "Insufficient balance AFTER gift send. "
                "sender=%s balance=%s required=%s",
                sender_id,
                current_balance,
                total_units,
            )

            await callback.message.edit_text(
                "\u26a0\ufe0f <b>Gift Sent Successfully</b>\n\n"
                "The real Telegram Gift was sent.\n\n"
                "However, the internal balance could "
                "not be deducted because the balance "
                "changed unexpectedly.\n\n"
                "Contact an admin immediately.",
                reply_markup=dashboard_keyboard(callback.from_user.id),
                parse_mode="HTML",
            )

            await state.clear()
            return

        # ----------------------------------------------------
        # Atomic deduction.
        # ----------------------------------------------------

        db.execute(
            """
            UPDATE users
            SET balance = balance - ?
            WHERE user_id = ?
              AND balance >= ?
            """,
            (
                total_units,
                sender_id,
                total_units,
            ),
        )

        if db.execute(
            "SELECT changes()"
        ).fetchone()[0] != 1:
            db.rollback()

            await callback.message.edit_text(
                "\u26a0\ufe0f Gift was sent, but the balance "
                "could not be updated.\n\n"
                "Contact an admin.",
                reply_markup=dashboard_keyboard(callback.from_user.id),
            )

            await state.clear()
            return

        # ----------------------------------------------------
        # Gift history.
        # ----------------------------------------------------

        db.execute(
            """
            INSERT INTO gifts (
                sender_id,
                receiver_id,
                receiver_username,
                receiver_name,
                gift_type,
                telegram_gift_id,
                telegram_price,
                balance_price,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sender_id,
                receiver_id,
                receiver_username,
                receiver_name,
                gift_type,
                current_gift_id,
                actual_gift_price,
                actual_total,
                description,
                now(),
            ),
        )

        # ----------------------------------------------------
        # Transaction history.
        # ----------------------------------------------------

        db.execute(
            """
            INSERT INTO transactions (
                user_id,
                amount,
                type,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sender_id,
                -total_units,
                "gift",
                (
                    f"{gift_name} sent to {receiver_id}; "
                    f"gift={actual_gift_price} \u2b50; no transaction fee"
                ),
                now(),
            ),
        )

        db.commit()
        await check_and_notify_level_up(sender_id)
        await send_activity_log(f"<b>Gift sent</b>\nSender: <code>{sender_id}</code>\nRecipient: <code>{receiver_id}</code> ({esc(receiver_name)})\nGift: {esc(gift_name)}\nPrice: <b>{actual_gift_price} Stars</b>")
        await send_vouch_message(
            f"🎁 <b>New Gift Delivered!</b> • {gift_name} (<b>{actual_gift_price} ⭐</b>)\n"
            f"✅ Sent by <b>{esc(callback.from_user.full_name)}</b> • Thank you for using our Gift Store! 🎉"
        )

    except Exception:
        logger.exception(
            "Internal balance update failed "
            "after successful sendGift."
        )

        try:
            db.rollback()
        except Exception:
            pass

        await callback.message.edit_text(
            "\u26a0\ufe0f <b>Gift Sent Successfully</b>\n\n"
            "The real Telegram Gift was sent, "
            "but the internal balance update failed.\n\n"
            "Contact an admin immediately.",
            reply_markup=dashboard_keyboard(callback.from_user.id),
            parse_mode="HTML",
        )

        await state.clear()
        return

    new_balance = get_balance_stars(
        sender_id
    )

    username_text = (
        f"@{receiver_username}"
        if receiver_username
        else f"ID {receiver_id}"
    )

    await callback.message.edit_text(
        "\U0001f389 <b>Gift Sent Successfully!</b>\n\n"
        f"\U0001f464 <b>Recipient:</b> "
        f"{esc(receiver_name)}\n"
        f"\U0001f517 <b>Username:</b> "
        f"{esc(username_text)}\n"
        f"\U0001f381 <b>Gift:</b> {gift_name}\n"
        f"\u2b50 <b>Gift price:</b> "
        f"{actual_gift_price} \u2b50\n"
        f"\U0001f4b3 <b>Total deducted:</b> "
        f"{actual_total} \u2b50\n"
        f"\U0001f4b0 <b>Remaining balance:</b> "
        f"{new_balance} \u2b50\n\n"
        f"\U0001f4dd <b>Message:</b>\n"
        f"{render_description_html(description, data.get('gift_entities'))}",
        reply_markup=dashboard_keyboard(callback.from_user.id),
        parse_mode="HTML",
    )

    await state.clear()


# ============================================================
# CANCEL
# ============================================================

@dp.callback_query(
    F.data == "gift_cancel"
)
async def cancel_gift(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.message.edit_text(
        "\u274c <b>Gift Cancelled</b>\n\n"
        "No balance was deducted.",
        reply_markup=dashboard_keyboard(callback.from_user.id),
        parse_mode="HTML",
    )

    await callback.answer()


def get_promo_balance(user_id: int) -> int:
    row = db.execute("SELECT stars FROM promo_wallets WHERE user_id=?", (user_id,)).fetchone()
    return int(row['stars']) if row else 0



# ============================================================
# USER JOIN & EARN TASKS (1-BY-1 PROMO CHANNELS)
# ============================================================

TASK_REWARD_UNITS = 1       # 0.5 Star
TASK_PENALTY_UNITS = 2      # 1.0 Star
TASK_HOLD_SECONDS = 180     # 3 minutes

TASK_RULES_TEXT = (
    "📌 <b>Task Rules:</b>\n"
    "• Join the channel below and tap <b>Verify</b> to earn <b>0.5 ⭐</b>.\n"
    "• If you are <b>already a member</b> of the channel, you will receive <b>0 ⭐</b>.\n"
    "• If you leave the channel within <b>3 minutes</b> of verifying, <b>1 ⭐</b> will be deducted from your balance.\n"
    "• Each channel task is given <b>only once</b> — once joined or checked, it will never be given again."
)


def _is_member_status(member) -> bool:
    status = getattr(member, "status", None)
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted" and getattr(member, "is_member", False):
        return True
    return False


async def get_next_user_task(user_id: int):
    campaigns = db.execute(
        "SELECT * FROM channel_promotions WHERE status='active' AND credits>0 AND user_id != ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()

    for promo in campaigns:
        promo_id = int(promo["id"])
        channel_id = int(promo["channel_id"])

        # Permanent no-repeat check per (user_id, channel_id)
        done = db.execute(
            "SELECT 1 FROM channel_task_records WHERE user_id=? AND channel_id=?",
            (user_id, channel_id),
        ).fetchone()
        if done:
            continue

        # Also check if already verified via start gate
        seen_gate = db.execute(
            "SELECT 1 FROM promo_verifications WHERE promotion_id=? AND user_id=?",
            (promo_id, user_id),
        ).fetchone()
        if seen_gate:
            db.execute(
                "INSERT OR IGNORE INTO channel_task_records(user_id, channel_id, promotion_id, status, created_at) VALUES(?,?,?,?,?)",
                (user_id, channel_id, promo_id, "already_member", now()),
            )
            db.commit()
            continue

        try:
            member = await bot.get_chat_member(channel_id, user_id)
            already_joined = _is_member_status(member)
        except Exception:
            # Skip channels where bot cannot inspect membership
            continue

        if already_joined:
            # User is already in this channel -> gets nothing and never gets this channel again
            db.execute(
                "INSERT OR IGNORE INTO channel_task_records(user_id, channel_id, promotion_id, status, created_at) VALUES(?,?,?,?,?)",
                (user_id, channel_id, promo_id, "already_member", now()),
            )
            db.commit()
            continue

        db.execute(
            "INSERT INTO task_eligibility(user_id, channel_id, promotion_id, was_member, shown_at) "
            "VALUES(?,?,?,0,?) ON CONFLICT(user_id, channel_id) DO UPDATE SET promotion_id=excluded.promotion_id, was_member=0, shown_at=excluded.shown_at",
            (user_id, channel_id, promo_id, now()),
        )
        db.commit()
        return promo

    return None


def task_card_keyboard(promo):
    kb = InlineKeyboardBuilder()
    if promo is not None:
        join_url = get_promo_join_url(promo)
        ctype = (promo["chat_type"] or "channel") if "chat_type" in promo.keys() else "channel"
        btn_label = "Join Group" if ctype in ("supergroup", "group") else "Join Channel"
        if join_url:
            kb.button(
                text=btn_label,
                url=join_url,
                style="primary",
                icon_custom_emoji_id=EMOJI_FORCE,
            )
        add_inline_button(kb, "✅ Verify", f"task_verify:{promo['id']}", get_button_style("VERIFY"), EMOJI_VERIFY)
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(1)
    return kb.as_markup()


def format_task_screen(promo) -> str:
    header = f"📝 <b>Join &amp; Earn Tasks</b>\n\n{TASK_RULES_TEXT}\n\n"
    if promo is None:
        return (
            header
            + "📭 <b>No tasks available right now.</b>\n"
            + "Please check back later for new promoted channels &amp; groups."
        )
    ctype = (promo["chat_type"] or "channel") if "chat_type" in promo.keys() else "channel"
    kind_label = "👥 <b>Group:</b>" if ctype in ("supergroup", "group") else "📢 <b>Channel:</b>"
    target_word = "group" if ctype in ("supergroup", "group") else "channel"
    return (
        header
        + "━━━━━━━━━━━━━━━━━━━━\n"
        + f"{kind_label} {esc(promo['channel_title'])}\n"
        + f"📝 <b>Description:</b> {esc(promo['description'])}\n"
        + "⭐ <b>Reward:</b> <b>0.5 ⭐</b> (Stay 3+ mins)\n\n"
        + f"Join the {target_word} above using the button link and tap <b>Verify</b>."
    )


@dp.callback_query(F.data == "dashboard_tasks")
async def dashboard_tasks(callback: CallbackQuery, state: FSMContext):
    if is_banned(callback.from_user.id):
        await callback.answer("Your access is restricted.", show_alert=True)
        return
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    await state.clear()
    ensure_user(callback.from_user)
    promo = await get_next_user_task(callback.from_user.id)
    if promo is not None and not (promo["invite_link"] or "").strip():
        try:
            await ensure_promo_invite_link(promo)
            promo = db.execute("SELECT * FROM channel_promotions WHERE id=?", (promo["id"],)).fetchone()
        except Exception:
            logger.warning("Could not create invite link for promo #%s", promo["id"])
    await callback.message.edit_text(
        format_task_screen(promo),
        reply_markup=task_card_keyboard(promo),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("task_verify:"))
async def task_verify_callback(callback: CallbackQuery):
    if is_banned(callback.from_user.id):
        await callback.answer("Your access is restricted.", show_alert=True)
        return
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return

    user_id = callback.from_user.id
    ensure_user(callback.from_user)

    try:
        promo_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid task.", show_alert=True)
        return

    promo = db.execute("SELECT * FROM channel_promotions WHERE id=?", (promo_id,)).fetchone()
    if not promo or promo["status"] != "active" or int(promo["credits"]) <= 0:
        next_promo = await get_next_user_task(user_id)
        await callback.message.edit_text(
            format_task_screen(next_promo),
            reply_markup=task_card_keyboard(next_promo),
            parse_mode="HTML",
        )
        await callback.answer("This task is no longer active. Loaded next task.", show_alert=True)
        return

    channel_id = int(promo["channel_id"])

    existing = db.execute(
        "SELECT 1 FROM channel_task_records WHERE user_id=? AND channel_id=?",
        (user_id, channel_id),
    ).fetchone()
    if existing:
        next_promo = await get_next_user_task(user_id)
        await callback.message.edit_text(
            format_task_screen(next_promo),
            reply_markup=task_card_keyboard(next_promo),
            parse_mode="HTML",
        )
        await callback.answer("You already completed or checked this channel.", show_alert=True)
        return

    elig = db.execute(
        "SELECT was_member FROM task_eligibility WHERE user_id=? AND channel_id=?",
        (user_id, channel_id),
    ).fetchone()
    if elig and int(elig["was_member"]) == 1:
        db.execute(
            "INSERT OR IGNORE INTO channel_task_records(user_id, channel_id, promotion_id, status, created_at) VALUES(?,?,?,?,?)",
            (user_id, channel_id, promo_id, "already_member", now()),
        )
        db.commit()
        next_promo = await get_next_user_task(user_id)
        await callback.message.edit_text(
            format_task_screen(next_promo),
            reply_markup=task_card_keyboard(next_promo),
            parse_mode="HTML",
        )
        await callback.answer("You were already joined in this channel, so no reward was given.", show_alert=True)
        return

    join_rec = db.execute(
        "SELECT status, source, joined_at FROM promo_link_joins WHERE promotion_id=? AND user_id=?",
        (promo_id, user_id),
    ).fetchone()
    if join_rec and join_rec["source"] == "other_link":
        await callback.answer(
            "❌ Please join using the bot's Join button link, not another invite link.",
            show_alert=True,
        )
        return

    try:
        member = await bot.get_chat_member(channel_id, user_id)
        joined = _is_member_status(member)
    except Exception:
        await callback.answer("Could not check membership right now. Please try again.", show_alert=True)
        return

    if not joined:
        await callback.answer("❌ You haven't joined yet! Tap the Join button first, then tap Verify.", show_alert=True)
        return

    ts = now()
    target_label = f"@{promo['channel_username']}" if promo["channel_username"] else promo["channel_title"]
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO channel_task_records(user_id, channel_id, promotion_id, status, rewarded_at, penalized, created_at) "
            "VALUES(?,?,?,'rewarded',?,0,?)",
            (user_id, channel_id, promo_id, ts, ts),
        )
        db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (TASK_REWARD_UNITS, user_id),
        )
        db.execute(
            "INSERT INTO transactions(user_id, amount, type, description, created_at) VALUES(?,?,?,?,?)",
            (
                user_id,
                TASK_REWARD_UNITS,
                "task_reward",
                f"Join task: {target_label} (+0.5 ⭐)",
                ts,
            ),
        )
        db.execute(
            "INSERT OR IGNORE INTO promo_verifications(promotion_id, user_id, verified_at) VALUES(?,?,?)",
            (promo_id, user_id, ts),
        )
        if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
            db.execute(
                "UPDATE channel_promotions SET credits = MAX(credits - 1, 0) WHERE id = ?",
                (promo_id,),
            )
        db.execute(
            "INSERT INTO promo_link_joins(promotion_id, channel_id, user_id, invite_link, joined_at, status, source) "
            "VALUES(?,?,?,?,?,'pending','task_verify') "
            "ON CONFLICT(promotion_id, user_id) DO UPDATE SET status = CASE WHEN promo_link_joins.status = 'left_early' THEN 'pending' ELSE promo_link_joins.status END, joined_at = CASE WHEN promo_link_joins.status = 'left_early' THEN excluded.joined_at ELSE promo_link_joins.joined_at END",
            (promo_id, channel_id, user_id, promo["invite_link"] or "", ts),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        next_promo = await get_next_user_task(user_id)
        await callback.message.edit_text(
            format_task_screen(next_promo),
            reply_markup=task_card_keyboard(next_promo),
            parse_mode="HTML",
        )
        await callback.answer("Task already processed.", show_alert=True)
        return
    except Exception:
        db.rollback()
        logger.exception("Task verification DB error")
        await callback.answer("Verification failed. Please try again.", show_alert=True)
        return

    await check_and_notify_level_up(user_id)
    await finalize_completed_promotions()
    await send_activity_log(
        f"<b>Task verified (+0.5 Star)</b>\nUser: <code>{user_id}</code>\nChannel: @{esc(promo['channel_username'])}"
    )

    next_promo = await get_next_user_task(user_id)
    await callback.message.edit_text(
        format_task_screen(next_promo),
        reply_markup=task_card_keyboard(next_promo),
        parse_mode="HTML",
    )
    await callback.answer("✅ Verified! +0.5 ⭐ added to your balance.", show_alert=True)


async def apply_task_leave_penalty_if_applicable(user_id: int, channel_id: int):
    row = db.execute(
        "SELECT * FROM channel_task_records WHERE user_id=? AND channel_id=? AND status='rewarded' AND penalized=0",
        (user_id, channel_id),
    ).fetchone()
    if not row or not row["rewarded_at"]:
        return False

    try:
        rewarded_dt = datetime.strptime(row["rewarded_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False

    elapsed = (datetime.utcnow() - rewarded_dt).total_seconds()
    if elapsed > TASK_HOLD_SECONDS:
        return False

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE channel_task_records SET penalized = 1, status = 'penalized' WHERE id = ? AND penalized = 0",
            (row["id"],),
        )
        if db.execute("SELECT changes() AS c").fetchone()["c"] != 1:
            db.rollback()
            return False

        db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (TASK_PENALTY_UNITS, user_id),
        )
        db.execute(
            "INSERT INTO transactions(user_id, amount, type, description, created_at) VALUES(?,?,?,?,?)",
            (
                user_id,
                -TASK_PENALTY_UNITS,
                "task_penalty",
                f"Left promoted channel {channel_id} within 3 minutes (-1 ⭐ penalty)",
                now(),
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed applying 3-min task leave penalty")
        return False

    new_bal = get_balance_stars(user_id)
    try:
        await send_text_only(
            user_id,
            "⚠️ <b>Task Leave Penalty (-1 ⭐)</b>\n\n"
            "You left the promoted channel within <b>3 minutes</b> of completing the task.\n"
            f"💸 Deducted: <b>1 ⭐</b>\n"
            f"💰 Current Balance: <b>{new_bal} ⭐</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await send_activity_log(
        f"<b>Task leave penalty (-1 Star)</b>\nUser: <code>{user_id}</code>\nChannel ID: <code>{channel_id}</code>"
    )
    return True


def _match_promo_by_invite_link(chat_id: int, invite_obj):
    if not invite_obj:
        return None
    used_url = (getattr(invite_obj, "invite_link", "") or "").strip()
    active_rows = db.execute(
        "SELECT * FROM channel_promotions WHERE channel_id = ? AND status = 'active' ORDER BY id ASC",
        (chat_id,),
    ).fetchall()
    if not active_rows:
        return None

    if used_url:
        for row in active_rows:
            stored = (row["invite_link"] or "").strip()
            if not stored:
                continue
            if stored == used_url:
                return row
            if used_url.endswith("...") and stored.startswith(used_url[:-3]):
                return row
    return None


async def handle_promo_link_early_leave(user_id: int, channel_id: int):
    rows = db.execute(
        "SELECT * FROM promo_link_joins WHERE user_id = ? AND channel_id = ? AND status = 'pending'",
        (user_id, channel_id),
    ).fetchall()
    if not rows:
        return

    now_dt = datetime.utcnow()
    ts = now()
    for r in rows:
        try:
            joined_dt = datetime.strptime(r["joined_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        elapsed = (now_dt - joined_dt).total_seconds()
        promo_id = int(r["promotion_id"])
        if elapsed >= TASK_HOLD_SECONDS:
            # User actually stayed >= 3 minutes before leaving!
            db.execute(
                "UPDATE promo_link_joins SET status = 'verified_3m' WHERE id = ? AND status = 'pending'",
                (r["id"],),
            )
            if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
                db.execute(
                    "UPDATE channel_promotions SET verified_joins = verified_joins + 1 WHERE id = ?",
                    (promo_id,),
                )
            db.commit()
        else:
            # Left before 3 minutes -> mark left_early and refund reserved slot if verified
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE promo_link_joins SET status = 'left_early', left_at = ? WHERE id = ? AND status = 'pending'",
                (ts, r["id"]),
            )
            if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
                db.execute(
                    "DELETE FROM promo_verifications WHERE promotion_id = ? AND user_id = ?",
                    (promo_id, user_id),
                )
                if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
                    db.execute(
                        "UPDATE channel_promotions SET credits = credits + 1 WHERE id = ? AND status = 'active'",
                        (promo_id,),
                    )
            db.commit()


@dp.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    new_member = event.new_chat_member
    if not new_member or not new_member.user or new_member.user.is_bot:
        return
    old_member = event.old_chat_member
    was_member = _is_member_status(old_member)
    is_member = _is_member_status(new_member)
    user_id = int(new_member.user.id)
    chat_id = int(event.chat.id)

    if not was_member and is_member:
        matched_promo = _match_promo_by_invite_link(chat_id, event.invite_link)
        if matched_promo is not None:
            promo_id = int(matched_promo["id"])
            if user_id != int(matched_promo["user_id"]):
                ts = now()
                db.execute(
                    "INSERT INTO promo_link_joins(promotion_id, channel_id, user_id, invite_link, joined_at, status, source) "
                    "VALUES(?,?,?,?,?,'pending','bot_link') "
                    "ON CONFLICT(promotion_id, user_id) DO UPDATE SET "
                    "joined_at = CASE WHEN promo_link_joins.status = 'left_early' THEN excluded.joined_at ELSE promo_link_joins.joined_at END, "
                    "status = CASE WHEN promo_link_joins.status = 'left_early' THEN 'pending' ELSE promo_link_joins.status END, "
                    "source = 'bot_link'",
                    (promo_id, chat_id, user_id, matched_promo["invite_link"] or "", ts),
                )
                db.commit()
        elif event.invite_link is not None:
            # Joined via some other invite link in a chat that has an active promotion
            active_promo = db.execute(
                "SELECT id FROM channel_promotions WHERE channel_id = ? AND status = 'active' ORDER BY id ASC LIMIT 1",
                (chat_id,),
            ).fetchone()
            if active_promo:
                db.execute(
                    "INSERT OR IGNORE INTO promo_link_joins(promotion_id, channel_id, user_id, invite_link, joined_at, status, source) "
                    "VALUES(?,?,?,?,?,'ignored','other_link')",
                    (int(active_promo["id"]), chat_id, user_id, getattr(event.invite_link, "invite_link", "") or "", now()),
                )
                db.commit()

    elif was_member and not is_member:
        await apply_task_leave_penalty_if_applicable(user_id, chat_id)
        await handle_promo_link_early_leave(user_id, chat_id)


async def task_leave_monitor():
    while True:
        try:
            rows = db.execute(
                "SELECT id, user_id, channel_id, rewarded_at FROM channel_task_records "
                "WHERE status='rewarded' AND penalized=0 AND rewarded_at IS NOT NULL"
            ).fetchall()
            now_dt = datetime.utcnow()
            for r in rows:
                try:
                    rewarded_dt = datetime.strptime(r["rewarded_at"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if (now_dt - rewarded_dt).total_seconds() > TASK_HOLD_SECONDS:
                    continue
                try:
                    member = await bot.get_chat_member(int(r["channel_id"]), int(r["user_id"]))
                    if not _is_member_status(member):
                        await apply_task_leave_penalty_if_applicable(int(r["user_id"]), int(r["channel_id"]))
                except Exception:
                    pass

            # Verify 3-minute retention for all pending bot-link joins
            pending_joins = db.execute(
                "SELECT id, promotion_id, channel_id, user_id, joined_at, invite_link FROM promo_link_joins "
                "WHERE status = 'pending'"
            ).fetchall()
            for pj in pending_joins:
                try:
                    joined_dt = datetime.strptime(pj["joined_at"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                elapsed = (now_dt - joined_dt).total_seconds()
                cid = int(pj["channel_id"])
                uid = int(pj["user_id"])
                promo_id = int(pj["promotion_id"])
                try:
                    member = await bot.get_chat_member(cid, uid)
                    still_in = _is_member_status(member)
                except Exception:
                    continue

                if not still_in:
                    await handle_promo_link_early_leave(uid, cid)
                elif elapsed >= TASK_HOLD_SECONDS:
                    # User joined via bot's link and stayed for at least 3 full minutes!
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "UPDATE promo_link_joins SET status = 'verified_3m' WHERE id = ? AND status = 'pending'",
                        (pj["id"],),
                    )
                    if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
                        db.execute(
                            "UPDATE channel_promotions SET verified_joins = verified_joins + 1 WHERE id = ?",
                            (promo_id,),
                        )
                        # If user joined directly via bot link without clicking Verify yet, reserve placement credit now
                        db.execute(
                            "INSERT OR IGNORE INTO promo_verifications(promotion_id, user_id, verified_at) VALUES(?,?,?)",
                            (promo_id, uid, now()),
                        )
                        if db.execute("SELECT changes() AS c").fetchone()["c"] == 1:
                            db.execute(
                                "UPDATE channel_promotions SET credits = MAX(credits - 1, 0) WHERE id = ?",
                                (promo_id,),
                            )
                    db.commit()

            await finalize_completed_promotions()
        except Exception:
            logger.exception("Task & promo retention monitor error.")
        await asyncio.sleep(20)


# ============================================================
# USER CHANNEL PROMOTION MARKETPLACE
# ============================================================

@dp.callback_query(F.data == "channelpromo_start")
async def channelpromo_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f4e2 <b>Channel Promotion</b>\n\n"
        f"Promo Balance: <b>{get_promo_balance(callback.from_user.id)} Stars</b>\n\n"
        "Promo Stars are separate from your gift balance and referral rewards.",
        reply_markup=promo_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "channelpromo_wallet")
async def channelpromo_wallet(callback: CallbackQuery):
    await callback.message.edit_text(
        f"\U0001f4b0 <b>Promo Wallet</b>\n\nAvailable Promo Stars: <b>{get_promo_balance(callback.from_user.id)}</b>\n\nThis wallet is separate from your normal balance and referral rewards.",
        reply_markup=promo_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "channelpromo_topup")
async def channelpromo_topup(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ChannelPromoStates.waiting_topup)
    await callback.message.edit_text(
        "\U0001f4b3 <b>Add Promo Stars</b>\n\nEnter the number of Telegram Stars to pay. They will be credited only to your separate Promo Balance.",
        reply_markup=user_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.message(ChannelPromoStates.waiting_topup)
async def channelpromo_topup_amount(message: Message, state: FSMContext):
    raw=(message.text or '').strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 100000:
        await message.answer("Enter a whole number from 1 to 100000.", reply_markup=user_cancel_keyboard()); return
    amount=int(raw); uid=message.from_user.id; token=uuid.uuid4().hex
    payload=f"promowallet:{uid}:{amount}:{token}"
    await state.clear()
    await bot.send_invoice(chat_id=message.chat.id, title="Channel Promotion Wallet", description=f"Add {amount} Stars to your separate Promo Balance.", payload=payload, currency="XTR", prices=[LabeledPrice(label="Promo Balance", amount=amount)])


@dp.callback_query(F.data == "channelpromo_my")
async def channelpromo_my_promotions(callback: CallbackQuery):
    uid = callback.from_user.id
    rows = db.execute(
        "SELECT * FROM channel_promotions WHERE user_id = ? ORDER BY id DESC LIMIT 8",
        (uid,),
    ).fetchall()
    if not rows:
        await callback.message.edit_text(
            "📊 <b>My Promotions</b>\n\nYou haven't created any channel or group promotions yet.",
            reply_markup=promo_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = ["📊 <b>My Promotions</b>", ""]
    for r in rows:
        promo_id = int(r["id"])
        status_icon = "🟢 Active" if r["status"] == "active" else "✅ Completed"
        init_cnt = int(r["initial_member_count"] or 0)
        ver_cnt = int(r["verified_joins"] or 0)
        tot_cnt = int(r["total_credits"] or (ver_cnt + int(r["credits"] or 0)))
        pending_cnt = db.execute(
            "SELECT COUNT(*) AS c FROM promo_link_joins WHERE promotion_id = ? AND status = 'pending'",
            (promo_id,),
        ).fetchone()["c"]
        early_cnt = db.execute(
            "SELECT COUNT(*) AS c FROM promo_link_joins WHERE promotion_id = ? AND status = 'left_early'",
            (promo_id,),
        ).fetchone()["c"]
        inv_link = r["invite_link"] or "Not generated"
        lines.append(
            f"<b>#{promo_id} • {esc(r['channel_title'])}</b> ({status_icon})\n"
            f"   👥 Start Count: <b>{init_cnt}</b> | ✅ 3-Min Verified: <b>{ver_cnt}/{tot_cnt}</b>\n"
            f"   ⏳ Pending 3m: <b>{pending_cnt}</b> | ⚠️ Left Early: <b>{early_cnt}</b>\n"
            f"   🔗 Bot Link: <code>{esc(inv_link)}</code>"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=promo_menu_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@dp.callback_query(F.data == "channelpromo_begin")
async def channelpromo_begin(callback: CallbackQuery, state: FSMContext):
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Complete the start verification first.", show_alert=True); return
    await state.clear()
    await state.set_state(ChannelPromoStates.waiting_channel)
    await callback.message.edit_text(
        "\U0001f4e2 <b>Promote Your Channel / Group</b>\n\n"
        f"Promo Balance: <b>{get_promo_balance(callback.from_user.id)} Stars</b>\n"
        "• 1 Promo Star = 1 verified member who joins via the bot's custom invite link and stays for <b>3+ minutes</b>.\n"
        "• The bot creates its own unlimited invite link (no auto-expiry limit) and tracks baseline &amp; 3-minute retained joins.\n\n"
        "Send your Channel/Group <code>@username</code>, Chat ID (<code>-100...</code>), or forward any message from it.\n"
        "<i>Make sure the bot is an admin with Invite Users permission.</i>",
        reply_markup=user_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.message(ChannelPromoStates.waiting_channel)
async def channelpromo_channel_received(message: Message, state: FSMContext):
    target = None
    if getattr(message, "forward_from_chat", None):
        target = int(message.forward_from_chat.id)
    else:
        raw = (message.text or "").strip()
        if raw.lstrip("-").isdigit():
            target = int(raw)
        else:
            username = raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "").strip().split("/")[0].lstrip("@")
            if not username or not re.fullmatch(r"[A-Za-z0-9_]{4,32}", username):
                await message.answer(
                    "Invalid Channel/Group input. Send <code>@username</code>, Chat ID (<code>-100...</code>), or forward a message from the chat.",
                    parse_mode="HTML",
                    reply_markup=user_cancel_keyboard(),
                )
                return
            target = "@" + username

    try:
        chat = await bot.get_chat(target)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in ("administrator", "creator"):
            await message.answer("Please add the bot as an administrator first, then submit again.", reply_markup=user_cancel_keyboard()); return
        if member.status == "administrator" and getattr(member, "can_invite_users", True) is False:
            await message.answer("Please give the bot <b>Invite Users via Link</b> admin permission first.", parse_mode="HTML", reply_markup=user_cancel_keyboard()); return
        owner = await bot.get_chat_member(chat.id, message.from_user.id)
        if owner.status not in ("administrator", "creator") and not is_admin(message.from_user.id):
            await message.answer("You must be an owner or administrator of this channel/group to promote it.", reply_markup=user_cancel_keyboard()); return
    except Exception:
        await message.answer("I could not verify this channel/group. Make sure the bot is added as an administrator.", reply_markup=user_cancel_keyboard()); return

    ctype = str(chat.type)
    if ctype not in ("channel", "supergroup", "group"):
        await message.answer("Only Channels and Groups are supported.", reply_markup=user_cancel_keyboard()); return

    try:
        initial_count = int(await bot.get_chat_member_count(chat.id))
    except Exception:
        initial_count = 0

    await state.update_data(
        promo_channel_id=int(chat.id),
        promo_channel_username=chat.username or "",
        promo_channel_title=chat.title or chat.username or str(chat.id),
        promo_chat_type=ctype,
        promo_initial_count=initial_count,
    )
    await state.set_state(ChannelPromoStates.waiting_description)
    await message.answer("Send a short description (max 180 characters). No misleading claims or prohibited content.", reply_markup=user_cancel_keyboard())


@dp.message(ChannelPromoStates.waiting_description)
async def channelpromo_description_received(message: Message, state: FSMContext):
    desc=(message.text or "").strip()
    if not desc or len(desc)>180:
        await message.answer("Description must be 1–180 characters. Try again.", reply_markup=user_cancel_keyboard()); return
    await state.update_data(promo_description=desc)
    await state.set_state(ChannelPromoStates.waiting_credits)
    await message.answer(
        f"How many verified 3-minute joins do you want?\n\nRate: 1 Promo Star = 1 verified join (stayed 3+ mins via bot link).\nYour Promo Balance: <b>{get_promo_balance(message.from_user.id)} Stars</b>.\n\nSend a whole number (minimum 1).",
        reply_markup=user_cancel_keyboard(), parse_mode="HTML")


@dp.message(ChannelPromoStates.waiting_credits)
async def channelpromo_credits_received(message: Message, state: FSMContext):
    raw=(message.text or "").strip()
    if not raw.isdigit() or int(raw)<1 or int(raw)>100000:
        await message.answer("Enter a whole number from 1 to 100000.", reply_markup=user_cancel_keyboard()); return
    credits=int(raw); uid=message.from_user.id
    if get_promo_balance(uid)<credits:
        await message.answer(f"Insufficient Promo Balance. You need {credits} Promo Stars but have {get_promo_balance(uid)}. Use Add Promo Stars first.", reply_markup=promo_menu_keyboard(), parse_mode="HTML"); await state.clear(); return
    data=await state.get_data()
    chat_id = int(data['promo_channel_id'])
    # Verify admin status & create dedicated unlimited invite link before charging.
    try:
        cm=await bot.get_chat_member(chat_id, (await bot.get_me()).id)
        if cm.status not in ("administrator", "creator"):
            await message.answer("Bot admin access was removed. No Stars were charged.", reply_markup=user_cancel_keyboard()); return
        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"Promo #{uid}",
        )
        created_invite_link = invite.invite_link
    except Exception:
        await message.answer("Could not create an invite link in this chat. Ensure the bot has 'Invite Users via Link' permission. No Stars were charged.", reply_markup=user_cancel_keyboard()); return

    try:
        baseline_count = int(await bot.get_chat_member_count(chat_id))
    except Exception:
        baseline_count = int(data.get('promo_initial_count', 0))

    chat_type = data.get('promo_chat_type', 'channel')
    db.execute("UPDATE promo_wallets SET stars=stars-? WHERE user_id=? AND stars>=?", (credits,uid,credits))
    if db.execute("SELECT changes() c").fetchone()["c"] != 1:
        db.rollback(); await message.answer("Promo Balance changed; please try again.", reply_markup=promo_menu_keyboard()); await state.clear(); return
    db.execute(
        "INSERT INTO channel_promotions(user_id,channel_id,channel_title,channel_username,description,credits,status,created_at,invite_link,initial_member_count,verified_joins,total_credits,chat_type) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?)",
        (uid, chat_id, data['promo_channel_title'], data['promo_channel_username'], data['promo_description'], credits, "active", now(), created_invite_link, baseline_count, credits, chat_type),
    )
    db.commit(); await state.clear()
    await check_and_notify_level_up(uid)
    handle_str = f"@{esc(data['promo_channel_username'])}" if data['promo_channel_username'] else f"ID <code>{chat_id}</code>"
    await send_activity_log(
        f"<b>Promotion purchased</b>\nUser: <code>{uid}</code>\nChat: {esc(data['promo_channel_title'])} ({handle_str})\n"
        f"Placements: <b>{credits}</b> Promo Stars\nBaseline Members: <b>{baseline_count}</b>\nLink: {esc(created_invite_link)}"
    )
    await message.answer(
        f"\u2705 <b>Promotion Activated!</b>\n\n"
        f"📢 <b>Chat:</b> {esc(data['promo_channel_title'])}\n"
        f"👥 <b>Starting Member Count:</b> <b>{baseline_count}</b>\n"
        f"🎯 <b>Target Verified Joins (3+ min):</b> <b>{credits}</b>\n"
        f"🔗 <b>Bot Invite Link:</b> <code>{esc(created_invite_link)}</code>\n"
        f"💰 <b>Promo Balance Remaining:</b> <b>{get_promo_balance(uid)} Stars</b>\n\n"
        "Users will join through the bot's link above, and only users who stay for at least <b>3 minutes</b> are counted.",
        reply_markup=promo_menu_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )




# ============================================================
# ADMIN DASHBOARD
# ============================================================

async def send_admin_dashboard(
    message: Message,
):
    total_users = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        """
    ).fetchone()["c"]

    total_balance_units = db.execute(
        """
        SELECT COALESCE(
            SUM(balance),
            0
        ) AS c
        FROM users
        """
    ).fetchone()["c"]

    total_gifts = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM gifts
        """
    ).fetchone()["c"]

    total_payments = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM payments
        """
    ).fetchone()["c"]

    force_count = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM force_join
        """
    ).fetchone()["c"]

    await message.answer(
        "\U0001f451 <b>Admin Dashboard</b>\n\n"
        f"\U0001f464 Users: <b>{total_users}</b>\n"
        f"\U0001f4b0 User Balance: "
        f"<b>{units_to_text(total_balance_units)} \u2b50</b>\n"
        f"\U0001f381 Gifts Sent: <b>{total_gifts}</b>\n"
        f"\U0001f4b3 Payments: <b>{total_payments}</b>\n"
        f"\U0001f4e2 Force Join Chats: <b>{force_count}</b>\n\n"
        "Choose an option:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.message(Command("admin"))
async def admin_command(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "\u274c Admin only."
        )
        return

    await send_admin_dashboard(
        message
    )


# ============================================================
# ADMIN USERS
# ============================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    total_users = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    total_balance = db.execute("SELECT COALESCE(SUM(balance),0) c FROM users").fetchone()["c"]
    kb = InlineKeyboardBuilder()
    for label, action in [
        ("\U0001f50e Search User", "search"), ("\u26d4 Ban User", "ban"),
        ("\u2705 Unban User", "unban"), ("\u2795 Add Balance", "addbalance"),
        ("\u2796 Deduct Balance", "deductbalance"), ("\U0001f48e Add VIP", "vipadd"),
        ("\U0001f48e Remove VIP", "vipremove"),
    ]:
        add_inline_button(kb, label, f"admin_action:{action}", "primary")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "danger")
    kb.adjust(2, 2, 2, 1)
    await callback.message.edit_text(
        "\U0001f464 <b>User Management</b>\n\n"
        f"Registered users: <b>{total_users}</b>\n"
        f"Combined user balance: <b>{units_to_text(total_balance)} \u2b50</b>\n\n"
        "Choose an action below. All actions run through buttons.",
        reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ============================================================
# ADMIN PAYMENTS
# ============================================================

@dp.callback_query(
    F.data == "admin_payments"
)
async def admin_payments(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Admin only.",
            show_alert=True,
        )
        return

    rows = db.execute(
        """
        SELECT *
        FROM payments
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    if not rows:
        text = (
            "\U0001f4b3 <b>Payments</b>\n\n"
            "No payments yet."
        )

    else:
        text = (
            "\U0001f4b3 <b>Recent Payments</b>\n\n"
        )

        for row in rows:
            text += (
                f"#{row['id']} "
                f"<code>{row['user_id']}</code> "
                f"\u2014 <b>{row['amount']} \u2b50 credited</b>\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=admin_submenu_back_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN GIFTS
# ============================================================

@dp.callback_query(
    F.data == "admin_gifts"
)
async def admin_gifts(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Admin only.",
            show_alert=True,
        )
        return

    rows = db.execute(
        """
        SELECT *
        FROM gifts
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    if not rows:
        text = (
            "\U0001f381 <b>Gift History</b>\n\n"
            "No gifts yet."
        )

    else:
        text = (
            "\U0001f381 <b>Recent Gifts</b>\n\n"
        )

        for row in rows:
            gift_name = format_stored_gift_type(row["gift_type"] or "")

            text += (
                f"#{row['id']} {gift_name}\n"
                f"From: <code>{row['sender_id']}</code>\n"
                f"To: <code>{row['receiver_id']}</code>\n"
                f"Gift: <b>{row['telegram_price']} \u2b50</b>\n"
                f"Charged: <b>{row['balance_price']} \u2b50</b>\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=admin_submenu_back_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN FORCE JOIN DASHBOARD
# ============================================================

def admin_force_keyboard(rows):
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u2795 Add Force Join", "admin_force_add", "success", EMOJI_ADD)
    for row in rows:
        title = (row["title"] or str(row["chat_id"]))[:24]
        add_inline_button(kb, f"\u2796 Remove {title}", f"admin_force_del:{row['chat_id']}", "danger", EMOJI_REMOVE)
    add_inline_button(kb, "\u2b05\ufe0f Back", "admin_home", "danger", EMOJI_BACK)
    kb.adjust(1)
    return kb.as_markup()


@dp.callback_query(
    F.data == "admin_force"
)
async def admin_force(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Admin only.",
            show_alert=True,
        )
        return

    rows = get_force_channels()

    if not rows:
        text = (
            "\U0001f4e2 <b>Force Join</b>\n\n"
            "No force-join channels/groups configured.\n\n"
            "Tap <b>Add Force Join</b> below or use <code>/force CHAT_ID</code>.\n"
            "The bot must already be an administrator in that chat."
        )

    else:
        text = (
            "\U0001f4e2 <b>Force Join Chats</b>\n\n"
        )

        for row in rows:
            text += (
                f"\u2022 <b>{esc(row['title'])}</b>\n"
                f"  ID: <code>{row['chat_id']}</code>\n"
                f"  Link: {esc(row['invite_link'] or 'None')}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=admin_force_keyboard(rows),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(F.data == "admin_force_add")
async def admin_force_add_start(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await state.set_state(ForceStates.waiting_chat_id)
    await callback.message.edit_text(
        "\U0001f4e2 <b>Add Force Join Chat</b>\n\n"
        "Send the Chat ID (e.g. <code>-1001234567890</code>) or public <code>@username</code>.\n\n"
        "Make sure the bot is already an administrator with invite link permission.",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(ForceStates.waiting_chat_id)
async def admin_force_receive_chat_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if raw.startswith("https://t.me/") or raw.startswith("http://t.me/") or raw.startswith("t.me/"):
        raw = "@" + raw.split("t.me/", 1)[1].split("/")[0].lstrip("@")
    target = int(raw) if raw.lstrip("-").isdigit() else raw

    try:
        chat = await bot.get_chat(target)
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
    except Exception as e:
        await message.answer(
            f"\u274c Could not access chat or check permissions.\n<code>{esc(e)}</code>",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if bot_member.status not in ("administrator", "creator"):
        await message.answer(
            "\u274c <b>Bot is not an administrator.</b>\nPromote the bot first and send again, or cancel.",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    try:
        existing = get_force_channel(chat.id)
        if existing and existing["invite_link"]:
            invite_link = existing["invite_link"]
        else:
            invite = await bot.create_chat_invite_link(chat_id=chat.id, name="Gift Bot Force Join")
            invite_link = invite.invite_link
    except Exception:
        await message.answer(
            "\u274c Bot is admin, but lacks permission to create invite links.",
            reply_markup=admin_cancel_keyboard(),
        )
        return

    db.execute(
        """
        INSERT INTO force_join (chat_id, chat_type, title, invite_link, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            chat_type = excluded.chat_type,
            title = excluded.title,
            invite_link = excluded.invite_link,
            added_by = excluded.added_by
        """,
        (chat.id, str(chat.type), chat.title or chat.username or "Telegram Chat", invite_link, message.from_user.id, now()),
    )
    db.commit()
    admin_log(message.from_user.id, "force_add", chat.id)
    await state.clear()
    rows = get_force_channels()
    await message.answer(
        f"\u2705 <b>Force Join Added</b>\n\nChat: <b>{esc(chat.title or chat.username or str(chat.id))}</b>\nID: <code>{chat.id}</code>",
        reply_markup=admin_force_keyboard(rows),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("admin_force_del:"))
async def admin_force_del_callback(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    try:
        chat_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Invalid chat ID.", show_alert=True)
        return
    row = get_force_channel(chat_id)
    if row:
        remove_force_channel(chat_id)
        admin_log(callback.from_user.id, "force_remove", chat_id)
        await callback.answer(f"Removed {row['title']}")
    else:
        await callback.answer("Already removed.")
    await admin_force(callback)


# ============================================================
# ADMIN BACK
# ============================================================

@dp.callback_query(
    F.data == "dashboard_back"
)
async def dashboard_back(
    callback: CallbackQuery,
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Admin only.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "\U0001f451 <b>Admin Dashboard</b>\n\n"
        "Choose an option:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# EXTENDED ADMIN PANEL: FEATURES 1-9
# ============================================================

async def admin_only_callback(callback):
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin only.", show_alert=True)
        return False
    return True


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not await admin_only_callback(callback): return
    total = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    today = db.execute("SELECT COUNT(*) c FROM users WHERE date(created_at)=date('now')").fetchone()["c"]
    gifts = db.execute("SELECT COUNT(*) c FROM gifts").fetchone()["c"]
    stars = db.execute("SELECT COALESCE(SUM(amount),0) c FROM payments").fetchone()["c"]
    refs = db.execute("SELECT COUNT(*) c FROM referrals WHERE rewarded=1").fetchone()["c"]
    body = ("\U0001f4ca <b>Live Statistics</b>\n\n"
            f"\U0001f464 Total users: <b>{total}</b>\n\U0001f195 Joined today: <b>{today}</b>\n"
            f"\U0001f381 Gifts recorded: <b>{gifts}</b>\n\U0001f4b3 Stars deposited: <b>{stars} \u2b50</b>\n"
            f"\U0001f517 Successful referrals: <b>{refs}</b>")
    await callback.message.edit_text(body, reply_markup=admin_submenu_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_security")
async def admin_security(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    banned = db.execute("SELECT COUNT(*) c FROM blocked_users").fetchone()["c"]
    maintenance = get_setting("maintenance", "0") == "1"
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u26d4 Ban User", "admin_action:ban", "danger")
    add_inline_button(kb, "\u2705 Unban User", "admin_action:unban", "success")
    add_inline_button(kb, "\U0001f527 Turn Maintenance OFF" if maintenance else "\U0001f527 Turn Maintenance ON", "admin_toggle_maintenance", "success" if maintenance else "danger")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "primary")
    kb.adjust(2, 1, 1)
    await callback.message.edit_text(
        "\U0001f6e1\ufe0f <b>Security & Access</b>\n\n"
        f"\u26d4 Banned users: <b>{banned}</b>\n"
        f"\U0001f527 Maintenance: <b>{'ON' if maintenance else 'OFF'}</b>\n\n"
        "Manage bans and maintenance using the buttons below.",
        reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    value = "0" if get_setting("maintenance", "0") == "1" else "1"
    set_setting("maintenance", value)
    admin_log(callback.from_user.id, "maintenance", value)
    await admin_security(callback)


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await callback.message.edit_text("\U0001f451 <b>Admin Dashboard</b>\n\nChoose a management section:", reply_markup=admin_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    rows = db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 15").fetchall()
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u2795 Create Promo", "admin_promo_create", "success")
    for row in rows:
        prefix = "\U0001f7e2 Disable" if row["enabled"] else "\u26aa Enable"
        label = f"{prefix} {row['code']}"
        add_inline_button(kb, label[:60], f"admin_promo_toggle:{row['code']}", "primary")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "danger")
    kb.adjust(1, 2, 1)
    lines = ["\U0001f39f\ufe0f <b>Promo Code Manager</b>", "", "Create promo with the button. Users redeem from the main menu.", ""]
    if rows:
        for row in rows:
            lines.append(f"\u2022 <code>{esc(row['code'])}</code> \u2014 {units_to_text(row['reward_units'])} \u2b50 | {row['used_count']}/{row['max_uses']} used | {'ON' if row['enabled'] else 'OFF'}")
    else:
        lines.append("No promo codes created yet.")
    await callback.message.edit_text("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_promo_create)
    await callback.message.edit_text(
        "\U0001f39f\ufe0f <b>Create Promo Code</b>\n\nSend details in one message in this format:\n<code>CODE STARS USES</code>\n\nExample: <code>WELCOME 5 100</code>",
        reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_promo_toggle:"))
async def admin_promo_toggle_button(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    code = callback.data.split(":", 1)[1].upper()
    row = db.execute("SELECT enabled FROM promo_codes WHERE code=?", (code,)).fetchone()
    if not row:
        await callback.answer("Promo code not found.", show_alert=True)
        return
    new_value = 0 if row["enabled"] else 1
    db.execute("UPDATE promo_codes SET enabled=? WHERE code=?", (new_value, code))
    db.commit()
    admin_log(callback.from_user.id, "promo_toggle", f"{code} {'on' if new_value else 'off'}")
    await admin_promos(callback)


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback): return
    await state.set_state(AdminStates.waiting_broadcast)
    kb = InlineKeyboardBuilder(); add_inline_button(kb, "\u274c Cancel", "admin_cancel_task", "danger")
    await callback.message.edit_text("\U0001f4e2 <b>Broadcast</b>\n\nSend the message you want delivered to all users. Text, photo, or video supported.\n\nUse Cancel to stop.", reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


BROADCAST_CANCEL_REQUESTS = set()


@dp.callback_query(F.data == "admin_broadcast_stop")
async def admin_broadcast_stop(callback: CallbackQuery):
    if not await admin_only_callback(callback): return
    BROADCAST_CANCEL_REQUESTS.add(callback.from_user.id)
    await callback.answer("Broadcast cancellation requested.", show_alert=True)


@dp.message(AdminStates.waiting_broadcast)
async def admin_broadcast_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.clear()
    ids = [r["user_id"] for r in db.execute("SELECT user_id FROM users").fetchall()]
    sent = failed = 0
    BROADCAST_CANCEL_REQUESTS.discard(message.from_user.id)
    stop_kb = InlineKeyboardBuilder()
    add_inline_button(stop_kb, "\u23f9 Cancel Broadcast", "admin_broadcast_stop", "danger")
    status = await message.answer(f"\U0001f4e2 Starting broadcast to {len(ids)} users...", reply_markup=stop_kb.as_markup())
    cancelled = False
    for uid in ids:
        if message.from_user.id in BROADCAST_CANCEL_REQUESTS:
            cancelled = True
            break
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 20 == 0:
            try: await status.edit_text(f"\U0001f4e2 Broadcast running\nDelivered: {sent} | Failed: {failed}", reply_markup=stop_kb.as_markup())
            except Exception: pass
            await asyncio.sleep(1)
    BROADCAST_CANCEL_REQUESTS.discard(message.from_user.id)
    admin_log(message.from_user.id, "broadcast", f"sent={sent}, failed={failed}, cancelled={cancelled}")
    final_state = "cancelled" if cancelled else "finished"
    icon = "\u26a0\ufe0f" if cancelled else "\u2705"
    await status.edit_text(f"{icon} <b>Broadcast {final_state}</b>\n\nDelivered: <b>{sent}</b>\nFailed: <b>{failed}</b>", parse_mode="HTML")


@dp.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\U0001f4b0 Change Gift Price", "admin_setting_input:giftprice", "primary")
    add_inline_button(kb, "\U0001f517 Change Referral Reward", "admin_setting_input:refreward", "primary")
    add_inline_button(kb, "\U0001f6e1\ufe0f Security / Maintenance", "admin_security", "primary")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "danger")
    kb.adjust(2, 1, 1)
    await callback.message.edit_text(
        "\u2699\ufe0f <b>Bot Settings</b>\n\n"
        f"Default gift price: <b>{GIFT_PRICE_STARS} \u2b50</b>\n"
        f"Referral reward: <b>{units_to_text(REFERRAL_REWARD_UNITS)} \u2b50</b>\n"
        "Gift transaction fee: <b>Disabled</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_setting_input:"))
async def admin_setting_input(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    which = callback.data.split(":", 1)[1]
    await state.clear()
    if which == "giftprice":
        await state.set_state(AdminStates.waiting_gift_price)
        prompt = "Send the new gift price in whole Stars (1\u2013100000)."
    elif which == "refreward":
        await state.set_state(AdminStates.waiting_referral_reward)
        prompt = "Send the referral reward in whole Stars (0\u201310000)."
    else:
        await callback.answer("Unknown setting.", show_alert=True)
        return
    await callback.message.edit_text("\u2699\ufe0f <b>Update Setting</b>\n\n" + prompt, reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


EDIT_GIFTS_PER_PAGE = 12


def build_edit_gifts_view(items, page: int = 0):
    total = len(items)
    total_pages = max(1, math.ceil(total / EDIT_GIFTS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * EDIT_GIFTS_PER_PAGE
    page_items = items[start : start + EDIT_GIFTS_PER_PAGE]

    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "🔄 Refresh", "admin_gifts_refresh", "primary", EMOJI_SETTINGS)
    row_sizes = [1]

    for item in page_items:
        gid = item["id"]
        emoji = normalize_gift_display_emoji(item.get("emoji") or "🎁")
        stars = item.get("star_count", 0)
        enabled = is_gift_id_enabled(gid, emoji)
        dot = "\U0001f7e2" if enabled else "\u26aa"
        state_lbl = "ON" if enabled else "OFF"
        lim = " [L]" if item.get("is_limited") else ""
        label = f"{dot} {emoji} {stars}\u2b50{lim} {state_lbl}"
        kb.button(
            text=label,
            callback_data=f"admin_gift_id_toggle:{gid}:{page}",
            style="success" if enabled else "danger",
        )

    if page_items:
        gift_rows = [2] * (len(page_items) // 2)
        if len(page_items) % 2:
            gift_rows.append(1)
        row_sizes.extend(gift_rows)

    if total_pages > 1:
        prev_p = (page - 1) % total_pages
        next_p = (page + 1) % total_pages
        kb.button(text="⬅️ Prev", callback_data=f"admin_edit_gifts_page:{prev_p}", style="primary")
        kb.button(text=f"{page + 1}/{total_pages}", callback_data="admin_edit_gifts_noop", style="primary")
        kb.button(text="Next ➡️", callback_data=f"admin_edit_gifts_page:{next_p}", style="primary")
        row_sizes.append(3)

    if total > 0:
        kb.button(text="\U0001f7e2 All ON", callback_data=f"admin_gifts_all:1:{page}", style="success")
        kb.button(text="\u26aa All OFF", callback_data=f"admin_gifts_all:0:{page}", style="danger")
        row_sizes.append(2)

    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "danger", EMOJI_BACK)
    row_sizes.append(1)
    kb.adjust(*row_sizes)

    enabled_count = sum(1 for it in items if is_gift_id_enabled(it["id"], it.get("emoji", "")))
    updated_at = get_setting("cached_gifts_updated_at", "Never")
    if total == 0:
        body = (
            "\U0001f381 <b>Edit Gifts</b>\n\n"
            "No sendable gifts loaded yet.\n"
            "Tap <b>Refresh</b> below to fetch all available gifts from Telegram."
        )
    else:
        body = (
            "\U0001f381 <b>Edit Gifts</b>\n\n"
            f"Total sendable gifts: <b>{total}</b>\n"
            f"Active (ON): <b>{enabled_count}</b> | Disabled (OFF): <b>{total - enabled_count}</b>\n"
            f"Last refreshed: <code>{esc(updated_at)}</code>\n\n"
            "Tap any gift to toggle <b>ON / OFF</b>, or tap <b>Refresh</b> to sync with Telegram:"
        )
    return body, kb.as_markup()


@dp.callback_query(F.data == "admin_edit_gifts")
async def admin_edit_gifts(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    items = get_cached_gifts()
    if not items:
        try:
            items = await refresh_available_gifts_cache()
        except Exception:
            logger.exception("Initial gift refresh failed")
            items = []
    body, markup = build_edit_gifts_view(items, page=0)
    await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_gifts_refresh")
async def admin_gifts_refresh(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    try:
        items = await refresh_available_gifts_cache()
    except Exception as e:
        logger.exception("Gift refresh failed")
        await callback.answer(f"Failed to refresh gifts: {e}", show_alert=True)
        return
    admin_log(callback.from_user.id, "gifts_refresh", f"loaded={len(items)}")
    body, markup = build_edit_gifts_view(items, page=0)
    try:
        await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer(f"✅ Refreshed! {len(items)} sendable gift(s) found.", show_alert=True)


@dp.callback_query(F.data.startswith("admin_edit_gifts_page:"))
async def admin_edit_gifts_page(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        page = 0
    items = get_cached_gifts()
    body, markup = build_edit_gifts_view(items, page=page)
    try:
        await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(F.data == "admin_edit_gifts_noop")
async def admin_edit_gifts_noop(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_gift_id_toggle:"))
async def admin_gift_id_toggle(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Invalid gift.", show_alert=True)
        return
    gid = parts[1]
    page = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
    items = get_cached_gifts()
    target = next((it for it in items if str(it["id"]) == gid), None)
    emoji = target.get("emoji", "") if target else ""
    new_val = "0" if is_gift_id_enabled(gid, emoji) else "1"
    set_setting(f"gift_enabled_id_{gid}", new_val)
    if "🧸" in emoji:
        set_setting("gift_enabled_teddy", new_val)
    elif any(x in emoji for x in ("❤", "💕", "💗", "💖", "💓", "💞", "💘", "💝", "💟")):
        set_setting("gift_enabled_love", new_val)
    admin_log(callback.from_user.id, "gift_toggle", f"id={gid} {'on' if new_val == '1' else 'off'}")
    body, markup = build_edit_gifts_view(items, page=page)
    try:
        await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer(f"{emoji or 'Gift'} is now {'ON' if new_val == '1' else 'OFF'}")


@dp.callback_query(F.data.startswith("admin_gifts_all:"))
async def admin_gifts_all(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    parts = callback.data.split(":")
    val = "1" if len(parts) >= 2 and parts[1] == "1" else "0"
    page = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
    items = get_cached_gifts()
    for it in items:
        set_setting(f"gift_enabled_id_{it['id']}", val)
    set_setting("gift_enabled_teddy", val)
    set_setting("gift_enabled_love", val)
    admin_log(callback.from_user.id, "gifts_bulk_toggle", f"all={'on' if val == '1' else 'off'}")
    body, markup = build_edit_gifts_view(items, page=page)
    try:
        await callback.message.edit_text(body, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer(f"All gifts turned {'ON' if val == '1' else 'OFF'}")


@dp.callback_query(F.data == "admin_vip")
async def admin_vip(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    rows = db.execute("SELECT user_id, expires_at FROM vip_users ORDER BY created_at DESC LIMIT 15").fetchall()
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u2795 Add VIP User", "admin_action:vipadd", "success")
    add_inline_button(kb, "\u2796 Remove VIP User", "admin_action:vipremove", "danger")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "primary")
    kb.adjust(2, 1)
    txt = "\U0001f48e <b>VIP Users</b>\n\n"
    txt += "\n".join(f"\u2022 <code>{r['user_id']}</code> \u2014 {esc(r['expires_at'] or 'No expiry')}" for r in rows) if rows else "No VIP users yet."
    await callback.message.edit_text(txt, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    if not await admin_only_callback(callback): return
    rows = db.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 12").fetchall()
    txt = "\U0001f4dc <b>Admin Activity Logs</b>\n\n"
    txt += "\n".join(f"#{r['id']} \u2022 <code>{r['admin_id']}</code> \u2022 {esc(r['action'])}\n{esc(r['details'])} \u2014 {esc(r['created_at'])}" for r in rows) if rows else "No admin actions logged yet."
    await callback.message.edit_text(txt, reply_markup=admin_submenu_back_keyboard(), parse_mode="HTML")
    await callback.answer()




# ============================================================
# INLINE ADMIN ACTIONS + PROMO REDEMPTION
# ============================================================

def admin_cancel_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u274c Cancel", "admin_cancel_task", "danger", EMOJI_CANCEL)
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "primary")
    kb.adjust(1, 1)
    return kb.as_markup()



# ============================================================
# LEADERBOARD (REFER BOARD, LEVEL BOARD, BALANCE BOARD)
# ============================================================

def leaderboard_menu_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "🏆 Refer Board", "lb:refer", "success", EMOJI_TROPHY)
    add_inline_button(kb, "🏅 Level Board", "lb:level", "success", EMOJI_MEDAL)
    add_inline_button(kb, "💰 Balance Board", "lb:balance", "success", EMOJI_BALANCE)
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def leaderboard_sub_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "⬅️ Back to Leaderboards", "dashboard_leaderboard", "primary", EMOJI_BACK)
    add_inline_button(kb, "⬅️ Back to Menu", "dashboard_home", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(2)
    return kb.as_markup()


@dp.callback_query(F.data == "dashboard_leaderboard")
async def dashboard_leaderboard(callback: CallbackQuery, state: FSMContext):
    if is_banned(callback.from_user.id):
        await callback.answer("Your access is restricted.", show_alert=True)
        return
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "🏆 <b>Top Leaderboards</b>\n\nChoose a leaderboard category below:",
        reply_markup=leaderboard_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("lb:"))
async def leaderboard_view_callback(callback: CallbackQuery):
    if is_banned(callback.from_user.id):
        await callback.answer("Your access is restricted.", show_alert=True)
        return
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return

    kind = callback.data.split(":", 1)[1]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    def _get_first_name_only(raw_name, uid):
        cleaned = (raw_name or "").strip()
        if not cleaned:
            return f"User {uid}"
        return cleaned.split()[0]

    if kind == "refer":
        title = "🏆 <b>Top Referrers Leaderboard</b>"
        rows = db.execute(
            '''
            SELECT referrer_user_id AS uid, COUNT(*) AS cnt
            FROM referrals
            WHERE rewarded = 1
            GROUP BY referrer_user_id
            ORDER BY cnt DESC
            LIMIT 10
            '''
        ).fetchall()
        lines = [title, ""]
        if not rows:
            lines.append("<i>No referral leaders yet.</i>")
        else:
            for idx, r in enumerate(rows):
                uid = int(r["uid"])
                val = int(r["cnt"])
                user_info = db.execute("SELECT first_name FROM users WHERE user_id=?", (uid,)).fetchone()
                raw_n = user_info["first_name"] if user_info and user_info["first_name"] else f"User {uid}"
                fname = _get_first_name_only(raw_n, uid)
                hidden_mention = f'<a href="tg://user?id={uid}">{esc(fname)}</a>'
                medal = medals[idx] if idx < len(medals) else f"{idx+1}."
                lines.append(f"{medal} {hidden_mention} — <b>{val} referrals</b>")

    elif kind == "level":
        title = "🏅 <b>Top Tier Level Leaderboard</b>"
        users = db.execute("SELECT user_id, first_name FROM users LIMIT 250").fetchall()
        ranked = []
        for u in users:
            uid = int(u["user_id"])
            lvl = get_user_level(uid)
            exp = get_user_exp_units(uid)
            ranked.append((uid, lvl, exp, u["first_name"]))
        ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
        top10 = ranked[:10]
        lines = [title, ""]
        if not top10:
            lines.append("<i>No tiered users yet.</i>")
        else:
            for idx, (uid, lvl, exp, fname) in enumerate(top10):
                raw_n = fname if fname else f"User {uid}"
                first_name_only = _get_first_name_only(raw_n, uid)
                hidden_mention = f'<a href="tg://user?id={uid}">{esc(first_name_only)}</a>'
                lvl_emoji = level_to_emoji(lvl)
                lines.append(f"{idx + 1}. {lvl_emoji} {hidden_mention}")

    elif kind == "balance":
        title = "💰 <b>Top Balance Leaderboard</b>"
        rows = db.execute(
            '''
            SELECT user_id AS uid, balance
            FROM users
            ORDER BY balance DESC
            LIMIT 10
            '''
        ).fetchall()
        lines = [title, ""]
        if not rows:
            lines.append("<i>No balance leaders yet.</i>")
        else:
            for idx, r in enumerate(rows):
                uid = int(r["uid"])
                bal_units = int(r["balance"])
                if bal_units <= 0:
                    continue
                user_info = db.execute("SELECT first_name FROM users WHERE user_id=?", (uid,)).fetchone()
                raw_n = user_info["first_name"] if user_info and user_info["first_name"] else f"User {uid}"
                fname = _get_first_name_only(raw_n, uid)
                hidden_mention = f'<a href="tg://user?id={uid}">{esc(fname)}</a>'
                medal = medals[idx] if idx < len(medals) else f"{idx+1}."
                lines.append(f"{medal} {hidden_mention} — <b>{units_to_text(bal_units)} ⭐</b>")
    else:
        await callback.answer("Invalid leaderboard.", show_alert=True)
        return

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=leaderboard_sub_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


def user_cancel_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\u274c Cancel", "user_cancel_operation", get_button_style("CANCEL"), EMOJI_CANCEL)
    add_inline_button(kb, "\u2b05\ufe0f Back to Menu", "user_back_menu", get_button_style("BACK_MENU"), EMOJI_BACK)
    kb.adjust(1, 1)
    return kb.as_markup()


def admin_parse_stars(value):
    value = str(value).strip()
    if not re.fullmatch(r"\d+(?:\.5)?", value):
        raise ValueError("Enter a whole or half-Star amount, e.g. 10 or 10.5.")
    if value.endswith(".5"):
        return int(value[:-2]) * 2 + 1
    return int(value) * 2


def admin_user_profile_keyboard(user_id):
    kb = InlineKeyboardBuilder()
    banned = is_banned(user_id)
    vip = db.execute("SELECT 1 FROM vip_users WHERE user_id=?", (user_id,)).fetchone() is not None
    add_inline_button(kb, "\u2705 Unban User" if banned else "\u26d4 Ban User", f"admin_profile:{'unban' if banned else 'ban'}:{user_id}", "success" if banned else "danger")
    add_inline_button(kb, "\u2795 Add Balance", f"admin_profile:addbalance:{user_id}", "success")
    add_inline_button(kb, "\u2796 Deduct Balance", f"admin_profile:deductbalance:{user_id}", "danger")
    add_inline_button(kb, "\U0001f48e Remove VIP" if vip else "\U0001f48e Add VIP", f"admin_profile:{'vipremove' if vip else 'vipadd'}:{user_id}", "primary")
    add_inline_button(kb, "\u2b05\ufe0f Users", "admin_users", "primary")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def format_admin_user(row):
    uid = int(row["user_id"])
    username = f"@{row['username']}" if row["username"] else "None"
    ban_row = db.execute("SELECT reason FROM blocked_users WHERE user_id=?", (uid,)).fetchone()
    vip_row = db.execute("SELECT expires_at FROM vip_users WHERE user_id=?", (uid,)).fetchone()
    gifts = db.execute("SELECT COUNT(*) c FROM gifts WHERE sender_id=?", (uid,)).fetchone()["c"]
    return (
        "\U0001f464 <b>User Profile</b>\n\n"
        f"\U0001f194 ID: <code>{uid}</code>\n"
        f"\U0001f464 Username: <b>{esc(username)}</b>\n"
        f"\U0001f4db Name: <b>{esc(row['first_name'] or 'None')}</b>\n"
        f"\U0001f4b0 Balance: <b>{units_to_text(row['balance'])} \u2b50</b>\n"
        f"\U0001f381 Gifts sent: <b>{gifts}</b>\n"
        f"\u26d4 Banned: <b>{'Yes' if ban_row else 'No'}</b>\n"
        f"\U0001f48e VIP: <b>{'Yes' if vip_row else 'No'}</b>\n"
        f"\U0001f4c5 Joined: <code>{esc(row['created_at'])}</code>"
    )


async def show_admin_user(message, user_id):
    row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        await message.answer("\u274c User not found in the bot database.", reply_markup=admin_users_keyboard())
        return
    await message.answer(format_admin_user(row), reply_markup=admin_user_profile_keyboard(user_id), parse_mode="HTML")


def admin_users_keyboard():
    kb = InlineKeyboardBuilder()
    actions = [("\U0001f50e Search User", "search"), ("\u26d4 Ban", "ban"), ("\u2705 Unban", "unban"), ("\u2795 Add Balance", "addbalance"), ("\u2796 Deduct Balance", "deductbalance"), ("\U0001f48e Add VIP", "vipadd"), ("\U0001f48e Remove VIP", "vipremove")]
    for label, action in actions:
        add_inline_button(kb, label, f"admin_action:{action}", "primary")
    add_inline_button(kb, "\u2b05\ufe0f Admin Menu", "admin_home", "danger")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


@dp.callback_query(F.data == "dashboard_admin")
async def dashboard_admin(callback: CallbackQuery):
    if not await admin_only_callback(callback):
        return
    await callback.message.edit_text("\U0001f451 <b>Admin Dashboard</b>\n\nChoose a management section:", reply_markup=admin_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "dashboard_redeem_promo")
async def dashboard_redeem_promo(callback: CallbackQuery, state: FSMContext):
    if is_banned(callback.from_user.id):
        await callback.answer("Your access is restricted.", show_alert=True)
        return
    if not await user_joined_force_channels(callback.from_user.id):
        await callback.answer("Join required first.", show_alert=True)
        return
    await state.clear()
    await state.set_state(PromoStates.waiting_code)
    await callback.message.edit_text("\U0001f39f\ufe0f <b>Redeem Promo Code</b>\n\nSend your promo code below.", reply_markup=user_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "user_cancel_operation")
async def user_cancel_operation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("\u274c <b>Operation cancelled.</b>\n\nChoose an option:", reply_markup=dashboard_keyboard(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "user_back_menu")
async def user_back_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(callback.from_user)
    await callback.message.edit_text(
        build_main_menu_text(callback.from_user),
        reply_markup=dashboard_keyboard(callback.from_user.id),
        parse_mode="HTML",
    )
    await callback.answer("Back to menu")


@dp.message(PromoStates.waiting_code)
async def promo_redeem_message(message: Message, state: FSMContext):
    if not await require_force_join(message):
        await state.clear()
        return
    ensure_user(message.from_user)
    code = (message.text or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,32}", code):
        await message.answer("\u274c Invalid promo code format. Try again or cancel.", reply_markup=user_cancel_keyboard())
        return
    row = db.execute("SELECT * FROM promo_codes WHERE code=? AND enabled=1", (code,)).fetchone()
    if not row or row["used_count"] >= row["max_uses"]:
        await message.answer("\u274c Promo code is invalid, disabled, or fully used.", reply_markup=user_cancel_keyboard())
        return
    if row["expires_at"] and row["expires_at"] < now():
        await message.answer("\u274c This promo code has expired.", reply_markup=user_cancel_keyboard())
        return
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO promo_uses(code,user_id,used_at) VALUES(?,?,?)", (code, message.from_user.id, now()))
        db.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE code=? AND enabled=1 AND used_count<max_uses", (code,))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("Promo usage limit reached.")
        db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row["reward_units"], message.from_user.id))
        db.execute("INSERT INTO transactions(user_id,amount,type,description,created_at) VALUES(?,?,?,?,?)", (message.from_user.id, row["reward_units"], "promo_reward", f"Promo {code}", now()))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        await message.answer("\u274c You have already redeemed this promo.", reply_markup=dashboard_keyboard(message.from_user.id))
        await state.clear()
        return
    except Exception:
        db.rollback()
        await message.answer("\u274c Could not redeem promo code. It may have reached its usage limit.", reply_markup=dashboard_keyboard(message.from_user.id))
        await state.clear()
        return
    await state.clear()
    await check_and_notify_level_up(message.from_user.id)
    cur_bal = get_balance_stars(message.from_user.id)
    await message.answer(
        f"✅ Added <b>{units_to_text(row['reward_units'])} ⭐</b> • Balance: <b>{cur_bal} ⭐</b>",
        reply_markup=dashboard_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("admin_action:"))
async def admin_action_start(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    action = callback.data.split(":", 1)[1]
    allowed = {"search", "ban", "unban", "addbalance", "deductbalance", "vipadd", "vipremove"}
    if action not in allowed:
        await callback.answer("Unknown action.", show_alert=True)
        return
    await state.clear()
    await state.update_data(admin_action=action)
    await state.set_state(AdminStates.waiting_user_id)
    labels = {"search": "search", "ban": "ban", "unban": "unban", "addbalance": "add balance to", "deductbalance": "deduct balance from", "vipadd": "add as VIP", "vipremove": "remove VIP from"}
    await callback.message.edit_text(f"\U0001f464 <b>User Management</b>\n\nSend the Telegram user ID to {labels[action]}.", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.message(AdminStates.waiting_user_id)
async def admin_receive_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("admin_action")
    raw = (message.text or "").strip()
    if action == "search" and raw.startswith("@"):
        row = db.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (raw.lstrip("@"),)).fetchone()
        if row:
            await state.clear()
            await message.answer(format_admin_user(row), reply_markup=admin_user_profile_keyboard(row["user_id"]), parse_mode="HTML")
        else:
            await message.answer("\u274c User not found. Send another ID or @username, or cancel.", reply_markup=admin_cancel_keyboard())
        return
    try:
        uid = int(raw)
        if uid <= 0:
            raise ValueError
    except ValueError:
        await message.answer("\u274c Enter a valid numeric Telegram user ID.", reply_markup=admin_cancel_keyboard())
        return
    if action == "search":
        await state.clear()
        await show_admin_user(message, uid)
        return
    if action in ("addbalance", "deductbalance"):
        await state.update_data(target_user_id=uid)
        await state.set_state(AdminStates.waiting_balance_amount)
        await message.answer(f"\U0001f4b0 Send the amount in Stars for user <code>{uid}</code>. You may use .5 (example: 10.5).", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
        return
    if action == "ban" and uid in ADMIN_IDS:
        await state.clear()
        await message.answer("\u274c You cannot ban a configured admin account.", reply_markup=admin_users_keyboard())
        return
    if action == "ban":
        db.execute("INSERT INTO blocked_users(user_id,reason,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason", (uid, "Restricted by admin", now()))
        db.commit(); admin_log(message.from_user.id, "ban", uid)
        result = f"\u26d4 User <code>{uid}</code> has been banned."
    elif action == "unban":
        db.execute("DELETE FROM blocked_users WHERE user_id=?", (uid,)); db.commit(); admin_log(message.from_user.id, "unban", uid)
        result = f"\u2705 User <code>{uid}</code> has been unbanned."
    elif action == "vipadd":
        db.execute("INSERT INTO vip_users(user_id,added_by,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET added_by=excluded.added_by", (uid, message.from_user.id, now())); db.commit(); admin_log(message.from_user.id, "vip_add", uid)
        result = f"\U0001f48e User <code>{uid}</code> added as VIP."
    else:
        db.execute("DELETE FROM vip_users WHERE user_id=?", (uid,)); db.commit(); admin_log(message.from_user.id, "vip_remove", uid)
        result = f"\U0001f48e VIP status removed from <code>{uid}</code>."
    await state.clear()
    await message.answer(result, reply_markup=admin_users_keyboard(), parse_mode="HTML")


@dp.message(AdminStates.waiting_balance_amount)
async def admin_receive_balance_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    uid = int(data.get("target_user_id", 0))
    action = data.get("admin_action")
    try:
        units = admin_parse_stars((message.text or "").strip())
        if units <= 0:
            raise ValueError("Amount must be greater than zero.")
    except Exception as exc:
        await message.answer(f"\u274c {esc(exc)}\nSend a valid amount or cancel.", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
        return
    row = db.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    if action == "deductbalance" and not row:
        await message.answer("\u274c User not found.", reply_markup=admin_cancel_keyboard())
        return
    if action == "deductbalance" and int(row["balance"]) < units:
        await message.answer("\u274c User does not have enough balance.", reply_markup=admin_cancel_keyboard())
        return
    try:
        if not row:
            db.execute("INSERT INTO users(user_id,username,first_name,balance,created_at) VALUES(?,?,?,?,?)", (uid, "", "", 0, now()))
            db.commit()
        db.execute("BEGIN IMMEDIATE")
        delta = units if action == "addbalance" else -units
        db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (delta, uid))
        db.execute("INSERT INTO transactions(user_id,amount,type,description,created_at) VALUES(?,?,?,?,?)", (uid, delta, "admin_credit" if delta > 0 else "admin_debit", f"Admin {message.from_user.id} manual balance adjustment", now()))
        db.commit()
    except Exception:
        db.rollback()
        await message.answer("\u274c Could not update balance. Try again or cancel.", reply_markup=admin_cancel_keyboard())
        return
    admin_log(message.from_user.id, "balance_add" if delta > 0 else "balance_deduct", f"user={uid}, units={units}")
    await state.clear()
    await message.answer(f"\u2705 <b>Balance updated</b>\n\nUser: <code>{uid}</code>\nChange: <b>{'+' if delta > 0 else '-'}{units_to_text(units)} \u2b50</b>\nNew balance: <b>{get_balance_stars(uid)} \u2b50</b>", reply_markup=admin_users_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("admin_profile:"))
async def admin_profile_action(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    try:
        _, action, raw_uid = callback.data.split(":", 2)
        uid = int(raw_uid)
    except Exception:
        await callback.answer("Invalid user action.", show_alert=True)
        return
    if action in ("addbalance", "deductbalance"):
        await state.clear(); await state.update_data(admin_action=action, target_user_id=uid)
        await state.set_state(AdminStates.waiting_balance_amount)
        await callback.message.edit_text(f"\U0001f4b0 Send amount in Stars for <code>{uid}</code> (example: 10.5).", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    if action == "ban" and uid in ADMIN_IDS:
        await callback.answer("You cannot ban a configured admin account.", show_alert=True)
        return
    if action == "ban":
        db.execute("INSERT INTO blocked_users(user_id,reason,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason", (uid, "Restricted by admin", now())); db.commit(); admin_log(callback.from_user.id, "ban", uid)
    elif action == "unban":
        db.execute("DELETE FROM blocked_users WHERE user_id=?", (uid,)); db.commit(); admin_log(callback.from_user.id, "unban", uid)
    elif action == "vipadd":
        db.execute("INSERT INTO vip_users(user_id,added_by,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET added_by=excluded.added_by", (uid, callback.from_user.id, now())); db.commit(); admin_log(callback.from_user.id, "vip_add", uid)
    elif action == "vipremove":
        db.execute("DELETE FROM vip_users WHERE user_id=?", (uid,)); db.commit(); admin_log(callback.from_user.id, "vip_remove", uid)
    row = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if row:
        await callback.message.edit_text(format_admin_user(row), reply_markup=admin_user_profile_keyboard(uid), parse_mode="HTML")
    else:
        await callback.message.edit_text(f"Action completed for <code>{uid}</code>.", reply_markup=admin_users_keyboard(), parse_mode="HTML")
    await callback.answer("Updated.")


@dp.message(AdminStates.waiting_promo_create)
async def admin_receive_promo_create(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("\u274c Send exactly: <code>CODE STARS USES</code> (example: <code>WELCOME 5 100</code>).", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
        return
    code = parts[0].upper()
    try:
        stars = int(parts[1]); uses = int(parts[2])
    except ValueError:
        await message.answer("\u274c Stars and uses must be whole numbers.", reply_markup=admin_cancel_keyboard())
        return
    if not re.fullmatch(r"[A-Z0-9]{2,32}", code) or not 1 <= stars <= 100000 or not 1 <= uses <= 100000:
        await message.answer("\u274c Invalid code, reward, or usage limit.", reply_markup=admin_cancel_keyboard())
        return
    try:
        db.execute("INSERT INTO promo_codes(code,reward_units,max_uses,created_at) VALUES(?,?,?,?)", (code, stars * UNITS_PER_STAR, uses, now())); db.commit()
    except sqlite3.IntegrityError:
        await message.answer("\u274c That promo code already exists. Send another code or cancel.", reply_markup=admin_cancel_keyboard())
        return
    admin_log(message.from_user.id, "promo_create", f"{code} {stars} stars / {uses} uses")
    await state.clear()
    await message.answer(f"\u2705 Promo <code>{code}</code> created: {stars} \u2b50, {uses} uses.", reply_markup=admin_keyboard(), parse_mode="HTML")


@dp.message(AdminStates.waiting_gift_price)
async def admin_receive_gift_price(message: Message, state: FSMContext):
    global GIFT_PRICE_STARS
    if not is_admin(message.from_user.id):
        await state.clear(); return
    try:
        price = int((message.text or "").strip())
        if not 1 <= price <= 100000: raise ValueError
    except ValueError:
        await message.answer("\u274c Enter a whole number from 1 to 100000.", reply_markup=admin_cancel_keyboard())
        return
    GIFT_PRICE_STARS = price; set_setting("gift_price_stars", price); admin_log(message.from_user.id, "gift_price", price)
    await state.clear()
    await message.answer(f"\u2705 Gift price updated to <b>{price} \u2b50</b>.", reply_markup=admin_keyboard(), parse_mode="HTML")


@dp.message(AdminStates.waiting_referral_reward)
async def admin_receive_referral_reward(message: Message, state: FSMContext):
    global REFERRAL_REWARD_UNITS
    if not is_admin(message.from_user.id):
        await state.clear(); return
    try:
        stars = int((message.text or "").strip())
        if not 0 <= stars <= 10000: raise ValueError
    except ValueError:
        await message.answer("\u274c Enter a whole number from 0 to 10000.", reply_markup=admin_cancel_keyboard())
        return
    REFERRAL_REWARD_UNITS = stars * UNITS_PER_STAR; set_setting("referral_reward_units", REFERRAL_REWARD_UNITS); admin_log(message.from_user.id, "referral_reward", stars)
    await state.clear()
    await message.answer(f"\u2705 Referral reward set to <b>{stars} \u2b50</b> for future successful referrals.", reply_markup=admin_keyboard(), parse_mode="HTML")



# ============================================================
# ADMIN CHANGE VARIABLES (IMAGE LINK, LOGS CHANNEL, VOUCH CHANNEL)
# ============================================================

def admin_variables_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "\U0001f4dd Change Bot Heading", "admin_var_input:heading", "primary", EMOJI_NOTE)
    add_inline_button(kb, "\u2699\ufe0f Change Button Colour", "admin_var_input:btn_color", "primary", EMOJI_SETTINGS)
    add_inline_button(kb, "\U0001f4ca Change Button Position", "admin_var_input:btn_layout", "primary", EMOJI_STATS)
    add_inline_button(kb, "\U0001f5bc\ufe0f Change Media Link (Photo/GIF/Video)", "admin_var_input:banner", "primary", EMOJI_SETTINGS)
    add_inline_button(kb, "\U0001f4dc Change Logs Channel", "admin_var_input:logs", "primary", EMOJI_LOGS)
    add_inline_button(kb, "\u2b50 Change Vouch Channel", "admin_var_input:vouch", "primary", EMOJI_STAR)
    add_inline_button(kb, "\U0001f381 Change Emoji ID", "admin_var_input:emoji", "primary", EMOJI_GIFT)
    add_inline_button(kb, "\u2b05\ufe0f Back", "admin_home", "danger", EMOJI_BACK)
    kb.adjust(1, 2, 1, 2, 1, 1)
    return kb.as_markup()


@dp.callback_query(F.data == "admin_variables")
async def admin_variables(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    heading_val = get_bot_heading()
    banner_val = get_banner_source()
    logs_val = get_log_channel_id() or "Not set"
    vouch_val = get_vouch_channel_id() or "Not set"
    active_emojis = len(CUSTOM_EMOJI_IDS)
    text = (
        "\U0001f527 <b>Change Variables</b>\n\n"
        f"\U0001f4dd <b>Bot Heading:</b> <code>{esc(heading_val)}</code>\n"
        f"\U0001f5bc\ufe0f <b>Media Link:</b> <code>{esc(banner_val)}</code>\n"
        f"\U0001f4dc <b>Logs Channel:</b> <code>{esc(logs_val)}</code>\n"
        f"\u2b50 <b>Vouch Channel:</b> <code>{esc(vouch_val)}</code>\n"
        f"\U0001f381 <b>Custom Emojis:</b> <b>{active_emojis}</b> active\n\n"
        "Select a variable below to update:"
    )
    await callback.message.edit_text(text, reply_markup=admin_variables_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_var_input:"))
async def admin_var_input(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    which = callback.data.split(":", 1)[1]
    await state.clear()
    if which == "banner":
        await state.set_state(AdminStates.waiting_var_banner)
        prompt = (
            "\U0001f5bc\ufe0f <b>Change Media Link (Photo / GIF / Video)</b>\n\n"
            "Send the new banner media link:\n"
            "\u2022 Telegram post link containing a Photo, GIF, or Video (e.g. <code>https://t.me/metahelpline/28</code>)\n"
            "\u2022 Direct URL ending with <code>.jpg</code>, <code>.png</code>, <code>.gif</code>, or <code>.mp4</code>\n"
            "\u2022 Or send <code>off</code> to disable banner media."
        )
    elif which == "logs":
        await state.set_state(AdminStates.waiting_var_logs)
        prompt = (
            "\U0001f4dc <b>Change Logs Channel</b>\n\n"
            "Send the new Logs Channel ID (e.g. <code>-1001234567890</code>) or <code>@username</code>.\n"
            "Make sure the bot is an admin in that channel."
        )
    elif which == "vouch":
        await state.set_state(AdminStates.waiting_var_vouch)
        prompt = (
            "\u2b50 <b>Change Vouch Channel</b>\n\n"
            "Send the Vouch Channel ID (e.g. <code>-1001234567890</code>) or <code>@username</code>.\n"
            "Bot will post a 2-line premium vouch message here whenever a gift is sent or a channel promo completes.\n"
            "Send <code>off</code> to disable."
        )
    elif which == "emoji":
        await state.set_state(AdminStates.waiting_var_emoji)
        items = [f"{uni_ch}{key}" for key, (uni_ch, _, _) in EMOJI_VAR_REGISTRY.items()]
        grouped = [" ".join(items[i:i + 6]) for i in range(0, len(items), 6)]
        prompt = (
            "\U0001f381 <b>Change Emoji ID (Single or Bulk)</b>\n\n"
            "Send one or multiple lines:\n"
            "<code>GIFT 5368324170671202286\n"
            "DEPOSIT 4967518033061872209\n"
            "STAR 5954135079662916434</code>\n\n"
            "Reset: <code>GIFT reset</code> | Off: <code>GIFT off</code> | All: <code>ALL reset</code>\n\n"
            "<b>Available Names:</b>\n" + "\n".join(grouped)
        )
    elif which == "heading":
        await state.set_state(AdminStates.waiting_var_heading)
        cur_h = get_bot_heading()
        prompt = (
            "\U0001f4dd <b>Change Bot Heading</b>\n\n"
            f"Current Heading: <b>{esc(cur_h)}</b>\n\n"
            "Send the new heading text (max 80 characters).\n"
            "Send <code>reset</code> to restore default (<code>Telegram Gift Store</code>)."
        )
    elif which == "btn_color":
        await state.set_state(AdminStates.waiting_var_btn_color)
        pairs = [f"{disp}: <b>{get_button_color_name(k)}</b>" for k, (disp, _) in BUTTON_STYLE_REGISTRY.items()]
        grouped = [" | ".join(pairs[i:i + 2]) for i in range(0, len(pairs), 2)]
        prompt = (
            "\u2699\ufe0f <b>Change Button Colour</b>\n\n"
            "Allowed colours: <code>red</code>, <code>green</code>, <code>blue</code> (or <code>reset</code>)\n"
            "Format: <code>Button Name colour</code>\n"
            "Examples: <code>Send Gift green</code> | <code>Deposit red</code> | <code>ALL blue</code>\n\n"
            "<b>Current Button Colours:</b>\n" + "\n".join(grouped)
        )
    elif which == "btn_layout":
        await state.set_state(AdminStates.waiting_var_btn_layout)
        cur_layout = get_dashboard_layout_text()
        avail = ", ".join(f"<code>{disp}</code>" for disp, _, _, _ in DASHBOARD_BUTTONS.values())
        prompt = (
            "\U0001f4ca <b>Change Button Position</b>\n\n"
            "Send each row on a new line. Use <code>-</code> to put buttons side-by-side:\n"
            "Example:\n"
            "<code>Send Gift\nDeposit - Balance\nTasks - Promote Channel\nReferral - Redeem Code</code>\n\n"
            f"<b>Available Buttons:</b> {avail}\n"
            "Send <code>reset</code> for default layout.\n\n"
            f"<b>Current Layout:</b>\n<code>{esc(cur_layout)}</code>"
        )
    else:
        await callback.answer("Unknown variable.", show_alert=True)
        return
    await callback.message.edit_text(prompt, reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.message(AdminStates.waiting_var_heading)
async def admin_receive_var_heading(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw or len(raw) > 80:
        await message.answer(
            "\u274c Please send a heading between 1 and 80 characters (or <code>reset</code>).",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    new_heading = DEFAULT_BOT_HEADING if raw.lower() == "reset" else raw
    set_setting("bot_heading", new_heading)
    admin_log(message.from_user.id, "var_heading", new_heading)
    await state.clear()
    await message.answer(
        f"\u2705 <b>Bot Heading updated!</b>\n\nNew Heading: <b>{esc(new_heading)}</b>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


@dp.message(AdminStates.waiting_var_btn_color)
async def admin_receive_var_btn_color(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    parts = raw.rsplit(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "\u274c Format: <code>Button Name colour</code>\nExample: <code>Send Gift green</code> (colours: <code>red</code>, <code>green</code>, <code>blue</code>).",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    target_name, color_raw = parts[0].strip(), parts[1].strip().lower()
    if color_raw not in ("red", "green", "blue", "reset"):
        await message.answer(
            "\u274c Invalid colour! Only 3 colours are allowed: <code>red</code>, <code>green</code>, <code>blue</code> (or <code>reset</code>).",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if target_name.upper() == "ALL":
        for key, (_, default_style) in BUTTON_STYLE_REGISTRY.items():
            val = default_style if color_raw == "reset" else COLOR_TO_STYLE[color_raw]
            set_setting(f"btn_style_{key}", val)
        admin_log(message.from_user.id, "var_btn_color", f"ALL={color_raw}")
        await state.clear()
        await message.answer(
            f"\u2705 <b>All button colours updated to {esc(color_raw)}!</b>",
            reply_markup=admin_variables_keyboard(),
            parse_mode="HTML",
        )
        return

    key = resolve_button_style_key(target_name)
    if not key:
        await message.answer(
            f"\u274c Unknown button name: <code>{esc(target_name)}</code>. Check the button list and try again.",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    disp_name, default_style = BUTTON_STYLE_REGISTRY[key]
    new_style = default_style if color_raw == "reset" else COLOR_TO_STYLE[color_raw]
    set_setting(f"btn_style_{key}", new_style)
    admin_log(message.from_user.id, "var_btn_color", f"{key}={color_raw}")
    await state.clear()
    applied_color = STYLE_TO_COLOR[new_style]
    await message.answer(
        f"\u2705 <b>Button Colour Updated!</b>\n\n"
        f"Button: <b>{esc(disp_name)}</b>\n"
        f"Colour: <b>{esc(applied_color)}</b>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


@dp.message(AdminStates.waiting_var_btn_layout)
async def admin_receive_var_btn_layout(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "\u274c Please send a valid button layout or <code>reset</code>.",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if raw.lower() == "reset":
        layout_to_save = DEFAULT_DASHBOARD_LAYOUT
        parsed = parse_dashboard_layout(layout_to_save)
    else:
        try:
            parsed = parse_dashboard_layout(raw)
        except ValueError as e:
            avail = ", ".join(f"<code>{disp}</code>" for disp, _, _, _ in DASHBOARD_BUTTONS.values())
            await message.answer(
                f"\u274c {esc(e)}\n\n<b>Available Buttons:</b> {avail}",
                reply_markup=admin_cancel_keyboard(),
                parse_mode="HTML",
            )
            return
        # Normalize canonical button names per line
        normalized_lines = [
            " - ".join(DASHBOARD_BUTTONS[k][0] for k in row)
            for row in parsed
        ]
        layout_to_save = "\n".join(normalized_lines)

    set_setting("dashboard_layout", layout_to_save)
    admin_log(message.from_user.id, "var_btn_layout", layout_to_save.replace("\n", " / "))
    await state.clear()
    await message.answer(
        f"\u2705 <b>Button Position Updated!</b>\n\n<b>New Layout:</b>\n<code>{esc(layout_to_save)}</code>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


@dp.message(AdminStates.waiting_var_banner)
async def admin_receive_var_banner(message: Message, state: FSMContext):
    global _BANNER_MEDIA
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("\u274c Please send a valid Photo/GIF/Video link or <code>off</code>.", reply_markup=admin_cancel_keyboard(), parse_mode="HTML")
        return
    set_setting("banner_source", raw)
    _BANNER_MEDIA = None
    admin_log(message.from_user.id, "var_banner", raw)
    await state.clear()
    await message.answer(
        f"\u2705 <b>Media Link updated!</b>\n\nNew value: <code>{esc(raw)}</code>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


@dp.message(AdminStates.waiting_var_emoji)
async def admin_receive_var_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_text = message.text or ""
    if not raw_text.strip():
        await message.answer(
            "\u274c Format: <code>NAME NEW_EMOJI_ID</code> (e.g. <code>GIFT 5368324170671202286</code>).",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    # Map any pasted Telegram custom_emoji entities to their exact line number
    line_custom_ids = {}
    utf16_bytes = raw_text.encode("utf-16-le")
    for ent in (message.entities or []):
        if getattr(ent, "type", None) == "custom_emoji" and getattr(ent, "custom_emoji_id", None):
            prefix = utf16_bytes[: ent.offset * 2].decode("utf-16-le", errors="ignore")
            line_num = prefix.count("\n")
            line_custom_ids[line_num] = str(ent.custom_emoji_id)

    raw_lines = raw_text.splitlines()
    non_empty_lines = [(idx, ln.strip()) for idx, ln in enumerate(raw_lines) if ln.strip()]

    # Single-line lookup check (e.g. admin sends just "GIFT")
    if len(non_empty_lines) == 1:
        line_idx, single = non_empty_lines[0]
        parts = re.split(r"[\s=:]+", single, maxsplit=1)
        key = parts[0].upper().removeprefix("EMOJI_")
        if key in EMOJI_VAR_REGISTRY and len(parts) == 1 and line_idx not in line_custom_ids:
            uni_ch, gvar, _ = EMOJI_VAR_REGISTRY[key]
            cur_val = globals().get(gvar) or "OFF"
            await message.answer(
                f"{uni_ch} <b>{key}</b> current Emoji ID:\n<code>{esc(cur_val)}</code>\n\n"
                f"Send <code>{key} NEW_ID</code> to update, or cancel.",
                reply_markup=admin_cancel_keyboard(),
                parse_mode="HTML",
            )
            return

    updated_items = []
    errors = []

    for line_idx, line in non_empty_lines:
        parts = re.split(r"[\s=:]+", line, maxsplit=1)
        key = parts[0].upper().removeprefix("EMOJI_")
        val_arg = parts[1].strip() if len(parts) == 2 else ""
        extracted_custom_id = line_custom_ids.get(line_idx)

        if key == "ALL":
            if val_arg.lower() == "reset":
                for k, (_, _, default_id) in EMOJI_VAR_REGISTRY.items():
                    set_setting(f"emoji_id_{k}", default_id or "off")
                updated_items.append("ALL → reset")
            elif val_arg.lower() in ("off", "none"):
                for k in EMOJI_VAR_REGISTRY:
                    set_setting(f"emoji_id_{k}", "off")
                updated_items.append("ALL → off")
            else:
                errors.append(f"<code>{esc(line)}</code> (use <code>ALL reset</code> or <code>ALL off</code>)")
            continue

        if key not in EMOJI_VAR_REGISTRY:
            errors.append(f"<code>{esc(line)}</code> (unknown name)")
            continue

        uni_ch, _, default_id = EMOJI_VAR_REGISTRY[key]

        if val_arg.lower() == "reset":
            new_id = default_id or "off"
        elif val_arg.lower() in ("off", "none"):
            new_id = "off"
        elif extracted_custom_id:
            new_id = extracted_custom_id
        elif val_arg.isdigit():
            new_id = val_arg
        else:
            errors.append(f"<code>{esc(line)}</code> (invalid ID)")
            continue

        set_setting(f"emoji_id_{key}", new_id)
        updated_items.append(f"{uni_ch} <code>{key}</code> → <code>{esc(new_id)}</code>")

    if not updated_items:
        err_text = "\n".join(f"• {e}" for e in errors[:10])
        await message.answer(
            f"\u274c <b>No valid emoji updates found.</b>\n\n{err_text}\n\n"
            "Format: <code>EMOJI_NAME EMOJI_ID</code>",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    reload_custom_emojis()
    admin_log(message.from_user.id, "var_emoji_bulk", f"updated={len(updated_items)}")
    await state.clear()

    preview = "\n".join(f"• {item}" for item in updated_items[:20])
    if len(updated_items) > 20:
        preview += f"\n• ...and <b>{len(updated_items) - 20}</b> more"

    msg_lines = [
        f"\u2705 <b>Updated {len(updated_items)} Emoji ID(s)!</b>",
        "",
        preview,
    ]
    if errors:
        msg_lines += [
            "",
            f"⚠️ <b>Skipped {len(errors)} invalid line(s):</b>",
            "\n".join(f"• {e}" for e in errors[:8]),
        ]

    await message.answer(
        "\n".join(msg_lines),
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


async def _resolve_channel_input(raw: str):
    cleaned = raw.strip()
    if cleaned.lower() in ("0", "off", "none"):
        return "off", "Disabled"
    if cleaned.startswith("https://t.me/") or cleaned.startswith("http://t.me/") or cleaned.startswith("t.me/"):
        cleaned = "@" + cleaned.split("t.me/", 1)[1].split("/")[0].lstrip("@")
    target = int(cleaned) if cleaned.lstrip("-").isdigit() else cleaned
    chat = await bot.get_chat(target)
    return str(chat.id), (chat.title or chat.username or str(chat.id))


@dp.message(AdminStates.waiting_var_logs)
async def admin_receive_var_logs(message: Message, state: FSMContext):
    global LOG_CHANNEL_ID
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        cid, title = await _resolve_channel_input(raw)
    except Exception as e:
        await message.answer(
            f"\u274c Could not access channel. Make sure bot is admin.\n<code>{esc(e)}</code>",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    set_setting("log_channel_id", cid)
    if cid.lstrip("-").isdigit():
        LOG_CHANNEL_ID = int(cid)
    admin_log(message.from_user.id, "var_logs_channel", f"{title} ({cid})")
    await state.clear()
    await message.answer(
        f"\u2705 <b>Logs Channel updated!</b>\n\nChannel: <b>{esc(title)}</b>\nID: <code>{esc(cid)}</code>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )


@dp.message(AdminStates.waiting_var_vouch)
async def admin_receive_var_vouch(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        cid, title = await _resolve_channel_input(raw)
    except Exception as e:
        await message.answer(
            f"\u274c Could not access channel. Make sure bot is admin.\n<code>{esc(e)}</code>",
            reply_markup=admin_cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    set_setting("vouch_channel_id", "" if cid == "off" else cid)
    admin_log(message.from_user.id, "var_vouch_channel", f"{title} ({cid})")
    await state.clear()
    await message.answer(
        f"\u2705 <b>Vouch Channel updated!</b>\n\nChannel: <b>{esc(title)}</b>\nID: <code>{esc(cid)}</code>",
        reply_markup=admin_variables_keyboard(),
        parse_mode="HTML",
    )



# ============================================================
# ADMIN MANAGEMENT (LIST, ADD, REMOVE ADMINS)
# ============================================================

def admin_manage_keyboard():
    kb = InlineKeyboardBuilder()
    add_inline_button(kb, "➕ Add Admin", "admin_admin_add", "success", EMOJI_ADD)
    add_inline_button(kb, "➖ Remove Admin", "admin_admin_remove", "danger", EMOJI_REMOVE)
    add_inline_button(kb, "⬅️ Back", "admin_home", "danger", EMOJI_BACK)
    kb.adjust(2, 1)
    return kb.as_markup()


@dp.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    rows = db.execute("SELECT * FROM bot_admins ORDER BY created_at ASC").fetchall()
    lines = ["👑 <b>Admin Management</b>\n", f"Total Admins: <b>{len(rows)}</b>\n"]
    for idx, r in enumerate(rows, 1):
        uid = int(r["user_id"])
        user_info = db.execute("SELECT first_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
        name = esc(user_info["first_name"] if user_info and user_info["first_name"] else f"Admin {uid}")
        uname = f" (@{esc(user_info['username'])})" if user_info and user_info["username"] else ""
        lines.append(f"{idx}. <b>{name}</b>{uname}\n   ID: <code>{uid}</code>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_admin_add")
async def admin_admin_add_start(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_admin_add)
    await callback.message.edit_text(
        "👑 <b>Add New Admin</b>\n\nSend the Telegram user ID of the person you want to make an admin.",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdminStates.waiting_admin_add)
async def admin_admin_add_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        new_admin_id = int(raw)
        if new_admin_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid numeric Telegram user ID.", reply_markup=admin_cancel_keyboard())
        return

    try:
        db.execute(
            "INSERT INTO bot_admins(user_id, added_by, created_at) VALUES(?, ?, ?)",
            (new_admin_id, message.from_user.id, now()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ This user is already an admin.", reply_markup=admin_manage_keyboard())
        await state.clear()
        return

    admin_log(message.from_user.id, "admin_add", new_admin_id)
    await state.clear()
    await message.answer(
        f"✅ Successfully added user <code>{new_admin_id}</code> as an admin!",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_admin_remove")
async def admin_admin_remove_start(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_admin_remove)
    await callback.message.edit_text(
        "👑 <b>Remove Admin</b>\n\nSend the Telegram user ID of the admin you want to remove.",
        reply_markup=admin_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdminStates.waiting_admin_remove)
async def admin_admin_remove_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        target_id = int(raw)
    except ValueError:
        await message.answer("❌ Enter a valid numeric Telegram user ID.", reply_markup=admin_cancel_keyboard())
        return

    if target_id in ADMIN_IDS:
        await message.answer("❌ Cannot remove primary root admin ID.", reply_markup=admin_manage_keyboard())
        await state.clear()
        return

    row = db.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (target_id,)).fetchone()
    if not row:
        await message.answer("❌ That user ID is not in the admin list.", reply_markup=admin_manage_keyboard())
        await state.clear()
        return

    db.execute("DELETE FROM bot_admins WHERE user_id=?", (target_id,))
    db.commit()
    admin_log(message.from_user.id, "admin_remove", target_id)
    await state.clear()
    await message.answer(
        f"✅ Successfully removed user <code>{target_id}</code> from admins.",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_cancel_task")
async def admin_cancel_task(callback: CallbackQuery, state: FSMContext):
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await callback.message.edit_text("\u274c <b>Operation cancelled.</b>", reply_markup=admin_keyboard(), parse_mode="HTML")
    await callback.answer()


# ============================================================
# /FORCE
# ============================================================

@dp.message(Command("force"))
async def force_command(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "\u274c Admin only."
        )
        return

    args = (
        message.text or ""
    ).split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "<code>/force CHAT_ID</code>\n\n"
            "Example:\n"
            "<code>/force -1001234567890</code>",
            parse_mode="HTML",
        )
        return

    try:
        chat_id = int(
            args[1]
        )
    except ValueError:
        await message.answer(
            "\u274c Invalid chat ID."
        )
        return

    # --------------------------------------------------------
    # Verify bot membership/admin status.
    # --------------------------------------------------------

    try:
        chat = await bot.get_chat(
            chat_id
        )
    except Exception as e:
        await message.answer(
            "\u274c Bot cannot access this channel/group.\n\n"
            f"<code>{esc(e)}</code>",
            parse_mode="HTML",
        )
        return

    try:
        me = await bot.get_me()

        bot_member = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=me.id,
        )

    except Exception as e:
        await message.answer(
            "\u274c Could not check bot permissions.\n\n"
            f"<code>{esc(e)}</code>",
            parse_mode="HTML",
        )
        return

    if bot_member.status not in (
        "administrator",
        "creator",
    ):
        await message.answer(
            "\u274c <b>Bot is not an administrator.</b>\n\n"
            "Promote the bot to administrator first, "
            "then run /force again.",
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # Create/reuse invite link.
    # --------------------------------------------------------

    invite_link = None

    try:
        existing = get_force_channel(
            chat_id
        )

        if existing and existing["invite_link"]:
            invite_link = existing[
                "invite_link"
            ]

        else:
            invite = (
                await bot.create_chat_invite_link(
                    chat_id=chat_id,
                    name="Gift Bot Force Join",
                )
            )

            invite_link = invite.invite_link

    except Exception as e:
        logger.exception(
            "Invite link creation failed."
        )

        await message.answer(
            "\u274c Bot is admin, but could not create "
            "an invite link.\n\n"
            "Make sure the bot has permission to "
            "manage invite links.",
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # Store.
    # --------------------------------------------------------

    try:
        db.execute(
            """
            INSERT INTO force_join (
                chat_id,
                chat_type,
                title,
                invite_link,
                added_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(chat_id)
            DO UPDATE SET
                chat_type = excluded.chat_type,
                title = excluded.title,
                invite_link = excluded.invite_link,
                added_by = excluded.added_by
            """,
            (
                chat_id,
                str(chat.type),
                chat.title
                or chat.username
                or "Telegram Chat",
                invite_link,
                message.from_user.id,
                now(),
            ),
        )

        db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "Force join database error."
        )

        await message.answer(
            "\u274c Could not save force-join chat."
        )
        return

    await message.answer(
        "\u2705 <b>Force Join Started</b>\n\n"
        f"\U0001f4e2 Chat: <b>{esc(chat.title or chat.username or 'Telegram Chat')}</b>\n"
        f"\U0001f194 ID: <code>{chat_id}</code>\n"
        f"\U0001f517 Link: {esc(invite_link)}\n\n"
        "All users will now be required to "
        "join this chat before using the bot.",
        parse_mode="HTML",
    )


# ============================================================
# /REMOVE
# ============================================================

@dp.message(Command("remove"))
async def remove_command(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "\u274c Admin only."
        )
        return

    args = (
        message.text or ""
    ).split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "<code>/remove CHAT_ID</code>",
            parse_mode="HTML",
        )
        return

    try:
        chat_id = int(
            args[1]
        )
    except ValueError:
        await message.answer(
            "\u274c Invalid chat ID."
        )
        return

    row = get_force_channel(
        chat_id
    )

    if not row:
        await message.answer(
            "\u274c This chat is not in force join."
        )
        return

    remove_force_channel(
        chat_id
    )

    await message.answer(
        "\u2705 <b>Force Join Removed</b>\n\n"
        f"Chat: <b>{esc(row['title'])}</b>\n"
        f"ID: <code>{chat_id}</code>",
        parse_mode="HTML",
    )


# ============================================================
# PAYMENTS COMMAND
# ============================================================

@dp.message(Command("payments"))
async def payments_command(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "\u274c Admin only."
        )
        return

    rows = db.execute(
        """
        SELECT *
        FROM payments
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    if not rows:
        await message.answer(
            "\U0001f4ed No payments yet."
        )
        return

    text = (
        "\U0001f4b3 <b>Recent Payments</b>\n\n"
    )

    for row in rows:
        text += (
            f"#{row['id']} "
            f"<code>{row['user_id']}</code> "
            f"\u2014 <b>{row['amount']} \u2b50</b>\n"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )


# ============================================================
# GIFTS COMMAND
# ============================================================

@dp.message(Command("gifts"))
async def gifts_command(
    message: Message,
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "\u274c Admin only."
        )
        return

    rows = db.execute(
        """
        SELECT *
        FROM gifts
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    if not rows:
        await message.answer(
            "\U0001f4ed No gifts yet."
        )
        return

    text = (
        "\U0001f381 <b>Recent Gifts</b>\n\n"
    )

    for row in rows:
        gift_name = format_stored_gift_type(row["gift_type"] or "")

        text += (
            f"#{row['id']} {gift_name}\n"
            f"From: <code>{row['sender_id']}</code>\n"
            f"To: <code>{row['receiver_id']}</code>\n"
            f"Gift: <b>{row['telegram_price']} \u2b50</b>\n"
            f"Charged: <b>{row['balance_price']} \u2b50</b>\n\n"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )


# ============================================================
# PAYMENT SUPPORT
# ============================================================

@dp.message(Command("paysupport"))
async def payment_support(
    message: Message,
):
    await message.answer(
        "\U0001f4b3 <b>Payment Support</b>\n\n"
        "If your Telegram Stars payment succeeded "
        "but your balance was not updated, contact "
        "an admin.\n\n"
        "Admin IDs:\n"
        "<code>6261736889</code>\n"
        "<code>8199495967</code>",
        parse_mode="HTML",
    )


# ============================================================
# UNKNOWN MESSAGE
# ============================================================

@dp.message()
async def unknown_message(
    message: Message,
):
    # Don't block the recipient user-picker handler.
    if message.user_shared:
        return

    if not await require_force_join(
        message
    ):
        return

    await message.answer(
        "\u2753 Unknown command.\n\n"
        "Use /start."
    )


# ============================================================
# MAIN
# ============================================================

async def db_backup_monitor():
    last_mtime = None
    while True:
        try:
            log_cid = get_log_channel_id()
            if log_cid and log_cid.lower() not in ("0", "off", "none") and os.path.exists(DB_FILE):
                curr_mtime = os.path.getmtime(DB_FILE)
                if last_mtime is None or curr_mtime != last_mtime:
                    last_mtime = curr_mtime
                    target = int(log_cid) if log_cid.lstrip("-").isdigit() else log_cid
                    from aiogram.types import FSInputFile
                    doc = FSInputFile(DB_FILE, filename=f"gift_bot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db")
                    token = _SKIP_BANNER.set(True)
                    try:
                        await bot.send_document(
                            target,
                            document=doc,
                            caption="🛡️ <b>Automated Database Backup</b> (Triggered by DB update)",
                            parse_mode="HTML",
                        )
                    finally:
                        _SKIP_BANNER.reset(token)
        except Exception:
            logger.exception("DB backup monitor error")
        await asyncio.sleep(600)  # Check every 10 minutes


async def main():
    logger.info(
        "Starting Gift Bot..."
    )

    ensure_default_admins()
    migrate_old_balances()

    monitor_task = asyncio.create_task(
        force_join_monitor()
    )
    leave_monitor_task = asyncio.create_task(
        task_leave_monitor()
    )
    backup_task = asyncio.create_task(
        db_backup_monitor()
    )

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )

    finally:
        monitor_task.cancel()
        leave_monitor_task.cancel()
        backup_task.cancel()

        for t in (monitor_task, leave_monitor_task, backup_task):
            try:
                await t
            except asyncio.CancelledError:
                pass

        await bot.session.close()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )
    except KeyboardInterrupt:
        logger.info(
            "Bot stopped."
        )