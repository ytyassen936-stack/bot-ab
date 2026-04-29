import asyncio
import json
import os
import threading
import http.server
import socketserver
from datetime import datetime, timedelta
import random
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6848483725
DAILY_SALARY = 10000
DATA_FILE = 'data.json'
PORT = 10000

# --- إدارة البيانات ---
def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "deposits": {}, "used_codes": [], "codes": {}, "usd_rate": 1500.0}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- السيرفر الوهمي ---
def run_fake_server():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is running")
        def do_HEAD(self):
            self.send_response(200); self.end_headers()
    with socketserver.TCPServer(("", PORT), Handler) as httpd: httpd.serve_forever()

# --- لوحات المفاتيح ---
def get_main_menu(user_id):
    data = load_data()
    buttons = [
        [InlineKeyboardButton("💰 راتبي اليومي", callback_data='salary'), InlineKeyboardButton("💵 رصيدي", callback_data='balance')],
        [InlineKeyboardButton("👤 حسابي", callback_data='account'), InlineKeyboardButton("🏦 إيداع", callback_data='deposit_info')],
        [InlineKeyboardButton("🎁 إدخال كود", callback_data='enter_code'), InlineKeyboardButton("💸 تحويل", callback_data='transfer_start')],
        [InlineKeyboardButton("🆘 الدعم الفني", url='https://t.me/YOUR_SUPPORT_USERNAME')]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data='admin_panel')])
    return InlineKeyboardMarkup(buttons)

def get_back_button(callback_data='main_menu'):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=callback_data)]])

# --- الدوال المساعدة ---
def update_user_info(user: Update.effective_user):
    data = load_data()
    user_id = str(user.id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"name": user.full_name, "username": user.username, "balance": 0, "last_salary_claim": None, "total_earned": 0, "total_withdrawn": 0}
    else:
        data["users"][user_id]["name"] = user.full_name
        data["users"][user_id]["username"] = user.username
    save_data(data)

def format_balance(amount):
    return f"{amount:,.0f}"

async def send_main_menu(update_or_query, context: ContextTypes.DEFAULT_TYPE, text="**أهلاً بك في البوت، اختر أحد الخيارات:**"):
    user_id = update_or_query.effective_user.id
    if isinstance(update_or_query, Update) and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=get_main_menu(user_id), parse_mode='Markdown')
    elif isinstance(update_or_query, Update) and update_or_query.callback_query:
        try:
            await update_or_query.callback_query.edit_message_text(text, reply_markup=get_main_menu(user_id), parse_mode='Markdown')
        except: # If message is not different
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=get_main_menu(user_id), parse_mode='Markdown')

# --- أوامر البوت ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_info(update.effective_user)
    await send_main_menu(update, context, text="**✅ أهلاً بك! تم تشغيل البوت بنجاح.**\n\nاختر أحد الخيارات:")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID: return
    text = "👑 **لوحة تحكم المدير**"
    buttons = [
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='admin_users'), InlineKeyboardButton("💰 إدارة الأكواد", callback_data='admin_codes')],
        [InlineKeyboardButton("💵 إدارة الرصيد", callback_data='admin_balance'), InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')],
        [InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data='main_menu')]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')

# --- معالج الأزرار ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = str(user.id)
    data = load_data()
    update_user_info(user)

    if query.data == 'main_menu':
        await send_main_menu(update, context)

    elif query.data == 'balance':
        balance = data["users"][user_id]["balance"]
        text = f"**💵 رصيدك الحالي هو:**\n\n`{format_balance(balance)}` دينار عراقي"
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif query.data == 'account':
        user_data = data["users"][user_id]
        text = f"**👤 معلومات حسابك:**\n\n" \
               f"**الاسم:** {user_data['name']}\n" \
               f"**اليوزر:** @{user_data.get('username', 'لا يوجد')}\n" \
               f"**الرصيد:** `{format_balance(user_data['balance'])}` د.ع\n" \
               f"**إجمالي الأرباح:** `{format_balance(user_data['total_earned'])}` د.ع"
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif query.data == 'salary':
        now = datetime.now()
        last_claim_str = data["users"][user_id].get("last_salary_claim")
        if last_claim_str and (now - datetime.fromisoformat(last_claim_str)) < timedelta(days=1):
            next_claim_time = datetime.fromisoformat(last_claim_str) + timedelta(days=1)
            text = f"**❌ لقد استلمت راتبك اليوم.**\n\nيمكنك المطالبة مرة أخرى في:\n`{next_claim_time.strftime('%I:%M %p')}`"
        else:
            data["users"][user_id]["balance"] += DAILY_SALARY
            data["users"][user_id]["total_earned"] += DAILY_SALARY
            data["users"][user_id]["last_salary_claim"] = now.isoformat()
            save_data(data)
            text = f"**✅ تمت إضافة راتبك اليومي!**\n\n`+{format_balance(DAILY_SALARY)}` د.ع"
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif query.data == 'deposit_info':
        text = "**🏦 معلومات الإيداع**\n\n" \
               "لإيداع رصيد، يرجى تحويل المبلغ إلى أحد الأرقام التالية:\n" \
               "**زين كاش:** `07801234567`\n" \
               "**آسيا حوالة:** `07701234567`\n\n" \
               "بعد التحويل، أرسل صورة الوصل مع رقم العملية للدعم الفني."
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode='Markdown')

    elif query.data == 'enter_code':
        context.user_data['state'] = 'awaiting_code'
        await query.edit_message_text("**🎁 أرسل الكود الذي لديك الآن:**", reply_markup=get_back_button())

    elif query.data == 'transfer_start':
        context.user_data['state'] = 'awaiting_transfer_id'
        await query.edit_message_text("**💸 لتحويل الرصيد:**\n\nأرسل **ID** المستخدم الذي تريد التحويل له:", reply_markup=get_back_button())

    # --- Admin Panel ---
    elif query.data == 'admin_panel' and user.id == ADMIN_ID:
        await admin_command(update, context)

    elif query.data == 'admin_stats' and user.id == ADMIN_ID:
        total_users = len(data["users"])
        total_balance = sum(u["balance"] for u in data["users"].values())
        text = f"**📊 إحصائيات البوت:**\n\n" \
               f"**👥 إجمالي المستخدمين:** `{total_users}`\n" \
               f"**💰 إجمالي الأرصدة:** `{format_balance(total_balance)}` د.ع"
        await query.edit_message_text(text, reply_markup=get_back_button('admin_panel'), parse_mode='Markdown')

    elif query.data == 'admin_codes' and user.id == ADMIN_ID:
        text = "**💰 إدارة الأكواد**\n\nاختر إجراء:"
        buttons = [
            [InlineKeyboardButton("➕ إنشاء كود جديد", callback_data='admin_create_code')],
            [InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data='admin_panel')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    elif query.data == 'admin_create_code' and user.id == ADMIN_ID:
        context.user_data['state'] = 'awaiting_code_amount'
        await query.edit_message_text("**أرسل قيمة الكود الجديد:**\n\n(مثال: 5000)", reply_markup=get_back_button('admin_codes'))

# --- معالج الرسائل ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    state = context.user_data.get('state')
    data = load_data()

    if state == 'awaiting_code':
        context.user_data.pop('state', None)
        code = text.upper()
        if code in data["codes"] and code not in data["used_codes"]:
            amount = data["codes"][code]
            data["users"][user_id]["balance"] += amount
            data["users"][user_id]["total_earned"] += amount
            data["used_codes"].append(code)
            save_data(data)
            await update.message.reply_text(f"**✅ تم تفعيل الكود بنجاح!**\n\nتمت إضافة `{format_balance(amount)}` د.ع إلى رصيدك.")
        else:
            await update.message.reply_text("**❌ الكود غير صالح أو مستخدم من قبل.**")
        await send_main_menu(update, context)

    elif state == 'awaiting_code_amount' and user_id == str(ADMIN_ID):
        try:
            amount = int(text)
            new_code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
            data["codes"][new_code] = amount
            save_data(data)
            await update.message.reply_text(f"**✅ تم إنشاء الكود بنجاح:**\n\n`{new_code}`\n\n**القيمة:** `{format_balance(amount)}` د.ع")
        except ValueError:
            await update.message.reply_text("**❌ الرجاء إرسال رقم صحيح.**")
        context.user_data.pop('state', None)
        await admin_command(update, context)

    elif state == 'awaiting_transfer_id':
        if text.isdigit() and text in data["users"]:
            context.user_data['transfer_to_id'] = text
            context.user_data['state'] = 'awaiting_transfer_amount'
            to_user_name = data["users"][text]["name"]
            await update.message.reply_text(f"**✅ تم العثور على المستخدم:** {to_user_name}\n\nالآن أرسل المبلغ الذي تريد تحويله:")
        else:
            await update.message.reply_text("**❌ ID غير صالح أو المستخدم غير موجود. حاول مرة أخرى.**")
            context.user_data.pop('state', None)
            await send_main_menu(update, context)

    elif state == 'awaiting_transfer_amount':
        to_id = context.user_data['transfer_to_id']
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError
            if data["users"][user_id]["balance"] >= amount:
                data["users"][user_id]["balance"] -= amount
                data["users"][to_id]["balance"] += amount
                data["users"][to_id]["total_earned"] += amount
                save_data(data)
                to_user_name = data["users"][to_id]["name"]
                await update.message.reply_text(f"**✅ تم التحويل بنجاح!**\n\nتم تحويل `{format_balance(amount)}` د.ع إلى **{to_user_name}**.")
                # Notify recipient
                await context.bot.send_message(chat_id=int(to_id), text=f"**🎉 لقد استلمت حوالة!**\n\nمن: **{update.effective_user.full_name}**\nالمبلغ: `{format_balance(amount)}` د.ع")
            else:
                await update.message.reply_text("**❌ رصيدك لا يكفي لإتمام هذه العملية.**")
        except ValueError:
            await update.message.reply_text("**❌ المبلغ غير صالح. الرجاء إرسال رقم صحيح.**")
        context.user_data.pop('state', None)
        context.user_data.pop('transfer_to_id', None)
        await send_main_menu(update, context)
    else:
        await send_main_menu(update, context)

# --- الدالة الرئيسية ---
async def main():
    if not BOT_TOKEN:
        print("خطأ: لم يتم العثور على توكن البوت!")
        return

    print("✅ البوت شغال - V2 مصلح")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

        # Keep alive loop
        last_dollar_check = datetime.now()
        while True:
            now = datetime.now()
            if now - last_dollar_check > timedelta(hours=1):
                last_dollar_check = now
            await asyncio.sleep(5)

if __name__ == "__main__":
    # هذا السطر يحذف اي Webhook معلق قبل لا يشتغل البوت
    asyncio.run(Bot(BOT_TOKEN).delete_webhook(drop_pending_updates=True))

    threading.Thread(target=run_fake_server, daemon=True).start()
    asyncio.run(main())
