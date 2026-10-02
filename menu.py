from spluspy import Button

def main_keyboard():
    return [
        [Button.text("🎮 بازی‌ها"), Button.text("🪙 سکه")],
        [Button.text("🎁 جایزه"), Button.text("🎯 مأموریت")],
        [Button.text("🛒 فروشگاه"), Button.text("🎒 کوله‌بری")],
        [Button.text("👤 پروفایل"), Button.text("🏆 رتبه")],
        [Button.text("🤝 دوستان / زوج"), Button.text("⚙️ تنظیمات")],
    ]

def games_keyboard():
    return [
        [Button.text("👤 تک‌نفره"), Button.text("🧩 حدس کلمه")],
        [Button.text("⚡ تست واکنش")],
        [Button.text("👥 دونفره"), Button.text("👥👥 چندنفره")],
        [Button.text("✅ پیوستن"), Button.text("🏠 منو")],
    ]

def shop_keyboard():
    return [
        [Button.text("🛒 فروشگاه"), Button.text("🎒 کوله‌بری")],
        [Button.text("🏠 منو")],
    ]

def friends_keyboard():
    return [
        [Button.text("🤝 دوستان / زوج"), Button.text("👤 پروفایل")],
        [Button.text("🏠 منو")],
    ]

def settings_keyboard():
    return [
        [Button.text("⚙️ تنظیمات"), Button.text("🏠 منو")],
    ]
