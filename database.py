import os
import sqlite3
import threading
from datetime import date, timedelta

class Database:
    SHOP = {
        "badge": {
            "price": 250,
            "name": "🧰 Lucky Badge",
            "detail": "یه بج تزئینی برای پروفایله؛ روی موجودی ذخیره می‌شه و برای نمایش/کلکسیون استفاده می‌شه.",
        },
        "frame": {
            "price": 400,
            "name": "🎨 Profile Frame",
            "detail": "قاب تزئینی پروفایله؛ یک آیتم کلکسیونی برای ظاهر پروفایل.",
        },
        "boost": {
            "price": 600,
            "name": "⚡ XP Boost",
            "detail": "آیتم تقویتی داخل سیستم XP است؛ در نسخه فعلی به‌عنوان آیتم Inventory ذخیره می‌شود و مصرف خودکار ندارد.",
        },
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
        text = str(text or "")
        return " ".join(
            text.strip().casefold()
            .replace("‌", "")
            .replace("ي", "ی")
            .replace("ك", "ک")
            .split()
        )

    def ensure_user(self, uid):
        with self.lock, self.conn:
            self.conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (uid,))

    def touch_user(self, uid):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE user_id=?", (uid,)
            )

    def row(self, uid):
        self.ensure_user(uid)
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM users WHERE user_id=?", (uid,)
            ).fetchone()

    def add_xp(self, uid, amount):
        self.ensure_user(uid)
        with self.lock, self.conn:
            row = self.row(uid)
            xp = row["xp"] + int(amount)
            level = 1 + xp // 100
            self.conn.execute(
                "UPDATE users SET xp=?, level=? WHERE user_id=?",
                (xp, level, uid),
            )

    def mark_mission(self, uid, mission_id, amount=1):
        today = date.today().isoformat()
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO missions(user_id,mission_id,mission_date) VALUES (?,?,?)",
                (uid, mission_id, today),
            )
            self.conn.execute(
                "UPDATE missions SET progress=progress+? "
                "WHERE user_id=? AND mission_id=? AND mission_date=?",
                (int(amount), uid, mission_id, today),
            )

    def claim_daily(self, uid):
        self.ensure_user(uid)
        today = date.today()
        row = self.row(uid)
        if row["daily_date"] == today.isoformat():
            return "🎁 جایزه امروز رو قبلاً گرفتی 😎
فردا دوباره سر بزن."

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
        return (
            "🎁 جایزه روزانه دریافت شد!
"
            f"🪙 مقدار دریافتی: +{reward} سکه
"
            f"🔥 Streak: {streak}
"
            "✨ +20 XP"
        )

    def home_text(self, uid):
        row = self.row(uid)
        return (
            "⚡ T3R0ZA BOT

"
            f"سلام رفیق 😎
"
            f"🏅 Level: {row['level']} | ✨ XP: {row['xp']} | 🪙 {row['coins']}

"
            "هرچی خواستی عادی بنویس؛ مثلاً «بازی»، «سکه»، «فروشگاه» یا «پروفایل»."
        )

    def wallet_text(self, uid):
        r = self.row(uid)
        return (
            "🪙 کیف پول

"
            f"موجودی فعلی تو: {r['coins']} سکه
"
            f"✨ XP: {r['xp']}
"
            f"🏅 Level: {r['level']}

"
            "سکه‌ها کاملاً مجازی و فقط برای امکانات داخل بات هستند."
        )

    def profile_text(self, uid):
        r = self.row(uid)
        return (
            "👤 پروفایل T3R0ZA

"
            f"شناسه: {uid}
"
            f"🏅 Level: {r['level']}
"
            f"✨ XP: {r['xp']}
"
            f"🪙 Coins: {r['coins']}
"
            f"🔥 Streak: {r['streak']}
"
            f"🎮 بازی‌ها: {r['games_played']}
"
            f"🏆 بردها: {r['games_won']}"
        )

    def leaderboard_text(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT user_id,xp,level,coins,games_won FROM users "
                "ORDER BY xp DESC, games_won DESC LIMIT 10"
            ).fetchall()

        if not rows:
            return "🏆 هنوز رکوردی ثبت نشده."

        lines = ["🏆 رتبه‌بندی T3R0ZA
"]
        for i, r in enumerate(rows, 1):
            lines.append(
                f"{i}. {r['user_id']} — Lv.{r['level']} — "
                f"{r['xp']} XP — 🏆 {r['games_won']}"
            )
        return "
".join(lines)

    def missions_text(self, uid):
        row = self.row(uid)
        return (
            "🎯 مأموریت‌های امروز

"
            "✅ ورود به بات — +5 XP
"
            "🎁 گرفتن جایزه روزانه — +20 XP
"
            "🎮 انجام یک بازی — XP طبق نتیجه
"
            "🏆 بردن بازی — XP بیشتر

"
            f"وضعیت تو: Level {row['level']} | {row['xp']} XP"
        )

    def shop_text(self):
        return (
            "🛒 فروشگاه T3R0ZA

"
            "هر آیتم دکمه مخصوص خودش رو داره.
"
            "اول روی آیتم بزن تا بگم چی هست و دقیقاً چه کاری می‌کنه؛ "
            "بعد خودت تصمیم می‌گیری بخری یا نه.

"
            "🪙 همهٔ قیمت‌ها با سکهٔ مجازی داخل بات هستند."
        )

    def shop_detail(self, item_id):
        item = self.SHOP.get(item_id)
        if not item:
            return "❌ این آیتم رو پیدا نکردم."
        return (
            f"{item['name']}

"
            f"💰 قیمت: {item['price']} سکه
"
            f"ℹ️ چی هست؟ {item['detail']}

"
            "برای خرید بنویس «خرید badge» یا از دکمه خرید استفاده کن."
        )

    def buy_item(self, uid, item):
        key = self.normalize(item or "")
        aliases = {
            "badge": "badge",
            "بج": "badge",
            "لکی badge": "badge",
            "frame": "frame",
            "قاب": "frame",
            "profile frame": "frame",
            "boost": "boost",
            "بوست": "boost",
            "xp boost": "boost",
        }
        item_id = aliases.get(key)
        if not item_id:
            return "❌ آیتم رو نشناختم. یکی از اینا رو بگو: badge، frame، boost"

        item_data = self.SHOP[item_id]
        row = self.row(uid)
        if row["coins"] < item_data["price"]:
            return (
                f"❌ سکه کافی نداری.
"
                f"💰 قیمت: {item_data['price']}
"
                f"🪙 موجودی تو: {row['coins']}"
            )

        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET coins=coins-? WHERE user_id=?",
                (item_data["price"], uid),
            )
            self.conn.execute(
                "INSERT INTO inventory(user_id,item_id,qty) VALUES (?,?,1) "
                "ON CONFLICT(user_id,item_id) DO UPDATE SET qty=qty+1",
                (uid, item_id),
            )

        return (
            f"✅ خرید انجام شد!
{item_data['name']}
"
            f"🪙 -{item_data['price']} سکه"
        )

    def inventory_text(self, uid):
        with self.lock:
            rows = self.conn.execute(
                "SELECT item_id,qty FROM inventory WHERE user_id=?", (uid,)
            ).fetchall()
        if not rows:
            return "🎒 کوله‌بری خالیه؛ از فروشگاه یه آیتم بگیر."

        lines = ["🎒 کوله‌بری
"]
        for r in rows:
            item = self.SHOP.get(r["item_id"])
            name = item["name"] if item else r["item_id"]
            lines.append(f"• {name} × {r['qty']}")
        return "
".join(lines)

    def friends_text(self, uid):
        pair = self.pair_of(uid)
        if pair:
            return (
                f"🤝 Pair فعلی: {pair}

"
                "می‌تونید بازی‌های دونفره و مأموریت‌های مشترک داشته باشید."
            )
        return (
            "🤝 امکانات دوستانه

"
            "برای Pair کردن یک کاربر می‌تونی بنویسی:
"
            "زوج <شناسه کاربر>"
        )

    def pair_text(self, uid):
        return self.friends_text(uid)

    def pair_of(self, uid):
        with self.lock:
            row = self.conn.execute(
                "SELECT partner_id FROM pairs WHERE user_id=?", (uid,)
            ).fetchone()
        return row["partner_id"] if row else None

    def pair_with(self, uid, partner_id):
        partner = self.normalize(partner_id or "")
        if not partner or partner == uid:
            return "❌ شناسهٔ کاربر دیگری رو وارد کن."
        self.ensure_user(partner)
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO pairs(user_id,partner_id) VALUES (?,?)",
                (uid, partner),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO pairs(user_id,partner_id) VALUES (?,?)",
                (partner, uid),
            )
        return (
            "🤝 Pair ساخته شد!
"
            f"تو: {uid}
"
            f"طرف مقابل: {partner}

"
            "از اینجا می‌تونید بازی‌ها و مأموریت‌های دوستانه داشته باشید."
        )

    def settings_text(self, uid):
        return (
            "⚙️ تنظیمات

"
            "🌐 زبان: فارسی
"
            "🔔 اعلان‌ها: فعال
"
            "😎 سبک پاسخ: خودمونی

"
            "تنظیمات این بخش فعلاً نمایشی نیستند؛ گزینه‌های موجود همین بالا هستند."
        )

    def help_text(self):
        return (
            "🧠 راهنمای T3R0ZA

"
            "🎮 بازی — انتخاب بازی و تعداد نفرات
"
            "🪙 سکه — دیدن موجودی
"
            "🎁 جایزه — دریافت پاداش روزانه
"
            "🎯 مأموریت — دیدن مأموریت‌ها
"
            "🛒 فروشگاه — دیدن آیتم و توضیح هر آیتم
"
            "🎒 کوله — دیدن وسایل خریداری‌شده
"
            "👤 پروفایل — آمار حساب
"
            "🏆 رتبه — جدول XP
"
            "🤝 زوج — Pair دوستانه"
        )

    def parse_action(self, text):
        t = self.normalize(text)
        direct = {
            "/menu": "home",
            "منو": "home",
            "خانه": "home",
            "کمک": "help",
            "/help": "help",
            "🎮 بازی‌ها": "games",
            "بازی": "games",
            "گیم": "games",
            "game": "games",
            "games": "games",
            "🪙 سکه": "wallet",
            "سکه": "wallet",
            "کیف پول": "wallet",
            "wallet": "wallet",
            "coins": "wallet",
            "🎁 جایزه": "reward",
            "جایزه": "reward",
            "جایزه روزانه": "reward",
            "پاداش": "reward",
            "👤 پروفایل": "profile",
            "پروفایل": "profile",
            "profile": "profile",
            "🏆 رتبه": "leaderboard",
            "رتبه": "leaderboard",
            "رنک": "leaderboard",
            "رتبه بندی": "leaderboard",
            "رتبه‌بندی": "leaderboard",
            "leaderboard": "leaderboard",
            "🎯 مأموریت": "missions",
            "🎯 ماموریت": "missions",
            "مأموریت": "missions",
            "ماموریت": "missions",
            "mission": "missions",
            "🛒 فروشگاه": "shop",
            "فروشگاه": "shop",
            "shop": "shop",
            "🎒 کوله‌بری": "inventory",
            "کوله": "inventory",
            "کوله‌بری": "inventory",
            "inventory": "inventory",
            "🤝 دوستان / زوج": "friends",
            "دوست": "friends",
            "دوستان": "friends",
            "زوج": "pair",
            "pair": "pair",
            "⚙️ تنظیمات": "settings",
            "تنظیمات": "settings",
            "settings": "settings",
            "🏠 منو": "home",
            "👤 تک‌نفره": "mode_solo",
            "تک نفره": "mode_solo",
            "تک‌نفره": "mode_solo",
            "👥 دونفره": "mode_duo",
            "دونفره": "mode_duo",
            "دو نفره": "mode_duo",
            "👥👥 چندنفره": "mode_multi",
            "چندنفره": "mode_multi",
            "چند نفره": "mode_multi",
            "مولتی": "mode_multi",
            "✅ پیوستن": "join",
            "پیوستن": "join",
            "عضویت": "join",
            "join": "join",
        }

        if t in direct:
            return direct[t], None

        if t.startswith("خرید "):
            return "buy", t[5:].strip()

        if t.startswith("جزئیات "):
            return "shop_detail", t[7:].strip()

        if t.startswith("زوج "):
            return "pair_with", t[4:].strip()

        if t.startswith("pair "):
            return "pair_with", t[5:].strip()

        return None, None

    def suggest(self, text):
        normalized = self.normalize(text)
        choices = [
            "بازی",
            "سکه",
            "جایزه",
            "پروفایل",
            "رتبه",
            "مأموریت",
            "فروشگاه",
            "کوله",
            "زوج",
        ]
        for choice in choices:
            if normalized and (
                normalized[:2] == choice[:2] or choice[:2] in normalized
            ):
                return (
                    f"🤔 فکر کنم منظورت «{choice}» بود 😎
"
                    "همین رو بفرست تا برات بازش کنم."
                )
        return (
            "🧠 اینو هنوز نفهمیدم 😅
"
            "یکی از اینا رو بفرست: بازی، سکه، جایزه، پروفایل، رتبه، "
            "مأموریت، فروشگاه، کوله، زوج"
        )

    def record_game(self, uid, win=False):
        self.ensure_user(uid)
        self.mark_mission(uid, "game")
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET games_played=games_played+1, games_won=games_won+? "
                "WHERE user_id=?",
                (1 if win else 0, uid),
            )
        self.add_xp(uid, 30 if win else 10)
