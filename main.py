import os
import json
import logging
import asyncio
import requests
from datetime import datetime
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import socket
import sys

# ======== منع تشغيل نسختين ========
def check_single_instance():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('localhost', 47200))
        return s
    except:
        print("البوت شغال بنسخة ثانية!")
        sys.exit(1)

lock_socket = check_single_instance()

# ======== الاعدادات الاساسية ========
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
CHANNEL_ID = os.getenv('CHANNEL_ID')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
app_flask = Flask(__name__)

# ======== تسجيل الاخطاء ========
async def send_error_to_admin(error):
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ **خطأ بالبوت**\n\n{str(error)[:500]}\n\nالوقت: {datetime.now().strftime('%H:%M:%S')}")
    except:
        pass

# ======== تحميل الاعدادات ========
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "silent_mode": False,
            "dollar_enabled": True,
            "news_enabled": True,
            "last_news": [],
            "last_dollar_msg": 0
        }

def save_config():
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

# ======== جلب الاخبار ========
async def get_news():
    try:
        url = "https://www.alsumaria.tv/news"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
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
        await send_error_to_admin(f"خطأ جلب الاخبار: {e}")
        return "❌ صار خطأ بجلب الاخبار"

# ======== سعر الدولار ========
def sarf_dolar():
    try:
        r = requests.get("https://api.albankaldawli.org/rate", timeout=10)
        data = r.json()
        return int(data['usd_iqd'])
    except Exception as e:
        logger.error(f"Dollar error: {e}")
        return 0

# ======== الاوامر ========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    await update.message.reply_text("🟢 البوت شغال\n\n/admin - لوحة التحكم\n/help - المساعدة")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    msg = """🔧 **اوامر البوت:**

/start - تشغيل البوت
/admin - لوحة التحكم
/status - حالة البوت
/help - هاي الرسالة
/sarf - سعر الدولار الحالي

📢 القناة: {}
🔔 المطور: @w_3_vv""".format(CHANNEL_ID)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    uptime = datetime.now() - datetime.fromtimestamp(os.path.getctime(__file__))
    msg = f"""📊 **حالة البوت**

🟢 شغال منذ: {str(uptime).split('.')[0]}
📢 القناة: {CHANNEL_ID}
🔕 الصامت: {'مفعل' if config['silent_mode'] else 'معطل'}
💵 الدولار: {'مفعل' if config['dollar_enabled'] else 'معطل'}
📰 الاخبار: {'مفعل' if config['news_enabled'] else 'معطل'}
📨 اخبار محفوظة: {len(config['last_news'])}

✅ كلشي تمام"""
    await update.message.reply_text(msg, parse_mode='Markdown')

async def sarf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    price = sarf_dolar()
    await update.message.reply_text(f"💵 سعر الدولار: {price} دينار")

# ======== لوحة الادمن ========
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton(f"{'🔕' if config['silent_mode'] else '🔔'} الوضع الصامت", callback_data="toggle_silent")],
        [InlineKeyboardButton(f"{'💵' if config['dollar_enabled'] else '❌'} الدولار", callback_data="toggle_dollar")],
        [InlineKeyboardButton(f"{'📰' if config['news_enabled'] else '❌'} الاخبار", callback_data="toggle_news")],
        [InlineKeyboardButton("📰 جلب الاخبار", callback_data="get_news")],
        [InlineKeyboardButton("🗑️ مسح كل التثبيتات", callback_data="clear_pins")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔧 **لوحة التحكم**", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if update.effective_user.id!= ADMIN_ID: return

    if data == "toggle_silent":
        config['silent_mode'] = not config['silent_mode']
        save_config()
        await query.edit_message_text(f"✅ الوضع الصامت: {'مفعل' if config['silent_mode'] else 'معطل'}\n\n/admin")

    elif data == "toggle_dollar":
        config['dollar_enabled'] = not config['dollar_enabled']
        save_config()
        await query.edit_message_text(f"✅ الدولار: {'مفعل' if config['dollar_enabled'] else 'معطل'}\n\n/admin")

    elif data == "toggle_news":
        config['news_enabled'] = not config['news_enabled']
        save_config()
        await query.edit_message_text(f"✅ الاخبار: {'مفعل' if config['news_enabled'] else 'معطل'}\n\n/admin")

    elif data == "get_news":
        await query.edit_message_text("⏳ جاري جلب الاخبار...")
        news = await get_news()
        try:
            await bot.send_message(update.effective_user.id, f"📰 **آخر الاخبار**\n\n{news}", parse_mode='Markdown', disable_web_page_preview=True)
            await query.edit_message_text("✅ دزيتلك الاخبار عالخاص\n\n/admin")
        except:
            await query.edit_message_text("❌ لازم تراسل البوت /start اول شي\n\n/admin")

    elif data == "clear_pins":
        try:
            await bot.unpin_all_chat_messages(CHANNEL_ID)
            await query.edit_message_text("✅ تم مسح كل التثبيتات\n\n/admin")
        except Exception as e:
            await send_error_to_admin(f"فشل مسح التثبيتات: {e}")
            await query.edit_message_text("❌ فشل المسح - تأكد ان البوت ادمن\n\n/admin")

# ======== حلقة الدولار ========
async def check_dollar_loop():
    last_price = 0
    while True:
        try:
            if config["dollar_enabled"] and not config["silent_mode"]:
                price = sarf_dolar()
                if price > 0 and price!= last_price:
                    last_price = price
                    try:
                        await bot.unpin_all_chat_messages(CHANNEL_ID)
                    except: pass

                    msg = f"""💵 **سعر صرف الدولار**

السعر: {price} دينار عراقي
الوقت: {datetime.now().strftime('%Y/%m/%d - %H:%M')}

📊 المصدر: البنك المركزي + السوق المحلي
🔔 @w_3_vv"""
                    sent = await bot.send_message(CHANNEL_ID, msg, parse_mode='Markdown')
                    await bot.pin_chat_message(CHANNEL_ID, sent.message_id, disable_notification=True)
                    config["last_dollar_msg"] = sent.message_id
                    save_config()
        except Exception as e:
            logger.error(f"Dollar error: {e}")
            await send_error_to_admin(f"خطأ حلقة الدولار: {e}")
        await asyncio.sleep(3600)

# ======== Flask للـ Render ========
@app_flask.route('/')
def home():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app_flask.run(host='0.0.0.0', port=port)

# ======== التشغيل الرئيسي + اعادة التشغيل ========
def main():
    while True:
        try:
            app = Application.builder().token(TOKEN).build()

            app.add_handler(CommandHandler("start", start_cmd))
            app.add_handler(CommandHandler("help", help_cmd))
            app.add_handler(CommandHandler("status", status_cmd))
            app.add_handler(CommandHandler("sarf", sarf_cmd))
            app.add_handler(CommandHandler("admin", admin_cmd))
            app.add_handler(CallbackQueryHandler(button_handler))

            loop = asyncio.get_event_loop()
            loop.create_task(check_dollar_loop())

            logger.info("Bot started")
            app.run_polling()

        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            try:
                asyncio.run(send_error_to_admin(f"البوت طاح واعاد التشغيل: {e}"))
            except: pass
            import time
            time.sleep(10)
            continue

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    main()
