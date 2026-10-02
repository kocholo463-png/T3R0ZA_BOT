# T3R0ZA_BOT

ربات رسمی T3R0ZA برای Soroush Plus.

## امکانات فعلی
- منوی دکمه‌ای فارسی
- /start و /menu
- عبارت‌های طبیعی مثل «بازی»، «سکه»، «جایزه»، «پروفایل» و «رتبه»
- سکهٔ کاملاً مجازی
- XP / Level / Streak
- جایزه روزانه
- مأموریت
- فروشگاه و Inventory
- رتبه‌بندی
- کوئیز، حدس کلمه و تست واکنش
- اتاق دونفره و چندنفره
- Pair دوستانه و غیرجنسی
- SQLite
- health endpoint برای Render Web Service

## اجرای Render
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: python bot.py
Health Check Path: /

Environment Variable:
BOT_TOKEN = توکن جدید ربات

توکن واقعی را داخل GitHub یا کد نگذار.

## نکتهٔ دیتابیس
SQLite در فایل محلی است. برای داده‌های مهم و استفادهٔ طولانی‌مدت، دیتابیس پایدار مثل PostgreSQL مناسب‌تر است.


Final automated verification trigger.
