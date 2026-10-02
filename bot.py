import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from spluspy import Robot, Button, filters

from database import Database
from game_engine import GameEngine

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data/t3r0za.sqlite3")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Render Environment Variables.")

db = Database(DB_PATH)
games = GameEngine(db)
bot = Robot(TOKEN)

pending_game = {}
pending_shop = {}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"T3R0ZA_BOT OK")

    def log_message(self, *_args):
        return

def start_health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

def kb(rows):
    return [[Button.text(label, resize=True, persistent=True) for label in row] for row in rows]

MAIN_KB = kb([
    ["🎮 بازی‌ها", "🪙 سکه"],
    ["🎁 جایزه", "🎯 مأموریت"],
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
    ["👤 پروفایل", "🏆 رتبه"],
    ["🤝 دوستان / زوج", "⚙️ تنظیمات"],
])

GAMES_KB = kb([
    ["🎯 کوئیز سریع", "🧩 حدس کلمه"],
    ["⚡ تست واکنش"],
    ["🏠 منو"],
])

MODES_KB = kb([
    ["👤 تک‌نفره", "👥 دونفره"],
    ["👥👥 چندنفره"],
    ["🎮 بازی‌ها", "🏠 منو"],
])

SHOP_KB = kb([
    ["🧰 Lucky Badge", "🎨 Profile Frame"],
    ["⚡ XP Boost"],
    ["🏠 منو"],
])

SHOP_ACTION_KB = kb([
    ["✅ خرید badge"],
    ["✅ خرید frame"],
    ["✅ خرید boost"],
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
])

REWARD_KB = kb([
    ["🎁 دریافت جایزه"],
    ["🪙 سکه", "🏠 منو"],
])

def uid_of(event):
    msg = getattr(event, "message", event)
    return str(getattr(msg, "sender_id", None) or getattr(event, "sender_id", "unknown"))

def cid_of(event):
    msg = getattr(event, "message", event)
    return str(getattr(msg, "chat_id", None) or getattr(event, "chat_id", None) or uid_of(event))

def text_of(event):
    msg = getattr(event, "message", event)
    return (getattr(msg, "raw_text", None) or getattr(msg, "text", None) or getattr(event, "raw_text", None) or "").strip()

async def reply(event, text, buttons=MAIN_KB):
    msg = getattr(event, "message", event)
    await msg.reply(str(text), buttons=buttons)

def game_choice_text(kind):
    names = {
        "solo_quiz": "🎯 کوئیز سریع",
        "word_game": "🧩 حدس کلمه",
        "reaction": "⚡ تست واکنش",
    }
    return names[kind]

@bot.on_message(filters.text)
async def on_message(client, event):
    try:
        text = text_of(event)
        if not text:
            return

        uid = uid_of(event)
        cid = cid_of(event)
        db.ensure_user(uid)
        db.touch_user(uid)
        normalized = db.normalize(text)

        if normalized in {"/start", "شروع", "استارت"}:
            pending_game.pop(uid, None)
            pending_shop.pop(uid, None)
            db.mark_mission(uid, "login")
            db.add_xp(uid, 5)
            await reply(event, db.home_text(uid), MAIN_KB)
            return

        active = games.answer_active(uid, cid, text)
        if active:
            await reply(event, active, GAMES_KB)
            return

        if normalized in {"🎮 بازی‌ها", "بازی", "گیم", "game", "games"}:
            pending_game.pop(uid, None)
            await reply(
                event,
                "🎮 مرکز بازی T3R0ZA

"
                "چه بازی‌هایی داریم؟

"
                "🎯 کوئیز سریع
"
                "🧩 حدس کلمه
"
                "⚡ تست واکنش

"
                "یکی رو انتخاب کن 👇",
                GAMES_KB,
            )
            return

        if text in {"🎯 کوئیز سریع", "🎯 کوئیز سریع".replace(" ", "")}:
            pending_game[uid] = "solo_quiz"
            await reply(
                event,
                games.game_detail("solo_quiz") + "\n\n"
                "👤 تک‌نفره\n👥 دونفره\n👥👥 چندنفره\n\n"
                "چند نفره می‌خوای بازی کنی؟",
                MODES_KB,
            )
            return

        if text == "🧩 حدس کلمه":
            pending_game[uid] = "word_game"
            await reply(
                event,
                games.game_detail("word_game") + "\n\n"
                "👤 تک‌نفره\n👥 دونفره\n\n"
                "چند نفره؟",
                MODES_KB,
            )
            return

        if text == "⚡ تست واکنش":
            pending_game[uid] = "reaction"
            await reply(
                event,
                games.game_detail("reaction") + "\n\n"
                "👤 تک‌نفره\n👥 دونفره\n\n"
                "چند نفره؟",
                MODES_KB,
            )
            return

        if uid in pending_game:
            kind = pending_game[uid]
            if normalized in {"👤 تک‌نفره", "تک‌نفره", "تک نفره"}:
                pending_game.pop(uid, None)
                await reply(event, games.start_solo(uid, cid, kind), GAMES_KB)
                return
            if normalized in {"👥 دونفره", "دونفره", "دو نفره"}:
                pending_game.pop(uid, None)
                await reply(event, games.create_room(uid, cid, "duo", kind), GAMES_KB)
                return
            if normalized in {"👥👥 چندنفره", "چندنفره", "چند نفره", "مولتی"}:
                if kind != "solo_quiz":
                    await reply(event, "⚠️ این بازی چندنفره نیست. برایش تک‌نفره یا دونفره رو انتخاب کن.", MODES_KB)
                    return
                pending_game.pop(uid, None)
                await reply(event, games.create_room(uid, cid, "multi", kind), GAMES_KB)
                return

        if normalized in {"🪙 سکه", "سکه", "کیف پول", "wallet", "coins"}:
            await reply(event, db.wallet_text(uid), REWARD_KB)
            return

        if normalized in {"🎁 جایزه", "جایزه", "جایزه روزانه", "پاداش"}:
            await reply(event, db.claim_daily(uid), REWARD_KB)
            return

        if normalized == "🎁 دریافت جایزه":
            await reply(event, db.claim_daily(uid), REWARD_KB)
            return

        if normalized in {"👤 پروفایل", "پروفایل", "profile"}:
            await reply(event, db.profile_text(uid), MAIN_KB)
            return

        if normalized in {"🏆 رتبه", "رتبه", "رنک", "رتبه بندی", "رتبه‌بندی", "leaderboard"}:
            await reply(event, db.leaderboard_text(), MAIN_KB)
            return

        if normalized in {"🎯 مأموریت", "🎯 ماموریت", "مأموریت", "ماموریت", "mission"}:
            await reply(event, db.missions_text(uid), MAIN_KB)
            return

        if normalized in {"🛒 فروشگاه", "فروشگاه", "shop"}:
            await reply(event, db.shop_text(), SHOP_KB)
            return

        if text in {"🧰 Lucky Badge", "🎨 Profile Frame", "⚡ XP Boost"}:
            item_map = {
                "🧰 Lucky Badge": "badge",
                "🎨 Profile Frame": "frame",
                "⚡ XP Boost": "boost",
            }
            item = item_map[text]
            pending_shop[uid] = item
            await reply(event, db.shop_detail(item), SHOP_ACTION_KB)
            return

        if normalized in {"✅ خرید badge", "خرید badge"}:
            await reply(event, db.buy_item(uid, "badge"), SHOP_KB)
            return

        if normalized in {"✅ خرید frame", "خرید frame"}:
            await reply(event, db.buy_item(uid, "frame"), SHOP_KB)
            return

        if normalized in {"✅ خرید boost", "خرید boost"}:
            await reply(event, db.buy_item(uid, "boost"), SHOP_KB)
            return

        if normalized in {"🎒 کوله‌بری", "کوله", "کوله‌بری", "inventory"}:
            await reply(event, db.inventory_text(uid), SHOP_KB)
            return

        if normalized in {"🤝 دوستان / زوج", "دوست", "دوستان", "زوج", "pair"}:
            await reply(event, db.friends_text(uid), MAIN_KB)
            return

        if normalized in {"⚙️ تنظیمات", "تنظیمات", "settings"}:
            await reply(event, db.settings_text(uid), MAIN_KB)
            return

        if normalized in {"✅ پیوستن", "پیوستن", "عضویت", "join"}:
            await reply(event, games.join_room(uid, cid), GAMES_KB)
            return

        if normalized in {"🏠 منو", "منو", "خانه"}:
            await reply(event, db.home_text(uid), MAIN_KB)
            return

        if normalized in {"کمک", "/help", "help"}:
            await reply(event, db.help_text(), MAIN_KB)
            return

        if normalized.startswith("خرید "):
            await reply(event, db.buy_item(uid, normalized[5:]), SHOP_KB)
            return

        if normalized.startswith("زوج "):
            await reply(event, db.pair_with(uid, normalized[4:].strip()), MAIN_KB)
            return

        await reply(event, db.suggest(text), MAIN_KB)

    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try:
            await reply(event, "⚠️ یه خطای موقت پیش اومد 😅\nهمین گزینه رو دوباره بفرست.", MAIN_KB)
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    print("T3R0ZA_BOT starting...")
    bot.run()
