import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    UserAlreadyParticipant, 
    InviteHashExpired, 
    InviteRequestSent, 
    UserBannedInChannel
)

# ==============================================================================
# 🔴 1. المعلومات الأساسية والبريد (املاء البيانات هنا مباشرة)
# ==============================================================================
API_ID = 30277194               # اكتب الـ API_ID الخاص بك
API_HASH = "c491b2abf1654641536efb798e50cf15"     # اكتب الـ API_HASH الخاص بك
BOT_TOKEN = "8292971150:AAHD75wBeGS_pUEUKE93PCSp9ZPy1L9TGTM"   # اكتب توكن البوت الخاص بك
MAIN_ADMIN_ID = 7493679412       # اكتب أيدي حسابك في التليكرام هنا

# إعدادات البريد الإلكتروني المرسل (SMTP)
SENDER_EMAIL = "shdsbam@gmail.com"      # اكتب إيميلك الذي سيرسل البوت منه
SENDER_PASSWORD = "fgyujbho980" # اكتب كلمة مرور التطبيق (App Password)
# ==============================================================================

# قائمة المطورين المعتمدين
DEV_USERS = [MAIN_ADMIN_ID]

# اشتراكات المستخدمين: {user_id: days}
USER_SUBSCRIPTIONS = {}

# إعدادات التلغيم والصور الخاصة بالمطور
MINE_CONFIG = {
    "word": "ا",                    # الكلمة/الحرف الافتراضي للتلغيم
    "mine_photo": "mine_pic.jpg",   # مسار/رابط صورة التلغيم
    "main_photo": "main_pic.jpg"    # مسار/رابط الصورة الأساسية بعد الانتهاء
}

# ---------------- CLIENTS INITIALIZATION ----------------
user_account = Client("my_account", api_id=API_ID, api_hash=API_HASH)
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# حالات الجلسات والمتابعة للمستخدمين
user_states = {}

# ---------------- HELPER FUNCTIONS ----------------
def send_email_smtp(to_email, subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD or "example" in SENDER_EMAIL:
        return False, "لم يتم ضبط إيميل وباسورد المرسل داخل الكود بشكل صحيح!"
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, to_email, text)
        server.quit()
        return True, "تم الإرسال بنجاح"
    except Exception as e:
        return False, str(e)

# ---------------- KEYBOARDS ----------------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 بدء السبام", callback_data="spam_flow_start"),
            InlineKeyboardButton("🛑 إيقاف السبام", callback_data="stop_spam")
        ],
        [
            InlineKeyboardButton("💣 بدء الهجوم", callback_data="attack_flow_start"),
            InlineKeyboardButton("⚙️ لوحة المطورين", callback_data="dev_panel")
        ],
        [
            InlineKeyboardButton("📊 حالة النظام", callback_data="bot_status")
        ]
    ])

def attack_count_keyboard():
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(f"{i}", callback_data=f"set_attack_count_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)

def dev_panel_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة مطور", callback_data="dev_add_admin"),
            InlineKeyboardButton("🎟️ إضافة اشتراك", callback_data="dev_add_sub")
        ],
        [
            InlineKeyboardButton("✏️ تغيير كلمة التلغيم", callback_data="dev_set_word"),
            InlineKeyboardButton("🖼️ ضبط صور التلغيم", callback_data="dev_set_photos")
        ],
        [
            InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")
        ]
    ])

# ---------------- BOT HANDLERS ----------------
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = None
    
    welcome_msg = (
        f"🙋‍♂️ أهلاً بك يا {message.from_user.mention} في اليوزربوت الشامل!\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "• قسم السبام المطور عبر البريد (من 100 إلى 2000 رسالة)\n"
        "• قسم الهجوم والتلغيم الذكي مع تغيير الصور تلقائياً\n"
        "• لوحة تحكم كاملة للمطورين والاشتراكات\n\n"
        "👇 اختر المطلوب من القائمة:"
    )
    await message.reply_text(welcome_msg, reply_markup=main_menu_keyboard())

@bot.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data == "main_menu":
        user_states[user_id] = None
        await callback.message.edit_text("⚙️ **القائمة الرئيسية:**", reply_markup=main_menu_keyboard())

    # --- مسار السبام ---
    elif data == "spam_flow_start":
        user_states[user_id] = {"step": "SPAM_SUBJECT"}
        await callback.message.edit_text(
            "🚀 **بدء إعداد السبام:**\n\nيرجى إرسال **موضوع السبام** الآن:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]])
        )

    elif data == "stop_spam":
        user_states[user_id] = None
        await callback.answer("🛑 تم إيقاف العمليات!", show_alert=True)
        await callback.message.edit_text("⏸️ **تم إيقاف العمليات المعلقة.**", reply_markup=main_menu_keyboard())

    # --- مسار بدء الهجوم ---
    elif data == "attack_flow_start":
        user_states[user_id] = {"step": "WAIT_GROUP_LINK"}
        await callback.message.edit_text(
            "💣 **بدء الهجوم:**\n\nأرسل رابط المجموعة الآن فقط (بدون أي كلام إضافي مع الرابط):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]])
        )

    elif data.startswith("set_attack_count_"):
        count = int(data.split("_")[-1])
        group_link = user_states.get(user_id, {}).get("group_link")
        
        if not group_link:
            await callback.message.edit_text("❌ حدث خطأ في الحصول على الرابط، حاول مجدداً.", reply_markup=main_menu_keyboard())
            return

        await callback.message.edit_text(f"⏳ **جاري تنفيذ الهجوم للعدد ({count})...**")
        
        try:
            # 1. تغيير الصورة إلى صورة التلغيم
            try:
                await user_account.set_profile_photo(photo=MINE_CONFIG["mine_photo"])
            except Exception:
                pass

            # 2. إرسال الكلمة/الحرف
            chat = await user_account.get_chat(group_link)
            for _ in range(count):
                await user_account.send_message(chat.id, MINE_CONFIG["word"])
                await asyncio.sleep(0.5)

            # 3. إرجاع الصورة إلى الصورة الأساسية
            try:
                await user_account.set_profile_photo(photo=MINE_CONFIG["main_photo"])
            except Exception:
                pass

            await callback.message.edit_text(f"✅ **تم تنفيذ الهجوم بنجاح وصافحت المجموعة {count} مرة! 💣**", reply_markup=main_menu_keyboard())
        except Exception as e:
            await callback.message.edit_text(f"❌ **حدث خطأ أثناء تنفيذ الهجوم:**\n`{e}`", reply_markup=main_menu_keyboard())

    # --- لوحة المطورين ---
    elif data == "dev_panel":
        if user_id not in DEV_USERS and user_id != MAIN_ADMIN_ID:
            await callback.answer("❌ هذه اللوحة مخصصة للمطورين فقط!", show_alert=True)
            return
        await callback.message.edit_text("⚙️ **لوحة التحكم الخاصة بالمطورين:**", reply_markup=dev_panel_keyboard())

    elif data == "dev_add_admin":
        if user_id not in DEV_USERS and user_id != MAIN_ADMIN_ID: return
        user_states[user_id] = {"step": "DEV_ADD_ADMIN"}
        await callback.message.edit_text("👤 أرسل الآن **ايدي (ID)** المطور الجديد لإضافته:")

    elif data == "dev_add_sub":
        if user_id not in DEV_USERS and user_id != MAIN_ADMIN_ID: return
        user_states[user_id] = {"step": "DEV_ADD_SUB_ID"}
        await callback.message.edit_text("🎟️ أرسل الآن **ايدي (ID)** المستخدم لإعطائه اشتراك:")

    elif data == "dev_set_word":
        if user_id not in DEV_USERS and user_id != MAIN_ADMIN_ID: return
        user_states[user_id] = {"step": "DEV_SET_WORD"}
        await callback.message.edit_text(f"✏️ الكلمة الحالية: `{MINE_CONFIG['word']}`\n\nأرسل **الكلمة/الحرف الجديد** للتلغيم:")

    elif data == "dev_set_photos":
        if user_id not in DEV_USERS and user_id != MAIN_ADMIN_ID: return
        user_states[user_id] = {"step": "DEV_SET_MINE_PHOTO"}
        await callback.message.edit_text("🖼️ أرسل مسار أو رابط **صورة التلغيم** الجديدة:")

    elif data == "bot_status":
        status_text = (
            "📊 **حالة النظام واليوزربوت:**\n\n"
            f"• إيميل المرسل: `{SENDER_EMAIL}`\n"
            f"• كلمة التلغيم الحالية: `{MINE_CONFIG['word']}`\n"
            f"• عدد المطورين: `{len(DEV_USERS)}`\n"
            f"• عدد المشتركين: `{len(USER_SUBSCRIPTIONS)}`\n"
            "• حالة البوت: 🟢 يعمل بنجاح"
        )
        await callback.message.edit_text(status_text, reply_markup=main_menu_keyboard())

# ---------------- MESSAGES PROCESSOR (STATES) ----------------
@bot.on_message(filters.private & filters.text & ~filters.bot)
async def process_inputs(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state or not isinstance(state, dict):
        return

    step = state.get("step")

    # --- خطوات السبام ---
    if step == "SPAM_SUBJECT":
        user_states[user_id] = {"step": "SPAM_MESSAGE", "subject": message.text.strip()}
        await message.reply_text("✅ تم حفظ الموضوع.\n\nالان يرجى إرسال **نص الرسالة**:")

    elif step == "SPAM_MESSAGE":
        user_states[user_id]["body"] = message.text.strip()
        user_states[user_id]["step"] = "SPAM_EMAIL"
        await message.reply_text("✅ تم حفظ النص.\n\nالان يرجى إرسال **البريد الإلكتروني المستهدف**:")

    elif step == "SPAM_EMAIL":
        user_states[user_id]["target_email"] = message.text.strip()
        user_states[user_id]["step"] = "SPAM_COUNT"
        await message.reply_text("✅ تم حفظ البريد.\n\nأدخل **عدد رسائل السبام** المطلوب (أقل شيء **100** وأكثر شيء **2000**):")

    elif step == "SPAM_COUNT":
        try:
            count = int(message.text.strip())
            if count < 100 or count > 2000:
                await message.reply_text("⚠️ يرجى إدخال عدد صحيح بين 100 و 2000 رسالة!")
                return
            
            subject = user_states[user_id]["subject"]
            body = user_states[user_id]["body"]
            target_email = user_states[user_id]["target_email"]
            
            wait_msg = await message.reply_text(f"⏳ جاري بدء إرسال ({count}) رسالة سبام إلى `{target_email}`...")
            
            success_count = 0
            for i in range(count):
                ok, err = send_email_smtp(target_email, subject, body)
                if ok:
                    success_count += 1
                await asyncio.sleep(0.2)

            await wait_msg.edit_text(f"✅ **تم الانتهاء من عملية السبام!**\n\n🎯 الإيميل الهدف: `{target_email}`\n📩 تم إرسال: `{success_count}` من أصل `{count}` رسالة.")
            user_states[user_id] = None
        except ValueError:
            await message.reply_text("⚠️ يرجى إدخال رقم صحيح فقط!")

    # --- خطوة استقبال رابط الهجوم ---
    elif step == "WAIT_GROUP_LINK":
        link = message.text.strip()
        wait_msg = await message.reply_text("⏳ جاري فحص المجموعة والانضمام...")

        try:
            await user_account.join_chat(link)
            user_states[user_id] = {"group_link": link}
            await wait_msg.edit_text("✅ **تم الانضمام إلى المجموعة!**\n\nاختر الآن **عدد التلغيم** المطلوب تنفيذها:", reply_markup=attack_count_keyboard())

        except UserBannedInChannel:
            user_states[user_id] = None
            await wait_msg.edit_text("❌ **الحساب مطرود من هذه المجموعة!**", reply_markup=main_menu_keyboard())

        except InviteRequestSent:
            user_states[user_id] = None
            await wait_msg.edit_text("⏳ **انتظر لحد ما يوافقون على طلب الانضمام...**", reply_markup=main_menu_keyboard())

        except UserAlreadyParticipant:
            user_states[user_id] = {"group_link": link}
            await wait_msg.edit_text("⚠️ **الحساب موجود بالفعل بالجروب.**\n\nاختر عدد التلغيم مباشرة:", reply_markup=attack_count_keyboard())

        except InviteHashExpired:
            user_states[user_id] = None
            await wait_msg.edit_text("❌ **الرابط غير صالح أو منتهي الصلاحية!**", reply_markup=main_menu_keyboard())

        except Exception as e:
            user_states[user_id] = None
            await wait_msg.edit_text(f"❌ **حدث خطأ:**\n`{e}`", reply_markup=main_menu_keyboard())

    # --- خطوات إعدادات المطور ---
    elif step == "DEV_ADD_ADMIN":
        try:
            new_dev = int(message.text.strip())
            if new_dev not in DEV_USERS:
                DEV_USERS.append(new_dev)
                await message.reply_text(f"✅ تم إضافة المطور بنجاح: `{new_dev}`", reply_markup=dev_panel_keyboard())
            else:
                await message.reply_text("⚠️ هذا المستخدم مطور بالفعل!", reply_markup=dev_panel_keyboard())
        except ValueError:
            await message.reply_text("❌ يرجى إرسال ايدي أرقام فقط!")
        user_states[user_id] = None

    elif step == "DEV_ADD_SUB_ID":
        user_states[user_id] = {"step": "DEV_ADD_SUB_DAYS", "sub_id": message.text.strip()}
        await message.reply_text("🎟️ أدخل الآن **عدد أيام الاشتراك**:")

    elif step == "DEV_ADD_SUB_DAYS":
        try:
            target_sub = int(user_states[user_id]["sub_id"])
            days = int(message.text.strip())
            USER_SUBSCRIPTIONS[target_sub] = days
            await message.reply_text(f"✅ تم إضافة اشتراك للمستخدم `{target_sub}` لمدة `{days}` يوم!", reply_markup=dev_panel_keyboard())
        except ValueError:
            await message.reply_text("❌ يرجى كتابة أرقام صحيحة فقط!")
        user_states[user_id] = None

    elif step == "DEV_SET_WORD":
        MINE_CONFIG["word"] = message.text.strip()
        await message.reply_text(f"✅ تم تغيير كلمة التلغيم إلى: `{MINE_CONFIG['word']}`", reply_markup=dev_panel_keyboard())
        user_states[user_id] = None

    elif step == "DEV_SET_MINE_PHOTO":
        MINE_CONFIG["mine_photo"] = message.text.strip()
        user_states[user_id] = {"step": "DEV_SET_MAIN_PHOTO"}
        await message.reply_text("✅ تم حفظ صورة التلغيم.\n\nالان أرسل مسار/رابط **الصورة الأساسية** بعد التلغيم:")

    elif step == "DEV_SET_MAIN_PHOTO":
        MINE_CONFIG["main_photo"] = message.text.strip()
        await message.reply_text("✅ تم حفظ الصورة الأساسية بنجاح!", reply_markup=dev_panel_keyboard())
        user_states[user_id] = None

# ---------------- MAIN RUNNER ----------------
async def main():
    print("⏳ جاري تشغيل البوت والخدمات...")
    await bot.start()
    print("✅ تم تشغيل البوت الخدمي بنجاح!")

    try:
        await user_account.start()
        print("✅ تم تشغيل الحساب الشخصي!")
    except Exception as e:
        print(f"⚠️ تنبيه الحساب الشخصي: {e}")

    print("🚀 البوت جاهز للاستخدام بنجاح!")
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف البوت.")
