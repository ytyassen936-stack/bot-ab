# -*- coding: utf-8 -*-
import asyncio, json, os, re
from datetime import datetime
import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ========== الإعدادات ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# معلومات المطور - غيرها
DEV_NAME = "مطور البوت @w3vv"
DEV_USERNAME = "@w_3_vv"
DEV_PHOTO = "https://i.imgur.com/placeholder.jpg" # حط رابط صورتك هنا

CHECK_INTERVAL = 600
DOLLAR_INTERVAL = 3600

client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
bot = Bot(token=BOT_TOKEN)
CONFIG_FILE = 'bot_config.json'

# ========== مصادر الرواتب ==========
SALARY_SOURCES = {
    "الرعاية الاجتماعية والمتقاعدين": {
        "URL": "https://molsa.gov.iq/",
        "KEYWORDS": ["نحن", "نا", "رواتب", "الرواتب", "دفعة", "اطلاق", "صرف", "مستحقات", "الوجبة", "ملحق"]
    },
    "البيان الرسمي لوزارة المالية": {
        "URL": "https://www.mof.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "اطلاق", "تمويل", "صرف", "المالية", "الموازنة", "حسابات", "استحقاق"]
    },
    "وزارة التربية": {
        "URL": "https://moedu.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "الملاك", "صرف", "التربية", "المعلمين", "المدرسين", "الكوادر", "محاضرين"]
    },
    "وزارة الصحة": {
        "URL": "https://moh.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الصحة", "الكوادر", "منتسبي"]
    },
    "وزارة الدفاع": {
        "URL": "https://mod.mil.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الدفاع", "الجيش", "منتسبي"]
    },
    "وزارة الداخلية": {
        "URL": "https://moi.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الداخلية", "الشرطة", "منتسبي"]
    },
    "وزارة التعليم العالي": {
        "URL": "https://mohesr.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "التعليم", "الجامعات", "التدريسيين"]
    },
    "وزارة الكهرباء": {
        "URL": "https://moelc.gov.iq/",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الكهرباء", "منتسبي"]
    }
}

# ========== كلمات النفي للفحص الذكي ==========
NEGATIVE_CONTEXT = ["لا يوجد", "عدم", "تأجيل", "ايقاف", "الغاء", "نفي", "اشاعة", "كاذب", "غير صحيح", "لم يتم"]

# ========== دوال التكوين ==========
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data.get("آخر عملية بيع", 0) == 0: data["آخر عملية بيع"] = 1550
            if data.get("آخر عملية شراء", 0) == 0: data["آخر عملية شراء"] = 1310
            if "مصادر" not in data: data["مصادر"] = {}
            if "users" not in data: data["users"] = []
            for name in SALARY_SOURCES:
                if name not in data["مصادر"]:
                    data["مصادر"][name] = {"enabled": True, "keywords": SALARY_SOURCES[name]["KEYWORDS"]}
            return data
    except:
        config = {
            "آخر_الأخبار": [], "is_running": True, "الوضع الصامت": False,
            "dollar_enabled": True, "آخر عملية شراء": 1310, "آخر عملية بيع": 1550,
            "آخر_تاريخ_للشراء": "", "آخر_تاريخ_للبيع": "", "dollar_msg_id": None,
            "last_salary_msg_id": None, "admin_ids": [ADMIN_ID], "مصادر": {}, "users": [],
            "waiting_broadcast": False, "waiting_keywords": None
        }
        for name in SALARY_SOURCES:
            config["مصادر"][name] = {"enabled": True, "keywords": SALARY_SOURCES[name]["KEYWORDS"]}
        return config

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ========== الفحص الذكي ==========
def is_real_news(text, keyword):
    keyword_pos = text.find(keyword)
    if keyword_pos == -1: return False
    context = text[max(0, keyword_pos-100):keyword_pos+100]
    for neg in NEGATIVE_CONTEXT:
        if neg in context:
            return False
    return True

# ========== دوال الفحص المحدثة ==========
async def fetch_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        r = await client.get(url, headers=headers, follow_redirects=True, timeout=20.0)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

async def check_single_source(name, source, config, silent=True):
    if not config["مصادر"].get(name, {}).get("enabled", True):
        return f"⚪ {name}: معطل"

    urls_to_try = [
        source["URL"],
        source["URL"] + "news",
        source["URL"] + "ar",
        source["URL"] + "ar/news",
        source["URL"] + "ar/node",
        source["URL"] + "latest"
    ]

    status, text = 0, ""
    for url in urls_to_try:
        status, text = await fetch_url(url)
        if status == 200:
            break
        await asyncio.sleep(0.5)

    if status!= 200:
        if status == 403:
            return f"🚫 {name}: محظور 403"
        elif status == 0:
            return f"🔴 {name}: الموقع واقع"
        else:
            return f"🔴 {name}: خطأ {status}"

    keywords = config["مصادر"][name].get("keywords", source["KEYWORDS"])
    found_keyword = None

    for keyword in keywords:
        if keyword in text and is_real_news(text, keyword):
            found_keyword = keyword
            break

    if found_keyword:
        news_id = f"{name}_{hash(text[:500])}"
        if news_id not in config["آخر_الأخبار"]:
            if not silent:
                msg = f"🔴 عاجل | {name}\n\nتم رصد خبر صرف الرواتب.\n\nالمصدر: {source['URL']}"
                if config["الوضع الصامت"]:
                    try:
                        await bot.send_message(chat_id=CHANNEL_ID, text=msg, disable_web_page_preview=True, disable_notification=True)
                    except: pass
                else:
                    try:
                        sent = await bot.send_message(chat_id=CHANNEL_ID, text=msg, disable_web_page_preview=True)
                        config["last_salary_msg_id"] = sent.message_id
                    except: pass

                config["آخر_الأخبار"].append(news_id)
                if len(config["آخر_الأخبار"]) > 50:
                    config["آخر_الأخبار"] = config["آخر_الأخبار"][-50:]
                save_config(config)
            return f"🟢 {name}: تم العثور على '{found_keyword}'"
        else:
            return f"🟡 {name}: خبر مكرر"
    return f"🔵 {name}: لا يوجد جديد"

async def check_salaries(silent=True):
    config = load_config()
    if not config["is_running"] and silent: return []

    results = []
    for name, source in SALARY_SOURCES.items():
        result = await check_single_source(name, source, config, silent)
        results.append(result)
        await asyncio.sleep(1)
    return results

# ========== فحص الدولار ==========
async def check_dollar():
    config = load_config()
    if not config["is_running"] or not config["dollar_enabled"]: return False

    try:
        r = await client.get("https://api.albarakaexchange.com.iq/api/v1/rates", follow_redirects=True)
        if r.status_code == 200:
            data = r.json()
            buy = int(data["data"]["buy"])
            sell = int(data["data"]["sell"])

            if buy!= config["آخر عملية شراء"] or sell!= config["آخر عملية بيع"]:
                now = datetime.now().strftime("%Y/%m/%d - %H:%M")

                msg = f"""💵 اسعار صرف الدولار الحالية 💵

البنك المركزي - الشراء 🏦
الدولار: {buy:,} دينار 🔸
الورقة: {buy * 100:,} دينار 🔸

السوق - البيع 🏦
الدولار: {sell:,} دينار 🔸
الورقة: {sell * 100:,} دينار 🔸

الآن: {now} 🕒
تابع قناتنا @w3vv لكل جديد"""

                try:
                    if config["dollar_msg_id"]:
                        await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=config["dollar_msg_id"], text=msg)
                    else:
                        sent = await bot.send_message(chat_id=CHANNEL_ID, text=msg)
                        config["dollar_msg_id"] = sent.message_id
                except:
                    try:
                        sent = await bot.send_message(chat_id=CHANNEL_ID, text=msg)
                        config["dollar_msg_id"] = sent.message_id
                    except: pass

                config["آخر عملية شراء"] = buy
                config["آخر عملية بيع"] = sell
                config["آخر_تاريخ_للشراء"] = now
                config["آخر_تاريخ_للبيع"] = now
                save_config(config)
                return True
    except: pass
    return False

# ========== كليشة سعر الصرف ==========
def get_dollar_message():
    config = load_config()
    buy = config['آخر عملية شراء']
    sell = config['آخر عملية بيع']
    now = datetime.now().strftime("%Y/%m/%d - %H:%M")

    msg = f"""💵 اسعار صرف الدولار الحالية 💵

البنك المركزي - الشراء 🏦
الدولار: {buy:,} دينار 🔸
الورقة: {buy * 100:,} دينار 🔸

السوق - البيع 🏦
الدولار: {sell:,} دينار 🔸
الورقة: {sell * 100:,} دينار 🔸

الآن: {now} 🕒
تابع قناتنا @w3vv لكل جديد"""
    return msg

# ========== لوحة التحكم ==========
def get_admin_panel(config):
    enabled_count = sum(1 for s in config["مصادر"].values() if s.get("enabled", True))
    status_run = "شغال" if config['is_running'] else "متوقف"
    status_silent = "مفعل" if config['الوضع الصامت'] else "معطل"
    status_dollar = "مفعل" if config['dollar_enabled'] else "معطل"
    pin_status = "مثبت" if config['dollar_msg_id'] else "غير مثبت"

    status_text = f"⚙️ لوحة تحكم @w3vv\n\n📊 الحالة: {status_run} | الصامت: {status_silent} 🔔\n💵 الدولار: {status_dollar} | {pin_status} ❌\n🏦 شراء: {config['آخر عملية شراء']:,} | بيع: {config['آخر عملية بيع']:,}\n📡 مصادر الرواتب: {enabled_count} مفعلة"

    keyboard = [
        [InlineKeyboardButton("👨‍💻 معلومات المطور", callback_data="dev_info")],
        [InlineKeyboardButton("💵 اسعار الدولار", callback_data="dollar_prices")],
        [InlineKeyboardButton("📰 جلب الاخبار", callback_data="fetch_news")],
        [InlineKeyboardButton("🗑️ حذف آخر منشور", callback_data="delete_last")],
        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="backup")],
        [InlineKeyboardButton("📢 اذاعة", callback_data="broadcast"), InlineKeyboardButton("⏯️ تشغيل/ايقاف", callback_data="toggle_run")],
        [InlineKeyboardButton("🔕 صامت", callback_data="toggle_silent"), InlineKeyboardButton("💵 دولار تلقائي", callback_data="toggle_dollar")],
        [InlineKeyboardButton("📌 الغاء تثبيت الدولار", callback_data="unpin_dollar")],
        [InlineKeyboardButton("🔄 فحص يدوي", callback_data="manual_check"), InlineKeyboardButton("🔄 تحديث", callback_data="refresh")],
        [InlineKeyboardButton("✏️ تعديل الكلمات المفتاحية", callback_data="edit_keywords")]
    ]
    return status_text, InlineKeyboardMarkup(keyboard)

async def handle_message(update):
    if not update.message: return
    config = load_config()

    user_id = update.message.from_user.id
    if user_id not in config["users"]:
        config["users"].append(user_id)
        save_config(config)

    # امر /start للكل مع زرين
    if update.message.text == "/start":
        keyboard = [
            [InlineKeyboardButton("👨‍💻 المطور", callback_data="dev_info_user")],
            [InlineKeyboardButton("💵 سعر صرف الدولار", callback_data="sarf_user")]
        ]
        await bot.send_message(
            chat_id=update.message.chat.id,
            text="👋 اهلاً بك في بوت رواتب العراق\n\nاختر من الازرار:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if update.message.text == "/sarf":
        await bot.send_message(chat_id=update.message.chat.id, text=get_dollar_message())
        return

    if update.message.from_user.id == ADMIN_ID and config.get("waiting_keywords"):
        source_name = config["waiting_keywords"]
        config["waiting_keywords"] = None
        new_keywords = [k.strip() for k in update.message.text.split(",")]
        config["مصادر"][source_name]["keywords"] = new_keywords
        save_config(config)
        await bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم تحديث كلمات {source_name}:\n{', '.join(new_keywords)}")
        return

    if update.message.from_user.id == ADMIN_ID and config.get("waiting_broadcast"):
        config["waiting_broadcast"] = False
        save_config(config)
        count = 0
        for uid in config.get("users", []):
            try:
                await bot.send_message(chat_id=uid, text=update.message.text)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم الارسال لـ {count} مستخدم")
        return

    if update.message.from_user.id!= ADMIN_ID: return
    if update.message.text == "/admin":
        status_text, keyboard = get_admin_panel(config)
        await bot.send_message(chat_id=ADMIN_ID, text=status_text, reply_markup=keyboard)

async def handle_callback(update):
    query = update.callback_query
    data = query.data
    await query.answer()

    # ازرار عامة للكل
    if data == "dev_info_user":
        caption = f"👨‍💻 {DEV_NAME}\n\n📢 القناة: @w_3_vv\n💬 للتواصل: {DEV_USERNAME}"
        try:
            await bot.send_photo(chat_id=query.from_user.id, photo=DEV_PHOTO, caption=caption)
        except:
            await bot.send_message(chat_id=query.from_user.id, text=caption)
        return
    elif data == "sarf_user":
        await bot.send_message(chat_id=query.from_user.id, text=get_dollar_message())
        return

    # ازرار الادمن فقط
    if query.from_user.id!= ADMIN_ID:
        await query.answer("غير مصرح لك")
        return

    config = load_config()

    if data == "toggle_run":
        config["is_running"] = not config["is_running"]
        save_config(config)
    elif data == "toggle_silent":
        config["الوضع الصامت"] = not config["الوضع الصامت"]
        save_config(config)
    elif data == "toggle_dollar":
        config["dollar_enabled"] = not config["dollar_enabled"]
        save_config(config)
    elif data == "dev_info":
        await bot.send_message(chat_id=ADMIN_ID, text=f"👨‍💻 مطور البوت: {DEV_USERNAME}\n⚙️ اصدار: V2 Pro")
        return
    elif data == "dollar_prices":
        buy = config['آخر عملية شراء']
        sell = config['آخر عملية بيع']
        await bot.send_message(chat_id=ADMIN_ID, text=f"💵 اسعار الدولار الحالية:\n\n🔻 شراء: {buy:,} د.ع\n🔺 بيع: {sell:,} د.ع\n\n⏰ {config.get('آخر_تاريخ_للبيع', 'لا يوجد')}")
        return
    elif data == "fetch_news":
        msg = await bot.send_message(chat_id=ADMIN_ID, text="⏳ جاري جلب الاخبار...")
        await check_salaries(silent=False)
        await bot.edit_message_text(chat_id=ADMIN_ID, message_id=msg.message_id, text="✅ تم الجلب والنشر للقناة")
        return
    elif data == "delete_last":
        if config.get("last_salary_msg_id"):
            try:
                await bot.delete_message(chat_id=CHANNEL_ID, message_id=config["last_salary_msg_id"])
                await bot.send_message(chat_id=ADMIN_ID, text="✅ تم حذف آخر منشور")
                config["last_salary_msg_id"] = None
                save_config(config)
            except:
                await bot.send_message(chat_id=ADMIN_ID, text="❌ فشل الحذف")
        else:
            await bot.send_message(chat_id=ADMIN_ID, text="❌ لا يوجد منشور محفوظ")
        return
    elif data == "backup":
        with open(CONFIG_FILE, 'rb') as f:
            await bot.send_document(chat_id=ADMIN_ID, document=f, filename='backup.json', caption='💾 نسخة احتياطية')
        return
    elif data == "broadcast":
        config["waiting_broadcast"] = True
        save_config(config)
        await bot.send_message(chat_id=ADMIN_ID, text="📢 ارسل الرسالة اللي تريد اذاعتها:")
        return
    elif data == "unpin_dollar":
        if config.get("dollar_msg_id"):
            try:
                await bot.unpin_chat_message(chat_id=CHANNEL_ID, message_id=config["dollar_msg_id"])
                config["dollar_msg_id"] = None
                save_config(config)
                await bot.send_message(chat_id=ADMIN_ID, text="✅ تم الغاء التثبيت")
            except:
                await bot.send_message(chat_id=ADMIN_ID, text="❌ فشل")
        return
    elif data == "manual_check":
        msg = await bot.send_message(chat_id=ADMIN_ID, text="⏳ جاري الفحص اليدوي لجميع المصادر...")
        results = await check_salaries(silent=True)
        result_text = "🔄 نتائج الفحص اليدوي:\n\n" + "\n".join(results)
        await bot.edit_message_text(chat_id=ADMIN_ID, message_id=msg.message_id, text=result_text)
        return
    elif data == "edit_keywords":
        keyboard = []
        for name in SALARY_SOURCES.keys():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"editkw_{name}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="refresh")])
        await query.edit_message_text("✏️ اختر الوزارة لتعديل كلماتها:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("editkw_"):
        source_name = data.replace("editkw_", "")
        config["waiting_keywords"] = source_name
        save_config(config)
        current_kw = ", ".join(config["مصادر"][source_name]["keywords"])
        await bot.send_message(chat_id=ADMIN_ID, text=f"✏️ الكلمات الحالية لـ {source_name}:\n{current_kw}\n\nارسل الكلمات الجديدة مفصولة بفاصلة,")
        return
    elif data == "refresh":
        pass

    status_text, keyboard = get_admin_panel(config)
    try:
        await query.edit_message_text(text=status_text, reply_markup=keyboard)
    except: pass

# ========== التشغيل الرئيسي ==========
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    offset = 0
    last_salary_check = 0
    last_dollar_check = 0

    print("✅ البوت شغال - V2 Pro")

    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update.update_id + 1
                if update.callback_query:
                    await handle_callback(update)
                elif update.message:
                    await handle_message(update)

            now = asyncio.get_event_loop().time()
            if now - last_salary_check >= CHECK_INTERVAL:
                await check_salaries(silent=False)
                last_salary_check = now

            if now - last_dollar_check >= DOLLAR_INTERVAL:
                await check_dollar()
                last_dollar_check = now

        except Exception as e:
            print(f"خطأ: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    import threading, os
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Bot Running')
        def log_message(self, format, *args):
            return

    def start_fake_server():
        port = int(os.environ.get('PORT', 10000))
        HTTPServer(('0.0.0.0', port), DummyHandler).serve_forever()

    threading.Thread(target=start_fake_server, daemon=True).start()
    asyncio.run(main())
