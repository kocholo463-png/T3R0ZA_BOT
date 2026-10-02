import os
import sqlite3
import threading
from datetime import date, timedelta

class Database:
    SHOP = {
        "badge": (250, "🧰 Lucky Badge"),
        "frame": (400, "🎨 Profile Frame"),
        "boost": (600, "⚡ XP Boost"),
    }

    def __init__(self, path):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init()

    def _init(self):
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    coins INTEGER NOT NULL DEFAULT 100,
                    xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    streak INTEGER NOT NULL DEFAULT 0,
                    daily_date TEXT,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    games_won INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    qty INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(user_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS missions (
                    user_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    mission_date TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, mission_id, mission_date)
                );
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    host_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'waiting',
                    question TEXT,
                    answer TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS room_players (
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY(room_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS pairs (
                    user_id TEXT PRIMARY KEY,
                    partner_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def normalize(self, text):
        return " ".join(text.strip().casefold().replace("‌", "").split())

    def ensure_user(self, uid):
        with self.lock, self.conn:
            self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (uid,))

    def touch_user(self, uid):
        with self.lock, self.conn:
            self.conn.execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE user_id=?", (uid,))

    def row(self, uid):
        self.ensure_user(uid)
        with self.lock:
            return self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

    def add_xp(self, uid, amount):
        self.ensure_user(uid)
        with self.lock, self.conn:
            row = self.row(uid)
            xp = row["xp"] + int(amount)
            level = 1 + xp // 100
            self.conn.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (xp, level, uid))

    def mark_mission(self, uid, mission_id, amount=1):
        today = date.today().isoformat()
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO missions(user_id,mission_id,mission_date) VALUES (?,?,?)",
                (uid, mission_id, today),
            )
            self.conn.execute(
                "UPDATE missions SET progress=progress+? WHERE user_id=? AND mission_id=? AND mission_date=?",
                (int(amount), uid, mission_id, today),
            )

    def claim_daily(self, uid):
        self.ensure_user(uid)
        today = date.today()
        row = self.row(uid)
        if row["daily_date"] == today.isoformat():
            return "🎁 جایزهٔ امروز رو قبلاً گرفتی؛ فردا دوباره سر بزن 😎"
        yesterday = (today - timedelta(days=1)).isoformat()
        streak = row["streak"] + 1 if row["daily_date"] == yesterday else 1
        reward = 50 + min(streak, 7) * 10
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET coins=coins+?, streak=?, daily_date=? WHERE user_id=?",
                (reward, streak, today.isoformat(), uid),
            )
        self.add_xp(uid, 20)
        self.mark_mission(uid, "daily")
        return f"🎁 جایزه روزانه گرفتی!\n🪙 +{reward} سکه\n🔥 استریک: {streak}\n✨ +20 XP"

    def home_text(self, uid):
        row = self.row(uid)
        return (
            "⚡ T3R0ZA BOT\n\n"
            f"سلام رفیق 😎\n🏅 Level: {row['level']} | ✨ XP: {row['xp']} | 🪙 {row['coins']}\n\n"
            "از دکمه‌ها استفاده کن یا عادی بنویس: بازی، سکه، جایزه، پروفایل، رتبه..."
        )

    def wallet_text(self, uid):
        r = self.row(uid)
        return f"🪙 کیف پول\n\nموجودی: {r['coins']} سکه\n✨ XP: {r['xp']}\n🏅 Level: {r['level']}"

    def profile_text(self, uid):
        r = self.row(uid)
        return (
            "👤 پروفایل\n\n"
            f"شناسه: {uid}\n🏅 Level: {r['level']}\n✨ XP: {r['xp']}\n"
            f"🪙 Coins: {r['coins']}\n🔥 Streak: {r['streak']}\n"
            f"🎮 بازی‌ها: {r['games_played']}\n🏆 بردها: {r['games_won']}"
        )

    def leaderboard_text(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT user_id,xp,level,coins,games_won FROM users ORDER BY xp DESC, games_won DESC LIMIT 10"
            ).fetchall()
        if not rows:
            return "🏆 هنوز کسی رکوردی ثبت نکرده."
        lines = ["🏆 رتبه‌بندی T3R0ZA\n"]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {r['user_id']} — Lv.{r['level']} — {r['xp']} XP — 🏆 {r['games_won']}")
        return "\n".join(lines)

    def missions_text(self, uid):
        row = self.row(uid)
        return (
            "🎯 مأموریت‌های امروز\n\n"
            "✅ ورود به بات — +5 XP\n"
            "🎁 گرفتن جایزه روزانه — +20 XP\n"
            "🎮 انجام یک بازی — پاداش طبق نتیجه\n"
            "🏆 بردن یک بازی — پاداش بیشتر\n\n"
            f"وضعیت تو: Level {row['level']} | {row['xp']} XP"
        )

    def shop_text(self):
        return (
            "🛒 فروشگاه\n\n"
            "🧰 Lucky Badge — 250 سکه\n"
            "🎨 Profile Frame — 400 سکه\n"
            "⚡ XP Boost — 600 سکه\n\n"
            "برای خرید بنویس: خرید badge / خرید frame / خرید boost\n"
            "🪙 سکه‌ها فقط مجازی و داخل بات هستند."
        )

    def buy_item(self, uid, item):
        key = self.normalize(item or "")
        aliases = {"badge": "badge", "لکی": "badge", "frame": "frame", "قاب": "frame", "boost": "boost", "بوست": "boost"}
        item_id = aliases.get(key)
        if not item_id:
            return "❌ آیتم رو نشناختم. اینا هستن: badge، frame، boost"
        price, name = self.SHOP[item_id]
        row = self.row(uid)
        if row["coins"] < price:
            return f"❌ سکه کافی نداری.\n💰 قیمت: {price}\n🪙 موجودی تو: {row['coins']}"
        with self.lock, self.conn:
            self.conn.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (price, uid))
            self.conn.execute(
                "INSERT INTO inventory(user_id,item_id,qty) VALUES (?,?,1) "
                "ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+1",
                (uid, item_id),
            )
        return f"✅ خرید انجام شد!\n{name}\n🪙 -{price} سکه"

    def inventory_text(self, uid):
        with self.lock:
            rows = self.conn.execute("SELECT item_id,qty FROM inventory WHERE user_id=?", (uid,)).fetchall()
        if not rows:
            return "🎒 کوله‌بری خالیه؛ از فروشگاه یه آیتم بگیر."
        return "🎒 کوله‌بری\n\n" + "\n".join(f"• {r['item_id']} × {r['qty']}" for r in rows)

    def friends_text(self, uid):
        pair = self.pair_of(uid)
        if pair:
            return f"🤝 Pair فعلی: {pair}\n\nتعامل‌ها دوستانه و غیرجنسی هستند."
        return "🤝 امکانات دوستانه\n\nبرای Pair کردن یک کاربر، بنویس: زوج <شناسه‌کاربر>\nمثال: زوج 12345"

    def pair_text(self, uid):
        return self.friends_text(uid)

    def pair_of(self, uid):
        with self.lock:
            row = self.conn.execute("SELECT partner_id FROM pairs WHERE user_id=?", (uid,)).fetchone()
        return row["partner_id"] if row else None

    def pair_with(self, uid, partner_id):
        partner = self.normalize(partner_id or "")
        if not partner or partner == uid:
            return "❌ شناسهٔ کاربر دیگری رو وارد کن."
        self.ensure_user(partner)
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO pairs(user_id,partner_id) VALUES (?,?)", (uid, partner))
            self.conn.execute("INSERT OR REPLACE INTO pairs(user_id,partner_id) VALUES (?,?)", (partner, uid))
        return f"🤝 Pair ساخته شد!\nتو: {uid}\nطرف مقابل: {partner}\n\nحالا می‌تونید بازی‌های دونفره و مأموریت‌های مشترک داشته باشید."

    def settings_text(self, uid):
        return "⚙️ تنظیمات\n\nزبان: فارسی\nاعلان‌ها: فعال\nحالت پاسخ: خودمونی 😎"

    def help_text(self):
        return (
            "🧠 راهنمای T3R0ZA\n\n"
            "🎮 بازی\n🪙 سکه\n🎁 جایزه\n👤 پروفایل\n🏆 رتبه\n"
            "🎯 مأموریت\n🛒 فروشگاه\n🎒 کوله\n🤝 زوج\n⚙️ تنظیمات\n\n"
            "برای بازی دونفره: دونفره → پیوستن\nبرای چندنفره: چندنفره → پیوستن"
        )

    def parse_action(self, text):
        t = self.normalize(text)
        direct = {
            "/menu": "home", "منو": "home", "خانه": "home", "هوم": "home", "کمک": "help", "/help": "help",
            "🎮 بازی‌ها": "games", "بازی": "games", "گیم": "games", "game": "games", "games": "games",
            "🪙 سکه": "wallet", "سکه": "wallet", "کیف پول": "wallet", "wallet": "wallet", "coins": "wallet",
            "🎁 جایزه": "reward", "جایزه": "reward", "جایزه روزانه": "reward", "پاداش": "reward",
            "👤 پروفایل": "profile", "پروفایل": "profile", "profile": "profile",
            "🏆 رتبه": "leaderboard", "رتبه": "leaderboard", "رنک": "leaderboard", "رتبه بندی": "leaderboard", "leaderboard": "leaderboard",
            "🎯 مأموریت": "missions", "🎯 ماموریت": "missions", "مأموریت": "missions", "ماموریت": "missions", "mission": "missions",
            "🛒 فروشگاه": "shop", "فروشگاه": "shop", "shop": "shop",
            "🎒 کوله‌بری": "inventory", "کوله": "inventory", "کوله‌بری": "inventory", "inventory": "inventory",
            "🤝 دوستان / زوج": "friends", "دوست": "friends", "دوستان": "friends", "زوج": "pair", "pair": "pair",
            "⚙️ تنظیمات": "settings", "تنظیمات": "settings", "settings": "settings",
            "تک نفره": "solo_quiz", "تک‌نفره": "solo_quiz", "کوئیز": "solo_quiz", "quiz": "solo_quiz",
            "حدس کلمه": "word_game", "کلمه": "word_game", "word": "word_game",
            "تست واکنش": "reaction", "سرعت": "reaction", "واکنش": "reaction", "reaction": "reaction",
            "دونفره": "duo", "دو نفره": "duo", "duo": "duo",
            "چندنفره": "multiplayer", "چند نفره": "multiplayer", "مولتی": "multiplayer", "multiplayer": "multiplayer",
            "پیوستن": "join", "عضویت": "join", "join": "join",
            "🏠 منو": "home",
        }
        if t in direct:
            return direct[t], None
        if t.startswith("خرید "):
            return "buy", t[5:]
        if t.startswith("زوج "):
            return "pair_with", t[4:].strip()
        if t.startswith("pair "):
            return "pair_with", t[5:].strip()
        return None, None

    def suggest(self, text):
        normalized = self.normalize(text)
        choices = ["بازی", "سکه", "جایزه", "پروفایل", "رتبه", "مأموریت", "فروشگاه", "کوله", "زوج"]
        for choice in choices:
            if normalized and (normalized[:2] == choice[:2] or choice[:2] in normalized):
                return f"🤔 فکر کنم منظورت «{choice}» بود 😎\nهمین کلمه رو بفرست یا از منو استفاده کن."
        return "🧠 اینو هنوز نفهمیدم 😅\nیکی از اینا رو بفرست: بازی، سکه، جایزه، پروفایل، رتبه، مأموریت، فروشگاه، کوله، زوج"

    def record_game(self, uid, win=False):
        self.ensure_user(uid)
        self.mark_mission(uid, "game")
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET games_played=games_played+1, games_won=games_won+? WHERE user_id=?",
                (1 if win else 0, uid),
            )
        self.add_xp(uid, 30 if win else 10)
