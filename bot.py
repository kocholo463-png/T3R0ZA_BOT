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

pending_game = {}

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

def keyboard(rows):
    builder = ReplyKeyboardBuilder()
    for row in rows:
        for label in row:
            builder.button(text=label)
        builder.adjust(len(row))
    return builder.as_markup()

MAIN_KB = keyboard([
    ["🎮 بازی‌ها", "🪙 سکه"],
    ["🎁 جایزه", "🎯 مأموریت"],
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
    ["👤 پروفایل", "🏆 رتبه"],
    ["🤝 دوستان / زوج", "⚙️ تنظیمات"],
])

GAMES_KB = keyboard([
    ["🎯 کوئیز سریع"],
    ["🧩 حدس کلمه"],
    ["⚡ تست واکنش"],
    ["🏠 منو"],
])

MODES_KB = keyboard([
    ["👤 تک‌نفره", "👥 دونفره"],
    ["👥👥 چندنفره"],
    ["🎮 بازی‌ها"],
    ["🏠 منو"],
])

SHOP_KB = keyboard([
    ["🧰 Lucky Badge", "🎨 Profile Frame"],
    ["⚡ XP Boost"],
    ["🏠 منو"],
])

SHOP_ACTION_KB = keyboard([
    ["✅ خرید badge"],
    ["✅ خرید frame"],
    ["✅ خرید boost"],
    ["🛒 فروشگاه", "🎒 کوله‌بری"],
])

REWARD_KB = keyboard([
    ["🎁 دریافت جایزه"],
    ["🪙 سکه"],
    ["🏠 منو"],
])

GAME_KIND_BY_TEXT = {
    "🎯 کوئیز سریع": "solo_quiz",
    "کوئیز سریع": "solo_quiz",
    "🧩 حدس کلمه": "word_game",
    "حدس کلمه": "word_game",
    "⚡ تست واکنش": "reaction",
    "تست واکنش": "reaction",
}

SHOP_KIND_BY_TEXT = {
    "🧰 lucky badge": "badge",
    "lucky badge": "badge",
    "🧰 Lucky Badge".casefold(): "badge",
    "🎨 profile frame": "frame",
    "profile frame": "frame",
    "🎨 Profile Frame".casefold(): "frame",
    "⚡ xp boost": "boost",
    "xp boost": "boost",
    "⚡ XP Boost".casefold(): "boost",
}

def uid_of(message: Message):
    return str(message.from_user.id) if message.from_user else "unknown"

def cid_of(message: Message):
    return str(message.chat.id) if message.chat else uid_of(message)

async def reply(message: Message, text: str, markup=None):
    await message.reply(str(text), reply_markup=markup or MAIN_KB)

def mode_question(kind):
    name = {
        "solo_quiz": "🎯 کوئیز سریع",
        "word_game": "🧩 حدس کلمه",
        "reaction": "⚡ تست واکنش",
    }[kind]
    supported = {
        "solo_quiz": "۱، ۲ یا چندنفره",
        "word_game": "۱ یا ۲ نفره",
        "reaction": "۱ یا ۲ نفره",
    }[kind]
    return (
        f"{name} انتخاب شد ✅\n\n"
        f"این بازی برای {supported} طراحی شده.\n"
        "چند نفره می‌خوای بازی کنی؟"
    )

async def handle(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    uid = uid_of(message)
    cid = cid_of(message)
    db.ensure_user(uid)
    db.touch_user(uid)

    normalized = db.normalize(text)

    # Answer an ongoing solo/room game first.
    active = games.answer_active(uid, cid, text)
    if active:
        pending_game.pop(uid, None)
        await reply(message, active, GAMES_KB)
        return

    if normalized in {"/start", "شروع", "استارت"}:
        pending_game.pop(uid, None)
        db.mark_mission(uid, "login")
        db.add_xp(uid, 5)
        await reply(message, db.home_text(uid), MAIN_KB)
        return

    # When a game has been selected, the next message chooses its player count.
    if uid in pending_game:
        kind = pending_game[uid]
        action, _ = db.parse_action(normalized)

        if action == "mode_solo":
            pending_game.pop(uid, None)
            if kind == "solo_quiz" or kind == "word_game" or kind == "reaction":
                await reply(message, games.start_solo(uid, cid, kind), GAMES_KB)
            return

        if action == "mode_duo":
            if kind in {"word_game", "reaction", "solo_quiz"}:
                pending_game.pop(uid, None)
                await reply(
                    message,
                    games.create_room(uid, cid, "duo", kind),
                    GAMES_KB,
                )
                return

        if action == "mode_multi":
            if kind != "solo_quiz":
                await reply(
                    message,
                    "⚠️ این بازی چندنفره نیست.
برای این بازی «تک‌نفره» یا «دونفره» رو انتخاب کن.",
                    MODES_KB,
                )
                return
            pending_game.pop(uid, None)
            await reply(
                message,
                games.create_room(uid, cid, "multi", kind),
                GAMES_KB,
            )
            return

        if normalized in {"🏠 منو", "منو", "خانه"}:
            pending_game.pop(uid, None)
            await reply(message, db.home_text(uid), MAIN_KB)
            return

        # Ignore a new top-level command while a game mode is being selected only if it
        # is not a menu command; otherwise allow normal routing below.

    # Game catalog entry.
    if normalized in {"🎮 بازی‌ها", "بازی", "گیم", "game", "games"}:
        await reply(message, games.catalog_text(), GAMES_KB)
        return

    # Specific game entry.
    game_key = text.casefold()
    if game_key in GAME_KIND_BY_TEXT:
        kind = GAME_KIND_BY_TEXT[game_key]
        pending_game[uid] = kind
        await reply(message, games.game_detail(kind) + "\n\n" + mode_question(kind), MODES_KB)
        return

    action, argument = db.parse_action(normalized)

    if action == "home":
        await reply(message, db.home_text(uid), MAIN_KB)
    elif action == "wallet":
        await reply(message, db.wallet_text(uid), REWARD_KB)
    elif action == "reward":
        await reply(message, db.claim_daily(uid), REWARD_KB)
    elif normalized == "🎁 دریافت جایزه":
        await reply(message, db.claim_daily(uid), REWARD_KB)
    elif action == "profile":
        await reply(message, db.profile_text(uid), MAIN_KB)
    elif action == "leaderboard":
        await reply(message, db.leaderboard_text(), MAIN_KB)
    elif action == "missions":
        await reply(message, db.missions_text(uid), MAIN_KB)
    elif action == "shop":
        await reply(message, db.shop_text(), SHOP_KB)
    elif action == "shop_detail":
        await reply(message, db.shop_detail(argument), SHOP_ACTION_KB)
    elif action == "inventory":
        await reply(message, db.inventory_text(uid), SHOP_KB)
    elif action == "buy":
        await reply(message, db.buy_item(uid, argument), SHOP_KB)
    elif action == "friends":
        await reply(message, db.friends_text(uid), MAIN_KB)
    elif action == "pair":
        await reply(message, db.pair_text(uid), MAIN_KB)
    elif action == "pair_with":
        await reply(message, db.pair_with(uid, argument), MAIN_KB)
    elif action == "settings":
        await reply(message, db.settings_text(uid), MAIN_KB)
    elif action == "join":
        await reply(message, games.join_room(uid, cid), GAMES_KB)
    elif action == "mode_solo" or action == "mode_duo" or action == "mode_multi":
        await reply(
            message,
            "اول یک بازی رو انتخاب کن تا بعد تعداد نفراتش رو مشخص کنیم.",
            GAMES_KB,
        )
    elif text.casefold() in SHOP_KIND_BY_TEXT:
        item_id = SHOP_KIND_BY_TEXT[text.casefold()]
        await reply(message, db.shop_detail(item_id), SHOP_ACTION_KB)
    elif action == "help":
        await reply(message, db.help_text(), MAIN_KB)
    else:
        await reply(message, db.suggest(text), MAIN_KB)

@dp.message(Command("start"))
async def start_handler(message: Message):
    await handle(message)

@dp.message(Command("menu"))
async def menu_handler(message: Message):
    uid = uid_of(message)
    db.ensure_user(uid)
    await reply(message, db.home_text(uid), MAIN_KB)

@dp.message()
async def message_handler(message: Message):
    try:
        await handle(message)
    except Exception as exc:
        print(f"T3R0ZA handler error: {type(exc).__name__}: {exc}")
        try:
            await reply(message, "⚠️ یه خطای موقت شد 😅\nدوباره همین گزینه رو بفرست.", MAIN_KB)
        except Exception as reply_exc:
            print(f"T3R0ZA reply error: {type(reply_exc).__name__}: {reply_exc}")

async def main():
    me = await bot.get_me()
    print(f"T3R0ZA_BOT authenticated as {getattr(me, 'first_name', 'bot')}")
    print("T3R0ZA_BOT polling started")
    await dp.start_polling(bot, drop_pending_updates=False)

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    asyncio.run(main())
