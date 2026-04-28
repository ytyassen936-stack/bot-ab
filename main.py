import os
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram.request import HTTPXRequest
from datetime import datetime
import asyncio
import nest_asyncio
import urllib3
import warnings
import json
import traceback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")
nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [int(os.getenv("ADMIN_ID"))]
CHECK_INTERVAL = 600
DOLLAR_INTERVAL = 3600
BROADCAST = range(1)

request = HTTPXRequest(connection_pool_size=8, read_timeout=60, write_timeout=60, connect_timeout=60)
bot = Bot(token=TOKEN, request=request)
CONFIG_FILE = 'bot_config.json'

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"last_news": [], "is_running": True, "silent_mode": False, "dollar_enabled": True, "last_buy": 1310, "last_sell": 0, "last_buy_date": "", "last_sell_date": "", "dollar_msg_id": None, "last_salary_msg_id": None, "admin_ids": ADMIN_IDS, "sources": {"الرعاية والمتقاعدين": {"url": "https://molsa.gov.iq/", "keywords": ["اطلاق", "صرف", "رواتب", "الرعاية", "المتقاعدين"], "enabled": True}, "المعين المتفرغ": {"url": "https://molsa.gov.iq/", "keywords": ["المعين", "المتفرغ", "ذوي الاعاقة"], "enabled": True}, "الموظفين": {"url": "https://mof.gov.iq/", "keywords": ["تمويل", "رواتب", "الموظفين"], "enabled": True}}}

def save_config():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

# ======== دالة ارسال الخطأ للادمن ========
async def send_error_to_admin(error_text):
    for admin_id in config["admin_ids"]:
        try:
            await bot.send_message(admin_id, f"❌ **صار خطأ بالبوت:**\n\n<code>{error_text[:3000]}</code>", parse_mode='HTML')
        except: pass

# ======== دالة جلب الاخبار ========
async def get_latest_news():
    try:
        url = "https://www.alsumaria.tv/news"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        news_list = []
        for item in soup.select('.media-news-item')[:5]:
            title = item.select_one('h3').text.strip()
            link = item.select_one('a')['href']
            if not link.startswith('http'):
                link = "https://www.alsumaria.tv" + link
            news_list.append(f"• [{title}]({link})")
        return "\n\n".join(news_list) if news_list else "ما لكيت اخبار حاليا"
    except Exception as e:
        await send_error_to_admin(f"get_latest_news:\n{traceback.format_exc()}")
        return f"❌ صار خطأ: {str(e)[:100]}"

def get_dollar_prices():
    buy_price = 1310
    sell_prices = []
    try:
        res = requests.get("https://www.iraqidinarchat.com/", timeout=15, verify=False)
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        for line in text.split('\n'):
            if ("بغداد" in line or "الكفاح" in line or "بيع" in line) and any(c.isdigit() for c in line):
                nums = [int(s) for s in line.split() if s.isdigit() and len(s) >= 4]
                for num in nums:
                    if 1450 <= num <= 1600: sell_prices.append(num)
                    elif 145000 <= num <= 160000: sell_prices.append(num // 100)
    except: pass
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=15)
        data = res.json()
        if 'rates' in data and 'IQD' in data['rates']:
            market = int(data['rates']['IQD'])
            if 1400 <= market <= 1600: sell_prices.append(market)
    except: pass
    sell_price = int(sum(sell_prices) / len(sell_prices)) if sell_prices else config.get("last_sell", 1550)
    return {"buy": buy_price, "sell": sell_price}

def make_dollar_post(prices):
    now = datetime.now()
    date_now = now.strftime("%Y/%m/%d - %H:%M")
    buy = prices["buy"]
    sell = prices["sell"]
    old_buy = config.get("last_buy", 1310)
    old_sell = config.get("last_sell", 0)
    if old_buy!= buy: config["last_buy_date"] = date_now
    if old_sell!= sell and old_sell!= 0: config["last_sell_date"] = date_now
    if old_buy == buy: change_buy = "➡️ استقرار"
    else: change_buy = f"📈 صعود {buy - old_buy}" if buy > old_buy else f"📉 نزول {old_buy - buy}"
    if old_sell == 0: change_sell, change_paper = "", ""
    elif sell > old_sell:
        diff = sell - old_sell
        change_sell = f"📈 صعود {diff} دينار"
        change_paper = f"📈 صعود {diff * 100:,} دينار"
    elif sell < old_sell:
        diff = old_sell - sell
        change_sell = f"📉 نزول {diff} دينار"
        change_paper = f"📉 نزول {diff * 100:,} دينار"
    else: change_sell, change_paper = "➡️ استقرار", "➡️ استقرار"
    config["last_buy"] = buy
    config["last_sell"] = sell
    save_config()
    paper_buy = buy * 100
    paper_sell = sell * 100
    buy_date = config.get("last_buy_date", date_now)
    sell_date = config.get("last_sell_date", date_now)
    return f"\n📌 **مثبت - اسعار صرف الدولار** 📌\n\n🏦 **البنك المركزي - الشراء**\n🔸 الدولار: **{buy:,} دينار**\n🔸 الورقة: **{paper_buy:,} دينار**\n{change_buy}\n📅 اخر تغيير: {buy_date}\n\n🏪 **السوق - البيع**\n🔸 الدولار: **{sell:,} دينار**\n🔸 الورقة: **{paper_sell:,} دينار**\n{change_sell}\n{change_paper}\n📅 اخر تغيير: {sell_date}\n\n🕐 وقت النشر: {date_now}\n📍 بورصة الكفاح والحارثية\n\n⚠️ اسعار السوق تقريبية وتختلف بين الصيرفات\n🔔 تابعنا @w_3_vv\n\n#الدولار #سعر_الصرف #العراق #الورقة #البنك_المركزي\n"

async def pin_dollar_message(message_id):
    try:
        if config.get("dollar_msg_id"):
            try: await bot.unpin_chat_message(CHANNEL_ID, config["dollar_msg_id"])
            except: pass
        await bot.pin_chat_message(CHANNEL_ID, message_id, disable_notification=True)
        config["dollar_msg_id"] = message_id
        save_config()
    except Exception as e:
        await send_error_to_admin(f"pin_dollar_message:\n{traceback.format_exc()}")

def make_klesha(no3, title, link):
    date = datetime.now().strftime("%Y/%m/%d - %H:%M")
    return f"\n🚨 #عاجل_الان | #تم_الصرف ✅\n\n💰 رواتب {no3} 💰\n\n📌 الخبر: {title}\n📅 وقت الرصد: {date}\n🏦 الصرف: البطاقة الذكية + منافذ الصرف\n\n⚡️ راجع اقرب منفذ لاستلام مستحقاتك\n🔔 تابعنا @w_3_vv لكل جديد\n\n#رواتب_العراق #تم_الاطلاق #{no3.replace(' ', '_')}\n"

async def check_dollar():
    while True:
        if config["dollar_enabled"] and not config["silent_mode"]:
            try:
                prices = get_dollar_prices()
                if prices["sell"]!= config.get("last_sell", 0):
                    post = make_dollar_post(prices)
                    msg = await bot.send_message(CHANNEL_ID, post, parse_mode='Markdown')
                    await pin_dollar_message(msg.message_id) # ← يثبت تلقائي ويلغي القديم
            except Exception as e:
                await send_error_to_admin(f"check_dollar:\n{traceback.format_exc()}")
        await asyncio.sleep(DOLLAR_INTERVAL)

async def check_salaries():
    while True:
        if not config["is_running"]:
            await asyncio.sleep(10)
            continue
        for no3, data in config["sources"].items():
            if not data["enabled"]: continue
            try:
                res = requests.get(data["url"], timeout=30, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
                soup = BeautifulSoup(res.text, 'html.parser')
                news_items = soup.find_all(['h1', 'h2', 'h3', 'a', 'p'], limit=30)
                for item in news_items:
                    text = item.get_text(strip=True)
                    link = item.get('href') or data["url"]
                    if "رواتب" in text and any(kw in text for kw in data["keywords"]):
                        news_id = f"{no3}-{text[:60]}"
                        if news_id not in config["last_news"] and len(text) > 25:
                            config["last_news"].append(news_id)
                            if len(config["last_news"]) > 50: config["last_news"].pop(0)
                            save_config()
                            if link.startswith('/'): link = data["url"].rstrip('/') + link
                            if not link.startswith('http'): link = data["url"]
                            if not config["silent_mode"]:
                                klesha = make_klesha(no3, text, link)
                                keyboard = [[InlineKeyboardButton("📄 المصدر الرسمي", url=link)]]
                                msg = await bot.send_message(CHANNEL_ID, klesha, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
                                config["last_salary_msg_id"] = msg.message_id # ← نحفظ ايدي آخر منشور
                                save_config()
                            await asyncio.sleep(5)
            except Exception as e:
                await send_error_to_admin(f"check_salaries:\n{traceback.format_exc()}")
        await asyncio.sleep(CHECK_INTERVAL)

async def check_user_joined(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

async def sarf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_joined = await check_user_joined(user_id)
    if not is_joined:
        keyboard = [[InlineKeyboardButton("📢 اشترك بالقناة", url="https://t.me/w_3_vv")]]
        await update.message.reply_text("❌ **لازم تشترك بالقناة اولاً**\n\nاشترك @w_3_vv وبعدها اكتب /sarf مرة ثانية", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    prices = get_dollar_prices()
    buy, sell = prices["buy"], prices["sell"]
    text = f"\n💵 **اسعار صرف الدولار الحالية** 💵\n\n🏦 **البنك المركزي - الشراء**\n🔸 الدولار: **{buy:,} دينار**\n🔸 الورقة: **{buy * 100:,} دينار**\n\n🏪 **السوق - البيع**\n🔸 الدولار: **{sell:,} دينار**\n🔸 الورقة: **{sell * 100:,} دينار**\n\n🕐 الان: {datetime.now().strftime('%Y/%m/%d - %H:%M')}\nتابع قناتنا @w_3_vv لكل جديد\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in config["admin_ids"]:
        await update.message.reply_text("❌ انت مو ادمن")
        return
    status = "🟢 شغال" if config["is_running"] else "🔴 متوقف"
    silent = "🔕 مفعل" if config["silent_mode"] else "🔔 معطل"
    dollar = "💵 مفعل" if config["dollar_enabled"] else "💵 معطل"
    pinned = "📌 مثبت" if config.get("dollar_msg_id") else "❌ غير مثبت"
    text = f"\n⚙️ **لوحة تحكم @w_3_vv**\n\n📊 الحالة: {status} | الصامت: {silent}\n💵 الدولار: {dollar} | {pinned}\n🏦 شراء: {config.get('last_buy', 1310):,} | 🏪 بيع: {config.get('last_sell', 0):,}\n"
    keyboard = [
        [InlineKeyboardButton("👨‍💻 معلومات المطور", callback_data="dev_info")],
        [InlineKeyboardButton("💵 اسعار الدولار", callback_data="get_dollar")],
        [InlineKeyboardButton("📰 جلب الاخبار", callback_data="get_news")],
        [InlineKeyboardButton("🗑️ حذف آخر منشور", callback_data="del_last_post")], # ← جديد
        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="backup")], # ← جديد
        [InlineKeyboardButton("📢 اذاعة", callback_data="broadcast"), InlineKeyboardButton("▶️⏸️ تشغيل/ايقاف", callback_data="toggle")],
        [InlineKeyboardButton("🔕 صامت", callback_data="silent"), InlineKeyboardButton("💵 دولار تلقائي", callback_data="toggle_dollar")],
        [InlineKeyboardButton("📌 الغاء تثبيت الدولار", callback_data="unpin_dollar")],
        [InlineKeyboardButton("🔄 فحص يدوي", callback_data="manual_check"), InlineKeyboardButton("🔄 تحديث", callback_data="refresh")]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in config["admin_ids"]:
        await query.answer("❌ انت مو ادمن", show_alert=True)
        return
    await query.answer()
    data = query.data
    if data == "dev_info":
        user = query.from_user
        name = user.full_name
        username = f"@{user.username}" if user.username else "ماكو"
        user_id = user.id
        bio = "ماكو بايو"
        try:
            chat = await bot.get_chat(user_id)
            if chat.bio: bio = chat.bio
        except: pass
        text = f"\n👨‍💻 **معلومات المطور**\n\n👤 **الاسم:** {name}\n🔗 **اليوزر:** {username}\n🆔 **الايدي:** `{user_id}`\n📝 **البايو:** {bio}\n📅 **تاريخ الانشاء:** {datetime.now().strftime('%Y/%m/%d')}\n"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="refresh")]]
        try:
            photos = await bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                await query.message.reply_photo(photos.photos[0][-1].file_id, caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                await query.delete_message()
            else:
                await query.edit_message_text(text + "\n\n❌ ماكو صورة بروفايل", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif data == "del_last_post": # ← جديد
        if config.get("last_salary_msg_id"):
            try:
                await bot.delete_message(CHANNEL_ID, config["last_salary_msg_id"])
                config["last_salary_msg_id"] = None
                save_config()
                await query.edit_message_text("✅ تم حذف آخر منشور رواتب\n\n/admin")
            except:
                await query.edit_message_text("❌ فشل الحذف - يمكن المنشور محذوف اصلا\n\n/admin")
        else:
            await query.edit_message_text("❌ ماكو منشور محفوظ\n\n/admin")
    elif data == "backup": # ← جديد
        try:
            await bot.send_document(user_id, document=open(CONFIG_FILE, 'rb'), caption=f"💾 نسخة احتياطية\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            await query.edit_message_text("✅ دزيتلك النسخة الاحتياطية عالخاص\n\n/admin")
        except:
            await query.edit_message_text("❌ فشل - لازم تراسل البوت /start اول\n\n/admin")
    elif data == "toggle":
        config["is_running"] = not config["is_running"]
        save_config()
        await admin_panel(update, context)
    elif data == "silent":
        config["silent_mode"] = not config["silent_mode"]
        save_config()
        await admin_panel(update, context)
    elif data == "toggle_dollar":
        config["dollar_enabled"] = not config["dollar_enabled"]
        save_config()
        await admin_panel(update, context)
    elif data == "unpin_dollar":
        if config.get("dollar_msg_id"):
            try:
                await bot.unpin_chat_message(CHANNEL_ID, config["dollar_msg_id"])
                config["dollar_msg_id"] = None
                save_config()
                await query.edit_message_text("✅ تم الغاء التثبيت\n\n/admin")
            except: await query.edit_message_text("❌ فشل\n\n/admin")
        else: await query.edit_message_text("❌ لا توجد رسالة مثبتة\n\n/admin")
    elif data == "get_dollar":
        await query.edit_message_text("⏳ جاري جلب الاسعار...")
        prices = get_dollar_prices()
        post = make_dollar_post(prices)
        keyboard = [[InlineKeyboardButton("✅ نشر وتثبيت", callback_data=f"post_dollar")], [InlineKeyboardButton("🔙 رجوع", callback_data="refresh")]]
        await query.edit_message_text(f"💵 **الاسعار**\n\n🏦 **شراء**: {prices['buy']:,}\n🏪 **بيع**: {prices['sell']:,}\n\n{post}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif data == "post_dollar":
        prices = get_dollar_prices()
        post = make_dollar_post(prices)
        msg = await bot.send_message(CHANNEL_ID, post, parse_mode='Markdown')
        await pin_dollar_message(msg.message_id)
        await query.edit_message_text(f"✅ تم النشر والتثبيت\n\n/admin")
    elif data == "get_news":
        await query.edit_message_text("⏳ جاري جلب الاخبار...")
        news = await get_latest_news()
        try:
            await bot.send_message(user_id, f"📰 **آخر الاخبار**\n\n{news}", parse_mode='Markdown', disable_web_page_preview=True)
            await query.edit_message_text("✅ دزيتلك الاخبار عالخاص\n\n/admin")
        except:
            await query.edit_message_text("❌ لازم تراسل البوت /start اول شي\n\n/admin")
    elif data == "manual_check":
        await query.edit_message_text("⏳ جاري الفحص...")
        await manual_check_once()
        await query.edit_message_text("✅ تم\n\n/admin")
    elif data == "refresh":
        await admin_panel(update, context)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 **ارسل الرسالة للاذاعة**\n\n/cancel للالغاء")
    return BROADCAST

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.text: await bot.send_message(CHANNEL_ID, update.message.text_html, parse_mode='HTML')
        elif update.message.photo: await bot.send_photo(CHANNEL_ID, update.message.photo[-1].file_id, caption=update.message.caption_html, parse_mode='HTML')
        await update.message.reply_text("✅ تم\n\n/admin")
    except Exception as e:
        await send_error_to_admin(f"broadcast_send:\n{traceback.format_exc()}")
        await update.message.reply_text(f"❌ {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الالغاء\n\n/admin")
    return ConversationHandler.END

async def manual_check_once():
    for no3, data in config["sources"].items():
        if not data["enabled"]: continue
        try:
            res = requests.get(data["url"], timeout=30, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
            soup = BeautifulSoup(res.text, 'html.parser')
            news_items = soup.find_all(['h1', 'h2', 'h3', 'a', 'p'], limit=30)
            for item in news_items:
                text = item.get_text(strip=True)
                link = item.get('href') or data["url"]
                if "رواتب" in text and any(kw in text for kw in data["keywords"]):
                    news_id = f"{no3}-{text[:60]}"
                    if news_id not in config["last_news"] and len(text) > 25:
                        config["last_news"].append(news_id)
                        save_config()
                        if not config["silent_mode"]:
                            if link.startswith('/'): link = data["url"].rstrip('/') + link
                            if not link.startswith('http'): link = data["url"]
                            klesha = make_klesha(no3, text, link)
                            keyboard = [[InlineKeyboardButton("📄 المصدر الرسمي", url=link)]]
                            msg = await bot.send_message(CHANNEL_ID, klesha, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
                            config["last_salary_msg_id"] = msg.message_id # ← نحفظ ايدي آخر منشور
                            save_config()
                        await asyncio.sleep(3)
        except Exception as e:
            await send_error_to_admin(f"manual_check_once:\n{traceback.format_exc()}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in config["admin_ids"]:
        await update.message.reply_text("اهلاً ادمن ❤️\n/admin\n/sarf")
    else:
        await update.message.reply_text("هلا بيك ❤️\n\nاكتب /sarf لمعرفة سعر الدولار\nتابع قناتنا @w_3_vv")

async def post_init(application):
    asyncio.create_task(check_salaries())
    asyncio.create_task(check_dollar())

def main():
    app = ApplicationBuilder().token(TOKEN).request(request).post_init(post_init).build()
    conv_handler = ConversationHandler(entry_points=[CallbackQueryHandler(broadcast_start, pattern="^broadcast$")], states={BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)]}, fallbacks=[CommandHandler("cancel", cancel)], per_message=False, per_chat=True, per_user=True)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sarf", sarf_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    print("بوت قناة @w_3_vv اشتغل...")
    app.run_polling(stop_signals=None, read_timeout=60, write_timeout=60, connect_timeout=60)

if __name__ == '__main__':
    main()
