import os
import json
import asyncio
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import (
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
    PasswordHashInvalidError
)

# ==================== [ إعدادات البوت الأساسية ] ====================
API_ID = 34733680              # ضع API_ID الخاص بك هنا (رقم)
API_HASH = "dc47a14a8d693f8afbb73237d2ad7de8"      # ضع API_HASH الخاص بك هنا
BOT_TOKEN = "8989979653:AAFIc8-0CGN-8403v6B1chNs3MyRU56Dtdk"    # ضع توكن البوت هنا

SUDO_ID = 7493679412             # أيدي المطور الأساسي (رقم)
DEV_USERNAME = "XX7X6"  # يوزر المطور بدون @

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
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db_data, f, ensure_ascii=False, indent=4)

db = load_data()
user_states = {}

# ==================== [ الأزرار الشفافة ] ====================

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
        [Button.inline(f"📱 إضافة حساب مساعد ({assistant_status})", data="add_assistant"),
         Button.inline("🚫 حظر شخص", data="block_user")],
        [Button.inline("📢 إذاعة", data="broadcast"),
         Button.inline(f"🆓 الوضع المجاني: {free_status}", data="toggle_free_mode")],
        [Button.inline("🎙️ إعدادات المقدمين", data="provider_settings"),
         Button.inline("📦 نسخ احتياطي", data="take_backup")],
        [Button.inline("🔙 رجوع", data="main_menu")]
    ]

def provider_settings_keyboard():
    buttons = [
        [Button.inline("➕ إضافة مقدم", data="add_provider"),
         Button.inline("🗑️ حذف مقدم", data="remove_provider")]
    ]
    for p_id, p_data in db["providers"].items():
        buttons.append([Button.inline(f"🎙️ {p_data['name']}", data=f"manage_prov_{p_id}")])
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
        f"أهلاً بك **{first_name}** في بوت التدريب الصوتي! 🎙️\n\nاختر من الأزرار أدناه:",
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
    await event.reply("✅ **تم تفعيل البوت بنجاح في هذه المجموعة!**\n\nللبدء أرسل: `ابداء التدريب الصوتي`", buttons=buttons)

# ==================== [ معالجة البدء والتدريب الصوتي ] ====================

@bot.on(events.NewMessage(pattern=r"^(ابداء التدريب الصوتي|ابدأ التدريب الصوتي)$"))
async def start_voice_training(event):
    if event.is_private:
        return
    chat_id = event.chat_id

    if chat_id not in db["activated_groups"]:
        return await event.reply("⚠️ المجموعة غير مفعلة! أرسل `تفعيل` أولاً.")

    file_to_play = None
    for p_id, p_data in db.get("providers", {}).items():
        file_to_play = p_data.get("numbers") or p_data.get("words") or p_data.get("random")
        if file_to_play:
            break

    if not file_to_play:
        return await event.reply("⚠️ لم يتم العثور على أي ملف صوتي مسجل في إعدادات المقدمين.")

    msg = await event.reply("🎙️ **جاري بدء جلسة التدريب الصوتي...**")

    try:
        await bot.send_file(chat_id, file_to_play, voice_note=True, caption="🎙️ مقطع التدريب الصوتي")
        await msg.delete()
    except Exception as e:
        await msg.edit(f"❌ حدث خطأ أثناء إرسال الصوتية:\n`{e}`")

# ==================== [ معالجة مدخلات النصوص للمطور ] ====================

@bot.on(events.NewMessage(incoming=True))
async def process_inputs(event):
    if not event.is_private or event.text.startswith("/"):
        return

    user_id = event.sender_id
    if user_id not in db["developers"]:
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    text = event.text.strip() if event.text else ""

    if action == "awaiting_dev_id":
        try:
            new_dev = int(text)
            if new_dev not in db["developers"]:
                db["developers"].append(new_dev)
                save_data(db)
                await event.reply(f"✅ تم إضافة المطور `{new_dev}` بنجاح.")
            else:
                await event.reply("⚠️ هذا الحساب مطور بالفعل.")
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

    elif action == "awaiting_assistant_phone":
        from telethon.sessions import StringSession
        phone_number = text.replace(" ", "")
        temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        try:
            await temp_client.connect()
            code_info = await temp_client.send_code_request(phone_number)
            user_states[user_id] = {
                "action": "awaiting_assistant_code",
                "client": temp_client,
                "phone_number": phone_number,
                "phone_code_hash": code_info.phone_code_hash
            }
            await event.reply("📩 تم إرسال كود التحقيق إلى حسابك في تليجرام.\n\nأرسل **الكود** الآن:")
        except PhoneNumberInvalidError:
            await event.reply("❌ رقم الهاتف غير صحيح. حاول مرة أخرى.")
            user_states.pop(user_id, None)
        except Exception as e:
            await event.reply(f"❌ حدث خطأ عند إرسال الكود:\n`{e}`")
            user_states.pop(user_id, None)

    elif action == "awaiting_assistant_code":
        temp_client = state["client"]
        phone_number = state["phone_number"]
        phone_code_hash = state["phone_code_hash"]
        phone_code = text.replace(" ", "")

        try:
            await temp_client.sign_in(phone=phone_number, code=phone_code, phone_code_hash=phone_code_hash)
            session_string = temp_client.session.save()
            await temp_client.disconnect()

            db["assistant_session"] = session_string
            save_data(db)

            user_states.pop(user_id, None)
            await event.reply("✅ **تم تسجيل الدخول وحفظ الحساب المساعد بنجاح!**")
        except SessionPasswordNeededError:
            user_states[user_id]["action"] = "awaiting_assistant_password"
            await event.reply("🔐 هذا الحساب مدمج بالتحقق بخطوتين.\nأرسل **باسورد الحساب (2FA)**:")
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await event.reply("❌ الكود غير صحيح أو منتهي الصلاحية. يرجى البدء من جديد.")
            await temp_client.disconnect()
            user_states.pop(user_id, None)
        except Exception as e:
            await event.reply(f"❌ حدث خطأ:\n`{e}`")
            await temp_client.disconnect()
            user_states.pop(user_id, None)

    elif action == "awaiting_assistant_password":
        temp_client = state["client"]
        password = text

        try:
            await temp_client.sign_in(password=password)
            session_string = temp_client.session.save()
            await temp_client.disconnect()

            db["assistant_session"] = session_string
            save_data(db)

            user_states.pop(user_id, None)
            await event.reply("✅ **تم التحقق من الباسورد وتسجيل الحساب المساعد بنجاح!**")
        except PasswordHashInvalidError:
            await event.reply("❌ الباسورد غير صحيح. حاول إرساله مرة أخرى:")
        except Exception as e:
            await event.reply(f"❌ حدث خطأ أثناء فحص الباسورد:\n`{e}`")
            await temp_client.disconnect()
            user_states.pop(user_id, None)

    elif action == "awaiting_provider_id":
        user_states[user_id] = {"action": "awaiting_provider_name", "provider_id": text}
        await event.reply("👍 ممتاز، أرسل الآن **اسم المقدم**:")

    elif action == "awaiting_provider_name":
        p_id = state.get("provider_id")
        p_name = text
        db["providers"][p_id] = {"name": p_name, "numbers": None, "words": None, "random": None}
        save_data(db)

        await event.reply(
            f"✅ **تم حفظ المقدم [{p_name}] بنجاح!**\n\nاختر من اللوحة رفع الصوتيات الخاصة به:",
            buttons=provider_voices_keyboard(p_id)
        )
        user_states.pop(user_id, None)

    elif action == "awaiting_voice":
        p_id = state.get("provider_id")
        v_type = state.get("voice_type")

        if event.voice or event.audio or event.document:
            file_id = event.media
            db["providers"][p_id][v_type] = file_id
            save_data(db)

            await event.reply(
                f"✅ تم حفظ الملف الصوتي لـ **({v_type})** بنجاح!",
                buttons=provider_voices_keyboard(p_id)
            )
            user_states.pop(user_id, None)
        else:
            await event.reply("❌ يرجى إرسال مقطع صوتي / فويس.")

# ==================== [ الأزرار الشفافة Callbacks ] ====================

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    user_id = event.sender_id

    if data == "main_menu":
        await event.edit("القائمة الرئيسية للبوت:", buttons=await main_keyboard(user_id))

    elif data == "user_guide":
        guide_text = (
            "📖 **دليل الاستخدام الشامل للبوت:**\n\n"
            "1️⃣ قم بإضافة البوت للمجموعة الخاصة بك.\n"
            "2️⃣ ارفع البوت مشرفاً في المجموعة.\n"
            "3️⃣ اكتب كلمة `تفعيل` لتنشيط خدمات البوت.\n"
            "4️⃣ اكتب `ابداء التدريب الصوتي` للبدء."
        )
        buttons = [[Button.inline("🔙 رجوع", data="main_menu")]]
        await event.edit(guide_text, buttons=buttons)

    elif data == "dev_settings" and user_id in db["developers"]:
        await event.edit("🛠️ **لوحة إعدادات المطورين:**", buttons=dev_keyboard())

    elif data == "add_dev_id" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_dev_id"}
        await event.edit("📥 أرسل **آيدي الحساب (ID)** لإضافته كمطور:")

    elif data == "change_dev_user" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_dev_user"}
        await event.edit("👤 أرسل **يوزر حسابك الجديد** بدون @:")

    elif data == "add_assistant" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_assistant_phone"}
        await event.edit(
            "📱 **إضافة حساب مساعد جديد**\n\n"
            "أرسل رقم الهاتف مع رمز الدولة الآن.\n"
            "مثال: `+9647800000000`"
        )

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
            await bot.send_file(user_id, DATA_FILE, caption="📦 **ملف النسخة الاحتياطية.**")
            await event.answer("✅ تم الاستخراج بنجاح!", alert=True)

    elif data == "provider_settings" and user_id in db["developers"]:
        await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())

    elif data == "add_provider" and user_id in db["developers"]:
        user_states[user_id] = {"action": "awaiting_provider_id"}
        await event.edit("📥 أرسل **آيدي حساب المقدم**: ")

    elif data.startswith("manage_prov_") and user_id in db["developers"]:
        p_id = data.split("_")[2]
        p_name = db["providers"].get(p_id, {}).get("name", "غير معروف")
        await event.edit(
            f"⚙️ إعدادات وصوتيات المقدم: **{p_name}**",
            buttons=provider_voices_keyboard(p_id)
        )

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
            buttons.append([Button.inline(f"❌ {p_data['name']}", data=f"del_prov_{p_id}")])
        buttons.append([Button.inline("🔙 رجوع", data="provider_settings")])
        await event.edit("🗑️ اختر المقدم المراد حذفه:", buttons=buttons)

    elif data.startswith("del_prov_") and user_id in db["developers"]:
        p_id = data.split("_")[2]
        if p_id in db["providers"]:
            del db["providers"][p_id]
            save_data(db)
            await event.answer("✅ تم حذف المقدم.", alert=True)
        await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())

if __name__ == "__main__":
    print("🚀 تم تشغيل البوت بنجاح...")
    bot.start(bot_token=BOT_TOKEN)
    bot.run_until_disconnected()
