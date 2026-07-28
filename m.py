import asyncio
import os
from aiohttp import web

# حل مشكلة Python 3.10+ / 3.14 على Render
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

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
# 🔴 1. اكتب البيانات الخاصة بك هنا
# ==============================================================================
API_ID = 30277194               # اكتب الـ API_ID الخاص بك هنا
API_HASH = "c491b2abf1654641536efb798e50cf15"     # اكتب الـ API_HASH الخاص بك هنا
BOT_TOKEN = "8292971150:AAHD75wBeGS_pUEUKE93PCSp9ZPy1L9TGTM"   # اكتب توكن البوت الخاص بك هنا
MAIN_ADMIN_ID = 7493679412       # اكتب أيدي حسابك في التليكرام هنا
DEV_USERNAME = "XX7X6"  # اكتب معرفك بدون علامة @ (مثال: DevUser)

# إعدادات البريد الإلكتروني المرسل (SMTP)
SENDER_EMAIL = "shdsbam@gmail.com"      # اكتب البريد الإلكتروني للارسال
SENDER_PASSWORD = "fgyujbho980" # اكتب كلمة مرور التطبيق (App Password)
# ==============================================================================

# قائمة المطورين
DEV_USERS = [MAIN_ADMIN_ID]

# اشتراكات المستخدمين: {user_id: True}
USER_SUBSCRIPTIONS = {}

# قائمة الأزرار المخصصة التي يضيفها المطور: [{"text": "...", "url": "..."}]
CUSTOM_BUTTONS = []

# إعدادات التلغيم والصور
MINE_CONFIG = {
    "word": "ا",          # الكلمة/الحرف الافتراضي للتلغيم
    "mine_photo": None,  # file_id لصورة التلغيم
    "main_photo": None   # file_id للصورة الأساسية
}

# ---------------- CLIENTS INITIALIZATION ----------------
user_account = Client("my_account", api_id=API_ID, api_hash=API_HASH)
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# حالات الجلسات
user_states = {}

# ---------------- WEB SERVER (KEEP-ALIVE FOR RENDER & UPTIMEROBOT) ----------------
async def handle_ping(request):
    return web.Response(text="Bot is running alive 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web Server started on port {port}")

# ---------------- HELPER FUNCTIONS ----------------
def is_authorized(user_id):
    """التحقق هل المستخدم مطور أو يملك اشتراك مفعل"""
    return (user_id in DEV_USERS) or (user_id == MAIN_ADMIN_ID) or (USER_SUBSCRIPTIONS.get(user_id) == True)

def is_dev(user_id):
    """التحقق هل المستخدم مطور"""
    return (user_id in DEV_USERS) or (user_id == MAIN_ADMIN_ID)

def send_email_smtp(to_email, subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD or "example" in SENDER_EMAIL:
        return False, "لم يتم ضبط البريد بشكل صحيح!"
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
def main_menu_keyboard(user_id):
    buttons = [
        [
            InlineKeyboardButton("🚀 بدء السبام", callback_data="spam_flow_start"),
            InlineKeyboardButton("🛑 إيقاف السبام", callback_data="stop_spam")
        ],
        [
            InlineKeyboardButton("💣 بدء الهجوم", callback_data="attack_flow_start")
        ]
    ]
    
    # إضافة الأزرار المخصصة المضافة من المطور إن وجدت
    for btn in CUSTOM_BUTTONS:
        buttons.append([InlineKeyboardButton(btn["text"], url=btn["url"])])

    # إذا كان المستخدم مطور يظهر له لوحة المطورين وحالة النظام
    if is_dev(user_id):
        buttons.append([
            InlineKeyboardButton("⚙️ لوحة المطورين", callback_data="dev_panel"),
            InlineKeyboardButton("📊 حالة النظام", callback_data="bot_status")
        ])

    # زر المطور يظهر للجميع في الأسفل
    buttons.append([
        InlineKeyboardButton("developer 🧑‍💻", url=f"https://t.me/{DEV_USERNAME}")
    ])

    return InlineKeyboardMarkup(buttons)

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
            InlineKeyboardButton("🎟️ تفعيل اشتراك لمستخدم", callback_data="dev_add_sub")
        ],
        [
            InlineKeyboardButton("✏️ تغيير كلمة التلغيم", callback_data="dev_set_word"),
            InlineKeyboardButton("🖼️ تغيير صور التلغيم", callback_data="dev_set_photos")
        ],
        [
            InlineKeyboardButton("🔘 إضافة زر مخصص", callback_data="dev_add_button"),
            InlineKeyboardButton("🗑️ مسح الأزرار المخصصة", callback_data="dev_clear_buttons")
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

    if not is_authorized(user_id):
        # إرسال رسالة ترحيبية مع زر المطور للمستخدم غير المصرح له
        unauthorized_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("developer 🧑‍💻", url=f"https://t.me/{DEV_USERNAME}")]
        ])
        await message.reply_text(
            "🔒 **عذراً، البوت غير مصرح لك باستخدامه!**\n\n"
            "ليس لديك اشتراك فعال لتشغيل البوت.\n"
            f"للاشتراك وتفعيل الحساب، يرجى التواصل مع المطور عبر الزر أدناه:",
            reply_markup=unauthorized_kb
        )
        return
    
    welcome_msg = (
        f"🙋‍♂️ أهلاً بك يا {message.from_user.mention}!\n\n"
        "✨ **الخدمات المتاحة:**\n"
        "• قسم السبام المطور عبر البريد\n"
        "• قسم الهجوم والتلغيم الذكي\n\n"
        "👇 اختر المطلوب من القائمة:"
    )
    await message.reply_text(welcome_msg, reply_markup=main_menu_keyboard(user_id))

@bot.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if not is_authorized(user_id):
        await callback.answer(f"🔒 البوت غير مصرح لك! تواصل مع المطور: @{DEV_USERNAME}", show_alert=True)
        return

    if data == "main_menu":
        user_states[user_id] = None
        await callback.message.edit_text("⚙️ **القائمة الرئيسية:**", reply_markup=main_menu_keyboard(user_id))

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
        await callback.message.edit_text("⏸️ **تم إيقاف العمليات المعلقة.**", reply_markup=main_menu_keyboard(user_id))

    # --- مسار الهجوم ---
    elif data == "attack_flow_start":
        user_states[user_id] = {"step": "WAIT_GROUP_LINK"}
        await callback.message.edit_text(
            "💣 **بدء الهجوم:**\n\nأرسل رابط المجموعة الآن فقط:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]])
        )

    elif data.startswith("set_attack_count_"):
        count = int(data.split("_")[-1])
        group_link = user_states.get(user_id, {}).get("group_link")
        
        if not group_link:
            await callback.message.edit_text("❌ حدث خطأ في الحصول على الرابط، حاول مجدداً.", reply_markup=main_menu_keyboard(user_id))
            return

        await callback.message.edit_text(f"⏳ **جاري تنفيذ الهجوم للعدد ({count})...**")
        
        try:
            # تغيير صورة التلغيم إن وجدت
            if MINE_CONFIG["mine_photo"]:
                try:
                    file_path = await bot.download_media(MINE_CONFIG["mine_photo"])
                    await user_account.set_profile_photo(photo=file_path)
                    if os.path.exists(file_path): os.remove(file_path)
                except Exception:
                    pass

            chat = await user_account.get_chat(group_link)
            for _ in range(count):
                await user_account.send_message(chat.id, MINE_CONFIG["word"])
                await asyncio.sleep(0.5)

            # إعادة الصورة الأساسية إن وجدت
            if MINE_CONFIG["main_photo"]:
                try:
                    file_path = await bot.download_media(MINE_CONFIG["main_photo"])
                    await user_account.set_profile_photo(photo=file_path)
                    if os.path.exists(file_path): os.remove(file_path)
                except Exception:
                    pass

            await callback.message.edit_text(f"✅ **تم تنفيذ الهجوم بنجاح وصافحت المجموعة {count} مرة! 💣**", reply_markup=main_menu_keyboard(user_id))
        except Exception as e:
            await callback.message.edit_text(f"❌ **حدث خطأ أثناء الهجوم:**\n`{e}`", reply_markup=main_menu_keyboard(user_id))

    # --- لوحة المطورين ---
    elif data == "dev_panel":
        if not is_dev(user_id):
            await callback.answer("❌ هذه اللوحة مخصصة للمطورين فقط!", show_alert=True)
            return
        await callback.message.edit_text("⚙️ **لوحة التحكم الخاصة بالمطورين:**", reply_markup=dev_panel_keyboard())

    elif data == "dev_add_admin":
        if not is_dev(user_id): return
        user_states[user_id] = {"step": "DEV_ADD_ADMIN"}
        await callback.message.edit_text("👤 أرسل الآن **ايدي (ID)** المطور الجديد:")

    elif data == "dev_add_sub":
        if not is_dev(user_id): return
        user_states[user_id] = {"step": "DEV_ADD_SUB_ID"}
        await callback.message.edit_text("🎟️ أرسل الآن **ايدي (ID)** المستخدم لتفعيل اشتراكه:")

    elif data == "dev_set_word":
        if not is_dev(user_id): return
        user_states[user_id] = {"step": "DEV_SET_WORD"}
        await callback.message.edit_text(f"✏️ الكلمة الحالية: `{MINE_CONFIG['word']}`\n\nأرسل **الكلمة الجديدة** للتلغيم:")

    elif data == "dev_set_photos":
        if not is_dev(user_id): return
        user_states[user_id] = {"step": "DEV_SET_MINE_PHOTO"}
        await callback.message.edit_text("🖼️ قم بإرسال **صورة التلغيم الأولى** الآن بالدردشة:")

    elif data == "dev_add_button":
        if not is_dev(user_id): return
        user_states[user_id] = {"step": "DEV_ADD_BTN_TEXT"}
        await callback.message.edit_text("🔘 أرسل الآن **النص/الاسم** الذي سيظهر على الزر:")

    elif data == "dev_clear_buttons":
        if not is_dev(user_id): return
        CUSTOM_BUTTONS.clear()
        await callback.answer("🗑️ تم مسح جميع الأزرار المخصصة!", show_alert=True)
        await callback.message.edit_text("⚙️ **لوحة التحكم الخاصة بالمطورين:**", reply_markup=dev_panel_keyboard())

    elif data == "bot_status":
        if not is_dev(user_id):
            await callback.answer("❌ محمي للمطورين فقط!", show_alert=True)
            return
        status_text = (
            "📊 **حالة النظام واليوزربوت:**\n\n"
            f"• كلمة التلغيم الحالية: `{MINE_CONFIG['word']}`\n"
            f"• عدد المطورين: `{len(DEV_USERS)}`\n"
            f"• عدد المشتركين: `{len(USER_SUBSCRIPTIONS)}`\n"
            f"• صورة التلغيم: {'مضبوطة ✅' if MINE_CONFIG['mine_photo'] else 'غير مضبوطة ❌'}\n"
            f"• الصورة الأساسية: {'مضبوطة ✅' if MINE_CONFIG['main_photo'] else 'غير مضبوطة ❌'}\n"
            "• حالة البوت: 🟢 يعمل بنجاح"
        )
        await callback.message.edit_text(status_text, reply_markup=main_menu_keyboard(user_id))

# ---------------- MEDIA & MESSAGES PROCESSOR ----------------
@bot.on_message(filters.private & ~filters.bot)
async def process_inputs(client: Client, message: Message):
    user_id = message.from_user.id

    if not is_authorized(user_id):
        unauthorized_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("developer 🧑‍💻", url=f"https://t.me/{DEV_USERNAME}")]
        ])
        await message.reply_text(
            "🔒 **عذراً، البوت غير مصرح لك باستخدامه!**\n\n"
            "ليس لديك اشتراك فعال.\n"
            f"تواصل مع المطور للتفعيل: @{DEV_USERNAME}",
            reply_markup=unauthorized_kb
        )
        return

    state = user_states.get(user_id)
    if not state or not isinstance(state, dict):
        return

    step = state.get("step")

    # --- استقبال الصور للمطور ---
    if step == "DEV_SET_MINE_PHOTO" and message.photo:
        MINE_CONFIG["mine_photo"] = message.photo.file_id
        user_states[user_id] = {"step": "DEV_SET_MAIN_PHOTO"}
        await message.reply_text("✅ تم حفظ صورة التلغيم!\n\nالان أرسل **الصورة الأساسية** بالدردشة لتثبيتها بعد الهجوم:")
        return

    elif step == "DEV_SET_MAIN_PHOTO" and message.photo:
        MINE_CONFIG["main_photo"] = message.photo.file_id
        user_states[user_id] = None
        await message.reply_text("✅ تم حفظ الصورة الأساسية بنجاح!", reply_markup=dev_panel_keyboard())
        return

    # --- خطوات إضافة الأزرار المخصصة ---
    if step == "DEV_ADD_BTN_TEXT" and message.text:
        user_states[user_id] = {"step": "DEV_ADD_BTN_URL", "btn_text": message.text.strip()}
        await message.reply_text("🔗 ممتاز، الآن أرسل **رابط الزر** (يجب أن يبدأ بـ http:// أو https://):")
        return

    elif step == "DEV_ADD_BTN_URL" and message.text:
        url = message.text.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            await message.reply_text("⚠️ الرابط غير صالح! يرجى إرسال رابط يبدأ بـ http:// أو https://")
            return
        
        btn_text = user_states[user_id]["btn_text"]
        CUSTOM_BUTTONS.append({"text": btn_text, "url": url})
        user_states[user_id] = None
        await message.reply_text(f"✅ تم إضافة الزر المخصص (`{btn_text}`) بنجاح!", reply_markup=dev_panel_keyboard())
        return

    # --- خطوات السبام ---
    if step == "SPAM_SUBJECT" and message.text:
        user_states[user_id] = {"step": "SPAM_MESSAGE", "subject": message.text.strip()}
        await message.reply_text("✅ تم حفظ الموضوع.\n\nالان يرجى إرسال **نص الرسالة**:")

    elif step == "SPAM_MESSAGE" and message.text:
        user_states[user_id]["body"] = message.text.strip()
        user_states[user_id]["step"] = "SPAM_EMAIL"
        await message.reply_text("✅ تم حفظ النص.\n\nالان يرجى إرسال **البريد الإلكتروني المستهدف**:")

    elif step == "SPAM_EMAIL" and message.text:
        user_states[user_id]["target_email"] = message.text.strip()
        user_states[user_id]["step"] = "SPAM_COUNT"
        await message.reply_text("✅ تم حفظ البريد.\n\nأدخل **عدد رسائل السبام** المطلوب (بين **100** و **2000**):")

    elif step == "SPAM_COUNT" and message.text:
        try:
            count = int(message.text.strip())
            if count < 100 or count > 2000:
                await message.reply_text("⚠️ يرجى إدخال عدد بين 100 و 2000!")
                return
            
            subject = user_states[user_id]["subject"]
            body = user_states[user_id]["body"]
            target_email = user_states[user_id]["target_email"]
            
            wait_msg = await message.reply_text(f"⏳ جاري بدء إرسال ({count}) رسالة سبام إلى `{target_email}`...")
            
            success_count = 0
            for _ in range(count):
                ok, _ = send_email_smtp(target_email, subject, body)
                if ok: success_count += 1
                await asyncio.sleep(0.2)

            await wait_msg.edit_text(f"✅ **تم الانتهاء!**\n\n🎯 الهدف: `{target_email}`\n📩 تم إرسال: `{success_count}` / `{count}`")
            user_states[user_id] = None
        except ValueError:
            await message.reply_text("⚠️ أدخل أرقام فقط!")

    # --- خطوة رابط الهجوم ---
    elif step == "WAIT_GROUP_LINK" and message.text:
        link = message.text.strip()
        wait_msg = await message.reply_text("⏳ جاري فحص المجموعة والانضمام...")

        try:
            await user_account.join_chat(link)
            user_states[user_id] = {"group_link": link}
            await wait_msg.edit_text("✅ **تم الانضمام!**\n\nاختر الآن **عدد التلغيم**:", reply_markup=attack_count_keyboard())

        except UserBannedInChannel:
            user_states[user_id] = None
            await wait_msg.edit_text("❌ **الحساب مطرود من المجموعة!**", reply_markup=main_menu_keyboard(user_id))

        except InviteRequestSent:
            user_states[user_id] = None
            await wait_msg.edit_text("⏳ **تم إرسال طلب انضمام، انتظر الموافقة.**", reply_markup=main_menu_keyboard(user_id))

        except UserAlreadyParticipant:
            user_states[user_id] = {"group_link": link}
            await wait_msg.edit_text("⚠️ **الحساب موجود بالفعل.**\n\nاختر عدد التلغيم:", reply_markup=attack_count_keyboard())

        except InviteHashExpired:
            user_states[user_id] = None
            await wait_msg.edit_text("❌ **الرابط منتهي الصلاحية!**", reply_markup=main_menu_keyboard(user_id))

        except Exception as e:
            user_states[user_id] = None
            await wait_msg.edit_text(f"❌ **حدث خطأ:**\n`{e}`", reply_markup=main_menu_keyboard(user_id))

    # --- خطوات المطور ---
    elif step == "DEV_ADD_ADMIN" and message.text:
        try:
            new_dev = int(message.text.strip())
            if new_dev not in DEV_USERS:
                DEV_USERS.append(new_dev)
                await message.reply_text(f"✅ تم إضافة المطور: `{new_dev}`", reply_markup=dev_panel_keyboard())
            else:
                await message.reply_text("⚠️ مطور بالفعل!")
        except ValueError:
            await message.reply_text("❌ أرسل أرقام فقط!")
        user_states[user_id] = None

    elif step == "DEV_ADD_SUB_ID" and message.text:
        try:
            target_sub = int(message.text.strip())
            USER_SUBSCRIPTIONS[target_sub] = True
            await message.reply_text(f"✅ تم تفعيل الاشتراك للمستخدم `{target_sub}` بنجاح!", reply_markup=dev_panel_keyboard())
        except ValueError:
            await message.reply_text("❌ أرسل ايدي أرقام فقط!")
        user_states[user_id] = None

    elif step == "DEV_SET_WORD" and message.text:
        MINE_CONFIG["word"] = message.text.strip()
        await message.reply_text(f"✅ تم تغيير الكلمة إلى: `{MINE_CONFIG['word']}`", reply_markup=dev_panel_keyboard())
        user_states[user_id] = None

# ---------------- MAIN RUNNER ----------------
async def main():
    print("⏳ جاري تشغيل البوت والخدمات...")
    await start_web_server()
    await bot.start()
    print("✅ تم تشغيل البوت الخدمي بنجاح!")

    try:
        await user_account.start()
        print("✅ تم تشغيل الحساب الشخصي!")
    except Exception as e:
        print(f"⚠️ تنبيه الحساب الشخصي: {e}")

    print("🚀 البوت جاهز للاستخدام ومحمي بالكامل!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف البوت.")

