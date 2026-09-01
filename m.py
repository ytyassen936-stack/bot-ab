import os
import json
import asyncio
from aiohttp import web
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.sessions import StringSession

# مكتبة تشغيل الصوت في المكالمات الجماعية
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# ==================== [ إعدادات البوت الأساسية ] ====================
API_ID = int(os.environ.get("API_ID", 34733680))            # API_ID الخاص بك
API_HASH = os.environ.get("API_HASH", "dc47a14a8d693f8afbb73237d2ad7de8")       # API_HASH الخاص بك
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8989979653:AAHs6E9-33n5DdOLtU6hvn4LNW5wgsSRy4Q")    # BOT_TOKEN الخاص بك

SUDO_ID = int(os.environ.get("SUDO_ID", 7493679412))          # آيدي المطور الأساسي
DEV_USERNAME = os.environ.get("DEV_USERNAME", "XX7X6") # يوزر المطور بدون @

bot = TelegramClient("VoiceTrainingBot", API_ID, API_HASH)

# ==================== [ قاعدة البيانات ] ====================
DATA_FILE = "bot_database.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "developers": [SUDO_ID],
        "blocked_users": [],
        "activated_groups": [],
        "providers": {},
        "free_mode": True,
        "dev_username": DEV_USERNAME,
        "assistant_session": None
    }

def save_data(db_data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving database: {e}")

db = load_data()
user_states = {}
temp_clients = {}  # لتخزين كينسيت الهواتف المؤقتة أثناء التسجيل برقم الهاتف

# ==================== [ لوحات التحكم والأزرار الشفافة ] ====================

def get_dev_link():
    dev_user = db.get("dev_username", DEV_USERNAME).replace("@", "")
    return f"https://t.me/{dev_user}"

async def main_keyboard(user_id):
    me = await bot.get_me()
    buttons = [
        [Button.url("➕ إضافة إلى مجموعة", f"https://t.me/{me.username}?startgroup=true")],
        [Button.inline("📖 دليل الاستخدام", data="user_guide"),
         Button.url("👨‍💻 المطور", get_dev_link())]
    ]
    if user_id in db["developers"]:
        buttons.append([Button.inline("⚙️ إعدادات المطورين", data="dev_settings")])
    return buttons

def dev_keyboard():
    free_status = "مفعل 🟢" if db.get("free_mode", True) else "معطل 🔴"
    assistant_status = "مربوط ✅" if db.get("assistant_session") else "غير مربوط ❌"
    
    return [
        [Button.inline("➕ إضافة مطور", data="add_dev_id"),
         Button.inline("👤 تغيير يوزر المطور", data="change_dev_user")],
        [Button.inline(f"📱 ربط الحساب المساعد ({assistant_status})", data="assistant_menu"),
         Button.inline("🚫 حظر شخص", data="block_user")],
        [Button.inline(f"🆓 الوضع المجاني: {free_status}", data="toggle_free_mode")],
        [Button.inline("🎙️ إعدادات المقدمين", data="provider_settings"),
         Button.inline("📦 نسخ احتياطي", data="take_backup")],
        [Button.inline("🔙 رجوع", data="main_menu")]
    ]

def assistant_menu_keyboard():
    return [
        [Button.inline("📞 تسجيل الدخول برقم الهاتف", data="login_by_phone")],
        [Button.inline("🔑 طريقة كود الـ Session (مباشرة)", data="add_assistant_session")],
        [Button.inline("🗑️ حذف الحساب المساعد الحالي", data="remove_assistant")],
        [Button.inline("🔙 رجوع", data="dev_settings")]
    ]

def provider_settings_keyboard():
    buttons = [
        [Button.inline("➕ إضافة مقدم", data="add_provider"),
         Button.inline("🗑️ حذف مقدم", data="remove_provider")]
    ]
    for p_id, p_data in db["providers"].items():
        buttons.append([Button.inline(f"🎙️ {p_data.get('name', p_id)}", data=f"manage_prov_{p_id}")])
    buttons.append([Button.inline("🔙 رجوع", data="dev_settings")])
    return buttons

def provider_voices_keyboard(p_id):
    p_data = db["providers"].get(p_id, {})
    num_status = "✅" if p_data.get("numbers") else "❌"
    word_status = "✅" if p_data.get("words") else "❌"
    rand_status = "✅" if p_data.get("random") else "❌"

    return [
        [Button.inline(f"🔢 أرقام ({num_status})", data=f"upload_voice_{p_id}_numbers")],
        [Button.inline(f"📝 كلمات ({word_status})", data=f"upload_voice_{p_id}_words")],
        [Button.inline(f"🔀 عشوائي ({rand_status})", data=f"upload_voice_{p_id}_random")],
        [Button.inline("🔙 رجوع لإعدادات المقدمين", data="provider_settings")]
    ]

# ==================== [ الأوامر والتفعيل ] ====================

@bot.on(events.NewMessage(pattern=r"^/start$", incoming=True))
async def start_handler(event):
    if not event.is_private:
        return
    user_id = event.sender_id
    if user_id in db["blocked_users"]:
        return await event.reply("❌ أنت محظور من استخدام هذا البوت.")
    
    user_states.pop(user_id, None)
    sender = await event.get_sender()
    first_name = sender.first_name if sender else "المستخدم"
    
    await event.reply(
        f"أهلاً بك **{first_name}** في بوت التدريب الصوتي! 🎙️\n\nاختر من الأزرار أدناه للتحكم:",
        buttons=await main_keyboard(user_id)
    )

@bot.on(events.NewMessage(pattern=r"^تفعيل$"))
async def activate_group(event):
    if event.is_private:
        return
    chat_id = event.chat_id
    user_id = event.sender_id

    is_admin = False
    if user_id in db["developers"]:
        is_admin = True
    else:
        try:
            part = await bot(GetParticipantRequest(chat_id, user_id))
            if isinstance(part.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                is_admin = True
        except Exception:
            pass

    if not is_admin:
        return await event.reply("❌ هذا الأمر محصور بمشرفي المجموعة فقط.")

    if chat_id not in db["activated_groups"]:
        db["activated_groups"].append(chat_id)
        save_data(db)

    buttons = [
        [Button.inline("📖 دليل الاستخدام", data="user_guide"),
         Button.url("👨‍💻 المطور", get_dev_link())]
    ]
    await event.reply("✅ **تم تفعيل البوت بنجاح في هذه المجموعة!**\n\nقم بفتح الاتصال الصوتي أولاً ثم أرسل: `ابداء التدريب الصوتي`", buttons=buttons)

# ==================== [ تشغيل الصوت في الاتصال ] ====================

@bot.on(events.NewMessage(pattern=r"^(ابداء التدريب الصوتي|ابدأ التدريب الصوتي)$"))
async def start_voice_training(event):
    if event.is_private:
        return
    chat_id = event.chat_id

    if chat_id not in db["activated_groups"]:
        return await event.reply("⚠️ المجموعة غير مفعلة! أرسل `تفعيل` أولاً.")

    if not db.get("assistant_session"):
        return await event.reply("❌ لم يتم ربط الحساب المساعد بعد من قبل المطور!")

    file_to_play = None
    for p_id, p_data in db.get("providers", {}).items():
        file_to_play = p_data.get("numbers") or p_data.get("words") or p_data.get("random")
        if file_to_play and os.path.exists(file_to_play):
            break

    if not file_to_play:
        return await event.reply("⚠️ لم يتم العثور على أي ملف صوتي محجوز في إعدادات المقدمين.")

    msg = await event.reply("🎙️ **جاري صعود الحساب المساعد للمكالمة الصوتية...**")

    try:
        assistant = TelegramClient(StringSession(db["assistant_session"]), API_ID, API_HASH)
        await assistant.connect()

        if not await assistant.is_user_authorized():
            await assistant.disconnect()
            return await msg.edit("❌ جلسة الحساب المساعد منتهية أو غير صالحة. يرجى إعادة ربطه من اللوحة.")

        call_py = PyTgCalls(assistant)
        await call_py.start()

        await call_py.join_group_call(
            chat_id,
            MediaStream(file_to_play, video_flags=MediaStream.Flags.IGNORE)
        )

        await msg.edit("✅ **صعد الحساب المساعد إلى المكالمة بنجاح وبدأ قراءة الصوتيات في الاتصال!** 🎙️")

    except Exception as e:
        await msg.edit(
            f"❌ **حدث خطأ عند صعود الاتصال الصوتي:**\n`{e}`\n\n"
            "⚠️ **خطوات التأكد:**\n"
            "1️⃣ تأكد من **فتح المكالمة الصوتية (Voice Chat)** في الكروب يدوياً أولاً.\n"
            "2️⃣ تأكد من أن الحساب المساعد موجود في المجموعة ويمتلك صلاحية التحدث."
        )

# ==================== [ معالجة المدخلات والنصوص ] ====================

@bot.on(events.NewMessage(incoming=True))
async def process_inputs(event):
    if not event.is_private:
        return

    user_id = event.sender_id
    if user_id not in db["developers"]:
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    text = event.text.strip() if event.text else ""

    # 1. إدخال رقم الهواتف للحساب المساعد
    if action == "awaiting_phone_number":
        phone = text
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent = await client.send_code_request(phone)
            temp_clients[user_id] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}
            user_states[user_id] = {"action": "awaiting_phone_code"}
            await event.reply("📲 **تم إرسال كود التحقق إلى حسابك في تلغرام.**\n\nأرسل الكود الآن (مع مسافات أو أرقام متصلة):")
        except Exception as e:
            await event.reply(f"❌ حدث خطأ أثناء إرسال الكود:\n`{e}`\n\nأعد المحاولة بالضغط على زر تسجيل الدخول برقم الهاتف مجدداً.")
            user_states.pop(user_id, None)
        return

    # 2. إدخال كود التحقق المرسل
    elif action == "awaiting_phone_code":
        code = text.replace(" ", "")
        data = temp_clients.get(user_id)
        if not data:
            user_states.pop(user_id, None)
            return await event.reply("❌ انتهت الجلسة المؤقتة. يرجى البدء من جديد.")
        
        client = data["client"]
        phone = data["phone"]
        phone_code_hash = data["phone_code_hash"]

        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            session_str = client.session.save()
            db["assistant_session"] = session_str
            save_data(db)
            me = await client.get_me()
            await client.disconnect()
            temp_clients.pop(user_id, None)
            user_states.pop(user_id, None)
            await event.reply(
                f"✅ **تم تسجيل الدخول وربط الحساب المساعد بنجاح!**\n\n"
                f"👤 الاسم: **{me.first_name}**\n"
                f"🆔 الآيدي: `{me.id}`"
            )
        except Exception as e:
            if "SessionPasswordNeededError" in str(e) or "two-step" in str(e).lower():
                user_states[user_id] = {"action": "awaiting_2fa_password"}
                await event.reply("🔒 **الحساب محمي بالتحقق بخطوتين (كلمة مرور رئيسية).**\n\nأرسل كلمة المرور الخاصة بحسابك الآن:")
            else:
                await event.reply(f"❌ الكود غير صحيح أو حدث خطأ:\n`{e}`")
        return

    # 3. إدخال كلمة المرور للتحقق بخطوتين (2FA)
    elif action == "awaiting_2fa_password":
        password = text
        data = temp_clients.get(user_id)
        if not data:
            user_states.pop(user_id, None)
            return await event.reply("❌ انتهت الجلسة المؤقتة. يرجى البدء من جديد.")
        
        client = data["client"]
        try:
            await client.sign_in(password=password)
            session_str = client.session.save()
            db["assistant_session"] = session_str
            save_data(db)
            me = await client.get_me()
            await client.disconnect()
            temp_clients.pop(user_id, None)
            user_states.pop(user_id, None)
            await event.reply(
                f"✅ **تم تسجيل الدخول وتخطي التحقق بخطوتين بنجاح!**\n\n"
                f"👤 الاسم: **{me.first_name}**\n"
                f"🆔 الآيدي: `{me.id}`"
            )
        except Exception as e:
            await event.reply(f"❌ كلمة المرور غير صحيحة:\n`{e}`")
            user_states.pop(user_id, None)
        return

    # استلام الملف الصوتي وحفظه
    elif action == "awaiting_voice":
        p_id = state.get("provider_id")
        v_type = state.get("voice_type")

        if event.voice or event.audio or event.document:
            try:
                os.makedirs("voices", exist_ok=True)
                file_path = f"voices/{p_id}_{v_type}.ogg"
                await event.download_media(file=file_path)

                if p_id not in db["providers"]:
                    db["providers"][p_id] = {"name": p_id, "numbers": None, "words": None, "random": None}

                db["providers"][p_id][v_type] = file_path
                save_data(db)

                await event.reply(
                    f"✅ **تم حفظ المقطع الصوتي لـ ({v_type}) بنجاح!**",
                    buttons=provider_voices_keyboard(p_id)
                )
                user_states.pop(user_id, None)
            except Exception as e:
                await event.reply(f"❌ حدث خطأ أثناء حفظ الملف الصوتي:\n`{e}`")
        else:
            await event.reply("❌ يرجى إرسال مقطع صوتي / فويس حصراً.")
        return

    # ربط الحساب المساعد عن طريق الـ Session String المباشر
    elif action == "awaiting_assistant_session":
        session_str = text.strip()
        try:
            temp_client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await temp_client.connect()
            if await temp_client.is_user_authorized():
                me = await temp_client.get_me()
                db["assistant_session"] = session_str
                save_data(db)
                await temp_client.disconnect()
                await event.reply(
                    f"✅ **تم ربط الحساب المساعد بنجاح!**\n\n"
                    f"👤 الاسم: **{me.first_name}**\n"
                    f"🆔 الآيدي: `{me.id}`"
                )
            else:
                await temp_client.disconnect()
                await event.reply("❌ كود الـ Session غير صالح أو منتهي الصلاحية.")
        except Exception as e:
            await event.reply(f"❌ حدث خطأ أثناء فحص الـ Session:\n`{e}`")
        user_states.pop(user_id, None)

    elif action == "awaiting_dev_id":
        try:
            new_dev = int(text)
            if new_dev not in db["developers"]:
                db["developers"].append(new_dev)
                save_data(db)
            await event.reply(f"✅ تم إضافة المطور `{new_dev}` بنجاح.")
        except ValueError:
            await event.reply("❌ يرجى إرسال آيدي رقمي صحيح.")
        user_states.pop(user_id, None)

    elif action == "awaiting_dev_user":
        db["dev_username"] = text.replace("@", "")
        save_data(db)
        await event.reply(f"✅ تم تحديث يوزر المطور إلى: @{db['dev_username']}")
        user_states.pop(user_id, None)

    elif action == "awaiting_block_id":
        try:
            target_id = int(text)
            if target_id not in db["blocked_users"]:
                db["blocked_users"].append(target_id)
                save_data(db)
            await event.reply(f"🚫 تم حظر المستخدم `{target_id}` بنجاح.")
        except ValueError:
            await event.reply("❌ يرجى إرسال آيدي رقمي صحيح.")
        user_states.pop(user_id, None)

    elif action == "awaiting_provider_id":
        user_states[user_id] = {"action": "awaiting_provider_name", "provider_id": text}
        await event.reply("👍 ممتاز، أرسل الآن **اسم المقدم**: ")

    elif action == "awaiting_provider_name":
        p_id = state.get("provider_id")
        p_name = text
        db["providers"][p_id] = {"name": p_name, "numbers": None, "words": None, "random": None}
        save_data(db)

        await event.reply(
            f"✅ **تم حفظ المقدم [{p_name}] بنجاح!**",
            buttons=provider_voices_keyboard(p_id)
        )
        user_states.pop(user_id, None)

# ==================== [ الأزرار الشفافة Callbacks ] ====================

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    user_id = event.sender_id

    if data == "main_menu":
        await event.edit("القائمة الرئيسية للبوت:", buttons=await main_keyboard(user_id))

    elif data == "user_guide":
        guide_text = (
            "📖 **دليل التشغيل والتدريب الصوتي:**\n\n"
            "1️⃣ قم بإضافة البوت للمجموعة وارفعه مشرفاً.\n"
            "2️⃣ افتح المحادثة الصوتية (Voice Chat) في الكروب.\n"
            "3️⃣ أرسل أمر `تفعيل` داخل المجموعة.\n"
            "4️⃣ أرسل `ابداء التدريب الصوتي` ليصعد الحساب المساعد مباشرة إلى المحادثة الصوتية ويقرأ الصوت المقترن."
        )
        await event.edit(guide_text, buttons=[[Button.inline("🔙 رجوع", data="main_menu")]])

    elif data == "dev_settings" and user_id in db["developers"]:
        await event.edit("🛠️ **لوحة إعدادات المطورين:**", buttons=dev_keyboard())

    elif data == "assistant_menu" and user_id in db["developers"]:
        await event.edit("📱 **ربط الحساب المساعد:**", buttons=assistant_menu_keyboard())

    elif data == "login_by_phone" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_phone_number"}
        await event.edit("📞 **أرسل رقم هاتف الحساب المساعد الآن (مع رمز الدولة، مثلاً: `+9647xxxxxxxxx`):**")

    elif data == "add_assistant_session" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_assistant_session"}
        await event.edit("🔑 **أرسل كود الـ String Session للحساب المساعد الآن:**")

    elif data == "remove_assistant" and user_id in db["developers"]:
        db["assistant_session"] = None
        save_data(db)
        await event.answer("✅ تم حذف الحساب المساعد.", alert=True)
        await event.edit("📱 **ربط الحساب المساعد:**", buttons=assistant_menu_keyboard())

    elif data == "add_dev_id" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_dev_id"}
        await event.edit("📥 أرسل **آيدي الحساب (ID)** لإضافته كمطور:")

    elif data == "change_dev_user" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_dev_user"}
        await event.edit("👤 أرسل **يوزر حسابك الجديد** بدون @:")

    elif data == "block_user" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_block_id"}
        await event.edit("🚫 أرسل **آيدي المستخدم** المراد حظره:")

    elif data == "toggle_free_mode" and user_id in db["developers"]:
        db["free_mode"] = not db.get("free_mode", True)
        save_data(db)
        await event.edit("🛠️ **لوحة إعدادات المطورين:**", buttons=dev_keyboard())

    elif data == "take_backup" and user_id in db["developers"]:
        save_data(db)
        if os.path.exists(DATA_FILE):
            await bot.send_file(user_id, DATA_FILE, caption="📦 **ملف النسخة الاحتياطية لقاعدة البيانات.**")
            await event.answer("✅ تم إرسال النسخة الاحتياطية!", alert=True)

    elif data == "provider_settings" and user_id in db["developers"]:
        await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())

    elif data == "add_provider" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_provider_id"}
        await event.edit("📥 أرسل **آيدي حساب المقدم**: ")

    elif data.startswith("manage_prov_") and user_id in db["developers"]:
        p_id = data.split("_")[2]
        await event.edit("⚙️ اختر نوع الصوتية لرفعها للمقدم:", buttons=provider_voices_keyboard(p_id))

    elif data.startswith("upload_voice_") and user_id in db["developers"]:
        parts = data.split("_")
        p_id, v_type = parts[2], parts[3]
        user_states[user_id] = {"action": "awaiting_voice", "provider_id": p_id, "voice_type": v_type}
        await event.edit(f"🎙️ أرسل الآن **الفويس الصوتي** لقسم ({v_type}):")

    elif data == "remove_provider" and user_id in db["developers"]:
        if not db["providers"]:
            return await event.answer("❌ لا يوجد مقدمين لحذفهم.", alert=True)
        
        buttons = []
        for p_id, p_data in db["providers"].items():
            buttons.append([Button.inline(f"❌ {p_data.get('name', p_id)}", data=f"del_prov_{p_id}")])
        buttons.append([Button.inline("🔙 رجوع", data="provider_settings")])
        await event.edit("🗑️ اختر المقدم المراد حذفه:", buttons=buttons)

    elif data.startswith("del_prov_") and user_id in db["developers"]:
        p_id = data.split("_")[2]
        if p_id in db["providers"]:
            del db["providers"][p_id]
            save_data(db)
            await event.answer("✅ تم حذف المقدم بنجاح.", alert=True)
        await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())

# ==================== [ خادم الويب وتوافق Render ] ====================

async def handle(request):
    return web.Response(text="Bot is running successfully!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

if __name__ == "__main__":
    print("🚀 تم تشغيل البوت وسيرفر الويب بنجاح...")
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    bot.start(bot_token=BOT_TOKEN)
    bot.run_until_disconnected()
