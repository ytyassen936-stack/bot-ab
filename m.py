import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# ---------------- CONFIGURATION ----------------
API_ID = 1234567  # ضع هنا API_ID من my.telegram.org
API_HASH = "your_api_hash_here"  # ضع هنا API_HASH
BOT_TOKEN = "your_bot_token_here"  # توكن البوت
MAIN_DEV_ID = 123456789  # آيدي المطور الأساسي
MAIN_DEV_USERNAME = "your_username"  # يوزر المطور بدون @
MUST_JOIN_CHANNEL = "your_channel"  # معرف قناة الاشتراك الإجباري بدون @

bot = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_account = Client("user_session", api_id=API_ID, api_hash=API_HASH)

# ---------------- DATA STORE ----------------
devs_list = [MAIN_DEV_ID]
custom_buttons = []  # الأزرار المضافة [{"text": "...", "url": "..."}]
spam_photos = []     # قائمة الصور المرفوعة للتلغيم
subscriptions = {}   # اشتراكات المستخدمين {user_id: expire_timestamp}
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
    # الأزرار المخصصة المضافة من قبل المطور
    for btn in custom_buttons:
        buttons.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    
    # زر المطور الأساسي
    buttons.append([InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{MAIN_DEV_USERNAME}")])
    
    # لوحة المطورين
    if user_id in devs_list:
        buttons.append([InlineKeyboardButton("⚙️ لوحة المطور", callback_data="dev_panel")])
        
    return InlineKeyboardMarkup(buttons)

async def rotate_photo_if_needed(msg_count):
    """تغيير صورة الحساب كل 10 رسائل"""
    if spam_photos and msg_count > 0 and msg_count % 10 == 0:
        # اختيار صورة من القائمة بناءً على التكرار
        photo_index = (msg_count // 10) % len(spam_photos)
        try:
            await user_account.set_profile_photo(photo=spam_photos[photo_index])
        except Exception as e:
            print(f"خطأ في تغيير الصورة: {e}")

# ---------------- START COMMAND ----------------
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await check_sub(client, user_id):
        await message.reply_text(f"⚠️ يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:\n@{MUST_JOIN_CHANNEL}")
        return

    await message.reply_text(
        "أهلاً بك في البوت!\n\n"
        "• أرسل كلمة **تلغيم** للبدء بعملية التكرار.\n"
        "• أرسل كلمة **المجموعات** لإدارة وإرسال رسائل للمجموعات المنضم لها الحساب.",
        reply_markup=build_main_keyboard(user_id)
    )

# ---------------- USER SPAM & GROUPS ----------------
@bot.on_message(filters.text == "تلغيم" & filters.private)
async def start_spam(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_subscribed_user(user_id):
        await message.reply_text("❌ ليس لديك اشتراك فعال لاستخدام البوت. تواصل مع المطور لتفعيل الاشتراك.")
        return

    user_states[user_id] = {"step": "wait_link"}
    await message.reply_text("ارسل رابط المجموعه:")

@bot.on_message(filters.text == "المجموعات" & filters.private)
async def show_groups_to_user(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_subscribed_user(user_id):
        await message.reply_text("❌ ليس لديك اشتراك فعال لاستخدام هذه الميزة.")
        return

    buttons = []
    async for dialog in user_account.get_dialogs():
        if dialog.chat.type.value in ["group", "supergroup"]:
            buttons.append([InlineKeyboardButton(dialog.chat.title, callback_data=f"user_select_grp_{dialog.chat.id}")])

    buttons.append([InlineKeyboardButton("➕ إضافة مجموعة", callback_data="user_add_group")])
    await message.reply_text("اختر مجموعة للإرسال إليها:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"^user_select_grp_"))
async def user_select_group(client, callback_query):
    group_id = int(callback_query.data.split("_")[3])
    user_id = callback_query.from_user.id
    user_states[user_id] = {"step": "user_wait_msg", "target_group": group_id}
    await callback_query.message.reply_text("أرسل الحرف أو الكلمة المراد إرسالها (مثال: ا):")

# ---------------- MESSAGE HANDLER ----------------
@bot.on_message(filters.private & ~filters.me)
async def handle_private_messages(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    state_data = user_states.get(user_id, {})
    state = state_data.get("step")

    # --- معالجة إعدادات المطور ---
    if user_id in devs_list:
        if state == "wait_dev_photo" and message.photo:
            photo_path = await message.download()
            spam_photos.append(photo_path)
            user_states[user_id] = {}
            await message.reply_text(f"✅ تم إضافة الصورة! إجمالي الصور المتاحة للتغيير التلقائي: {len(spam_photos)}")
            return

        if state == "wait_add_dev":
            try:
                new_dev_id = int(text)
                devs_list.append(new_dev_id)
                await message.reply_text(f"✅ تم إضافة المطور بنجاح: `{new_dev_id}`")
            except ValueError:
                await message.reply_text("❌ يرجى إرسال آيدي عددي صحيح.")
            user_states[user_id] = {}
            return

        if state == "wait_sub_id":
            user_states[user_id] = {"step": "wait_sub_days", "sub_target": int(text)}
            await message.reply_text("أدخل عدد أيام الاشتراك (مثال: 30):")
            return

        if state == "wait_sub_days":
            target = state_data.get("sub_target")
            days = int(text)
            expire_timestamp = time.time() + (days * 86400)
            subscriptions[target] = expire_timestamp
            user_states[user_id] = {}
            await message.reply_text(f"✅ تم تفعيل الاشتراك للمستخدم `{target}` لمدة {days} يوم.")
            return

        if state == "wait_button_text":
            user_states[user_id] = {"step": "wait_button_url", "btn_text": text}
            await message.reply_text("أرسل رابط الزر (URL):")
            return

        if state == "wait_button_url":
            btn_text = state_data.get("btn_text")
            custom_buttons.append({"text": btn_text, "url": text})
            user_states[user_id] = {}
            await message.reply_text(f"✅ تم إضافة الزر الشفاف [{btn_text}] بنجاح!")
            return

    # --- معالجة طلبات إرسال الرسائل للمستخدمين والمطورين ---
    if state == "wait_link":
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
            await rotate_photo_if_needed(i)  # تغيير الصورة كل 10 رسائل
            await asyncio.sleep(0.3)

        user_states[user_id] = {}
        await message.reply_text("✅ اكتملت عملية التلغيم بنجاح!")

    elif state == "user_wait_msg":
        user_states[user_id]["dev_text"] = text
        user_states[user_id]["step"] = "user_wait_count"
        await message.reply_text("أدخل عدد مرات التكرار (من 1 إلى 100):")

    elif state == "user_wait_count":
        if not text.isdigit() or not (1 <= int(text) <= 100):
            await message.reply_text("الرجاء إدخال رقم بين 1 و 100.")
            return

        count = int(text)
        target_group = state_data.get("target_group")
        msg_text = state_data.get("dev_text")

        await message.reply_text(f"⏳ جاري إرسال الرسائل ({count} مرة)...")

        for i in range(1, count + 1):
            await user_account.send_message(target_group, msg_text)
            await rotate_photo_if_needed(i)  # تغيير الصورة كل 10 رسائل
            await asyncio.sleep(0.3)

        user_states[user_id] = {}
        await message.reply_text("✅ تم إكمال الإرسال بنجاح!")

# ---------------- DEVELOPER PANEL CALLBACKS ----------------
@bot.on_callback_query(filters.regex("dev_panel"))
async def dev_panel_handler(client, callback_query):
    if callback_query.from_user.id not in devs_list:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مطور", callback_data="dev_add_dev")],
        [InlineKeyboardButton("💳 إضافة اشتراك لمستخدم", callback_data="dev_add_sub")],
        [InlineKeyboardButton("🖼️ إضافة صورة تلغيم", callback_data="dev_add_photo")],
        [InlineKeyboardButton("🔘 إضافة زر شفاف", callback_data="dev_add_button")],
        [InlineKeyboardButton("👨‍💻 حساب المطور الأساسي", url=f"https://t.me/{MAIN_DEV_USERNAME}")]
    ])
    await callback_query.message.edit_text("⚙️ **لوحة التحكم المتقدمة للمطور**", reply_markup=keyboard)

@bot.on_callback_query(filters.regex("dev_add_dev"))
async def cb_add_dev(client, callback_query):
    if callback_query.from_user.id != MAIN_DEV_ID:
        await callback_query.answer("⚠️ المطور الأساسي فقط يمكنه إضافة مطورين.", show_alert=True)
        return
    user_states[callback_query.from_user.id] = {"step": "wait_add_dev"}
    await callback_query.message.reply_text("أرسل آيدي المطور الجديد:")

@bot.on_callback_query(filters.regex("dev_add_sub"))
async def cb_add_sub(client, callback_query):
    if callback_query.from_user.id not in devs_list:
        return
    user_states[callback_query.from_user.id] = {"step": "wait_sub_id"}
    await callback_query.message.reply_text("أرسل آيدي المستخدم المراد تفعيل الاشتراك له:")

@bot.on_callback_query(filters.regex("dev_add_photo"))
async def cb_add_photo(client, callback_query):
    if callback_query.from_user.id not in devs_list:
        return
    user_states[callback_query.from_user.id] = {"step": "wait_dev_photo"}
    await callback_query.message.reply_text("قم بإرسال الصورة الآن ليتم إضافتها إلى قائمة التبديل التلقائي:")

@bot.on_callback_query(filters.regex("dev_add_button"))
async def cb_add_button(client, callback_query):
    if callback_query.from_user.id not in devs_list:
        return
    user_states[callback_query.from_user.id] = {"step": "wait_button_text"}
    await callback_query.message.reply_text("أرسل نص الزر الشفاف الذي تريد ظهوره في البوت:")

@bot.on_callback_query(filters.regex("user_add_group"))
async def cb_add_group(client, callback_query):
    await callback_query.message.reply_text("أرسل رابط المجموعة للانضمام إليها عبر الحساب:")
    user_states[callback_query.from_user.id] = {"step": "wait_link"}

# ---------------- RUN BOT ----------------
async def main():
    await bot.start()
    await user_account.start()
    print("🤖 البوت والحساب الشخصي يعملان بكامل الخصائص!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
