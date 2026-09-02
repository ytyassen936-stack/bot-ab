import os
import json
import re
import asyncio
import wave
import contextlib
from aiohttp import web
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.messages import ExportChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.sessions import StringSession
from telethon.errors import (
    MessageNotModifiedError, UserAlreadyParticipantError,
    PhoneNumberInvalidError, PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError,
    FloodWaitError
)

from pytgcalls import PyTgCalls

AudioStreamClass = None
try:
    from pytgcalls.types import AudioPiped as AudioStreamClass
except ImportError:
    try:
        from pytgcalls.types.input_stream import AudioPiped as AudioStreamClass
    except ImportError:
        try:
            from pytgcalls.types import MediaStream as AudioStreamClass
        except ImportError:
            pass

API_ID = int(os.environ.get("API_ID", 34733680))
API_HASH = os.environ.get("API_HASH", "dc47a14a8d693f8afbb73237d2ad7de8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8766360875:AAFUL_3pXZ8MdKoTeusTmKOJh6aKGte26vw")

ADMIN_ID = int(os.environ.get("ADMIN_ID", 7493679412))
DEV_USERNAME = os.environ.get("DEV_USERNAME", "XX7X6")

# استخدام sequential_updates لمنع التوازيات التي تسبب تكرار الردود في Telethon
bot = TelegramClient("voice_bot_session", API_ID, API_HASH, sequential_updates=True)
assistant_client = None
pytgcalls_client = None

DATA_FILE = "bot_database.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "developers": [ADMIN_ID],
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
login_clients = {}
active_sessions = {}
chat_locks = {}
processed_messages = set()

def get_lock(chat_id):
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()
    return chat_locks[chat_id]

def normalize_text(text):
    if not text:
        return ""
    text = re.sub(r'[\s\-_.\u064B-\u0652]', '', str(text))
    text = text.replace('ة', 'ه').replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    return text.lower()

def extract_numbers(text):
    if not text:
        return ""
    return "".join(re.findall(r'\d+', str(text)))

def get_dev_link():
    dev_user = db.get("dev_username", DEV_USERNAME).replace("@", "")
    return f"https://t.me/{dev_user}"

def get_audio_duration(file_path):
    try:
        if file_path.endswith('.wav'):
            with contextlib.closing(wave.open(file_path, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return frames / float(rate)
    except Exception:
        pass
    return 3.0

async def auto_backup_loop():
    while True:
        await asyncio.sleep(12 * 3600)
        try:
            save_data(db)
            print("💾 تم إجراء النسخ الاحتياطي التلقائي بنجاح.")
        except Exception as e:
            print(f"❌ خطأ في النسخ الاحتياطي: {e}")

async def main_keyboard(user_id):
    me = await bot.get_me()
    buttons = [
        [Button.url("➕ إضافة إلى مجموعة", f"https://t.me/{me.username}?startgroup=true")],
        [Button.inline("📖 دليل الاستخدام", data="user_guide"), Button.url("👨‍💻 المطور", get_dev_link())]
    ]
    if user_id in db.get("developers", []):
        buttons.append([Button.inline("⚙️ إعدادات المطورين", data="dev_settings")])
    return buttons

def dev_keyboard():
    free_status = "مفعل 🟢" if db.get("free_mode", True) else "معطل 🔴"
    assistant_status = "مربوط ✅" if db.get("assistant_session") else "غير مربوط ❌"
    return [
        [Button.inline("➕ إضافة مطور", data="add_dev_id"), Button.inline("🗑️ حذف مطور", data="remove_dev_menu")],
        [Button.inline("👤 تغيير يوزر المطور", data="change_dev_user"), Button.inline("🚫 حظر شخص", data="block_user")],
        [Button.inline(f"📱 ربط الحساب المساعد ({assistant_status})", data="assistant_menu")],
        [Button.inline(f"🆓 الوضع المجاني: {free_status}", data="toggle_free_mode")],
        [Button.inline("🎙️ إعدادات المقدمين", data="provider_settings"), Button.inline("📦 تحميل النسخة الحالية", data="take_backup")],
        [Button.inline("🔙 رجوع", data="main_menu")]
    ]

def remove_dev_keyboard():
    buttons = []
    devs = db.get("developers", [])
    for dev_id in devs:
        if dev_id != ADMIN_ID:
            buttons.append([Button.inline(f"❌ حذف: {dev_id}", data=f"delete_dev_{dev_id}")])
    buttons.append([Button.inline("🔙 رجوع", data="dev_settings")])
    return buttons

def assistant_menu_keyboard():
    return [
        [Button.inline("📞 تسجيل الدخول برقم الهاتف", data="login_by_phone")],
        [Button.inline("🗑️ حذف الحساب المساعد الحالي", data="remove_assistant")],
        [Button.inline("🔙 رجوع", data="dev_settings")]
    ]

def provider_settings_keyboard():
    buttons = [[Button.inline("➕ إضافة مقدم", data="add_provider")]]
    for p_id, p_data in db.get("providers", {}).items():
        buttons.append([Button.inline(f"🎙️ {p_data.get('name', p_id)}", data=f"manage_prov_{p_id}")])
    buttons.append([Button.inline("🔙 رجوع", data="dev_settings")])
    return buttons

def provider_voices_keyboard(p_id):
    p_data = db.get("providers", {}).get(p_id, {})
    num_count = len(p_data.get("voices", {}).get("numbers", []))
    word_count = len(p_data.get("voices", {}).get("words", []))
    rand_count = len(p_data.get("voices", {}).get("random", []))

    return [
        [Button.inline(f"🔢 أرقام ({num_count})", data=f"upload_voice_{p_id}_numbers"),
         Button.inline(f"📝 كلمات ({word_count})", data=f"upload_voice_{p_id}_words")],
        [Button.inline(f"🔀 عشوائي ({rand_count})", data=f"upload_voice_{p_id}_random")],
        [Button.inline("🗑️ حذف فويس معين", data=f"delete_voice_{p_id}")],
        [Button.inline("❌ حذف المقدم بالكامل", data=f"delete_provider_{p_id}")],
        [Button.inline("🔙 رجوع لإعدادات المقدمين", data="provider_settings")]
    ]

def group_providers_keyboard():
    return [[Button.inline(f"🎙️ {p_data.get('name', p_id)}", data=f"select_prov_{p_id}")] for p_id, p_data in db.get("providers", {}).items()]

def group_types_keyboard(p_id):
    return [
        [Button.inline("🔢 قسم الأرقام", data=f"start_play_{p_id}_numbers"), Button.inline("📝 قسم الكلمات", data=f"start_play_{p_id}_words")],
        [Button.inline("🔀 قسم العشوائي", data=f"start_play_{p_id}_random")],
        [Button.inline("🔙 إلغاء", data="close_menu")]
    ]

async def init_assistant_session():
    global assistant_client, pytgcalls_client
    session_str = db.get("assistant_session")
    if session_str:
        try:
            assistant_client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await assistant_client.connect()
            if await assistant_client.is_user_authorized():
                pytgcalls_client = PyTgCalls(assistant_client)
                await pytgcalls_client.start()
                print("✅ تم اتصال الحساب المساعد بنجاح!")
            else:
                assistant_client = None
                pytgcalls_client = None
        except FloodWaitError as e:
            print(f"⚠️ حظر مؤقت لتليجرام: {e.seconds} ثانية.")
            assistant_client = None
            pytgcalls_client = None
        except Exception as e:
            print(f"❌ خطأ الحساب المساعد: {e}")
            assistant_client = None
            pytgcalls_client = None

async def stop_and_leave_call(chat_id):
    sess = active_sessions.get(chat_id)
    if sess:
        if sess.get("timer_task"):
            sess["timer_task"].cancel()
        try:
            if pytgcalls_client:
                if hasattr(pytgcalls_client, 'leave_group_call'):
                    await pytgcalls_client.leave_group_call(chat_id)
                elif hasattr(pytgcalls_client, 'leave_call'):
                    await pytgcalls_client.leave_call(chat_id)
        except Exception:
            pass
        active_sessions.pop(chat_id, None)

async def auto_skip_timer(chat_id, expected_idx, wait_time):
    await asyncio.sleep(wait_time)
    async with get_lock(chat_id):
        sess = active_sessions.get(chat_id)
        if sess and sess["index"] == expected_idx:
            queue = sess["queue"]
            if expected_idx < len(queue):
                target_text = queue[expected_idx].get("text", "")
                await bot.send_message(chat_id, f"⚠️ **تسكيب تلقائي:** محد تجاوب (`{target_text}`)")
                sess["index"] += 1
                await play_current_voice(chat_id)

async def play_current_voice(chat_id):
    sess = active_sessions.get(chat_id)
    if not sess or not pytgcalls_client:
        return

    if sess.get("timer_task"):
        sess["timer_task"].cancel()
        sess["timer_task"] = None

    idx = sess["index"]
    queue = sess["queue"]

    if idx >= len(queue):
        await bot.send_message(chat_id, "✅ **انتهاء الصوتيات في هذا القسم.**")
        await stop_and_leave_call(chat_id)
        return

    file_path = queue[idx].get("file")
    try:
        stream = AudioStreamClass(file_path)
        if hasattr(pytgcalls_client, 'change_stream'):
            await pytgcalls_client.change_stream(chat_id, stream)
        elif hasattr(pytgcalls_client, 'join_group_call'):
            await pytgcalls_client.join_group_call(chat_id, stream)
        elif hasattr(pytgcalls_client, 'play'):
            await pytgcalls_client.play(chat_id, stream)
    except Exception as e:
        print(f"Error streaming audio: {e}")

    duration = get_audio_duration(file_path)
    sess["timer_task"] = asyncio.create_task(auto_skip_timer(chat_id, idx, duration + 4.0))

# ==================== [ المعالجات ] ====================

@bot.on(events.NewMessage(func=lambda e: e.is_private))
async def private_handler(event):
    if event.out:
        return

    msg_id = event.id
    if msg_id in processed_messages:
        return
    processed_messages.add(msg_id)
    if len(processed_messages) > 500:
        processed_messages.pop()

    text = event.raw_text.strip() if event.raw_text else ""
    user_id = event.sender_id

    if text.startswith("/start"):
        if user_id in db.get("blocked_users", []):
            return await event.reply("❌ أنت محظور.")
        user_states.pop(user_id, None)
        sender = await event.get_sender()
        name = sender.first_name if sender else "المستخدم"
        return await event.reply(f"أهلاً بك **{name}** في بوت التدريب الصوتي!", buttons=await main_keyboard(user_id))

    if user_id in db.get("developers", []) and user_id in user_states:
        state = user_states[user_id]
        action = state.get("action")

        if action == "awaiting_phone_number":
            phone = text.replace(" ", "").replace("-", "").strip()
            msg = await event.reply("🔄 جاري طلب الكود...")
            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                sent_code = await client.send_code_request(phone, force_sms=False)
                login_clients[user_id] = {
                    "client": client, "phone": phone, "phone_code_hash": sent_code.phone_code_hash
                }
                user_states[user_id] = {"action": "awaiting_phone_code"}
                return await msg.edit("📲 **أرسل الكود الآن مع إدخال مسافات بين الأرقام:**")
            except Exception as e:
                user_states.pop(user_id, None)
                return await msg.edit(f"❌ خطأ: `{e}`")

        elif action == "awaiting_phone_code":
            sess_data = login_clients.get(user_id)
            if not sess_data:
                user_states.pop(user_id, None)
                return await event.reply("❌ انتهت الجلسة.")

            client = sess_data["client"]
            code = re.sub(r'\D', '', text)
            msg = await event.reply("🔄 جاري التحقق...")
            try:
                await client.sign_in(phone=sess_data["phone"], code=code, phone_code_hash=sess_data["phone_code_hash"])
                db["assistant_session"] = client.session.save()
                save_data(db)
                login_clients.pop(user_id, None)
                user_states.pop(user_id, None)
                await init_assistant_session()
                return await msg.edit("✅ **تم ربط الحساب المساعد بنجاح!**")
            except SessionPasswordNeededError:
                user_states[user_id] = {"action": "awaiting_2fa"}
                return await msg.edit("🔐 أرسل كلمة سر التحقق بخطوتين:")
            except Exception as e:
                return await msg.edit(f"❌ خطأ الكود: `{e}`")

        elif action == "awaiting_2fa":
            sess_data = login_clients.get(user_id)
            if not sess_data:
                user_states.pop(user_id, None)
                return await event.reply("❌ انتهت الجلسة.")
            client = sess_data["client"]
            msg = await event.reply("🔄 جاري التحقق...")
            try:
                await client.sign_in(password=text)
                db["assistant_session"] = client.session.save()
                save_data(db)
                login_clients.pop(user_id, None)
                user_states.pop(user_id, None)
                await init_assistant_session()
                return await msg.edit("✅ **تم تفعيل الحساب المساعد بنجاح!**")
            except Exception as e:
                return await msg.edit(f"❌ كلمة سر خاطئة: `{e}`")

        elif action == "awaiting_voice_to_delete":
            p_id = state.get("provider_id")
            voices_db = db["providers"].get(p_id, {}).get("voices", {})
            deleted = 0
            for cat in ["numbers", "words", "random"]:
                if cat in voices_db:
                    new_list = []
                    for item in voices_db[cat]:
                        if item.get("text", "").strip() == text:
                            deleted += 1
                            if os.path.exists(item.get("file", "")):
                                try: os.remove(item.get("file", ""))
                                except Exception: pass
                        else:
                            new_list.append(item)
                    voices_db[cat] = new_list
            save_data(db)
            user_states.pop(user_id, None)
            return await event.reply(f"✅ تم حذف {deleted} فويس.", buttons=provider_voices_keyboard(p_id))

        elif action == "awaiting_voice":
            if event.voice or event.audio or event.document:
                os.makedirs("voices", exist_ok=True)
                p_id, v_type = state.get("provider_id"), state.get("voice_type")
                path = f"voices/{p_id}_{v_type}_{os.urandom(4).hex()}.ogg"
                await event.download_media(file=path)
                user_states[user_id] = {"action": "awaiting_voice_text", "provider_id": p_id, "voice_type": v_type, "file_path": path}
                return await event.reply("👍 أرسل النص المطابق للصوتية:")

        elif action == "awaiting_voice_text":
            p_id, v_type, path = state.get("provider_id"), state.get("voice_type"), state.get("file_path")
            if p_id not in db["providers"]:
                db["providers"][p_id] = {"name": p_id, "voices": {"numbers": [], "words": [], "random": []}}
            db["providers"][p_id]["voices"][v_type].append({"file": path, "text": text})
            save_data(db)
            user_states.pop(user_id, None)
            return await event.reply(f"✅ تم حفظ الصوتية ونصها: `{text}`", buttons=provider_voices_keyboard(p_id))

        elif action == "awaiting_provider_id":
            user_states[user_id] = {"action": "awaiting_provider_name", "provider_id": text}
            return await event.reply("أرسل اسم المقدم:")

        elif action == "awaiting_provider_name":
            p_id = state.get("provider_id")
            db["providers"][p_id] = {"name": text, "voices": {"numbers": [], "words": [], "random": []}}
            save_data(db)
            user_states.pop(user_id, None)
            return await event.reply("✅ تم الحفظ.", buttons=provider_voices_keyboard(p_id))

        elif action == "awaiting_dev_id":
            try:
                new_dev = int(text)
                if new_dev not in db["developers"]:
                    db["developers"].append(new_dev)
                    save_data(db)
                    await event.reply("✅ تم إضافته كمطور بنجاح.")
                else:
                    await event.reply("⚠️ المطور موجود بالفعل.")
            except ValueError:
                await event.reply("❌ يرجى إدخال ID صحيح (أرقام فقط).")
            user_states.pop(user_id, None)
            return

        elif action == "awaiting_dev_user":
            db["dev_username"] = text.replace("@", "")
            save_data(db)
            user_states.pop(user_id, None)
            return await event.reply("✅ تم التحديث.")

        elif action == "awaiting_block_id":
            try: db["blocked_users"].append(int(text)); save_data(db); await event.reply("🚫 تم الحظر.")
            except ValueError: pass
            user_states.pop(user_id, None)
            return

@bot.on(events.NewMessage(func=lambda e: e.is_group or e.is_channel))
async def group_handler(event):
    if event.out:
        return

    msg_id = event.id
    if msg_id in processed_messages:
        return
    processed_messages.add(msg_id)
    if len(processed_messages) > 500:
        processed_messages.pop()

    chat_id = event.chat_id
    text = event.raw_text.strip() if event.raw_text else ""
    user_id = event.sender_id

    if text == "تفعيل":
        is_admin = user_id in db.get("developers", [])
        if not is_admin:
            try:
                part = await bot(GetParticipantRequest(chat_id, user_id))
                if isinstance(part.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    is_admin = True
            except Exception:
                is_admin = True

        if not is_admin:
            return await event.reply("❌ هذا الأمر مخصص لمشرفي المجموعة فقط.")

        if "activated_groups" not in db:
            db["activated_groups"] = []

        if chat_id not in db["activated_groups"]:
            db["activated_groups"].append(chat_id)
            save_data(db)

        return await event.reply("✅ **تم تفعيل البوت في هذه المجموعة بنجاح!**\nأرسل الآن: `ابداء التدريب الصوتي`")

    elif text in ["ابداء التدريب الصوتي", "ابدأ التدريب الصوتي"]:
        if chat_id not in db.get("activated_groups", []):
            return await event.reply("⚠️ المجموعة غير مفعلة! أرسل كلمة `تفعيل` أولاً.")
        if not db.get("providers"):
            return await event.reply("❌ لا يوجد مقدمين مضافين في البوت بعد.")
        return await event.reply("🎙️ اختر المقدم:", buttons=group_providers_keyboard())

    elif text == "انزل":
        if chat_id in active_sessions:
            await stop_and_leave_call(chat_id)
            return await event.reply("👋 تم إنهاء الجلسة والنزول من الاتصال.")
        return await event.reply("⚠️ البوت غير متصل في الاتصال الصوتي حالياً.")

    sess = active_sessions.get(chat_id)
    if sess:
        async with get_lock(chat_id):
            curr_sess = active_sessions.get(chat_id)
            if not curr_sess:
                return

            queue = curr_sess.get("queue", [])
            idx = curr_sess.get("index", 0)

            if idx < len(queue):
                target_text = queue[idx].get("text", "")
                norm_single = normalize_text(text)
                norm_target = normalize_text(target_text)
                digits_single = extract_numbers(text)
                digits_target = extract_numbers(target_text)

                matched = False
                if norm_target and (norm_target == norm_single or norm_target in norm_single):
                    matched = True
                elif digits_target and digits_single and (digits_target == digits_single or digits_target in digits_single):
                    matched = True

                if matched:
                    curr_sess["index"] += 1
                    if curr_sess.get("timer_task"):
                        curr_sess["timer_task"].cancel()
                        curr_sess["timer_task"] = None

                    await bot.send_message(chat_id, "يمك نقطه", reply_to=event.id)
                    await play_current_voice(chat_id)

async def process_start_play(event, p_id, category):
    chat_id = event.chat_id
    if not assistant_client or not pytgcalls_client:
        return await event.respond("❌ الحساب المساعد غير متصل! أضفه من إعدادات المطور أولاً.")

    voices_list = db.get("providers", {}).get(p_id, {}).get("voices", {}).get(category, [])
    if not voices_list:
        return await event.respond("⚠️ لا توجد فويسات في هذا القسم!")

    try:
        await assistant_client.get_entity(chat_id)
    except Exception:
        try:
            invite = await bot(ExportChatInviteRequest(chat_id))
            match = re.search(r'(?:joinchat/|\+)([\w-]+)', invite.link)
            if match:
                await assistant_client(ImportChatInviteRequest(match.group(1)))
        except UserAlreadyParticipantError:
            pass
        except Exception as e:
            return await event.respond(f"❌ فشل دخول الحساب المساعد: `{e}`")

    try:
        if chat_id in active_sessions:
            await stop_and_leave_call(chat_id)

        active_sessions[chat_id] = {
            "queue": voices_list, "index": 0,
            "provider_name": db.get("providers", {}).get(p_id, {}).get("name", p_id),
            "category_name": category, "timer_task": None
        }
        await play_current_voice(chat_id)
        await event.delete()
    except Exception as e:
        await event.respond(f"❌ خطأ التشغيل: `{e}`")

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    user_id = event.sender_id

    try:
        if data == "close_menu":
            await event.delete()
        elif data == "main_menu":
            await event.edit("القائمة الرئيسية:", buttons=await main_keyboard(user_id))
        elif data == "user_guide":
            await event.edit("📖 **دليل الاستخدام:**\n1. أضف البوت للمجموعة.\n2. اكتب `تفعيل`.\n3. اكتب `ابداء التدريب الصوتي`.", buttons=[[Button.inline("🔙 رجوع", data="main_menu")]])
        elif data == "dev_settings" and user_id in db.get("developers", []):
            await event.edit("🛠️ إعدادات المطورين:", buttons=dev_keyboard())
        elif data == "remove_dev_menu" and user_id in db.get("developers", []):
            await event.edit("🗑️ اختر المطور المراد حذفه من القائمة:", buttons=remove_dev_keyboard())
        elif data.startswith("delete_dev_") and user_id in db.get("developers", []):
            target_dev = int(data.split("_")[2])
            if target_dev in db["developers"]:
                db["developers"].remove(target_dev)
                save_data(db)
                await event.answer("✅ تم حذف المطور بنجاح.", alert=True)
            await event.edit("🗑️ اختر المطور المراد حذفه من القائمة:", buttons=remove_dev_keyboard())
        elif data == "assistant_menu" and user_id in db.get("developers", []):
            await event.edit("📱 ربط الحساب المساعد:", buttons=assistant_menu_keyboard())
        elif data == "login_by_phone" and user_id in db.get("developers", []):
            user_states[user_id] = {"action": "awaiting_phone_number"}
            await event.edit("📞 أرسل رقم الهاتف المساعد بالصيغة الدولية:")
        elif data == "remove_assistant" and user_id in db.get("developers", []):
            db["assistant_session"] = None
            save_data(db)
            await event.answer("✅ تم الحذف", alert=True)
            await event.edit("📱 ربط الحساب المساعد:", buttons=assistant_menu_keyboard())
        elif data == "add_dev_id" and user_id in db.get("developers", []):
            user_states[user_id] = {"action": "awaiting_dev_id"}
            await event.edit("📥 أرسل ID المطور الجديد:")
        elif data == "change_dev_user" and user_id in db.get("developers", []):
            user_states[user_id] = {"action": "awaiting_dev_user"}
            await event.edit("👤 أرسل اليوزر الجديد:")
        elif data == "block_user" and user_id in db.get("developers", []):
            user_states[user_id] = {"action": "awaiting_block_id"}
            await event.edit("🚫 أرسل ID المراد حظره:")
        elif data == "toggle_free_mode" and user_id in db.get("developers", []):
            db["free_mode"] = not db.get("free_mode", True)
            save_data(db)
            await event.edit("🛠️ إعدادات المطورين:", buttons=dev_keyboard())
        elif data == "take_backup" and user_id in db.get("developers", []):
            save_data(db)
            if os.path.exists(DATA_FILE):
                await bot.send_file(user_id, DATA_FILE, caption="📦 النسخة الاحتياطية الحالية.")
        elif data == "provider_settings" and user_id in db.get("developers", []):
            await event.edit("🎙️ إعدادات المقدمين:", buttons=provider_settings_keyboard())
        elif data == "add_provider" and user_id in db.get("developers", []):
            user_states[user_id] = {"action": "awaiting_provider_id"}
            await event.edit("📥 أرسل معرف (ID) المقدم:")
        elif data.startswith("manage_prov_") and user_id in db.get("developers", []):
            p_id = data.split("_")[2]
            await event.edit("⚙️ اختر النوع:", buttons=provider_voices_keyboard(p_id))
        elif data.startswith("delete_provider_") and user_id in db.get("developers", []):
            p_id = data.split("_")[2]
            if p_id in db["providers"]:
                del db["providers"][p_id]
                save_data(db)
            await event.edit("🎙️ إعدادات المقدمين:", buttons=provider_settings_keyboard())
        elif data.startswith("delete_voice_") and user_id in db.get("developers", []):
            p_id = data.split("_")[2]
            user_states[user_id] = {"action": "awaiting_voice_to_delete", "provider_id": p_id}
            await event.edit("🗑️ أرسل نص الفويس المراد حذفه:")
        elif data.startswith("upload_voice_") and user_id in db.get("developers", []):
            parts = data.split("_")
            user_states[user_id] = {"action": "awaiting_voice", "provider_id": parts[2], "voice_type": parts[3]}
            await event.edit(f"🎙️ أرسل الملف الصوتي لقسم ({parts[3]}):")
        elif data.startswith("select_prov_"):
            p_id = data.split("_")[2]
            await event.edit(f"🎙️ المقدم المحدد: {db['providers'].get(p_id, {}).get('name', p_id)}", buttons=group_types_keyboard(p_id))
        elif data.startswith("start_play_"):
            parts = data.split("_")
            p_id, category = parts[2], parts[3]
            await event.edit("🎙️ جاري دخول الحساب المساعد للاتصال...")
            asyncio.create_task(process_start_play(event, p_id, category))

    except MessageNotModifiedError:
        pass

async def handle_ping(request):
    return web.Response(text="Bot Active")

async def main():
    app_web = web.Application()
    app_web.router.add_get('/', handle_ping)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    await bot.start(bot_token=BOT_TOKEN)
    await init_assistant_session()
    
    asyncio.create_task(auto_backup_loop())

    print("🚀 تم تشغيل البوت بنجاح.")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
