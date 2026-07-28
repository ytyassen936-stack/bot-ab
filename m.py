import asyncio
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# ---------------- CONFIGURATION ----------------
API_ID = 30673923  # ضع API_ID هنا
API_HASH = "2a32a980417aa537e2cb11cf1311eb82"  # ضع API_HASH هنا
BOT_TOKEN = "8292971150:AAHD75wBeGS_pUEUKE93PCSp9ZPy1L9TGTM"  # توكن البوت
MAIN_DEV_ID = 7493679412  # آيديك
MAIN_DEV_USERNAME = "XX7X6"  # يوزرك بدون @
MUST_JOIN_CHANNEL = "w_3_vv"  # معرف قناتك بدون @

# --- إعدادات البريد الإلكتروني (SMTP) ---
SENDER_EMAIL = "shdsbam@gmail.com"  # ايميلك الذي سيرسل منه البوت
SENDER_PASSWORD = "fgyujbho980"  # كلمة سر التطبيقات (App Password) من Google

bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_account = Client("user_session", api_id=API_ID, api_hash=API_HASH)

# ---------------- DATA STORE ----------------
devs_list = [MAIN_DEV_ID]
custom_buttons = []  # الأزرار الشفافة
spam_photos = []     # صور التلغيم
subscriptions = {}   # الاشتراكات
user_states = {}

# ---------------- HELPER FUNCTIONS ----------------
async def check_sub(client, user_id):
    try:
        member = await client.get_chat_member(f"@{MUST_JOIN_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def is_subscribed_user(user_id):
    if user_id in devs_list:
        return True
    expire_time = subscriptions.get(user_id, 0)
    return time.time() < expire_time

def build_main_keyboard(user_id):
    buttons = []
    # الأزرار المخصصة المضافة من المطور
    for btn in custom_buttons:
        buttons.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    
    # زر الشات التلقائي للإيميلات
    buttons.append([InlineKeyboardButton("📧 الشات التلقائي", callback_data="auto_chat_email")])
    
    # زر المطور الأساسي
    buttons.append([InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{MAIN_DEV_USERNAME}")])
    
    # لوحة المطورين
    if user_id in devs_list:
        buttons.append([InlineKeyboardButton("⚙️ لوحة المطور", callback_data="dev_panel")])
        
    return InlineKeyboardMarkup(buttons)

async def rotate_photo_if_needed(msg_count):
    if spam_photos and msg_count > 0 and msg_count % 10 == 0:
        photo_index = (msg_count // 10) % len(spam_photos)
        try:
            await user_account.set_profile_photo(photo=spam_photos[photo_index])
        except Exception as e:
            print(f"خطأ في تغيير الصورة: {e}")

def send_email_func(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"SMTP Error: {e}")
        return False

# ---------------- START COMMAND ----------------
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await check_sub(client, user_id):
        await message.reply_text(f"⚠️ يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:\n@{MUST_JOIN_CHANNEL}")
        return

    await message.reply_text(
        "أهلاً بك في البوت!\n\n"
        "• أرسل **تلغيم** للتكرار في التليكرام.\n"
        "• أرسل **المجموعات** لإدارة المجموعات.\n"
        "• اضغط على **الشات التلقائي** لإرسال رسائل بريدية متكررة.",
        reply_markup=build_main_keyboard(user_id)
    )

# ---------------- AUTO EMAIL CHAT (الشات التلقائي) ----------------
@bot.on_callback_query(filters.regex("auto_chat_email"))
async def start_auto_chat(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_subscribed_user(user_id):
        await callback_query.answer("❌ هذا الخيار متاح للمشتركين فقط! تواصل مع المطور للتفعيل.", show_alert=True)
        return

    user_states[user_id] = {"step": "email_wait_count"}
    await callback_query.message.reply_text("📧 **الشات التلقائي عبر البريد الإلكتروني**\n\nأدخل عدد الرسائل المراد إرسالها (من 100 إلى 2000):")

# ---------------- USER & DEV HANDLER ----------------
@bot.on_message(filters.private & ~filters.me)
async def handle_private_messages(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    state_data = user_states.get(user_id, {})
    state = state_data.get("step")

    # --- خطوات الشات التلقائي عبر البريد ---
    if state == "email_wait_count":
        if not text.isdigit() or not (100 <= int(text) <= 2000):
            await message.reply_text("❌ يرجى إدخال عدد صحيح بين 100 و 2000.")
            return
        user_states[user_id]["email_count"] = int(text)
        user_states[user_id]["step"] = "email_wait_target"
        await message.reply_text("أرسل البريد الإلكتروني المستهدف (المستلم):")

    elif state == "email_wait_target":
        if "@" not in text or "." not in text:
            await message.reply_text("❌ يرجى إرسال بريد إلكتروني صحيح.")
            return
        user_states[user_id]["target_email"] = text
        user_states[user_id]["step"] = "email_wait_subject"
        await message.reply_text("أرسل موضوع الرسالة (Subject):")

    elif state == "email_wait_subject":
        user_states[user_id]["email_subject"] = text
        user_states[user_id]["step"] = "email_wait_body"
        await message.reply_text("أرسل نص الرسالة:")

    elif state == "email_wait_body":
        email_body = text
        email_count = state_data.get("email_count")
        target_email = state_data.get("target_email")
        email_subject = state_data.get("email_subject")

        await message.reply_text(f"⏳ جاري بدء إرسال {email_count} رسالة بريدية إلى `{target_email}`...")

        success_sent = 0
        for i in range(1, email_count + 1):
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, send_email_func, target_email, email_subject, email_body)
            if res:
                success_sent += 1
            await asyncio.sleep(0.5)

        user_states[user_id] = {}
        await message.reply_text(f"✅ تم الانتهاء! تم إرسال {success_sent} من أصل {email_count} رسالة بنجاح.")

    # --- باقي الخطوات السابقة (تلغيم، إدارة المطورين، الخ) ---
    elif state == "wait_link":
        try:
            chat = await user_account.join_chat(text)
            chat_id = chat.id
        except Exception:
            chat_id = text
        user_states[user_id] = {"step": "wait_count", "chat_id": chat_id}
        await message.reply_text("ارسل عدد التلغيم (من 1 إلى 100):")

    elif state == "wait_count":
        if not text.isdigit() or not (1 <= int(text) <= 100):
            await message.reply_text("الرجاء إدخال عدد بين 1 و 100.")
            return
        count = int(text)
        chat_id = state_data.get("chat_id")
        await message.reply_text(f"⏳ جاري بدء الإرسال ({count} رسالة)...")

        for i in range(1, count + 1):
            await user_account.send_message(chat_id, "ا")
            await rotate_photo_if_needed(i)
            await asyncio.sleep(0.3)

        user_states[user_id] = {}
        await message.reply_text("✅ اكتملت العملية بنجاح!")

    elif state == "wait_dev_photo" and message.photo and user_id in devs_list:
        photo_path = await message.download()
        spam_photos.append(photo_path)
        user_states[user_id] = {}
        await message.reply_text(f"✅ تم إضافة الصورة! الإجمالي: {len(spam_photos)}")

    elif state == "wait_add_dev" and user_id in devs_list:
        devs_list.append(int(text))
        user_states[user_id] = {}
        await message.reply_text("✅ تم إضافة المطور بنجاح.")

    elif state == "wait_sub_id" and user_id in devs_list:
        user_states[user_id] = {"step": "wait_sub_days", "sub_target": int(text)}
        await message.reply_text("أدخل عدد أيام الاشتراك:")

    elif state == "wait_sub_days" and user_id in devs_list:
        target = state_data.get("sub_target")
        subscriptions[target] = time.time() + (int(text) * 86400)
        user_states[user_id] = {}
        await message.reply_text(f"✅ تم تفعيل الاشتراك للمستخدم `{target}`.")

    elif state == "wait_button_text" and user_id in devs_list:
        user_states[user_id] = {"step": "wait_button_url", "btn_text": text}
        await message.reply_text("أرسل رابط الزر:")

    elif state == "wait_button_url" and user_id in devs_list:
        custom_buttons.append({"text": state_data.get("btn_text"), "url": text})
        user_states[user_id] = {}
        await message.reply_text("✅ تم إضافة الزر الشفاف بنجاح!")

# ---------------- DEVELOPER PANEL ----------------
@bot.on_callback_query(filters.regex("dev_panel"))
async def dev_panel_handler(client, callback_query):
    if callback_query.from_user.id not in devs_list:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مطور", callback_data="dev_add_dev")],
        [InlineKeyboardButton("💳 إضافة اشتراك لمستخدم", callback_data="dev_add_sub")],
        [InlineKeyboardButton("🖼️ إضافة صورة تلغيم", callback_data="dev_add_photo")],
        [InlineKeyboardButton("🔘 إضافة زر شفاف", callback_data="dev_add_button")],
        [InlineKeyboardButton("👨‍💻 حساب المطور", url=f"https://t.me/{MAIN_DEV_USERNAME}")]
    ])
    await callback_query.message.edit_text("⚙️ **لوحة التحكم المتقدمة للمطور**", reply_markup=keyboard)

@bot.on_callback_query(filters.regex("dev_add_dev"))
async def cb_add_dev(client, callback_query):
    user_states[callback_query.from_user.id] = {"step": "wait_add_dev"}
    await callback_query.message.reply_text("أرسل آيدي المطور الجديد:")

@bot.on_callback_query(filters.regex("dev_add_sub"))
async def cb_add_sub(client, callback_query):
    user_states[callback_query.from_user.id] = {"step": "wait_sub_id"}
    await callback_query.message.reply_text("أرسل آيدي المستخدم المراد تفعيل الاشتراك له:")

@bot.on_callback_query(filters.regex("dev_add_photo"))
async def cb_add_photo(client, callback_query):
    user_states[callback_query.from_user.id] = {"step": "wait_dev_photo"}
    await callback_query.message.reply_text("أرسل صورة جديدة لإضافتها لقائمة الصور:")

@bot.on_callback_query(filters.regex("dev_add_button"))
async def cb_add_button(client, callback_query):
    user_states[callback_query.from_user.id] = {"step": "wait_button_text"}
    await callback_query.message.reply_text("أرسل عنوان الزر الشفاف الجديد:")

# ---------------- RUN BOT ----------------
async def main():
    await bot.start()
    await user_account.start()
    print("🤖 البوت يعمل بنجاح ومزود بجميع الميزات الشاملة!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
