import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from spluspy import Robot

from database import Database
from game_engine import GameEngine
from menu import (
    achievements_keyboard,
    friends_keyboard,
    game_keyboard,
    group_keyboard,
    item_keyboard,
    main_keyboard,
    mode_keyboard,
    profile_keyboard,
    reward_keyboard,
    room_keyboard,
    settings_keyboard,
    shop_keyboard,
)

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
last_message = {}

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

def uid_of(event):
    msg = getattr(event, "message", event)
    return str(getattr(msg, "sender_id", None) or getattr(event, "sender_id", "unknown"))

def chat_id_of(event):
    msg = getattr(event, "message", event)
    return str(
        getattr(msg, "chat_id", None)
        or getattr(event, "chat_id", None)
        or uid_of(event)
    )

def text_of(event):
    msg = getattr(event, "message", event)
    return str(
        getattr(msg, "raw_text", None)
        or getattr(msg, "text", None)
        or getattr(event, "raw_text", None)
        or ""
    ).strip()

def is_probable_group(uid, chat_id):
    return str(uid) != str(chat_id)

async def reply(event, text, buttons=None):
    msg = getattr(event, "message", event)
    await msg.reply(str(text), buttons=buttons or main_keyboard())

@bot.on_message()
async def on_message(client, event):
    try:
        text = text_of(event)
        if not text:
            return

        uid = uid_of(event)
        chat_id = chat_id_of(event)
        normalized = db.normalize(text)
        db.ensure_user(uid)
        db.record_message(uid)
        db.mark_mission(uid, "messages")

        now = time.time()
        previous = last_message.get((uid, chat_id))
        last_message[(uid, chat_id)] = (normalized, now)
        if previous and is_probable_group(uid, chat_id):
            old_text, old_time = previous
            settings = db.group_settings(chat_id)
            if settings["anti_spam"] and old_text == normalized and now - old_time < 2:
                try:
                    message = getattr(event, "message", event)
                    await message.delete()
                    return
                except Exception as exc:
                    print(f"T3R0ZA anti-spam delete skipped: {type(exc).__name__}: {exc}")

        if is_probable_group(uid, chat_id) and db.group_settings(chat_id)["anti_link"]:
            if re.search(r"(?:https?://|www\.|t\.me/|instagram\.com/|\.com\b)", normalized, re.I):
                try:
                    message = getattr(event, "message", event)
                    await message.delete()
                    return
                except Exception as exc:
                    print(f"T3R0ZA anti-link delete skipped: {type(exc).__name__}: {exc}")

        if normalized in {"/start", "شروع", "استارت"}:
            pending_game.pop(uid, None)
            pending_shop.pop(uid, None)
            db.mark_mission(uid, "login")
            db.add_xp(uid, 5)
            await reply(event, db.home_text(uid), main_keyboard())
            return

        active = games.answer_active(uid, chat_id, text)
        if active:
            await reply(event, active, game_keyboard())
            return

        if normalized in {"بازی", "گیم", "games", "game", "🎮 بازی", "🎮 بازی‌ها"}:
            pending_game.pop(uid, None)
            await reply(
                event,
                games.catalog(),
                game_keyboard(),
            )
            return

        game_text_map = {
            "🎯 کوئیز": "quiz",
            "کوئیز": "quiz",
            "🎯 کوئیز سریع": "quiz",
            "🧩 حدس کلمه": "word",
            "حدس کلمه": "word",
            "⚡ واکنش": "reaction",
            "⚡ تست واکنش": "reaction",
            "تست واکنش": "reaction",
            "🏆 چالش گروهی": "group_quiz",
            "چالش گروهی": "group_quiz",
        }
        normalized_game_map = {db.normalize(k): v for k, v in game_text_map.items()}
        if normalized in normalized_game_map:
            kind = normalized_game_map[normalized]
            pending_game[uid] = kind
            await reply(
                event,
                games.detail(kind) + "\n\n"
                "حالا تعداد نفرات رو انتخاب کن 👇",
                mode_keyboard(),
            )
            return

        if uid in pending_game:
            kind = pending_game[uid]
            if normalized in {"👤 تک‌نفره", "تک‌نفره", "تک نفره"}:
                pending_game.pop(uid, None)
                if kind == "group_quiz":
                    await reply(
                        event,
                        "⚠️ چالش گروهی باید داخل اتاق گروهی اجرا بشه.",
                        game_keyboard(),
                    )
                else:
                    await reply(
                        event,
                        games.start_solo(uid, chat_id, kind),
                        game_keyboard(),
                    )
                return

            if normalized in {"👥 دو نفره", "دونفره", "دو نفره", "👥 اتاق دو نفره"}:
                pending_game.pop(uid, None)
                await reply(
                    event,
                    games.create_room(uid, chat_id, "duo", kind),
                    room_keyboard(),
                )
                return

            if normalized in {"👥👥 چندنفره", "چندنفره", "چند نفره", "مولتی", "👥👥 اتاق گروهی"}:
                pending_game.pop(uid, None)
                if kind in {"quiz", "group_quiz"}:
                    await reply(
                        event,
                        games.create_room(uid, chat_id, "multi", "group_quiz"),
                        room_keyboard(),
                    )
                else:
                    await reply(
                        event,
                        "ℹ️ این بازی در این نسخه تا ۲ نفر پشتیبانی می‌شه.",
                        mode_keyboard(),
                    )
                return

            if normalized in {"↩️ برگشت بازی", "برگشت بازی"}:
                pending_game.pop(uid, None)
                await reply(event, games.catalog(), game_keyboard())
                return

        if normalized in {"سکه", "کیف پول", "🪙 سکه", "wallet", "coins"}:
            await reply(event, db.wallet_text(uid), reward_keyboard())
            return

        if normalized in {"جایزه", "جایزه روزانه", "پاداش", "🎁 جایزه", "🎁 دریافت جایزه"}:
            await reply(event, db.claim_daily(uid), reward_keyboard())
            return

        if normalized in {"پروفایل", "👤 پروفایل", "profile"}:
            await reply(event, db.profile_text(uid), profile_keyboard())
            return

        if normalized in {"افتخارات", "⭐ افتخارات", "achievement", "achievements"}:
            await reply(event, db.achievements_text(uid), achievements_keyboard())
            return

        if normalized in {"رتبه", "🏆 رتبه", "رنک", "leaderboard", "رتبه بندی", "رتبه‌بندی"}:
            await reply(event, db.leaderboard_text(), main_keyboard())
            return

        if normalized in {"مأموریت", "ماموریت", "🎯 مأموریت", "mission"}:
            await reply(event, db.missions_text(uid), main_keyboard())
            return

        if normalized in {"فروشگاه", "🛒 فروشگاه", "shop"}:
            await reply(event, db.shop_text(), shop_keyboard())
            return

        shop_map = {
            "🧰 lucky badge": "badge",
            "lucky badge": "badge",
            "🎨 profile frame": "frame",
            "profile frame": "frame",
            "⚡ xp boost": "boost",
            "xp boost": "boost",
        }
        if normalized in shop_map:
            item = shop_map[normalized]
            pending_shop[uid] = item
            await reply(event, db.shop_detail(item), item_keyboard(item))
            return

        if normalized in {"🛒 خرید badge", "خرید badge"}:
            await reply(event, db.buy_item(uid, "badge"), shop_keyboard())
            return

        if normalized in {"🛒 خرید frame", "خرید frame"}:
            await reply(event, db.buy_item(uid, "frame"), shop_keyboard())
            return

        if normalized in {"🛒 خرید boost", "خرید boost"}:
            await reply(event, db.buy_item(uid, "boost"), shop_keyboard())
            return

        if normalized in {"کوله", "🎒 کوله", "کوله‌بری", "🎒 کوله‌بری", "inventory"}:
            await reply(event, db.inventory_text(uid), shop_keyboard())
            return

        if normalized in {"↩️ برگشت فروشگاه", "برگشت فروشگاه"}:
            await reply(event, db.shop_text(), shop_keyboard())
            return

        if normalized in {"دوستان", "🤝 دوستان", "دوست", "pair", "🤝 pair"}:
            await reply(event, db.friends_text(uid), friends_keyboard())
            return

        if normalized.startswith("زوج "):
            await reply(event, db.pair_with(uid, normalized[4:].strip()), friends_keyboard())
            return

        if normalized in {"گروه", "🛡️ گروه", "پنل گروه", "پنل", "مدیریت گروه"}:
            await reply(event, db.group_text(chat_id), group_keyboard())
            return

        if normalized in {"👋 خوش‌آمد", "خوش‌آمد"}:
            if not is_probable_group(uid, chat_id):
                await reply(event, "🛡️ این گزینه فقط برای گروه کاربرد داره.", main_keyboard())
            else:
                await reply(
                    event,
                    db.toggle_group_setting(chat_id, "welcome"),
                    group_keyboard(),
                )
            return

        if normalized in {"🔗 ضدلینک", "ضدلینک"}:
            if not is_probable_group(uid, chat_id):
                await reply(event, "🛡️ این گزینه فقط برای گروه کاربرد داره.", main_keyboard())
            else:
                await reply(
                    event,
                    db.toggle_group_setting(chat_id, "anti_link"),
                    group_keyboard(),
                )
            return

        if normalized in {"🚨 ضداسپم", "ضداسپم"}:
            if not is_probable_group(uid, chat_id):
                await reply(event, "🛡️ این گزینه فقط برای گروه کاربرد داره.", main_keyboard())
            else:
                await reply(
                    event,
                    db.toggle_group_setting(chat_id, "anti_spam"),
                    group_keyboard(),
                )
            return

        if normalized in {"📊 آمار گروه", "آمار گروه"}:
            with db.lock:
                members = db.conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
            await reply(
                event,
                f"📊 آمار گروه\n\n👥 حساب‌های ثبت‌شده: {members}\n"
                "🛡️ تنظیمات این چت از پنل گروه قابل تغییرند.",
                group_keyboard(),
            )
            return

        if normalized in {"ℹ️ وضعیت گروه", "وضعیت گروه"}:
            await reply(event, db.group_text(chat_id), group_keyboard())
            return

        if normalized in {"🧹 پاکسازی", "پاکسازی"}:
            await reply(
                event,
                "🧹 پاکسازی پیام‌ها فقط وقتی API و سطح دسترسی بات اجازه حذف بدهند اجرا می‌شه.",
                group_keyboard(),
            )
            return

        if normalized in {"تنظیمات", "⚙️ تنظیمات", "settings"}:
            await reply(event, db.settings_text(uid), settings_keyboard())
            return

        if normalized in {"کمک", "/help", "help", "راهنما"}:
            await reply(event, db.help_text(), main_keyboard())
            return

        if normalized in {"🏠 منو", "منو", "خانه", "/menu"}:
            await reply(event, db.home_text(uid), main_keyboard())
            return

        if normalized in {"➕ پیوستن", "پیوستن", "join"}:
            await reply(event, games.join_room(uid, chat_id), room_keyboard())
            return

        if normalized in {"🔄 وضعیت اتاق", "وضعیت اتاق"}:
            room = games.find_room(chat_id, waiting=False)
            if room and room["state"] != "finished":
                await reply(event, games.room_text(room), room_keyboard())
            else:
                await reply(event, "❌ اتاق فعالی پیدا نشد.", game_keyboard())
            return

        if normalized in {"❌ لغو اتاق", "لغو اتاق"}:
            room = games.find_room(chat_id, waiting=True)
            if room:
                with db.lock, db.conn:
                    db.conn.execute(
                        "UPDATE rooms SET state='finished' WHERE room_id=?",
                        (room["room_id"],),
                    )
                await reply(event, "❌ اتاق لغو شد.", game_keyboard())
            else:
                await reply(event, "اتاق منتظری وجود نداره 😄", game_keyboard())
            return

        await reply(event, db.suggest(text), main_keyboard())

    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try:
            await reply(
                event,
                "⚠️ یه خطای موقت خوردیم 😅\nهمین گزینه رو دوباره بفرست.",
                main_keyboard(),
            )
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    print("T3R0ZA_BOT starting...")
    bot.run()
