import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from spluspy import Robot

from database import Database
from game_engine import GameEngine
from menu import main_keyboard, games_keyboard, shop_keyboard, friends_keyboard, settings_keyboard

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data/t3r0za.sqlite3")

db = Database(DB_PATH)
games = GameEngine(db)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"T3R0ZA_BOT OK")

    def log_message(self, *_args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it in Render Environment Variables.")

bot = Robot(TOKEN)

def _get_message(event):
    return getattr(event, "message", None) or event

def _get_value(obj, names):
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            value = None
        if value not in (None, ""):
            return value
    return None

def get_text(event):
    msg = _get_message(event)
    value = _get_value(msg, ("raw_text", "text", "message"))
    if value is not None:
        return str(value).strip()
    value = _get_value(event, ("raw_text", "text", "message"))
    return str(value).strip() if value is not None else ""

def get_user_id(event):
    msg = _get_message(event)
    value = _get_value(msg, ("sender_id", "user_id"))
    if value is None:
        value = _get_value(event, ("sender_id", "user_id"))
    return str(value) if value is not None else "unknown"

def get_chat_id(event):
    msg = _get_message(event)
    value = _get_value(msg, ("chat_id",))
    if value is None:
        value = _get_value(event, ("chat_id",))
    return str(value) if value is not None else get_user_id(event)

async def send(event, text, keyboard=None):
    if keyboard is None:
        keyboard = main_keyboard()
    target = event
    reply = getattr(target, "reply", None)
    if reply is None:
        target = _get_message(event)
        reply = getattr(target, "reply", None)
    if reply is None:
        raise RuntimeError("Incoming update has no reply() method.")
    await reply(str(text), buttons=keyboard)

@bot.on_message()
async def on_message(client, event):
    try:
        text = get_text(event)
        print(f"T3R0ZA incoming: {text!r}")

        if not text:
            return

        uid = get_user_id(event)
        cid = get_chat_id(event)
        db.ensure_user(uid)
        db.touch_user(uid)
        normalized = db.normalize(text)

        if normalized in {"/start", "شروع", "استارت"}:
            db.mark_mission(uid, "login")
            db.add_xp(uid, 5)
            await send(event, db.home_text(uid))
            return

        active_result = games.answer_active(uid, cid, text)
        if active_result:
            await send(event, active_result, games_keyboard())
            return

        action, argument = db.parse_action(normalized)

        if action == "home":
            await send(event, db.home_text(uid))
        elif action == "wallet":
            await send(event, db.wallet_text(uid))
        elif action == "reward":
            await send(event, db.claim_daily(uid))
        elif action == "profile":
            await send(event, db.profile_text(uid))
        elif action == "leaderboard":
            await send(event, db.leaderboard_text())
        elif action == "missions":
            await send(event, db.missions_text(uid))
        elif action == "shop":
            await send(event, db.shop_text(), shop_keyboard())
        elif action == "buy":
            await send(event, db.buy_item(uid, argument), shop_keyboard())
        elif action == "inventory":
            await send(event, db.inventory_text(uid))
        elif action == "friends":
            await send(event, db.friends_text(uid), friends_keyboard())
        elif action == "pair":
            await send(event, db.pair_text(uid), friends_keyboard())
        elif action == "pair_with":
            await send(event, db.pair_with(uid, argument), friends_keyboard())
        elif action == "settings":
            await send(event, db.settings_text(uid), settings_keyboard())
        elif action == "games":
            await send(event, games.catalog_text(), games_keyboard())
        elif action in {"solo_quiz", "word_game", "reaction"}:
            await send(event, games.start_solo(uid, cid, action), games_keyboard())
        elif action == "duo":
            await send(event, games.create_room(uid, cid, "duo"), games_keyboard())
        elif action == "multiplayer":
            await send(event, games.create_room(uid, cid, "multi"), games_keyboard())
        elif action == "join":
            await send(event, games.join_room(uid, cid), games_keyboard())
        elif action == "help":
            await send(event, db.help_text())
        else:
            await send(event, db.suggest(text))
    except Exception as exc:
        print(f"T3R0ZA update error: {type(exc).__name__}: {exc}")
        try:
            await send(event, "⚠️ یه خطای موقت پیش اومد 😅\nدوباره /start رو بفرست.")
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

if __name__ == "__main__":
    bot.run()
