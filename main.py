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

CHECK_INTERVAL = 600
DOLLAR_INTERVAL = 3600

client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
bot = Bot(token=BOT_TOKEN)
CONFIG_FILE = 'bot_config.json'

# ========== مصادر الرواتب - حذفت كل المواقع الميتة ==========
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

# ========== دوال التكوين ==========
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data.get("آخر عملية بيع", 0) == 0: data["آخر عملية بيع"] = 1550
            if data.get("آخر عملية شراء", 0) == 0: data["آخر عملية شراء"] = 1310
            if "مصادر" not in data: data["مصادر"] = {}
            for name in SALARY_SOURCES:
                if name not in data["مصادر"]:
                    data["مصادر"][name] = {"enabled": True, "keywords": SALARY_SOURCES[name]["KEYWORDS"]}
            return data
    except:
        config = {
            "آخر_الأخبار": [], "is_running": True, "الوضع الصامت": False,
            "dollar_enabled": True, "آخر عملية شراء": 1310, "آخر عملية بيع": 1550,
            "آخر_تاريخ_للشراء": "", "آخر_تاريخ_للبيع": "", "dollar_msg_id": None,
            "last_salary_msg_id": None, "admin_ids": [ADMIN_ID], "مصادر": {}
        }
        for name in SALARY_SOURCES:
            config["مصادر"][name] = {"enabled": True, "keywords": SALARY_SOURCES[name]["KEYWORDS"]}
        return config

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ========== دوال الفحص - تتجاهل الاخطاء بصمت ==========
async def fetch_url(url):
    try:
        r = await client.get(url, follow_redirects=True)
        return r.status_code, r.text
    except:
        return 0, "" # فشل بصمت بدون ارسال شي

async def check_single_source(name, source, config):
    if not config["مصادر"].get(name, {}).get("enabled", True):
        return

    status, text = await fetch_url(source["URL"])
    if status!= 200:
        return # تجاهل بصمت

    keywords = config["مصادر"][name].get("keywords", source["KEYWORDS"])
    found_keyword = None
    for keyword in keywords:
        if keyword in text:
            found_keyword = keyword
            break

    if found_keyword:
        news_id = f"{name}_{hash(text[:500])}"
        if news_id not in config["آخر_الأخبار"]:
            msg = f"🔴 عاجل | {name}\n\nتم رصد كلمة '{found_keyword}' في الموقع.\n\nالمصدر: {source['URL']}"

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

async def check_salaries():
    config = load_config()
    if not config["is_running"]: return

    tasks = [check_single_source(name, source, config) for name, source in SALARY_SOURCES.items()]
    await asyncio.gather(*tasks)

# ========== فحص الدولار ==========
async def check_dollar():
    config = load_config()
    if not config["is_running"] or not config["dollar_enabled"]: return

    try:
        r = await client.get("https://api.albarakaexchange.com.iq/api/v1/rates", follow_redirects=True)
        if r.status_code == 200:
            data = r.json()
            buy = int(data["data"]["buy"])
            sell = int(data["data"]["sell"])

            if buy!= config["آخر عملية شراء"] or sell!= config["آخر عملية بيع"]:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                msg = f"💵 تحديث أسعار الدولار\n\n🔻 الشراء: {buy} د.ع\n🔺 البيع: {sell} د.ع\n\n⏰ آخر تحديث: {now}"

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
    except: pass

# ========== لوحة التحكم ==========
async def handle_update(update):
    if not update.message: return
    if update.message.from_user.id!= ADMIN_ID: return
    if update.message.text!= "/admin": return

    config = load_config()
    enabled_count = sum(1 for s in config["مصادر"].values() if s.get("enabled", True))

    keyboard = [
        [InlineKeyboardButton("🔄 تشغيل المراقبة" if not config["is_running"] else "⏸️ إيقاف المراقبة", callback_data="toggle_run")],
        [InlineKeyboardButton("🔕 تفعيل الوضع الصامت" if not config["الوضع الصامت"] else "🔔 إلغاء الوضع الصامت", callback_data="toggle_silent")],
        [InlineKeyboardButton("💵 تفعيل الدولار" if not config["dollar_enabled"] else "💵 ايقاف الدولار", callback_data="toggle_dollar")],
        [InlineKeyboardButton("📡 ادارة المصادر", callback_data="manage_sources")],
        [InlineKeyboardButton("🗑️ مسح سجل الأخبار", callback_data="clear_news")]
    ]

    status_text = f"⚙️ لوحة تحكم @w_3_vv V2\n\n📊 حالة المراقبة: {'🟢 تعمل' if config['is_running'] else '🔴 متوقفة'}\n💵 مراقبة الدولار: {'✅ مفعلة' if config['dollar_enabled'] else '❌ متوقفة'}\n🔕 الوضع الصامت: {'✅ مفعل' if config['الوضع الصامت'] else '❌ متوقف'}\n\n📡 المصادر المفعلة: {enabled_count}/{len(SALARY_SOURCES)}\n\n💰 آخر سعر دولار:\n🔻 شراء: {config['آخر عملية شراء']} - {config.get('آخر_تاريخ_للشراء', 'لا يوجد')}\n🔺 بيع: {config['آخر عملية بيع']} - {config.get('آخر_تاريخ_للبيع', 'لا يوجد')}"

    await bot.send_message(chat_id=ADMIN_ID, text=status_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update):
    query = update.callback_query
    if query.from_user.id!= ADMIN_ID:
        await query.answer("غير مصرح لك")
        return

    config = load_config()
    data = query.data

    if data == "toggle_run":
        config["is_running"] = not config["is_running"]
        await query.answer(f"المراقبة {'اشتغلت' if config['is_running'] else 'توقفت'} ✅")
    elif data == "toggle_silent":
        config["الوضع الصامت"] = not config["الوضع الصامت"]
        await query.answer(f"الوضع الصامت {'تفعل' if config['الوضع الصامت'] else 'توقف'} ✅")
    elif data == "toggle_dollar":
        config["dollar_enabled"] = not config["dollar_enabled"]
        await query.answer(f"مراقبة الدولار {'اشتغلت' if config['dollar_enabled'] else 'توقفت'} ✅")
    elif data == "clear_news":
        config["آخر_الأخبار"] = []
        await query.answer("تم مسح السجل ✅")
    elif data == "manage_sources":
        keyboard = []
        for name, source in config["مصادر"].items():
            status = "✅" if source.get("enabled", True) else "❌"
            keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"toggle_source_{name}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        await query.edit_message_text("📡 ادارة مصادر الرواتب:\nاضغط للتفعيل/التعطيل", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data.startswith("toggle_source_"):
        name = data.replace("toggle_source_", "")
        if name in config["مصادر"]:
            config["مصادر"][name]["enabled"] = not config["مصادر"][name].get("enabled", True)
            await query.answer(f"{name}: {'تفعل' if config['مصادر'][name]['enabled'] else 'توقف'}")
            # اعادة عرض قائمة المصادر
            keyboard = []
            for n, s in config["مصادر"].items():
                status = "✅" if s.get("enabled", True) else "❌"
                keyboard.append([InlineKeyboardButton(f"{status} {n}", callback_data=f"toggle_source_{n}")])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
            save_config(config)
            return
    elif data == "back_main":
        await query.message.delete()
        await handle_update(query)
        return

    save_config(config)

    # اعادة عرض اللوحة
    enabled_count = sum(1 for s in config["مصادر"].values() if s.get("enabled", True))
    keyboard = [
        [InlineKeyboardButton("🔄 تشغيل المراقبة" if not config["is_running"] else "⏸️ إيقاف المراقبة", callback_data="toggle_run")],
        [InlineKeyboardButton("🔕 تفعيل الوضع الصامت" if not config["الوضع الصامت"] else "🔔 إلغاء الوضع الصامت", callback_data="toggle_silent")],
        [InlineKeyboardButton("💵 تفعيل الدولار" if not config["dollar_enabled"] else "💵 ايقاف الدولار", callback_data="toggle_dollar")],
        [InlineKeyboardButton("📡 ادارة المصادر", callback_data="manage_sources")],
        [InlineKeyboardButton("🗑️ مسح سجل الأخبار", callback_data="clear_news")]
    ]
    status_text = f"⚙️ لوحة تحكم @w_3_vv V2\n\n📊 حالة المراقبة: {'🟢 تعمل' if config['is_running'] else '🔴 متوقفة'}\n💵 مراقبة الدولار: {'✅ مفعلة' if config['dollar_enabled'] else '❌ متوقفة'}\n🔕 الوضع الصامت: {'✅ مفعل' if config['الوضع الصامت'] else '❌ متوقف'}\n\n📡 المصادر المفعلة: {enabled_count}/{len(SALARY_SOURCES)}\n\n💰 آخر سعر دولار:\n🔻 شراء: {config['آخر عملية شراء']} - {config.get('آخر_تاريخ_للشراء', 'لا يوجد')}\n🔺 بيع: {config['آخر عملية بيع']} - {config.get('آخر_تاريخ_للبيع', 'لا يوجد')}"
    await query.edit_message_text(text=status_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== التشغيل الرئيسي ==========
async def main():
    offset = 0
    last_salary_check = 0
    last_dollar_check = 0

    print("✅ البوت شغال - V2 مصلح")

    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update.update_id + 1
                if update.message:
                    await handle_update(update)
                elif update.callback_query:
                    await handle_callback(update)

            now = asyncio.get_event_loop().time()
            if now - last_salary_check >= CHECK_INTERVAL:
                await check_salaries()
                last_salary_check = now

            if now - last_dollar_check >= DOLLAR_INTERVAL:
                await check_dollar()
                last_dollar_check = now

        except Exception as e:
            print(f"خطأ: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
