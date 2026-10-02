import os
import random
import re
import sqlite3
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from spluspy import Robot, Button

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data/t3r0za.sqlite3")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from Render Environment Variables.")

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db_lock = threading.RLock()

def setup_db():
    with db_lock, db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                user_id TEXT PRIMARY KEY,
                coins INTEGER NOT NULL DEFAULT 100,
                xp INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                daily_date TEXT,
                games INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                messages INTEGER NOT NULL DEFAULT 0,
                last_seen TEXT
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
            """
        )

setup_db()

def norm(value):
    return " ".join(
        str(value or "").strip().casefold()
        .replace("‌", "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .split()
    )

def ensure_user(uid):
    with db_lock, db:
        db.execute("INSERT OR IGNORE INTO users(user_id,last_seen) VALUES (?,CURRENT_TIMESTAMP)", (uid,))
        db.execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE user_id=?", (uid,))

def user(uid):
    ensure_user(uid)
    return db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def add_xp(uid, amount):
    ensure_user(uid)
    with db_lock, db:
        db.execute("UPDATE users SET xp=xp+? WHERE user_id=?", (int(amount), uid))

def record_game(uid, won):
    with db_lock, db:
        db.execute(
            "UPDATE users SET games=games+1,wins=wins+? WHERE user_id=?",
            (1 if won else 0, uid),
        )
    add_xp(uid, 30 if won else 10)

def buttons(rows):
    return [[Button.text(str(x), resize=True, persistent=True) for x in row] for row in rows]

MAIN = buttons([
    ["🎮 بازی", "🪙 سکه"],
    ["🎁 جایزه", "🎯 مأموریت"],
    ["🛒 فروشگاه", "🎒 کوله"],
    ["👤 پروفایل", "🏆 رتبه"],
    ["⭐ افتخارات", "🤝 دوستان"],
    ["🛡️ گروه", "⚙️ تنظیمات"],
])

GAMES = buttons([
    ["🎯 کوئیز", "🧩 حدس کلمه"],
    ["⚡ واکنش", "🏆 چالش گروهی"],
    ["👥 اتاق دو نفره", "👥👥 اتاق گروهی"],
    ["🏠 منو"],
])

MODES = buttons([
    ["👤 تک‌نفره", "👥 دو نفره"],
    ["👥👥 چندنفره"],
    ["↩️ برگشت"],
])

ROOM = buttons([
    ["➕ پیوستن", "🔄 وضعیت اتاق"],
    ["❌ لغو اتاق", "🎮 بازی"],
])

SHOP = buttons([
    ["🧰 Lucky Badge", "🎨 Profile Frame"],
    ["⚡ XP Boost"],
    ["🎒 کوله", "🏠 منو"],
])

SHOP_ITEM = buttons([
    ["🛒 خرید badge", "🛒 خرید frame"],
    ["🛒 خرید boost"],
    ["↩️ فروشگاه", "🏠 منو"],
])

GROUP = buttons([
    ["👋 خوش‌آمد", "🔗 ضدلینک"],
    ["🚨 ضداسپم", "📊 آمار گروه"],
    ["🧹 پاکسازی", "ℹ️ وضعیت گروه"],
    ["🏠 منو"],
])

FRIENDS = buttons([
    ["👥 دوستان", "🤝 Pair"],
    ["🎯 مأموریت مشترک", "🎮 بازی دو نفره"],
    ["🏠 منو"],
])

pending = {}
active = {}
last_seen_message = {}

QUESTIONS = [
    ("پایتخت ژاپن کدام است؟", "توکیو"),
    ("سیاره سرخ کدام است؟", "مریخ"),
    ("5 × 8 چند می‌شود؟", "40"),
    ("آب در سطح دریا تقریباً در چند درجه می‌جوشد؟", "100"),
    ("بزرگ‌ترین اقیانوس زمین کدام است؟", "آرام"),
]
WORDS = [("🍎", "سیب"), ("🏠", "خانه"), ("🚗", "ماشین"), ("🐱", "گربه"), ("🌞", "خورشید")]

def is_group(message):
    return bool(getattr(message, "is_group", False))

def group_cfg(chat_id):
    with db_lock, db:
        row = db.execute("SELECT * FROM group_settings WHERE chat_id=?", (str(chat_id),)).fetchone()
        if row is None:
            db.execute("INSERT INTO group_settings(chat_id) VALUES (?)", (str(chat_id),))
            row = db.execute("SELECT * FROM group_settings WHERE chat_id=?", (str(chat_id),)).fetchone()
    return row

def home(uid):
    r = user(uid)
    level = 1 + r["xp"] // 100
    return (
        "⚡ T3R0ZA

"
        f"سلام 😎
🏅 Level: {level}   ✨ XP: {r['xp']}   🪙 {r['coins']}

"
        "هرچی خواستی عادی بنویس؛ مثلاً «بازی»، «سکه» یا «فروشگاه»."
    )

def wallet(uid):
    r = user(uid)
    return f"🪙 کیف پول

موجودی: {r['coins']} سکه
✨ XP: {r['xp']}
🏅 Level: {1 + r['xp']//100]}"

def claim_daily(uid):
    r = user(uid)
    today = date.today()
    if r["daily_date"] == today.isoformat():
        return "🎁 جایزه امروز رو قبلاً گرفتی 😎
فردا دوباره سر بزن."
    streak = r["streak"] + 1 if r["daily_date"] == (today - timedelta(days=1)).isoformat() else 1
    reward = 50 + min(streak, 7) * 10
    with db_lock, db:
        db.execute(
            "UPDATE users SET coins=coins+?,streak=?,daily_date=? WHERE user_id=?",
            (reward, streak, today.isoformat(), uid),
        )
    add_xp(uid, 20)
    return f"🎁 جایزه روزانه گرفتی!
🪙 +{reward} سکه
🔥 Streak: {streak}
✨ +20 XP"

def profile(uid):
    r = user(uid)
    return (
        "👤 پروفایل T3R0ZA

"
        f"🆔 {uid}
🏅 Level: {1 + r['xp']//100}
✨ XP: {r['xp']}
"
        f"🪙 Coins: {r['coins']}
🔥 Streak: {r['streak']}
"
        f"🎮 بازی: {r['games']}   🏆 برد: {r['wins']}"
    )

def achievements(uid):
    r = user(uid)
    checks = [
        ("🌱 شروع‌کننده", r["xp"] >= 5),
        ("🎮 گیمر", r["games"] >= 1),
        ("🏆 برنده", r["wins"] >= 1),
        ("🔥 فعال", r["streak"] >= 3),
        ("⭐ Level 10", r["xp"] >= 900),
    ]
    return "⭐ افتخارات

" + "
".join(f"{'✅' if ok else '🔒'} {name}" for name, ok in checks)

def leaderboard():
    rows = db.execute(
        "SELECT user_id,xp,wins FROM users ORDER BY xp DESC,wins DESC LIMIT 10"
    ).fetchall()
    if not rows:
        return "🏆 هنوز رکوردی ثبت نشده."
    lines = ["🏆 رتبه‌بندی T3R0ZA
"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['user_id']} — {r['xp']} XP — 🏆 {r['wins']}")
    return "
".join(lines)

def missions(uid):
    r = user(uid)
    return (
        "🎯 مأموریت‌های امروز

"
        "✅ ورود به بات — +5 XP
"
        "🎮 انجام بازی — +10/+30 XP
"
        "🎁 جایزه روزانه — +20 XP
"
        "💬 فعالیت در چت — ثبت می‌شود

"
        f"وضعیت تو: Level {1+r['xp']//100} | {r['xp']} XP"
    )

ITEMS = {
    "badge": (250, "🧰 Lucky Badge", "آیتم کلکسیونی پروفایل؛ برای نمایش و جمع‌آوری."),
    "frame": (400, "🎨 Profile Frame", "قاب تزئینی پروفایل؛ ظاهر حساب را شخصی می‌کند."),
    "boost": (600, "⚡ XP Boost", "آیتم تقویتی سیستم XP؛ در این نسخه در کوله ذخیره می‌شود."),
}

def shop():
    return (
        "🛒 فروشگاه T3R0ZA

"
        "🧰 Lucky Badge — 250 🪙
"
        "🎨 Profile Frame — 400 🪙
"
        "⚡ XP Boost — 600 🪙

"
        "یک آیتم رو بزن تا توضیحش رو ببینی."
    )

def shop_detail(item):
    price, name, detail = ITEMS[item]
    return f"{name}

💰 قیمت: {price} سکه
ℹ️ {detail}

بعدش می‌تونی خریدش کنی."

def buy(uid, item):
    price, name, detail = ITEMS[item]
    r = user(uid)
    if r["coins"] < price:
        return f"❌ سکه کافی نداری.
قیمت: {price}
موجودی: {r['coins']}"
    with db_lock, db:
        db.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (price, uid))
        db.execute(
            "INSERT INTO inventory(user_id,item_id,qty) VALUES (?,?,1) "
            "ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+1",
            (uid, item),
        )
    return f"✅ خرید شد!
{name}
🪙 -{price} سکه"

def inventory(uid):
    rows = db.execute("SELECT item_id,qty FROM inventory WHERE user_id=?", (uid,)).fetchall()
    if not rows:
        return "🎒 کوله‌بری خالیه."
    return "🎒 کوله‌بری

" + "
".join(
        f"• {ITEMS.get(r['item_id'], ('','', ''))[1]} × {r['qty']}" for r in rows
    )

def group_panel(chat_id):
    s = group_cfg(chat_id)
    return (
        "🛡️ T3R0ZA GROUP

"
        f"👋 خوش‌آمد: {'روشن' if s['welcome'] else 'خاموش'}
"
        f"🔗 ضدلینک: {'روشن' if s['anti_link'] else 'خاموش'}
"
        f"🚨 ضداسپم: {'روشن' if s['anti_spam'] else 'خاموش'}

"
        "از دکمه‌ها برای تغییر وضعیت استفاده کن."
    )

def toggle_group(chat_id, field):
    group_cfg(chat_id)
    with db_lock, db:
        cur = db.execute(f"SELECT {field} FROM group_settings WHERE chat_id=?", (str(chat_id),)).fetchone()[0]
        new = 0 if cur else 1
        db.execute(f"UPDATE group_settings SET {field}=? WHERE chat_id=?", (new, str(chat_id)))
    names = {"welcome": "👋 خوش‌آمد", "anti_link": "🔗 ضدلینک", "anti_spam": "🚨 ضداسپم"}
    return f"{names[field]} {'روشن' if new else 'خاموش'} شد."

def create_room(uid, chat_id, mode):
    room_id = uuid_id()
    needed = 2 if mode == "duo" else 3
    with db_lock, db:
        old = db.execute(
            "SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",
            (str(chat_id),),
        ).fetchone()
        if old:
            count = db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?", (old["room_id"],)).fetchone()[0]
            return f"🎮 اتاق فعاله!
🆔 {old['room_id']}
👥 {count}/{needed}

«پیوستن» رو بزن."
        db.execute(
            "INSERT INTO rooms(room_id,chat_id,mode,host_id) VALUES (?,?,?,?)",
            (room_id, str(chat_id), mode, uid),
        )
        db.execute("INSERT INTO room_players(room_id,user_id) VALUES (?,?)", (room_id, uid))
    return f"🎮 اتاق ساخته شد!

🆔 {room_id}
👥 1/{needed}

بقیه «پیوستن» رو بزنن."

def uuid_id():
    return ("%06X" % random.randrange(0x1000000))

def join_room(uid, chat_id):
    with db_lock, db:
        room = db.execute(
            "SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",
            (str(chat_id),),
        ).fetchone()
        if not room:
            return "❌ اتاقی برای ورود نیست. اول «اتاق دو نفره» یا «اتاق گروهی» رو بزن."
        db.execute("INSERT OR IGNORE INTO room_players(room_id,user_id) VALUES (?,?)", (room["room_id"], uid))
        count = db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?", (room["room_id"],)).fetchone()[0]
        needed = 2 if room["mode"] == "duo" else 3
        if count >= needed:
            q, answer = random.choice(QUESTIONS)
            db.execute(
                "UPDATE rooms SET state='started',question=?,answer=? WHERE room_id=?",
                (q, answer, room["room_id"]),
            )
            return f"🔥 تعداد کامل شد!

❓ {q}

اولین جواب درست برنده‌ست 🏆"
    return f"✅ وارد شدی!
👥 {count}/{needed}
منتظر بقیه‌ایم..."

def room_status(uid, chat_id):
    room = db.execute(
        "SELECT * FROM rooms WHERE chat_id=? AND state!='finished' ORDER BY created_at DESC LIMIT 1",
        (str(chat_id),),
    ).fetchone()
    if not room:
        return "❌ اتاق فعالی نیست."
    count = db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?", (room["room_id"],)).fetchone()[0]
    needed = 2 if room["mode"] == "duo" else 3
    return f"🎮 اتاق {room['room_id']}
👥 {count}/{needed}
وضعیت: {room['state']}"

def answer_room(uid, chat_id, text):
    room = db.execute(
        "SELECT * FROM rooms WHERE chat_id=? AND state='started' ORDER BY created_at DESC LIMIT 1",
        (str(chat_id),),
    ).fetchone()
    if not room or norm(text) != norm(room["answer"]):
        return None
    with db_lock, db:
        db.execute("UPDATE rooms SET state='finished' WHERE room_id=?", (room["room_id"],))
    record_game(uid, True)
    return f"🏆 برنده: {uid}\n✅ جواب: {room['answer']}\n✨ +30 XP"

def handle_game(uid, chat_id, text):
    key = (uid, str(chat_id))
    if key in active:
        kind, expected = active.pop(key)
        if norm(text) == norm(expected):
            record_game(uid, True)
            return "✅ جواب درست! 🏆\n✨ +30 XP"
        record_game(uid, False)
        return f"❌ جواب درست: {expected}\n✨ +10 XP"

    room_result = answer_room(uid, chat_id, text)
    if room_result:
        return room_result
    return None

bot = Robot(TOKEN)

@bot.on_message()
async def handler(client, event):
    try:
        message = getattr(event, "message", event)
        text = (getattr(message, "raw_text", None) or getattr(message, "text", None) or "").strip()
        if not text:
            return

        uid = str(getattr(message, "sender_id", None) or getattr(event, "sender_id", "unknown"))
        chat_id = str(getattr(message, "chat_id", None) or getattr(event, "chat_id", None) or uid)
        ensure_user(uid)

        group = is_group(message)
        cfg = group_cfg(chat_id) if group else None

        previous = last_seen_message.get((uid, chat_id))
        last_seen_message[(uid, chat_id)] = (norm(text), time.time())
        if group and cfg["anti_spam"] and previous:
            old_text, old_time = previous
            if old_text == norm(text) and time.time() - old_time < 2:
                try:
                    await message.delete()
                except Exception:
                    pass
                return

        if group and cfg["anti_link"] and re.search(r"(https?://|www\.|\.com\b|t\.me/)", text, re.I):
            try:
                await message.delete()
            except Exception:
                pass
            return

        db.execute("UPDATE users SET messages=messages+1 WHERE user_id=?", (uid,))

        n = norm(text)

        if n in {"/start", "شروع", "استارت"}:
            add_xp(uid, 5)
            await event.reply(home(uid), buttons=MAIN)
            return

        ongoing = handle_game(uid, chat_id, text)
        if ongoing:
            await event.reply(ongoing, buttons=GAMES)
            return

        if n in {"بازی", "گیم", "🎮 بازی"}:
            pending.pop(uid, None)
            await event.reply(
                "🎮 T3R0ZA GAME CENTER\n\n"
                "چه بازی‌ای بریم؟ 😎\n\n"
                "🎯 کوئیز\n🧩 حدس کلمه\n⚡ واکنش\n🏆 چالش گروهی\n\n"
                "یکی رو انتخاب کن 👇",
                buttons=GAMES,
            )
            return

        game_map = {
            "🎯 کوئیز": "quiz",
            "کوئیز": "quiz",
            "🧩 حدس کلمه": "word",
            "حدس کلمه": "word",
            "⚡ واکنش": "reaction",
            "واکنش": "reaction",
            "🏆 چالش گروهی": "group_quiz",
            "چالش گروهی": "group_quiz",
        }
        if n in {norm(k) for k in game_map}:
            kind = game_map[next(k for k in game_map if norm(k) == n)]
            pending[uid] = kind
            text_detail = {
                "quiz": "🎯 کوئیز: سؤال‌های کوتاه و سریع؛ ۱، ۲ یا چندنفره.",
                "word": "🧩 حدس کلمه: از روی ایموجی اسم کلمه رو پیدا کن؛ ۱ یا ۲ نفره.",
                "reaction": "⚡ واکنش: راند کوتاه تمرکز و پاسخ؛ ۱ یا ۲ نفره.",
                "group_quiz": "🏆 چالش گروهی: سؤال گروهی برای رقابت دوستانه.",
            }[kind]
            await event.reply(text_detail + "\n\n👤 تک‌نفره\n👥 دو نفره\n👥👥 چندنفره", buttons=MODES)
            return

        if uid in pending:
            kind = pending.pop(uid)
            if n in {"👤 تک‌نفره", "تک‌نفره", "تک نفره"}:
                if kind == "group_quiz":
                    await event.reply("🏆 چالش گروهی باید حداقل دو نفر داشته باشه.", buttons=MODES)
                    return
                if kind == "quiz":
                    q, a = random.choice(QUESTIONS)
                    active[(uid, chat_id)] = (kind, a)
                    await event.reply(f"🔥 شروع شد!\n\n❓ {q}\n\nجوابت رو بفرست.", buttons=GAMES)
                elif kind == "word":
                    em, a = random.choice(WORDS)
                    active[(uid, chat_id)] = (kind, a)
                    await event.reply(f"🔥 شروع شد!\n\n{em}\n\nاسمش چیه؟", buttons=GAMES)
                else:
                    active[(uid, chat_id)] = (kind, "go")
                    await event.reply("⚡ آماده‌ای؟\nوقتی دیدی GO اومد، بنویس GO.", buttons=GAMES)
                return

            if n in {"👥 دو نفره", "دونفره", "دو نفره"}:
                await event.reply(create_room(uid, chat_id, "duo"), buttons=ROOM)
                return

            if n in {"👥👥 چندنفره", "چندنفره", "چند نفره"}:
                await event.reply(create_room(uid, chat_id, "multi"), buttons=ROOM)
                return

            await event.reply("از گزینه‌های بالا یکی رو انتخاب کن 👆", buttons=MODES)
            return

        if n in {"سکه", "کیف پول", "🪙 سکه"}:
            await event.reply(wallet(uid), buttons=MAIN)
            return

        if n in {"جایزه", "🎁 جایزه", "جایزه روزانه"}:
            await event.reply(claim_daily(uid), buttons=MAIN)
            return

        if n in {"پروفایل", "👤 پروفایل"}:
            await event.reply(profile(uid), buttons=MAIN)
            return

        if n in {"رتبه", "🏆 رتبه", "رنک"}:
            await event.reply(leaderboard(), buttons=MAIN)
            return

        if n in {"افتخارات", "⭐ افتخارات"}:
            await event.reply(achievements(uid), buttons=MAIN)
            return

        if n in {"مأموریت", "ماموریت", "🎯 مأموریت"}:
            await event.reply(missions(uid), buttons=MAIN)
            return

        if n in {"فروشگاه", "🛒 فروشگاه"}:
            await event.reply(shop(), buttons=SHOP)
            return

        if n in {"🧰 lucky badge", "lucky badge", "🎨 profile frame", "profile frame", "⚡ xp boost", "xp boost"}:
            item = "badge" if "badge" in n else "frame" if "frame" in n else "boost"
            await event.reply(shop_detail(item), buttons=SHOP_ITEM)
            return

        if n in {"خرید badge", "🛒 خرید badge"}:
            await event.reply(buy(uid, "badge"), buttons=SHOP)
            return

        if n in {"خرید frame", "🛒 خرید frame"}:
            await event.reply(buy(uid, "frame"), buttons=SHOP)
            return

        if n in {"خرید boost", "🛒 خرید boost"}:
            await event.reply(buy(uid, "boost"), buttons=SHOP)
            return

        if n in {"کوله", "🎒 کوله", "inventory"}:
            await event.reply(inventory(uid), buttons=SHOP)
            return

        if n in {"پیوستن", "➕ پیوستن", "join"}:
            await event.reply(join_room(uid, chat_id), buttons=ROOM)
            return

        if n in {"وضعیت اتاق", "🔄 وضعیت اتاق"}:
            await event.reply(room_status(uid, chat_id), buttons=ROOM)
            return

        if n in {"پنل", "گروه", "🛡️ گروه", "پنل گروه"}:
            await event.reply(group_panel(chat_id), buttons=GROUP)
            return

        if n in {"خوش‌آمد", "👋 خوش‌آمد"} and group:
            await event.reply(toggle_group(chat_id, "welcome"), buttons=GROUP)
            return

        if n in {"ضدلینک", "🔗 ضدلینک"} and group:
            await event.reply(toggle_group(chat_id, "anti_link"), buttons=GROUP)
            return

        if n in {"ضداسپم", "🚨 ضداسپم"} and group:
            await event.reply(toggle_group(chat_id, "anti_spam"), buttons=GROUP)
            return

        if n in {"آمار گروه", "📊 آمار گروه"} and group:
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            await event.reply(f"📊 آمار\n\n👥 حساب‌های ثبت‌شده: {count}", buttons=GROUP)
            return

        if n in {"دوستان", "🤝 دوستان", "pair"}:
            await event.reply(
                "🤝 بخش دوستان\n\n"
                "برای Pair دوستانه بنویس: «زوج 12345»\n"
                "این بخش برای بازی و مأموریت دوستانه است.",
                buttons=FRIENDS,
            )
            return

        if n.startswith("زوج "):
            partner = n[4:].strip()
            if partner and partner != uid:
                await event.reply(f"🤝 Pair ثبت شد بین {uid} و {partner}.", buttons=FRIENDS)
            else:
                await event.reply("❌ شناسهٔ کاربر دیگری رو وارد کن.", buttons=FRIENDS)
            return

        if n in {"تنظیمات", "⚙️ تنظیمات"}:
            await event.reply("⚙️ تنظیمات\n\n🌐 فارسی\n😎 لحن خودمونی", buttons=MAIN)
            return

        if n in {"کمک", "/help", "راهنما", "help"}:
            await event.reply(
                "🧠 راهنما\n\n"
                "بازی، سکه، جایزه، مأموریت، فروشگاه، کوله، پروفایل، رتبه، افتخارات، دوستان و گروه.",
                buttons=MAIN,
            )
            return

        if n in {"منو", "🏠 منو", "/menu"}:
            await event.reply(home(uid), buttons=MAIN)
            return

        if is_group(message) and n in {"سلام", "hello"} and cfg["welcome"]:
            await event.reply("👋 سلام! T3R0ZA اینجاست 😎", buttons=MAIN)
            return

        await event.reply(
            "🤔 اینو کامل نگرفتم 😅\n"
            "مثلاً بنویس «بازی»، «سکه» یا «فروشگاه».",
            buttons=MAIN,
        )

    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try:
            await event.reply("⚠️ یه خطای موقت خوردیم 😅\nدوباره همین رو بفرست.", buttons=MAIN)
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"T3R0ZA_BOT OK")

    def log_message(self, *_args):
        return

def start_health():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health, daemon=True).start()
    print("T3R0ZA_BOT starting")
    bot.run()
