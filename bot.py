import os
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiosplus import Bot, Dispatcher
from aiosplus.filters import Command
from aiosplus.types import Message
from aiosplus.utils import ReplyKeyboardBuilder

from database import Database
from game_engine import GameEngine

TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data/t3r0za.sqlite3")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Render Environment Variables.")

db = Database(DB_PATH)
games = GameEngine(db)
bot = Bot(token=TOKEN)
dp = Dispatcher()

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
    builder = ReplyKeyboardBuilder()
    for row in rows:
        for label in row:
            builder.button(text=label)
        builder.adjust(len(row))
    return builder.as_markup()

MAIN_KB = kb([
    ["🎮 بازی‌ها", "🪙 سکه"],
    ["🎁 جایزه", "🎯 مأموریت"],
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
    ["👤 پروفایل", "🏆 رتبه"],
    ["🤝 دوستان / زوج", "⚙️ تنظیمات"],
])

GAMES_KB = kb([
    ["👤 تک‌نفره", "🧩 حدس کلمه"],
    ["⚡ تست واکنش"],
    ["👥 دونفره", "👥👥 چندنفره"],
    ["✅ پیوستن"],
    ["🏠 منو"],
])

SHOP_KB = kb([
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
    ["🏠 منو"],
])

FRIENDS_KB = kb([
    ["🤝 دوستان / زوج", "👤 پروفایل"],
    ["🏠 منو"],
])

SETTINGS_KB = kb([
    ["⚙️ تنظیمات", "🏠 منو"],
])

def uid_of(message: Message):
    return str(message.from_user.id) if message.from_user else "unknown"

def cid_of(message: Message):
    return str(message.chat.id) if message.chat else uid_of(message)

async def handle(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    uid = uid_of(message)
    cid = cid_of(message)
    db.ensure_user(uid)
    db.touch_user(uid)

    normalized = db.normalize(text)

    if normalized in {"/start", "شروع", "استارت"}:
        db.mark_mission(uid, "login")
        db.add_xp(uid, 5)
        await message.answer(db.home_text(uid), reply_markup=MAIN_KB)
        return

    active = games.answer_active(uid, cid, text)
    if active:
        await message.answer(active, reply_markup=GAMES_KB)
        return

    action, argument = db.parse_action(normalized)

    if action == "home":
        await message.answer(db.home_text(uid), reply_markup=MAIN_KB)
    elif action == "wallet":
        await message.answer(db.wallet_text(uid), reply_markup=MAIN_KB)
    elif action == "reward":
        await message.answer(db.claim_daily(uid), reply_markup=MAIN_KB)
    elif action == "profile":
        await message.answer(db.profile_text(uid), reply_markup=MAIN_KB)
    elif action == "leaderboard":
        await message.answer(db.leaderboard_text(), reply_markup=MAIN_KB)
    elif action == "missions":
        await message.answer(db.missions_text(uid), reply_markup=MAIN_KB)
    elif action == "shop":
        await message.answer(db.shop_text(), reply_markup=SHOP_KB)
    elif action == "buy":
        await message.answer(db.buy_item(uid, argument), reply_markup=SHOP_KB)
    elif action == "inventory":
        await message.answer(db.inventory_text(uid), reply_markup=SHOP_KB)
    elif action == "friends":
        await message.answer(db.friends_text(uid), reply_markup=FRIENDS_KB)
    elif action == "pair":
        await message.answer(db.pair_text(uid), reply_markup=FRIENDS_KB)
    elif action == "pair_with":
        await message.answer(db.pair_with(uid, argument), reply_markup=FRIENDS_KB)
    elif action == "settings":
        await message.answer(db.settings_text(uid), reply_markup=SETTINGS_KB)
    elif action == "games":
        await message.answer(games.catalog_text(), reply_markup=GAMES_KB)
    elif action in {"solo_quiz", "word_game", "reaction"}:
        await message.answer(games.start_solo(uid, cid, action), reply_markup=GAMES_KB)
    elif action == "duo":
        await message.answer(games.create_room(uid, cid, "duo"), reply_markup=GAMES_KB)
    elif action == "multiplayer":
        await message.answer(games.create_room(uid, cid, "multi"), reply_markup=GAMES_KB)
    elif action == "join":
        await message.answer(games.join_room(uid, cid), reply_markup=GAMES_KB)
    elif action == "help":
        await message.answer(db.help_text(), reply_markup=MAIN_KB)
    else:
        await message.answer(db.suggest(text), reply_markup=MAIN_KB)

@dp.message(Command("start"))
async def start_handler(message: Message):
    await handle(message)

@dp.message(Command("menu"))
async def menu_handler(message: Message):
    uid = uid_of(message)
    db.ensure_user(uid)
    await message.answer(db.home_text(uid), reply_markup=MAIN_KB)

@dp.message()
async def message_handler(message: Message):
    await handle(message)

async def main():
    me = await bot.get_me()
    print(f"T3R0ZA_BOT authenticated as {getattr(me, 'first_name', 'bot')}")
    print("T3R0ZA_BOT polling started")
    await dp.start_polling(bot, drop_pending_updates=False)

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    asyncio.run(main())
