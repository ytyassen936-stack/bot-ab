# -*- coding: utf-8 -*-
import asyncio, json, os, re, logging, hashlib
from datetime import datetime
import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002350481912"))
CHANNEL_USERNAME = "@w_3_vv"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DEV_NAME = "مطور البوت @w3vv"
DEV_USERNAME = "@w_3_vv"

CHECK_INTERVAL = 600
DOLLAR_INTERVAL = 3600

client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
bot = Bot(token=BOT_TOKEN)
CONFIG_FILE = 'bot_config.json'

SALARY_SOURCES = {
    "وزارة المالية": {
        "TELEGRAM": "Mof_Iraq",
        "DISPLAY": "وزارة المالية",
        "KEYWORDS": ["رواتب", "الرواتب", "اطلاق", "تمويل", "صرف", "المالية"],
        "PRIORITY": 1
    },
    "وزارة الداخلية": {
        "TELEGRAM": "MOI_Iraq",
        "DISPLAY": "وزارة الداخلية",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الداخلية", "الشرطة", "منتسبي"],
        "PRIORITY": 1
    },
    "وزارة الدفاع": {
        "TELEGRAM": "MODiraq",
        "DISPLAY": "وزارة الدفاع",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الدفاع", "الجيش", "منتسبي"],
        "PRIORITY": 1
    },
    "وزارة الصحة": {
        "TELEGRAM": "mohiraq",
        "DISPLAY": "وزارة الصحة",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الصحة", "الكوادر", "منتسبي"],
        "PRIORITY": 1
    },
    "وزارة التربية": {
        "TELEGRAM": "moedu_iq",
        "DISPLAY": "وزارة التربية",
        "KEYWORDS": ["رواتب", "الرواتب", "الملاك", "صرف", "التربية", "المعلمين"],
        "PRIORITY": 1
    },
    "هيئة التقاعد الوطنية": {
        "TELEGRAM": "pension_iraq", # قناة التقاعد الرسمية
        "DISPLAY": "المتقاعدين",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "المتقاعدين", "التقاعد", "المتقاعد", "معين"],
        "PRIORITY": 1
    },
    "وزارة العمل - الرعاية": {
        "TELEGRAM": "molsa_iq", # قناة وزارة العمل
        "DISPLAY": "الرعاية الاجتماعية",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الرعاية", "الحماية", "الاجتماعية", "المعين", "المتفرغ"],
        "PRIORITY": 1
    },
    "هيئة الحشد الشعبي": {
        "TELEGRAM": "teamsmediawar", # اعلام الحشد
        "DISPLAY": "الحشد الشعبي",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "الحشد", "الشعبي", "منتسبي"],
        "PRIORITY": 1
    },
    "هيئة النزاهة": {
        "TELEGRAM": "NazahaIq",
        "DISPLAY": "هيئة النزاهة",
        "KEYWORDS": ["رواتب", "الرواتب", "صرف", "النزاهة", "منتسبي"],
        "PRIORITY": 1
    },
    "وكالة الانباء العراقية": {
        "URL": "https://ina.iq/",
        "DISPLAY": "الوزارات العراقية",
        "KEYWORDS": ["رواتب", "الرواتب", "اطلاق", "صرف", "المالية", "الوزارات", "المتقاعدين", "الرعاية"],
        "PRIORITY": 2
    }
}

NEGATIVE_CONTEXT = ["لا يوجد", "عدم", "تأجيل", "ايقاف", "الغاء", "نفي", "اشاعة", "كاذب", "غير صحيح", "لم يتم"]
BANKS = ["الرافدين", "الرشيد", "الاهلي", "TBI", "الصناعي", "الزراعي", "مصرف الرافدين", "مصرف الرشيد"]

async def is_subscribed(user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"خطأ فحص الاشتراك للعضو {user_id}: {e}")
        return True

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data.get("آخر عملية بيع", 0) == 0: data["آخر عملية بيع"] = 1550
            if data.get("آخر عملية شراء", 0) == 0: data["آخر عملية شراء"] = 1310
            if "مصادر" not in data: data["مصادر"] = {}
            if "users" not in data: data["users"] = []
            if "اخبار_منشورة" not in data: data["اخبار_منشورة"] = []
            for name in SALARY_SOURCES:
                if name not in data["مصادر"]:
                    data["مصادر"][name] = {"enabled": True, "keywords": SALARY_SOURCES[name]["KEYWORDS"]}
            return data
    except:
        config = {
            "آخر_الأخبار": [], "اخبار_منشورة": [], "is_running": True, "الوضع الصامت": False,
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

def is_real_news(text, keyword):
    keyword_pos = text.find(keyword)
    if keyword_pos == -1: return False
    context = text[max(0, keyword_pos-100):keyword_pos+100]
    for neg in NEGATIVE_CONTEXT:
        if neg in context:
            return False
    return True

def extract_bank(text):
    text = text.lower()
    if "رافدين" in text or "rafidain" in text:
        return "مصرف الرافدين"
    if "رشيد" in text or "rasheed" in text:
        return "مصرف الرشيد"
    if "الاهلي" in text or "اهلي" in text:
        return "المصرف الاهلي"
    if "tbi" in text:
        return "مصرف TBI"
    return ""

async def fetch_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3'
    }
    try:
        r = await client.get(url, headers=headers, follow_redirects=True, timeout=20.0)
        return r.status_code, r.text
    except Exception as e:
        logger.error(f"خطأ جلب {url}: {e}")
        return 0, str(e)

async def check_telegram_channel(channel_username, keywords, display_name):
    try:
        url = f"https://t.me/s/{channel_username}"
        status, html = await fetch_url(url)
        if status!= 200:
            logger.error(f"فشل قراءة قناة {channel_username}: {status}")
            return False, "", ""

        messages = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        for msg_html in messages[-10:]:
            text = re.sub(r'<br/?>', '\n', msg_html)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()

            for keyword in keywords:
                if keyword in text and is_real_news(text, keyword):
                    bank = extract_bank(text)
                    return True, text[:300], bank
        return False, "", ""
    except Exception as e:
        logger.error(f"خطأ قراءة قناة {channel_username}: {e}")
        return False, "", ""

async def check_single_source(name, source, config, silent=True):
    if not config["مصادر"].get(name, {}).get("enabled", True):
        return f"⚪ {name}: معطل"

    keywords = config["مصادر"][name].get("keywords", source["KEYWORDS"])
    display_name = source.get("DISPLAY", name)
    priority = source.get("PRIORITY", 1)
    found = False
    news_text = ""
    bank_name = ""

    if "TELEGRAM" in source:
        found, news_text, bank_name = await check_telegram_channel(source["TELEGRAM"], keywords, display_name)
        if not found:
            return f"🔵 {name}: لا يوجد جديد بالقناة"

    elif "URL" in source:
        status, text = await fetch_url(source["URL"])
        if status!= 200:
            return f"🔴 {name}: خطأ {status}"

        for keyword in keywords:
            if keyword in text and is_real_news(text, keyword):
                found = True
                news_text = text
                bank_name = extract_bank(text)
                break
        if not found:
            return f"🔵 {name}: لا يوجد جديد"

    if found:
        today = datetime.now().strftime("%Y-%m-%d-%H")
        news_hash = hashlib.md5(f"{name}_{today}_{bank_name}".encode()).hexdigest()

        if priority == 2:
            for h in config.get("اخبار_منشورة", []):
                if today in h and "وزارة" in h:
                    logger.info(f"تخطي الخبر العام لان اكو خبر خاص منشور")
                    return f"🟡 {name}: تم تخطيه لان اكو خبر خاص"

        if news_hash not in config.get("اخبار_منشورة", []):
            if not silent:
                title = f"🔴 عاجل | رواتب {display_name}"
                if bank_name:
                    title += f" - {bank_name}"

                msg = f"""{title}

تم رصد خبر صرف رواتب {display_name}{f' - {bank_name}' if bank_name else ''} من مصادر موثوقة.

تابع الجديد على {CHANNEL_USERNAME}"""
                try:
                    if config["الوضع الصامت"]:
                        await bot.send_message(chat_id=CHANNEL_ID, text=msg, disable_web_page_preview=True, disable_notification=True)
                    else:
                        sent = await bot.send_message(chat_id=CHANNEL_ID, text=msg, disable_web_page_preview=True)
                        config["last_salary_msg_id"] = sent.message_id
                    logger.info(f"تم نشر خبر {name} - {bank_name}")
                except Exception as e:
                    logger.error(f"فشل نشر خبر {name}: {e}")

                if "اخبار_منشورة" not in config:
                    config["اخبار_منشورة"] = []
                config["اخبار_منشورة"].append(news_hash)
                if len(config["اخبار_منشورة"]) > 200:
                    config["اخبار_منشورة"] = config["اخبار_منشورة"][-200:]
                save_config(config)
            return f"🟢 {name}: تم العثور على خبر {bank_name}"
        else:
            return f"🟡 {name}: خبر مكرر"
    return f"🔵 {name}: لا يوجد جديد"

async def check_salaries(silent=True):
    config = load_config()
    if not config["is_running"] and silent: return []
    results = []
    sorted_sources = sorted(SALARY_SOURCES.items(), key=lambda x: x[1].get("PRIORITY", 1))
    for name, source in sorted_sources:
        result = await check_single_source(name, source, config, silent)
        results.append(result)
        await asyncio.sleep(2)
    return results

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
    except Exception as e:
        logger.error(f"خطأ الدولار: {e}")
    return False

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

def get_admin_panel(config):
    enabled_count = sum(1 for s in config["مصادر"].values() if s.get("enabled", True))
    status_run = "شغال" if config['is_running'] else "متوقف"
    status_silent = "مفعل" if config['الوضع الصامت'] else "معطل"
    status_dollar = "مفعل" if config['dollar_enabled'] else "معطل"
    pin_status = "مثبت" if config['dollar_msg_id'] else "غير مثبت"
    status_text = f"⚙️ لوحة تحكم @w3vv\n\n📊 الحالة: {status_run} | الصامت: {status_silent} 🔔\n💵 الدولار: {status_dollar} | {pin_status} ❌\n🏦 شراء: {config['آخر عملية شراء']:,} | بيع: {config['آخر عملية بيع']:,}\n📡 مصادر الرواتب: {enabled_count} مفعلة\n\nCHANNEL_ID: {CHANNEL_ID}"
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
    logger.info(f"وصلت رسالة من {user_id}: {update.message.text}")

    if user_id not in config["users"]:
        config["users"].append(user_id)
        save_config(config)

    if update.message.text == "/start":
        try:
            logger.info(f"تنفيذ /start للعضو {user_id}")

            if not await is_subscribed(user_id):
                keyboard = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")]]
                await bot.send_message(
                    chat_id=update.message.chat.id,
                    text="⚠️ لازم تشترك بالقناة اولاً علمود تستخدم البوت",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            keyboard = [
                [InlineKeyboardButton("👨‍💻 المطور", callback_data="dev_info_user")],
                [InlineKeyboardButton("💵 سعر صرف الدولار", callback_data="sarf_user")]
            ]
            if user_id == ADMIN_ID:
                keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])

            await bot.send_message(
                chat_id=update.message.chat.id,
                text="👋 اهلاً بك في بوت رواتب العراق\n\nاختر من الازرار:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"تم ارسال رد /start للعضو {user_id}")
        except Exception as e:
            logger.error(f"خطأ في /start: {e}")
            await bot.send_message(chat_id=update.message.chat.id, text="❌ صار خطأ، جرب مرة ثانية")
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
    user_id = query.from_user.id
    await query.answer()

    if data == "dev_info_user":
        caption = f"👨‍💻 {DEV_NAME}\n\n📢 القناة: {CHANNEL_USERNAME}\n💬 للتواصل: {DEV_USERNAME}"
        try:
            photos = await bot.get_user_profile_photos(user_id=ADMIN_ID, limit=1)
            if photos.total_count > 0:
                photo = photos.photos[0][-1].file_id
                await bot.send_photo(chat_id=user_id, photo=photo, caption=caption)
            else:
                await bot.send_message(chat_id=user_id, text=caption)
        except:
            await bot.send_message(chat_id=user_id, text=caption)
        return
    elif data == "sarf_user":
        await bot.send_message(chat_id=user_id, text=get_dollar_message())
        return
    elif data == "admin_panel":
        if user_id!= ADMIN_ID:
            await query.answer("غير مصرح لك")
            return
        config = load_config()
        status_text, keyboard = get_admin_panel(config)
        await bot.send_message(chat_id=ADMIN_ID, text=status_text, reply_markup=keyboard)
        return

    if user_id!= ADMIN_ID:
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
        await bot.send_message(chat_id=ADMIN_ID, text=f"👨‍💻 مطور البوت: {DEV_USERNAME}\n⚙️ اصدار: V7 Pro")
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

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    offset = 0
    last_salary_check = 0
    last_dollar_check = 0
    logger.info("✅ البوت شغال - V7 Pro التقاعد + الرعاية")
    logger.info(f"CHANNEL_ID: {CHANNEL_ID}")

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
            logger.error(f"خطأ رئيسي: {e}")
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
