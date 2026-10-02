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
        self.words = [("🍎", "سیب"), ("🏠", "خانه"), ("🚗", "ماشین"), ("🐱", "گربه"), ("🌞", "خورشید")]

    def catalog_text(self):
        return (
            "🎮 بازی‌ها\n\n"
            "👤 تک‌نفره\n• کوئیز سریع\n• حدس کلمه\n• تست واکنش\n\n"
            "👥 دونفره\n• Quiz Duel\n• جواب سریع\n\n"
            "👥👥 چندنفره\n• Quiz Room\n\n"
            "🪙 پاداش‌ها مجازی‌اند و شرط‌بندی یا پول واقعی در کار نیست."
        )

    def start_solo(self, uid, chat_id, kind):
        self.db.ensure_user(uid)
        if kind == "solo_quiz":
            q, answer, choices = random.choice(self.questions)
            self.active[(uid, "solo")] = ("quiz", answer, chat_id)
            return f"🎯 کوئیز شروع شد!\n\n❓ {q}\n\nگزینه‌ها: " + " | ".join(choices)
        if kind == "word_game":
            emoji, answer = random.choice(self.words)
            self.active[(uid, "solo")] = ("word", answer, chat_id)
            return f"🧩 حدس کلمه\n\n{emoji}\n\nاسمش چیه؟"
        self.active[(uid, "solo")] = ("reaction", "go", chat_id)
        return "⚡ تست واکنش آماده‌ست!\n\nوقتی آماده شدی فقط بنویس: GO"

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
                    return "⚡ درست! واکنش ثبت شد.\n🏆 بردی\n✨ +30 XP"
                return "⏱️ این جوابش نبود 😄 دوباره تست واکنش رو بزن."
            if self.db.normalize(text) == self.db.normalize(expected):
                self.db.record_game(uid, True)
                return "✅ جواب درست!\n🏆 بردی\n✨ +30 XP"
            self.db.record_game(uid, False)
            return f"❌ جواب درست: {expected}\n✨ +10 XP برای شرکت"

        room = self.find_room_any(chat_id)
        if room and room["state"] == "started":
            return self.answer_room(uid, room, text)
        return None

    def create_room(self, uid, chat_id, mode="duo"):
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
            self.db.conn.execute("INSERT INTO room_players(room_id,user_id) VALUES (?,?)", (room_id, uid))
        return f"🎮 اتاق ساخته شد\nکد اتاق: {room_id}\n👥 بازیکنان: 1/{needed}\n\nبرای ورود، «پیوستن» را بفرست."

    def join_room(self, uid, chat_id):
        room = self.find_room_any(chat_id, waiting=True)
        if not room:
            return "❌ فعلاً اتاقی برای این چت نیست. اول «دونفره» یا «چندنفره» رو بزن."
        with self.db.lock, self.db.conn:
            self.db.conn.execute(
                "INSERT OR IGNORE INTO room_players(room_id,user_id) VALUES (?,?)",
                (room["room_id"], uid),
            )
            count = self.db.conn.execute(
                "SELECT COUNT(*) c FROM room_players WHERE room_id=?", (room["room_id"],)
            ).fetchone()["c"]
            needed = 2 if room["mode"] == "duo" else 3
            if count >= needed:
                q, answer, _ = random.choice(self.questions)
                self.db.conn.execute(
                    "UPDATE rooms SET state='started', question=?, answer=? WHERE room_id=?",
                    (q, answer, room["room_id"]),
                )
                return self.start_room_text(room["room_id"], needed, q)
        return f"✅ وارد شدی!\n👥 بازیکنان: {count}/{needed}\nوقتی نفرات کافی باشن بازی شروع می‌شه."

    def find_room_any(self, chat_id, waiting=False):
        query = "SELECT * FROM rooms WHERE chat_id=?"
        params = [chat_id]
        if waiting:
            query += " AND state='waiting'"
        query += " ORDER BY created_at DESC LIMIT 1"
        return self.db.conn.execute(query, params).fetchone()

    def room_text(self, room):
        count = self.db.conn.execute(
            "SELECT COUNT(*) c FROM room_players WHERE room_id=?", (room["room_id"],)
        ).fetchone()["c"]
        needed = 2 if room["mode"] == "duo" else 3
        return f"🎮 اتاق فعال: {room['room_id']}\n👥 بازیکنان: {count}/{needed}\nبرای ورود «پیوستن» را بفرست."

    def start_room_text(self, room_id, needed, question):
        return f"🔥 بازی شروع شد!\n👥 {needed} نفر حاضرند.\n\n❓ {question}\n\nاولین جواب درست، برنده این راند است!"

    def answer_room(self, uid, room, text):
        if self.db.normalize(text) != self.db.normalize(room["answer"]):
            return None
        with self.db.lock, self.db.conn:
            self.db.conn.execute("UPDATE rooms SET state='finished' WHERE room_id=?", (room["room_id"],))
        self.db.record_game(uid, True)
        players = self.db.conn.execute(
            "SELECT user_id FROM room_players WHERE room_id=?", (room["room_id"],)
        ).fetchall()
        for player in players:
            player_id = str(player["user_id"])
            if player_id != uid:
                self.db.record_game(player_id, False)
        return f"🏆 {uid} برنده شد!\n✅ جواب درست بود: {room['answer']}\n✨ +30 XP برای برنده\n\nبرای بازی بعدی «دونفره» یا «چندنفره» رو بفرست."
