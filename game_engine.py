import random
import uuid

class GameEngine:
    def __init__(self, db):
        self.db = db
        self.active = {}
        self.questions = [
            ("پایتخت ژاپن کدام است؟", "توکیو", ["توکیو", "اوساکا", "کیوتو"]),
            ("کدام سیاره به سیاره سرخ معروف است؟", "مریخ", ["مریخ", "زهره", "نپتون"]),
            ("5 × 8 چند می‌شود؟", "40", ["35", "40", "45"]),
            ("آب در سطح دریا تقریباً در چند درجه می‌جوشد؟", "100", ["50", "100", "150"]),
            ("بزرگ‌ترین اقیانوس زمین کدام است؟", "آرام", ["اطلس", "آرام", "هند"]),
        ]
        self.words = [
            ("🍎", "سیب"),
            ("🏠", "خانه"),
            ("🚗", "ماشین"),
            ("🐱", "گربه"),
            ("🌞", "خورشید"),
        ]

    def catalog_text(self):
        return (
            "🎮 چه بازی‌هایی داریم؟

"
            "🎯 کوئیز سریع — 👤 ۱ نفره | 👥 ۲ نفره | 👥👥 چندنفره
"
            "🧩 حدس کلمه — 👤 ۱ نفره | 👥 ۲ نفره
"
            "⚡ تست واکنش — 👤 ۱ نفره | 👥 ۲ نفره

"
            "از دکمه‌ها یکی رو انتخاب کن؛ بعد از انتخاب بازی، "
            "تعداد نفرات مناسب هم ازت می‌پرسم.

"
            "🪙 بردها فقط XP و پاداش مجازی داخل بات دارند؛ شرط‌بندی یا پول واقعی وجود ندارد."
        )

    def game_detail(self, kind):
        details = {
            "solo_quiz": (
                "🎯 کوئیز سریع

"
                "چی هست؟ چند سؤال کوتاه دانستنی و منطقی.
"
                "نفرات: ۱، ۲ یا چندنفره.
"
                "هدف: سریع و درست جواب بدهی و XP بگیری."
            ),
            "word_game": (
                "🧩 حدس کلمه

"
                "چی هست؟ یک ایموجی می‌بینی و باید اسمش را حدس بزنی.
"
                "نفرات: ۱ یا ۲ نفره.
"
                "هدف: جواب درست و سریع."
            ),
            "reaction": (
                "⚡ تست واکنش

"
                "چی هست؟ راند کوتاه تمرکز و واکنش متنی.
"
                "نفرات: ۱ یا ۲ نفره.
"
                "هدف: وقتی علامت شروع را دیدی، سریع پاسخ بدهی."
            ),
        }
        return details.get(kind, "❌ بازی پیدا نشد.")

    def start_solo(self, uid, chat_id, kind):
        self.db.ensure_user(uid)
        if kind == "solo_quiz":
            q, answer, choices = random.choice(self.questions)
            self.active[(uid, "solo")] = ("quiz", answer, chat_id)
            return (
                "🔥 بازی شروع شد!

"
                f"❓ {q}

"
                "گزینه‌ها: " + " | ".join(choices) +
                "

جوابت رو همینجا بفرست."
            )

        if kind == "word_game":
            emoji, answer = random.choice(self.words)
            self.active[(uid, "solo")] = ("word", answer, chat_id)
            return f"🔥 بازی شروع شد!

{emoji}

اسمش چیه؟"

        self.active[(uid, "solo")] = ("reaction", "go", chat_id)
        return (
            "⚡ تست واکنش آماده‌ست!

"
            "وقتی رسیدی، دقیقاً بنویس: GO"
        )

    def answer_active(self, uid, chat_id, text):
        key = (uid, "solo")
        if key in self.active:
            kind, expected, game_chat = self.active.pop(key)
            if str(game_chat) != str(chat_id):
                self.active[key] = (kind, expected, game_chat)
                return None

            if kind == "reaction":
                if self.db.normalize(text) == "go":
                    self.db.record_game(uid, True)
                    return "⚡ درست! راند رو بردی 🏆
✨ +30 XP"
                self.db.record_game(uid, False)
                return "⏱️ این جوابش نبود 😄
✨ +10 XP برای شرکت"

            if self.db.normalize(text) == self.db.normalize(expected):
                self.db.record_game(uid, True)
                return "✅ جواب درست بود!
🏆 بردی
✨ +30 XP"

            self.db.record_game(uid, False)
            return (
                f"❌ جواب درست: {expected}
"
                "🎮 این راند تموم شد.
"
                "✨ +10 XP برای شرکت"
            )

        room = self.find_room_any(chat_id)
        if room and room["state"] == "started":
            return self.answer_room(uid, room, text)

        return None

    def create_room(self, uid, chat_id, mode="duo", game_kind="solo_quiz"):
        existing = self.find_room_any(chat_id, waiting=True)
        if existing:
            return self.room_text(existing)

        room_id = uuid.uuid4().hex[:6].upper()
        needed = 2 if mode == "duo" else 3

        with self.db.lock, self.db.conn:
            self.db.conn.execute(
                "INSERT INTO rooms(room_id,chat_id,mode,host_id) VALUES (?,?,?,?)",
                (room_id, chat_id, mode, uid),
            )
            self.db.conn.execute(
                "INSERT INTO room_players(room_id,user_id) VALUES (?,?)",
                (room_id, uid),
            )

        return (
            "🎮 اتاق ساخته شد!

"
            f"🆔 کد اتاق: {room_id}
"
            f"👥 نفرات: 1/{needed}

"
            "دوستات هم توی همین چت «پیوستن» رو بزنن.
"
            "وقتی تعداد کامل شد، بازی شروع می‌شه."
        )

    def join_room(self, uid, chat_id):
        room = self.find_room_any(chat_id, waiting=True)
        if not room:
            return (
                "❌ اتاق فعالی نیست.
"
                "اول «دونفره» یا «چندنفره» رو انتخاب کن."
            )

        with self.db.lock, self.db.conn:
            self.db.conn.execute(
                "INSERT OR IGNORE INTO room_players(room_id,user_id) VALUES (?,?)",
                (room["room_id"], uid),
            )
            count = self.db.conn.execute(
                "SELECT COUNT(*) c FROM room_players WHERE room_id=?",
                (room["room_id"],),
            ).fetchone()["c"]

            needed = 2 if room["mode"] == "duo" else 3

            if count >= needed:
                q, answer, _ = random.choice(self.questions)
                self.db.conn.execute(
                    "UPDATE rooms SET state='started', question=?, answer=? WHERE room_id=?",
                    (q, answer, room["room_id"]),
                )
                return (
                    "🔥 تعداد کامل شد؛ بازی شروع شد!

"
                    f"❓ {q}

"
                    "اولین جواب درست برنده‌ست 🏆"
                )

        return (
            "✅ وارد اتاق شدی!
"
            f"👥 نفرات: {count}/{needed}
"
            "منتظر بقیه‌ایم..."
        )

    def find_room_any(self, chat_id, waiting=False):
        query = "SELECT * FROM rooms WHERE chat_id=?"
        params = [chat_id]

        if waiting:
            query += " AND state='waiting'"

        query += " ORDER BY created_at DESC LIMIT 1"
        return self.db.conn.execute(query, params).fetchone()

    def room_text(self, room):
        count = self.db.conn.execute(
            "SELECT COUNT(*) c FROM room_players WHERE room_id=?",
            (room["room_id"],),
        ).fetchone()["c"]
        needed = 2 if room["mode"] == "duo" else 3
        return (
            "🎮 اتاق فعال داری!

"
            f"🆔 کد: {room['room_id']}
"
            f"👥 نفرات: {count}/{needed}
"
            "برای ورود «پیوستن» رو بزن."
        )

    def answer_room(self, uid, room, text):
        if self.db.normalize(text) != self.db.normalize(room["answer"]):
            return None

        with self.db.lock, self.db.conn:
            self.db.conn.execute(
                "UPDATE rooms SET state='finished' WHERE room_id=?",
                (room["room_id"],),
            )

        self.db.record_game(uid, True)
        players = self.db.conn.execute(
            "SELECT user_id FROM room_players WHERE room_id=?",
            (room["room_id"],),
        ).fetchall()

        for player in players:
            player_id = str(player["user_id"])
            if player_id != uid:
                self.db.record_game(player_id, False)

        return (
            "🏆 راند تموم شد!
"
            f"برنده: {uid}
"
            f"✅ جواب درست: {room['answer']}
"
            "✨ +30 XP برای برنده"
        )
