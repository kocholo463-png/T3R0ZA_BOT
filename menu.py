from spluspy import Button

def row(*labels):
    return [Button.text(label, resize=True, persistent=True) for label in labels]

def main_keyboard():
    return [
        row("🎮 بازی", "🪙 سکه"),
        row("🎁 جایزه", "🎯 مأموریت"),
        row("🛒 فروشگاه", "🎒 کوله"),
        row("👤 پروفایل", "🏆 رتبه"),
        row("🤝 دوستان", "🛡️ گروه"),
        row("⭐ افتخارات", "⚙️ تنظیمات"),
    ]

def game_keyboard():
    return [
        row("🎯 کوئیز", "🧩 حدس کلمه"),
        row("⚡ واکنش", "🏆 چالش گروهی"),
        row("👥 اتاق دو نفره", "👥👥 اتاق گروهی"),
        row("📖 راهنمای بازی", "🏠 منو"),
    ]

def mode_keyboard():
    return [
        row("👤 تک‌نفره", "👥 دو نفره"),
        row("👥👥 چندنفره"),
        row("↩️ برگشت بازی"),
    ]

def room_keyboard():
    return [
        row("➕ پیوستن", "🔄 وضعیت اتاق"),
        row("❌ لغو اتاق", "🎮 بازی"),
    ]

def shop_keyboard():
    return [
        row("🧰 Lucky Badge", "🎨 Profile Frame"),
        row("⚡ XP Boost"),
        row("🎒 کوله", "🏠 منو"),
    ]

def item_keyboard(item_id):
    return [
        row(f"🛒 خرید {item_id}"),
        row("↩️ برگشت فروشگاه", "🏠 منو"),
    ]

def reward_keyboard():
    return [
        row("🎁 دریافت جایزه", "🪙 سکه"),
        row("🎯 مأموریت", "🏠 منو"),
    ]

def group_keyboard():
    return [
        row("👋 خوش‌آمد", "🔗 ضدلینک"),
        row("🚨 ضداسپم", "📊 آمار گروه"),
        row("🧹 پاکسازی", "ℹ️ وضعیت گروه"),
        row("🏠 منو"),
    ]

def friends_keyboard():
    return [
        row("👥 دوستان", "🤝 Pair"),
        row("🎯 مأموریت مشترک", "🎮 بازی دو نفره"),
        row("🏠 منو"),
    ]

def profile_keyboard():
    return [
        row("⭐ افتخارات", "🏆 رتبه"),
        row("🎒 کوله", "🪙 سکه"),
        row("🏠 منو"),
    ]

def settings_keyboard():
    return [
        row("🔔 اعلان‌ها", "😎 لحن پاسخ"),
        row("🧼 پاک کردن پنل"),
        row("🏠 منو"),
    ]

def achievements_keyboard():
    return [
        row("🏆 رتبه", "👤 پروفایل"),
        row("🏠 منو"),
    ]
