import os
import random
import re
import sqlite3
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from spluspy import Robot, Button, filters

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data/t3r0za.sqlite3")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Render Environment Variables.")

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
lock = threading.RLock()

def sql(query, params=()):
    with lock, db:
        return db.execute(query, params)

def init_db():
    with lock, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id TEXT PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 100,
            xp INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            daily_date TEXT,
            games INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS inventory(
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(user_id,item_id)
        );
        CREATE TABLE IF NOT EXISTS group_settings(
            chat_id TEXT PRIMARY KEY,
            welcome INTEGER NOT NULL DEFAULT 1,
            anti_link INTEGER NOT NULL DEFAULT 0,
            anti_spam INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS rooms(
            room_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            host_id TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'waiting',
            question TEXT,
            answer TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS room_players(
            room_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY(room_id,user_id)
        );
        """)

init_db()

def norm(text):
    return " ".join(
        str(text or "").strip().casefold()
        .replace("‌", "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .split()
    )

def ensure_user(uid):
    with lock, db:
        db.execute(
            "INSERT OR IGNORE INTO users(user_id) VALUES (?)",
            (str(uid),)
        )

def get_user(uid):
    ensure_user(uid)
    return db.execute(
        "SELECT * FROM users WHERE user_id=?",
        (str(uid),)
    ).fetchone()

def add_xp(uid, amount):
    with lock, db:
        db.execute(
            "UPDATE users SET xp=xp+? WHERE user_id=?",
            (int(amount), str(uid))
        )

def record_game(uid, won):
    with lock, db:
        db.execute(
            "UPDATE users SET games=games+1, wins=wins+? WHERE user_id=?",
            (1 if won else 0, str(uid))
        )
    add_xp(uid, 30 if won else 10)

def k(rows):
    return [
        [Button.text(str(item)) for item in row]
        for row in rows
    ]

MAIN = k([
    ["🎮 بازی", "🪙 سکه"],
    ["🎁 جایزه", "🎯 مأموریت"],
    ["🛒 فروشگاه", "🎒 کوله"],
    ["👤 پروفایل", "🏆 رتبه"],
    ["⭐ افتخارات", "🤝 دوستان"],
    ["🛡️ گروه", "⚙️ تنظیمات"],
])

GAMES = k([
    ["🎯 کوئیز", "🧩 حدس کلمه"],
    ["⚡ واکنش", "🏆 چالش گروهی"],
    ["👥 اتاق دو نفره", "👥👥 اتاق گروهی"],
    ["🏠 منو"],
])

MODES = k([
    ["👤 تک‌نفره", "👥 دو نفره"],
    ["👥👥 چندنفره"],
    ["↩️ برگشت"],
])

ROOM = k([
    ["➕ پیوستن", "🔄 وضعیت اتاق"],
    ["❌ لغو اتاق", "🎮 بازی"],
])

SHOP = k([
    ["🧰 Lucky Badge", "🎨 Profile Frame"],
    ["⚡ XP Boost"],
    ["🎒 کوله", "🏠 منو"],
])

SHOP_ACTION = k([
    ["🛒 خرید badge", "🛒 خرید frame"],
    ["🛒 خرید boost"],
    ["↩️ فروشگاه", "🏠 منو"],
])

GROUP = k([
    ["👋 خوش‌آمد", "🔗 ضدلینک"],
    ["🚨 ضداسپم", "📊 آمار گروه"],
    ["🏠 منو"],
])

PENDING = {}
ACTIVE = {}
LAST = {}

QUESTIONS = [
    ("پایتخت ژاپن کدام است؟", "توکیو"),
    ("سیاره سرخ کدام است؟", "مریخ"),
    ("5 × 8 چند می‌شود؟", "40"),
    ("آب در سطح دریا تقریباً چند درجه است؟", "100"),
    ("بزرگ‌ترین اقیانوس زمین کدام است؟", "آرام"),
]

WORDS = [
    ("🍎", "سیب"),
    ("🏠", "خانه"),
    ("🚗", "ماشین"),
    ("🐱", "گربه"),
    ("🌞", "خورشید"),
]

ITEMS = {
    "badge": (250, "🧰 Lucky Badge", "آیتم کلکسیونی پروفایل."),
    "frame": (400, "🎨 Profile Frame", "قاب تزئینی پروفایل."),
    "boost": (600, "⚡ XP Boost", "آیتم سیستم XP؛ در کوله ذخیره می‌شود."),
}

def level(uid):
    return 1 + get_user(uid)["xp"] // 100

def home(uid):
    r = get_user(uid)
    return (
        "⚡ T3R0ZA\n\n"
        f"سلام 😎\n🏅 Level: {level(uid)} | ✨ XP: {r['xp']} | 🪙 {r['coins']}\n\n"
        "هرچی خواستی عادی بنویس؛ مثل «بازی»، «سکه» یا «فروشگاه»."
    )

def wallet(uid):
    r = get_user(uid)
    return (
        "🪙 کیف پول\n\n"
        f"موجودی: {r['coins']} سکه\n"
        f"✨ XP: {r['xp']}\n"
        f"🏅 Level: {level(uid)}"
    )

def daily(uid):
    r = get_user(uid)
    today = date.today()
    if r["daily_date"] == today.isoformat():
        return "🎁 جایزه امروز رو قبلاً گرفتی 😎\nفردا دوباره سر بزن."
    yesterday = (today - timedelta(days=1)).isoformat()
    streak = r["streak"] + 1 if r["daily_date"] == yesterday else 1
    reward = 50 + min(streak, 7) * 10
    with lock, db:
        db.execute(
            "UPDATE users SET coins=coins+?, streak=?, daily_date=? WHERE user_id=?",
            (reward, streak, today.isoformat(), uid)
        )
    add_xp(uid, 20)
    return (
        "🎁 جایزه روزانه گرفتی!\n"
        f"🪙 +{reward} سکه\n"
        f"🔥 Streak: {streak}\n"
        "✨ +20 XP"
    )

def profile(uid):
    r = get_user(uid)
    return (
        "👤 پروفایل\n\n"
        f"🆔 {uid}\n"
        f"🏅 Level: {level(uid)}\n"
        f"✨ XP: {r['xp']}\n"
        f"🪙 Coins: {r['coins']}\n"
        f"🔥 Streak: {r['streak']}\n"
        f"🎮 بازی: {r['games']}\n"
        f"🏆 برد: {r['wins']}"
    )

def leaderboard():
    rows = db.execute(
        "SELECT user_id,xp,wins FROM users ORDER BY xp DESC,wins DESC LIMIT 10"
    ).fetchall()
    if not rows:
        return "🏆 هنوز رکوردی ثبت نشده."
    return "🏆 رتبه‌بندی\n\n" + "\n".join(
        f"{i}. {r['user_id']} — {r['xp']} XP — 🏆 {r['wins']}"
        for i, r in enumerate(rows, 1)
    )

def achievements(uid):
    r = get_user(uid)
    items = [
        ("🌱 شروع‌کننده", r["xp"] >= 5),
        ("🎮 گیمر", r["games"] >= 1),
        ("🏆 برنده", r["wins"] >= 1),
        ("🔥 فعال", r["streak"] >= 3),
        ("⭐ Level 10", level(uid) >= 10),
    ]
    return "⭐ افتخارات\n\n" + "\n".join(
        ("✅ " if ok else "🔒 ") + name for name, ok in items
    )

def missions(uid):
    r = get_user(uid)
    return (
        "🎯 مأموریت‌ها\n\n"
        "✅ ورود — +5 XP\n"
        "🎮 بازی — +10/+30 XP\n"
        "🎁 جایزه روزانه — +20 XP\n\n"
        f"وضعیت: Level {level(uid)} | {r['xp']} XP"
    )

def shop():
    return (
        "🛒 فروشگاه T3R0ZA\n\n"
        "یک آیتم رو انتخاب کن تا بگم چی هست، چه کاربردی داره و قیمتش چقدره."
    )

def item_detail(item):
    price, name, detail = ITEMS[item]
    return f"{name}\n\n💰 قیمت: {price} سکه\nℹ️ {detail}\n\nاگر مناسبته، دکمه خرید رو بزن."

def buy(uid, item):
    price, name, _ = ITEMS[item]
    r = get_user(uid)
    if r["coins"] < price:
        return f"❌ سکه کافی نداری.\nقیمت: {price}\nموجودی: {r['coins']}"
    with lock, db:
        db.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (price, uid))
        db.execute(
            "INSERT INTO inventory(user_id,item_id,qty) VALUES (?,?,1) "
            "ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+1",
            (uid, item)
        )
    return f"✅ خرید انجام شد!\n{name}\n🪙 -{price} سکه"

def inventory(uid):
    rows = db.execute(
        "SELECT item_id,qty FROM inventory WHERE user_id=?",
        (uid,)
    ).fetchall()
    if not rows:
        return "🎒 کوله‌بری خالیه."
    return "🎒 کوله‌بری\n\n" + "\n".join(
        f"• {ITEMS.get(r['item_id'], ('', r['item_id'], ''))[1]} × {r['qty']}"
        for r in rows
    )

def group_cfg(chat_id):
    with lock, db:
        row = db.execute(
            "SELECT * FROM group_settings WHERE chat_id=?",
            (str(chat_id),)
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO group_settings(chat_id) VALUES (?)",
                (str(chat_id),)
            )
            row = db.execute(
                "SELECT * FROM group_settings WHERE chat_id=?",
                (str(chat_id),)
            ).fetchone()
    return row

def group_panel(chat_id):
    s = group_cfg(chat_id)
    return (
        "🛡️ T3R0ZA GROUP\n\n"
        f"👋 خوش‌آمد: {'روشن' if s['welcome'] else 'خاموش'}\n"
        f"🔗 ضدلینک: {'روشن' if s['anti_link'] else 'خاموش'}\n"
        f"🚨 ضداسپم: {'روشن' if s['anti_spam'] else 'خاموش'}"
    )

def toggle_group(chat_id, field):
    group_cfg(chat_id)
    with lock, db:
        value = db.execute(
            f"SELECT {field} FROM group_settings WHERE chat_id=?",
            (str(chat_id),)
        ).fetchone()[0]
        value = 0 if value else 1
        db.execute(
            f"UPDATE group_settings SET {field}=? WHERE chat_id=?",
            (value, str(chat_id))
        )
    names = {
        "welcome": "👋 خوش‌آمد",
        "anti_link": "🔗 ضدلینک",
        "anti_spam": "🚨 ضداسپم",
    }
    return f"{names[field]} {'روشن' if value else 'خاموش'} شد."

def room(chat_id, mode, uid):
    with lock, db:
        old = db.execute(
            "SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",
            (str(chat_id),)
        ).fetchone()
        if old:
            count = db.execute(
                "SELECT COUNT(*) FROM room_players WHERE room_id=?",
                (old["room_id"],)
            ).fetchone()[0]
            needed = 2 if old["mode"] == "duo" else 3
            return f"🎮 اتاق فعاله!\n🆔 {old['room_id']}\n👥 {count}/{needed}"
        room_id = f"{random.randrange(0x1000000):06X}"
        db.execute(
            "INSERT INTO rooms(room_id,chat_id,mode,host_id) VALUES (?,?,?,?)",
            (room_id, str(chat_id), mode, uid)
        )
        db.execute(
            "INSERT INTO room_players(room_id,user_id) VALUES (?,?)",
            (room_id, uid)
        )
    needed = 2 if mode == "duo" else 3
    return (
        "🎮 اتاق ساخته شد!\n\n"
        f"🆔 کد: {room_id}\n"
        f"👥 نفرات: 1/{needed}\n\n"
        "بقیه «پیوستن» رو بزنن."
    )

def join_room(uid, chat_id):
    with lock, db:
        r = db.execute(
            "SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",
            (str(chat_id),)
        ).fetchone()
        if not r:
            return "❌ اتاقی نیست. اول اتاق دو نفره یا اتاق گروهی بساز."
        db.execute(
            "INSERT OR IGNORE INTO room_players(room_id,user_id) VALUES (?,?)",
            (r["room_id"], uid)
        )
        count = db.execute(
            "SELECT COUNT(*) FROM room_players WHERE room_id=?",
            (r["room_id"],)
        ).fetchone()[0]
        needed = 2 if r["mode"] == "duo" else 3
        if count >= needed:
            q, ans = random.choice(QUESTIONS)
            db.execute(
                "UPDATE rooms SET state='started',question=?,answer=? WHERE room_id=?",
                (q, ans, r["room_id"])
            )
            return f"🔥 تعداد کامل شد!\n\n❓ {q}\n\nاولین جواب درست برنده‌ست 🏆"
    return f"✅ وارد شدی!\n👥 {count}/{needed}\nمنتظر بقیه‌ایم..."

def answer_room(uid, chat_id, text):
    r = db.execute(
        "SELECT * FROM rooms WHERE chat_id=? AND state='started' ORDER BY created_at DESC LIMIT 1",
        (str(chat_id),)
    ).fetchone()
    if not r or norm(text) != norm(r["answer"]):
        return None
    with lock, db:
        db.execute("UPDATE rooms SET state='finished' WHERE room_id=?", (r["room_id"],))
    record_game(uid, True)
    return f"🏆 برنده: {uid}\n✅ جواب: {r['answer']}\n✨ +30 XP"

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"T3R0ZA_BOT OK")
    def log_message(self, *args):
        return

def run_health():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

bot = Robot(TOKEN)

@bot.on_message(filters.text)
async def handler(client, event):
    try:
        message = event.message
        text = (message.raw_text or message.text or "").strip()
        if not text:
            return

        uid = str(message.sender_id)
        chat_id = str(message.chat_id)
        ensure_user(uid)

        if text != norm(text):
            normalized = norm(text)
        else:
            normalized = text

        if normalized in {"/start", "شروع", "استارت"}:
            add_xp(uid, 5)
            await message.reply(home(uid), buttons=MAIN)
            return

        if normalized in {"بازی", "گیم", "🎮 بازی"}:
            await message.reply(
                "🎮 T3R0ZA GAME CENTER\n\n"
                "چه بازی‌ای بریم؟ 😎\n\n"
                "🎯 کوئیز\n"
                "🧩 حدس کلمه\n"
                "⚡ واکنش\n"
                "🏆 چالش گروهی",
                buttons=GAMES
            )
            return

        game_map = {
            "🎯 کوئیز": "quiz",
            "کوئیز": "quiz",
            "🧩 حدس کلمه": "word",
            "حدس کلمه": "word",
            "⚡ واکنش": "reaction",
            "واکنش": "reaction",
            "🏆 چالش گروهی": "group"
        }
        if normalized in {norm(x) for x in game_map}:
            kind = game_map[next(x for x in game_map if norm(x) == normalized)]
            PENDING[uid] = kind
            descriptions = {
                "quiz": "🎯 کوئیز: سؤال‌های کوتاه و سریع؛ ۱، ۲ یا چندنفره.",
                "word": "🧩 حدس کلمه: از روی ایموجی جواب بده؛ ۱ یا ۲ نفره.",
                "reaction": "⚡ واکنش: راند کوتاه تمرکز و پاسخ؛ ۱ یا ۲ نفره.",
                "group": "🏆 چالش گروهی: رقابت دانستنی داخل اتاق."
            }
            await message.reply(
                descriptions[kind] + "\n\nحالت بازی رو انتخاب کن 👇",
                buttons=MODES
            )
            return

        if uid in PENDING:
            kind = PENDING.pop(uid)
            if normalized in {"👤 تک‌نفره", "تک‌نفره", "تک نفره"}:
                if kind == "group":
                    await message.reply("🏆 این چالش حداقل ۲ نفر می‌خواد.", buttons=MODES)
                    PENDING[uid] = kind
                    return
                if kind == "quiz":
                    q, ans = random.choice(QUESTIONS)
                    ACTIVE[(uid, chat_id)] = ans
                    await message.reply(f"🔥 شروع شد!\n\n❓ {q}\n\nجوابت رو بفرست.", buttons=GAMES)
                elif kind == "word":
                    em, ans = random.choice(WORDS)
                    ACTIVE[(uid, chat_id)] = ans
                    await message.reply(f"🔥 شروع شد!\n\n{em}\n\nاسمش چیه؟", buttons=GAMES)
                else:
                    ACTIVE[(uid, chat_id)] = "go"
                    await message.reply("⚡ آماده‌ای؟\nوقتی GO دیدی، بنویس GO.", buttons=GAMES)
                return

            if normalized in {"👥 دو نفره", "دونفره", "دو نفره"}:
                await message.reply(room(chat_id, "duo", uid), buttons=ROOM)
                return

            if normalized in {"👥👥 چندنفره", "چندنفره", "چند نفره"}:
                await message.reply(room(chat_id, "multi", uid), buttons=ROOM)
                return

            PENDING[uid] = kind
            await message.reply("از گزینه‌های بالا یکی رو انتخاب کن 👆", buttons=MODES)
            return

        active_key = (uid, chat_id)
        if active_key in ACTIVE:
            expected = ACTIVE.pop(active_key)
            if norm(text) == norm(expected):
                record_game(uid, True)
                await message.reply("✅ جواب درست! 🏆\n✨ +30 XP", buttons=GAMES)
            else:
                record_game(uid, False)
                await message.reply(f"❌ جواب درست: {expected}\n✨ +10 XP", buttons=GAMES)
            return

        if normalized in {"سکه", "کیف پول", "🪙 سکه"}:
            await message.reply(wallet(uid), buttons=MAIN)
            return

        if normalized in {"جایزه", "🎁 جایزه", "جایزه روزانه"}:
            await message.reply(daily(uid), buttons=MAIN)
            return

        if normalized in {"پروفایل", "👤 پروفایل"}:
            await message.reply(profile(uid), buttons=MAIN)
            return

        if normalized in {"رتبه", "🏆 رتبه", "رنک"}:
            await message.reply(leaderboard(), buttons=MAIN)
            return

        if normalized in {"افتخارات", "⭐ افتخارات"}:
            await message.reply(achievements(uid), buttons=MAIN)
            return

        if normalized in {"مأموریت", "ماموریت", "🎯 مأموریت"}:
            await message.reply(missions(uid), buttons=MAIN)
            return

        if normalized in {"فروشگاه", "🛒 فروشگاه"}:
            await message.reply(shop(), buttons=SHOP)
            return

        shop_map = {
            norm("🧰 Lucky Badge"): "badge",
            norm("🎨 Profile Frame"): "frame",
            norm("⚡ XP Boost"): "boost",
        }
        if normalized in shop_map:
            item = shop_map[normalized]
            await message.reply(item_detail(item), buttons=SHOP_ACTION)
            return

        if normalized in {"خرید badge", "🛒 خرید badge"}:
            await message.reply(buy(uid, "badge"), buttons=SHOP)
            return

        if normalized in {"خرید frame", "🛒 خرید frame"}:
            await message.reply(buy(uid, "frame"), buttons=SHOP)
            return

        if normalized in {"خرید boost", "🛒 خرید boost"}:
            await message.reply(buy(uid, "boost"), buttons=SHOP)
            return

        if normalized in {"کوله", "🎒 کوله", "inventory"}:
            await message.reply(inventory(uid), buttons=SHOP)
            return

        if normalized in {"پیوستن", "➕ پیوستن", "join"}:
            await message.reply(join_room(uid, chat_id), buttons=ROOM)
            return

        if normalized in {"وضعیت اتاق", "🔄 وضعیت اتاق"}:
            r = db.execute(
                "SELECT * FROM rooms WHERE chat_id=? AND state!='finished' ORDER BY created_at DESC LIMIT 1",
                (chat_id,)
            ).fetchone()
            if not r:
                result = "❌ اتاق فعالی نیست."
            else:
                count = db.execute(
                    "SELECT COUNT(*) FROM room_players WHERE room_id=?",
                    (r["room_id"],)
                ).fetchone()[0]
                needed = 2 if r["mode"] == "duo" else 3
                result = f"🎮 اتاق {r['room_id']}\n👥 {count}/{needed}\nوضعیت: {r['state']}"
            await message.reply(result, buttons=ROOM)
            return

        if normalized in {"گروه", "🛡️ گروه", "پنل", "پنل گروه"}:
            await message.reply(group_panel(chat_id), buttons=GROUP)
            return

        if normalized in {"👋 خوش‌آمد", "خوش‌آمد"}:
            await message.reply(toggle_group(chat_id, "welcome"), buttons=GROUP)
            return

        if normalized in {"🔗 ضدلینک", "ضدلینک"}:
            await message.reply(toggle_group(chat_id, "anti_link"), buttons=GROUP)
            return

        if normalized in {"🚨 ضداسپم", "ضداسپم"}:
            await message.reply(toggle_group(chat_id, "anti_spam"), buttons=GROUP)
            return

        if normalized in {"آمار گروه", "📊 آمار گروه"}:
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            await message.reply(f"📊 آمار\n\n👥 کاربران ثبت‌شده: {count}", buttons=GROUP)
            return

        if normalized in {"دوستان", "🤝 دوستان", "pair"}:
            await message.reply(
                "🤝 دوستان\n\nبرای Pair دوستانه بنویس:\nزوج 12345",
                buttons=MAIN
            )
            return

        if normalized.startswith("زوج "):
            partner = normalized[4:].strip()
            await message.reply(
                f"🤝 Pair ثبت شد: {uid} ↔ {partner}",
                buttons=MAIN
            )
            return

        if normalized in {"تنظیمات", "⚙️ تنظیمات"}:
            await message.reply("⚙️ تنظیمات\n\n🌐 فارسی\n😎 لحن خودمونی", buttons=MAIN)
            return

        if normalized in {"کمک", "/help", "راهنما", "help"}:
            await message.reply(
                "🧠 راهنما\n\nبازی، سکه، جایزه، مأموریت، فروشگاه، کوله، پروفایل، رتبه، افتخارات، دوستان و گروه.",
                buttons=MAIN
            )
            return

        if normalized in {"منو", "🏠 منو", "/menu"}:
            await message.reply(home(uid), buttons=MAIN)
            return

        await message.reply(
            "🤔 اینو کامل نگرفتم 😅\nمثلاً «بازی»، «سکه» یا «فروشگاه» رو بفرست.",
            buttons=MAIN
        )

    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try:
            await event.message.reply(
                "⚠️ یه خطای موقت خوردیم 😅\nدوباره همین رو بفرست.",
                buttons=MAIN
            )
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

if __name__ == "__main__":
    threading.Thread(target=run_health, daemon=True).start()
    print("T3R0ZA_BOT starting")
    bot.run()
