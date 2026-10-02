import os
import random
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

def init_db():
    with lock, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id TEXT PRIMARY KEY, coins INTEGER NOT NULL DEFAULT 100,
            xp INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0,
            daily_date TEXT, games INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS inventory(
            user_id TEXT NOT NULL, item_id TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(user_id, item_id)
        );
        CREATE TABLE IF NOT EXISTS rooms(
            room_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, mode TEXT NOT NULL,
            host_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'waiting',
            question TEXT, answer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS room_players(
            room_id TEXT NOT NULL, user_id TEXT NOT NULL,
            PRIMARY KEY(room_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS group_settings(
            chat_id TEXT PRIMARY KEY, welcome INTEGER NOT NULL DEFAULT 1,
            anti_link INTEGER NOT NULL DEFAULT 0, anti_spam INTEGER NOT NULL DEFAULT 0
        );
        """)

init_db()

def norm(text):
    return " ".join(str(text or "").strip().casefold().replace("‌", "").replace("ي", "ی").replace("ك", "ک").split())

def ensure_user(uid):
    with lock, db:
        db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (str(uid),))

def get_user(uid):
    ensure_user(uid)
    return db.execute("SELECT * FROM users WHERE user_id=?", (str(uid),)).fetchone()

def add_xp(uid, amount):
    with lock, db:
        db.execute("UPDATE users SET xp=xp+? WHERE user_id=?", (int(amount), str(uid)))

def level(uid):
    return 1 + get_user(uid)["xp"] // 100

def record_game(uid, won):
    with lock, db:
        db.execute("UPDATE users SET games=games+1,wins=wins+? WHERE user_id=?", (1 if won else 0, uid))
    add_xp(uid, 30 if won else 10)

def kb(rows):
    return [[Button.text(x) for x in row] for row in rows]

MAIN = kb([["🎮 بازی", "🪙 سکه"], ["🎁 جایزه", "🎯 مأموریت"], ["🛒 فروشگاه", "🎒 کوله"], ["👤 پروفایل", "🏆 رتبه"], ["⭐ افتخارات", "🤝 دوستان"], ["🛡️ گروه", "⚙️ تنظیمات"]])
GAMES = kb([["🎯 کوئیز", "🧩 حدس کلمه"], ["⚡ واکنش", "🏆 چالش گروهی"], ["👥 اتاق دو نفره", "👥👥 اتاق گروهی"], ["🏠 منو"]])
MODES = kb([["👤 تک‌نفره", "👥 دو نفره"], ["👥👥 چندنفره"], ["↩️ برگشت"]])
ROOMS = kb([["➕ پیوستن", "🔄 وضعیت اتاق"], ["❌ لغو اتاق", "🎮 بازی"]])
SHOP = kb([["🧰 Lucky Badge", "🎨 Profile Frame"], ["⚡ XP Boost"], ["🎒 کوله", "🏠 منو"]])
SHOP_ACTIONS = kb([["🛒 خرید badge", "🛒 خرید frame"], ["🛒 خرید boost"], ["↩️ فروشگاه", "🏠 منو"]])
GROUP = kb([["👋 خوش‌آمد", "🔗 ضدلینک"], ["🚨 ضداسپم", "📊 آمار گروه"], ["🏠 منو"]])

ITEMS = {
    "badge": (250, "🧰 Lucky Badge", "آیتم کلکسیونی پروفایل."),
    "frame": (400, "🎨 Profile Frame", "قاب تزئینی پروفایل."),
    "boost": (600, "⚡ XP Boost", "آیتم سیستم XP؛ در کوله ذخیره می‌شود."),
}
QUESTIONS = [("پایتخت ژاپن کدام است؟", "توکیو"), ("سیاره سرخ کدام است؟", "مریخ"), ("5 × 8 چند می‌شود؟", "40"), ("آب در سطح دریا تقریباً چند درجه می‌جوشد؟", "100"), ("بزرگ‌ترین اقیانوس زمین کدام است؟", "آرام")]
WORDS = [("🍎", "سیب"), ("🏠", "خانه"), ("🚗", "ماشین"), ("🐱", "گربه"), ("🌞", "خورشید")]
PENDING = {}
ACTIVE = {}

def home(uid):
    r = get_user(uid)
    return f"""⚡ T3R0ZA

سلام رفیق 😎

🏅 Level: {level(uid)}
✨ XP: {r["xp"]}
🪙 سکه: {r["coins"]}

«بازی»، «سکه»، «جایزه»، «فروشگاه» یا «پروفایل» رو بفرست.
"""

def wallet(uid):
    r = get_user(uid)
    return f"""🪙 کیف پول

موجودی: {r["coins"]} سکه
✨ XP: {r["xp"]}
🏅 Level: {level(uid)}
"""

def daily(uid):
    r = get_user(uid)
    today = date.today()
    if r["daily_date"] == today.isoformat():
        return """🎁 جایزه امروز رو قبلاً گرفتی 😎

فردا دوباره سر بزن.
"""
    yesterday = (today - timedelta(days=1)).isoformat()
    streak = r["streak"] + 1 if r["daily_date"] == yesterday else 1
    reward = 50 + min(streak, 7) * 10
    with lock, db:
        db.execute("UPDATE users SET coins=coins+?,streak=?,daily_date=? WHERE user_id=?", (reward, streak, today.isoformat(), uid))
    add_xp(uid, 20)
    return f"""🎁 جایزه روزانه گرفتی!

🪙 +{reward} سکه
🔥 Streak: {streak}
✨ +20 XP
"""

def profile(uid):
    r = get_user(uid)
    return f"""👤 پروفایل T3R0ZA

🆔 {uid}
🏅 Level: {level(uid)}
✨ XP: {r["xp"]}
🪙 Coins: {r["coins"]}
🔥 Streak: {r["streak"]}
🎮 بازی‌ها: {r["games"]}
🏆 بردها: {r["wins"]}
"""

def leaderboard():
    rows = db.execute("SELECT user_id,xp,wins FROM users ORDER BY xp DESC,wins DESC LIMIT 10").fetchall()
    if not rows: return "🏆 هنوز رکوردی ثبت نشده."
    return "🏆 رتبه‌بندی T3R0ZA\n\n" + "\n".join(f"{i}. {r['user_id']} — {r['xp']} XP — 🏆 {r['wins']}" for i,r in enumerate(rows,1))

def achievements(uid):
    r = get_user(uid)
    checks = [("🌱 شروع‌کننده", r["xp"] >= 5), ("🎮 گیمر", r["games"] >= 1), ("🏆 برنده", r["wins"] >= 1), ("🔥 فعال", r["streak"] >= 3), ("⭐ Level 10", level(uid) >= 10)]
    return "⭐ افتخارات\n\n" + "\n".join((("✅ " if ok else "🔒 ") + name) for name,ok in checks)

def missions(uid):
    r = get_user(uid)
    return f"""🎯 مأموریت‌های امروز

✅ ورود به بات — +5 XP
🎮 انجام بازی — +10/+30 XP
🎁 جایزه روزانه — +20 XP

🏅 Level {level(uid)}
✨ XP {r["xp"]}
"""

def shop():
    return """🛒 فروشگاه T3R0ZA

هر آیتم رو بزن تا توضیحش رو ببینی.
"""

def item_detail(item):
    price,name,detail = ITEMS[item]
    return f""" {name}

💰 قیمت: {price} سکه
ℹ️ {detail}

بعدش می‌تونی خرید کنی.
"""

def buy(uid,item):
    price,name,_ = ITEMS[item]
    r = get_user(uid)
    if r["coins"] < price:
        return f"""❌ سکه کافی نداری.

💰 قیمت: {price}
🪙 موجودی: {r["coins"]}
"""
    with lock,db:
        db.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (price,uid))
        db.execute("INSERT INTO inventory(user_id,item_id,qty) VALUES (?,?,1) ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+1", (uid,item))
    return f"""✅ خرید انجام شد!

{name}
🪙 -{price} سکه
"""

def inventory(uid):
    rows = db.execute("SELECT item_id,qty FROM inventory WHERE user_id=?", (uid,)).fetchall()
    if not rows: return "🎒 کوله‌بری خالیه."
    return "🎒 کوله‌بری\n\n" + "\n".join(f"• {ITEMS.get(r['item_id'], (0,r['item_id'],))[1]} × {r['qty']}" for r in rows)

def group_cfg(chat_id):
    with lock,db:
        row = db.execute("SELECT * FROM group_settings WHERE chat_id=?", (str(chat_id),)).fetchone()
        if row is None:
            db.execute("INSERT INTO group_settings(chat_id) VALUES (?)",(str(chat_id),))
            row = db.execute("SELECT * FROM group_settings WHERE chat_id=?",(str(chat_id),)).fetchone()
    return row

def group_panel(chat_id):
    r=group_cfg(chat_id)
    return f"""🛡️ T3R0ZA GROUP

👋 خوش‌آمد: {"روشن" if r["welcome"] else "خاموش"}
🔗 ضدلینک: {"روشن" if r["anti_link"] else "خاموش"}
🚨 ضداسپم: {"روشن" if r["anti_spam"] else "خاموش"}
"""

def toggle_group(chat_id,field):
    r=group_cfg(chat_id)
    current=r[field]
    new=0 if current else 1
    with lock,db:
        db.execute(f"UPDATE group_settings SET {field}=? WHERE chat_id=?",(new,str(chat_id)))
    labels={"welcome":"👋 خوش‌آمد","anti_link":"🔗 ضدلینک","anti_spam":"🚨 ضداسپم"}
    state="روشن" if new else "خاموش"
    return f"{labels[field]} {state} شد."

def make_room(uid,chat_id,mode):
    needed=2 if mode=="duo" else 3
    with lock,db:
        old=db.execute("SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",(str(chat_id),)).fetchone()
        if old:
            count=db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?",(old["room_id"],)).fetchone()[0]
            return f"🎮 اتاق فعاله!\n🆔 {old['room_id']}\n👥 {count}/{needed}\n\n«پیوستن» رو بزن."
        room_id=f"{random.randrange(0x1000000):06X}"
        db.execute("INSERT INTO rooms(room_id,chat_id,mode,host_id) VALUES (?,?,?,?)",(room_id,str(chat_id),mode,uid))
        db.execute("INSERT INTO room_players(room_id,user_id) VALUES (?,?)",(room_id,uid))
    return f"""🎮 اتاق ساخته شد!

🆔 کد: {room_id}
👥 بازیکنان: 1/{needed}

بقیه «پیوستن» رو بزنن.
"""

def join_room(uid,chat_id):
    with lock,db:
        room=db.execute("SELECT * FROM rooms WHERE chat_id=? AND state='waiting' ORDER BY created_at DESC LIMIT 1",(str(chat_id),)).fetchone()
        if not room: return "❌ اتاقی برای ورود نیست."
        db.execute("INSERT OR IGNORE INTO room_players(room_id,user_id) VALUES (?,?)",(room["room_id"],uid))
        count=db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?",(room["room_id"],)).fetchone()[0]
        needed=2 if room["mode"]=="duo" else 3
        if count>=needed:
            q,a=random.choice(QUESTIONS)
            db.execute("UPDATE rooms SET state='started',question=?,answer=? WHERE room_id=?",(q,a,room["room_id"]))
            return f"""🔥 تعداد کامل شد!

❓ {q}

اولین جواب درست برنده‌ست 🏆
"""
    return f"✅ وارد شدی!\n👥 {count}/{needed}\nمنتظر بقیه‌ایم..."

def room_answer(uid,chat_id,text):
    row=db.execute("SELECT * FROM rooms WHERE chat_id=? AND state='started' ORDER BY created_at DESC LIMIT 1",(str(chat_id),)).fetchone()
    if not row or norm(text)!=norm(row["answer"]): return None
    with lock,db:
        db.execute("UPDATE rooms SET state='finished' WHERE room_id=?",(row["room_id"],))
    record_game(uid,True)
    return f"🏆 برنده: {uid}\n✅ جواب: {row['answer']}\n✨ +30 XP"

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"T3R0ZA_BOT OK")
    def log_message(self,*args): return

def start_health():
    HTTPServer(("0.0.0.0",PORT),HealthHandler).serve_forever()

bot=Robot(TOKEN)

async def reply_safe(event, text_value, buttons=None):
    reply_fn = getattr(event, "reply", None)
    if not callable(reply_fn):
        message_obj = getattr(event, "message", None)
        reply_fn = getattr(message_obj, "reply", None)
    if not callable(reply_fn):
        raise RuntimeError("SplusPy event has no reply() method.")
    if buttons is not None:
        try:
            return await reply_fn(text_value, buttons=buttons)
        except TypeError:
            return await reply_fn(text_value)
    return await reply_fn(text_value)

@bot.on_message()
async def handler(client,event):
    try:
        message=getattr(event, "message", event)
        text_value = (
            getattr(event, "raw_text", None)
            or getattr(event, "text", None)
            or getattr(message, "raw_text", None)
            or getattr(message, "text", None)
            or getattr(message, "message", None)
            or ""
        )
        text = str(text_value).strip()
        if not text:
            return
        uid_value = getattr(event, "sender_id", None) or getattr(message, "sender_id", None)
        chat_value = getattr(event, "chat_id", None) or getattr(message, "chat_id", None)
        uid=str(uid_value)
        chat_id=str(chat_value)
        print(f"T3R0ZA incoming text={text!r} uid={uid} chat={chat_id}")
        ensure_user(uid)
        n=norm(text)

        if "تروزا" in n or "t3r0za" in n:
            if "کونی" in n:
                caller_reply = "😂 بنال داش، گوشم با توئه."
            elif "سلام" in n:
                caller_reply = "سلام داش 😎 تروزا اینجاست."
            elif "چطوری" in n or "خوبی" in n:
                caller_reply = "رو فرمَم داش ⚡ تو چی؟"
            elif "کی هستی" in n or "کی ای" in n:
                caller_reply = "من T3R0ZA‌م 😎 رفیق سرگرمیِ این جمع."
            else:
                caller_reply = random.choice([
                    "جان داش؟ 😎",
                    "بنال، تروزا گوشه 👀",
                    "حواسم هست داش ⚡",
                    "چی شده؟ بگو 😏",
                ])
            await reply_safe(event, caller_reply, buttons=MAIN)
            return

        if n in {"/start","شروع","استارت"}:
            add_xp(uid,5)
            await reply_safe(event, home(uid),buttons=MAIN)
            return

        active_key=(uid,chat_id)
        if active_key in ACTIVE:
            expected=ACTIVE.pop(active_key)
            if norm(text)==norm(expected):
                record_game(uid,True)
                await reply_safe(event, "✅ جواب درست! 🏆\n✨ +30 XP",buttons=GAMES)
            else:
                record_game(uid,False)
                await reply_safe(event, f"❌ جواب درست: {expected}\n✨ +10 XP",buttons=GAMES)
            return

        room_result=room_answer(uid,chat_id,text)
        if room_result:
            await reply_safe(event, room_result,buttons=ROOMS)
            return

        if n in {"بازی","گیم","🎮 بازی"}:
            await reply_safe(event, """🎮 T3R0ZA GAME CENTER

چه بازی‌ای بریم؟ 😎

🎯 کوئیز
🧩 حدس کلمه
⚡ واکنش
🏆 چالش گروهی

یکی رو انتخاب کن 👇
""",buttons=GAMES)
            return

        game_map={"🎯 کوئیز":"quiz","کوئیز":"quiz","🧩 حدس کلمه":"word","حدس کلمه":"word","⚡ واکنش":"reaction","واکنش":"reaction","🏆 چالش گروهی":"group","چالش گروهی":"group"}
        if n in {norm(x) for x in game_map}:
            key=next(x for x in game_map if norm(x)==n)
            kind=game_map[key]
            PENDING[uid]=kind
            desc={
                "quiz":"🎯 کوئیز\n\nسؤال‌های کوتاه و سریع؛ ۱، ۲ یا چندنفره.",
                "word":"🧩 حدس کلمه\n\nاز روی ایموجی حدس بزن؛ ۱ یا ۲ نفره.",
                "reaction":"⚡ واکنش\n\nراند کوتاه تمرکز و پاسخ؛ ۱ یا ۲ نفره.",
                "group":"🏆 چالش گروهی\n\nمسابقه دانستنی برای جمع."
            }[kind]
            await reply_safe(event, desc+"\n\nحالت بازی رو انتخاب کن 👇",buttons=MODES)
            return

        if uid in PENDING:
            kind=PENDING.pop(uid)
            if n in {"👤 تک‌نفره","تک‌نفره","تک نفره"}:
                if kind=="group":
                    PENDING[uid]=kind
                    await reply_safe(event, "🏆 چالش گروهی حداقل دو نفر می‌خواد.",buttons=MODES)
                    return
                if kind=="quiz":
                    q,a=random.choice(QUESTIONS)
                    ACTIVE[(uid,chat_id)]=a
                    await reply_safe(event, f"🔥 شروع شد!\n\n❓ {q}\n\nجوابت رو بفرست.",buttons=GAMES)
                elif kind=="word":
                    em,a=random.choice(WORDS)
                    ACTIVE[(uid,chat_id)]=a
                    await reply_safe(event, f"🔥 شروع شد!\n\n{em}\n\nاسمش چیه؟",buttons=GAMES)
                else:
                    ACTIVE[(uid,chat_id)]="go"
                    await reply_safe(event, """⚡ تست واکنش

وقتی GO دیدی، سریع بنویس GO.
""",buttons=GAMES)
                return
            if n in {"👥 دو نفره","دونفره","دو نفره"}:
                await reply_safe(event, make_room(uid,chat_id,"duo"),buttons=ROOMS)
                return
            if n in {"👥👥 چندنفره","چندنفره","چند نفره"}:
                await reply_safe(event, make_room(uid,chat_id,"multi"),buttons=ROOMS)
                return
            PENDING[uid]=kind
            await reply_safe(event, "از گزینه‌های بالا یکی رو انتخاب کن 👆",buttons=MODES)
            return

        if n in {"سکه","کیف پول","🪙 سکه"}:
            await reply_safe(event, wallet(uid),buttons=MAIN)
            return
        if n in {"جایزه","🎁 جایزه","جایزه روزانه"}:
            await reply_safe(event, daily(uid),buttons=MAIN)
            return
        if n in {"پروفایل","👤 پروفایل"}:
            await reply_safe(event, profile(uid),buttons=MAIN)
            return
        if n in {"رتبه","🏆 رتبه","رنک"}:
            await reply_safe(event, leaderboard(),buttons=MAIN)
            return
        if n in {"افتخارات","⭐ افتخارات"}:
            await reply_safe(event, achievements(uid),buttons=MAIN)
            return
        if n in {"مأموریت","ماموریت","🎯 مأموریت"}:
            await reply_safe(event, missions(uid),buttons=MAIN)
            return
        if n in {"فروشگاه","🛒 فروشگاه"}:
            await reply_safe(event, shop(),buttons=SHOP)
            return
        items_by_text={norm("🧰 Lucky Badge"):"badge",norm("🎨 Profile Frame"):"frame",norm("⚡ XP Boost"):"boost"}
        if n in items_by_text:
            await reply_safe(event, item_detail(items_by_text[n]),buttons=SHOP_ACTIONS)
            return
        if n in {"خرید badge","🛒 خرید badge"}:
            await reply_safe(event, buy(uid,"badge"),buttons=SHOP)
            return
        if n in {"خرید frame","🛒 خرید frame"}:
            await reply_safe(event, buy(uid,"frame"),buttons=SHOP)
            return
        if n in {"خرید boost","🛒 خرید boost"}:
            await reply_safe(event, buy(uid,"boost"),buttons=SHOP)
            return
        if n in {"کوله","🎒 کوله","کوله‌بری"}:
            await reply_safe(event, inventory(uid),buttons=SHOP)
            return
        if n in {"پیوستن","➕ پیوستن","join"}:
            await reply_safe(event, join_room(uid,chat_id),buttons=ROOMS)
            return
        if n in {"وضعیت اتاق","🔄 وضعیت اتاق"}:
            row=db.execute("SELECT * FROM rooms WHERE chat_id=? AND state!='finished' ORDER BY created_at DESC LIMIT 1",(chat_id,)).fetchone()
            if not row: result="❌ اتاق فعالی نیست."
            else:
                count=db.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?",(row["room_id"],)).fetchone()[0]
                needed=2 if row["mode"]=="duo" else 3
                result=f"🎮 اتاق {row['room_id']}\n👥 {count}/{needed}\nوضعیت: {row['state']}"
            await reply_safe(event, result,buttons=ROOMS)
            return
        if n in {"گروه","🛡️ گروه","پنل","پنل گروه"}:
            await reply_safe(event, group_panel(chat_id),buttons=GROUP)
            return
        if n in {"👋 خوش‌آمد","خوش‌آمد"}:
            await reply_safe(event, toggle_group(chat_id,"welcome"),buttons=GROUP)
            return
        if n in {"🔗 ضدلینک","ضدلینک"}:
            await reply_safe(event, toggle_group(chat_id,"anti_link"),buttons=GROUP)
            return
        if n in {"🚨 ضداسپم","ضداسپم"}:
            await reply_safe(event, toggle_group(chat_id,"anti_spam"),buttons=GROUP)
            return
        if n in {"📊 آمار گروه","آمار گروه"}:
            count=db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            await reply_safe(event, f"📊 آمار گروه\n\n👥 کاربران ثبت‌شده: {count}",buttons=GROUP)
            return
        if n in {"دوستان","🤝 دوستان","pair"}:
            await reply_safe(event, "🤝 دوستان\n\nبرای Pair دوستانه بنویس: زوج 12345",buttons=MAIN)
            return
        if n.startswith("زوج "):
            await reply_safe(event, f"🤝 Pair ثبت شد!\n\n{uid} ↔ {n[4:].strip()}",buttons=MAIN)
            return
        if n in {"تنظیمات","⚙️ تنظیمات"}:
            await reply_safe(event, "⚙️ تنظیمات\n\n🌐 فارسی\n😎 لحن خودمونی",buttons=MAIN)
            return
        if n in {"کمک","/help","راهنما","help"}:
            await reply_safe(event, "🧠 راهنما\n\nبازی، سکه، جایزه، مأموریت، فروشگاه، کوله، پروفایل، رتبه، افتخارات، دوستان و گروه.",buttons=MAIN)
            return
        await reply_safe(event, "🤔 اینو کامل نگرفتم 😅\nمثلاً «بازی»، «سکه» یا «فروشگاه» رو بفرست.",buttons=MAIN)
    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try: await reply_safe(event, "⚠️ یه خطای موقت خوردیم 😅",buttons=MAIN)
        except Exception as reply_exc: print(f"reply error: {type(reply_exc).__name__}: {reply_exc}")

if __name__ == "__main__":
    threading.Thread(target=start_health,daemon=True).start()
    print("T3R0ZA_BOT starting")
    bot.run()