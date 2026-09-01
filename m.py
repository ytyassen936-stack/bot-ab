import os
import json
import re
import asyncio
import threading
import time
from flask import Flask
from waitress import serve
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.sessions import StringSession
from telethon.errors import MessageNotModifiedError, FloodWaitError

# ==================== [ استدعاء ذكي لـ PyTgCalls ] ====================
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

# ==================== [ خادم الويب لـ Render ] ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running successfully!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    serve(app, host="0.0.0.0", port=port)

threading.Thread(target=run_web_server, daemon=True).start()

# ==================== [ إعدادات البوت الأساسية ] ====================
API_ID = int(os.environ.get("API_ID", 34733680))
API_HASH = os.environ.get("API_HASH", "8766360875:AAFUL_3pXZ8MdKoTeusTmKOJh6aKGte26vw")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

ADMIN_ID = int(os.environ.get("ADMIN_ID", 7493679412))
DEV_USERNAME = os.environ.get("DEV_USERNAME", "XX7X6")

bot = TelegramClient("voice_bot_session", API_ID, API_HASH)

# ==================== [ قاعدة البيانات والذاكرة المؤقتة ] ====================
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
temp_clients = {}
active_sessions = {}

# 🛡️ حماية قصوى ضد التكرار: تخزين الأي دي الخاص بالرسائل المعالجة
processed_msg_ids = set()
bot_id = None

# ==================== [ دوال تنظيف وتحليل النصوص والأرقام ] ====================

def normalize_text(text):
    if not text:
        return ""
    text = re.sub(r'[\s\-_.\u064B-\u0652]', '', str(text))
    text = text.replace('ة', 'ه')
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    return text.lower()

def extract_numbers(text):
    if not text:
        return ""
    digits = re.findall(r'\d+', str(text))
    return "".join(digits)

# ==================== [ الأزرار واللوحات ] ====================

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
        [Button.inline("🗑️ حذف الحساب المساعد الحالي", data="remove_assistant")],
        [Button.inline("🔙 رجوع", data="dev_settings")]
    ]

def provider_settings_keyboard():
    buttons = [
        [Button.inline("➕ إضافة مقدم", data="add_provider")]
    ]
    for p_id, p_data in db["providers"].items():
        buttons.append([Button.inline(f"🎙️ {p_data.get('name', p_id)}", data=f"manage_prov_{p_id}")])
    buttons.append([Button.inline("🔙 رجوع", data="dev_settings")])
    return buttons

def provider_voices_keyboard(p_id):
    p_data = db["providers"].get(p_id, {})
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
    buttons = []
    for p_id, p_data in db.get("providers", {}).items():
        buttons.append([Button.inline(f"🎙️ {p_data.get('name', p_id)}", data=f"select_prov_{p_id}")])
    return buttons

def group_types_keyboard(p_id):
    return [
        [Button.inline("🔢 قسم الأرقام", data=f"start_play_{p_id}_numbers"),
         Button.inline("📝 قسم الكلمات", data=f"start_play_{p_id}_words")],
        [Button.inline("🔀 قسم العشوائي", data=f"start_play_{p_id}_random")],
        [Button.inline("🔙 إلغاء", data="close_menu")]
    ]

# ==================== [ الأوامر والتفعيل والخروج ] ====================

@bot.on(events.NewMessage(pattern=r"^/start$"))
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
    await event.reply("✅ **تم تفعيل البوت بنجاح في هذه المجموعة!**\n\nأرسل الان: `ابداء التدريب الصوتي`", buttons=buttons)

@bot.on(events.NewMessage(pattern=r"^(ابداء التدريب الصوتي|ابدأ التدريب الصوتي)$"))
async def start_voice_training_group(event):
    if event.is_private:
        return
    chat_id = event.chat_id

    if chat_id not in db["activated_groups"]:
        return await event.reply("⚠️ المجموعة غير مفعلة! اكتب `تفعيل` أولاً.")

    if not db.get("providers"):
        return await event.reply("❌ لا يوجد مقدمين مضافين حالياً.")

    await event.reply("🎙️ **اختر المقدم للبدء في المحادثة الصوتية:**", buttons=group_providers_keyboard())

@bot.on(events.NewMessage(pattern=r"^انزل$"))
async def leave_voice_call(event):
    if event.is_private:
        return
    chat_id = event.chat_id
    if chat_id in active_sessions:
        await stop_and_leave_call(chat_id)
        await event.reply("👋 تم نزول الحساب المساعد من الاتصال الصوتي.")
    else:
        await event.reply("⚠️ الحساب المساعد غير موجود في اتصال هذا الكروب حالياً.")

async def stop_and_leave_call(chat_id):
    sess = active_sessions.get(chat_id)
    if sess:
        if sess.get("timer_task"):
            sess["timer_task"].cancel()
        try:
            call_py = sess.get("pytgcalls")
            if hasattr(call_py, 'leave_group_call'):
                await call_py.leave_group_call(chat_id)
            elif hasattr(call_py, 'leave_call'):
                await call_py.leave_call(chat_id)
            await sess["assistant"].disconnect()
        except Exception:
            pass
        active_sessions.pop(chat_id, None)

# ==================== [ تشغيل الصوت وتأقيت التسكيب التلقائي ] ====================

async def auto_skip_timer(chat_id, expected_idx):
    await asyncio.sleep(3)
    sess = active_sessions.get(chat_id)
    if not sess:
        return

    lock = sess["lock"]
    async with lock:
        if sess["index"] == expected_idx:
            queue = sess["queue"]
            if expected_idx < len(queue):
                target_item = queue[expected_idx]
                target_text = target_item.get("text", "")
                
                await bot.send_message(chat_id, f"⚠️ **تم تسكيب الصوتية:** `{target_text}` (محد جاوب)")
                
                sess["index"] += 1
                await play_current_voice(chat_id)

async def play_current_voice(chat_id):
    sess = active_sessions.get(chat_id)
    if not sess:
        return

    if sess.get("timer_task"):
        sess["timer_task"].cancel()
        sess["timer_task"] = None

    idx = sess["index"]
    queue = sess["queue"]

    if idx >= len(queue):
        p_name = sess["provider_name"]
        cat_name = sess["category_name"]
        await bot.send_message(chat_id, f"✅ **تم انتهاء الفئة ({cat_name}) للمقدم ({p_name})**")
        await stop_and_leave_call(chat_id)
        return

    current_item = queue[idx]
    file_path = current_item.get("file")

    try:
        call_py = sess["pytgcalls"]
        stream = AudioStreamClass(file_path)
        if hasattr(call_py, 'change_stream'):
            await call_py.change_stream(chat_id, stream)
        elif hasattr(call_py, 'join_group_call'):
            await call_py.join_group_call(chat_id, stream)
        elif hasattr(call_py, 'play'):
            await call_py.play(chat_id, stream)
    except Exception:
        try:
            if hasattr(call_py, 'join_group_call'):
                await call_py.join_group_call(chat_id, stream)
        except Exception:
            pass

    sess["timer_task"] = asyncio.create_task(auto_skip_timer(chat_id, idx))

# ==================== [ استجابة الدردشة - معالجة الحماية القاطعة من التكرار ] ====================

@bot.on(events.NewMessage(func=lambda e: not e.is_private))
async def handle_group_chat_trigger(event):
    if not event.text:
        return

    # 1. منع تكرار نفس أحدث الرسائل نهائياً باستعمال ID الرسالة
    unique_msg_identifier = f"{event.chat_id}_{event.id}"
    if unique_msg_identifier in processed_msg_ids:
        return
    processed_msg_ids.add(unique_msg_identifier)

    # تنظيف الذاكرة المؤقتة من المعرفات القديمة لعدم استهلاك الذاكرة
    if len(processed_msg_ids) > 2000:
        processed_msg_ids.clear()

    global bot_id
    if not bot_id:
        me = await bot.get_me()
        bot_id = me.id

    # 2. تجاهل رسايل البوت نفسه
    if event.sender_id == bot_id:
        return

    chat_id = event.chat_id
    sess = active_sessions.get(chat_id)
    if not sess:
        return

    lock = sess["lock"]
    async with lock:
        queue = sess["queue"]
        idx = sess["index"]

        if idx >= len(queue):
            return

        target_item = queue[idx]
        target_text = target_item.get("text", "")
        if not target_text:
            return

        raw_text = event.text.strip()
        norm_single = normalize_text(raw_text)
        norm_target = normalize_text(target_text)

        digits_single = extract_numbers(raw_text)
        digits_target = extract_numbers(target_text)

        matched = False

        if norm_target and (norm_target == norm_single or norm_target in norm_single):
            matched = True

        if not matched and digits_target and digits_single:
            if digits_target == digits_single or digits_target in digits_single:
                matched = True

        if matched:
            # 🛑 زيادة رقم الصوتية فوراً داخل الـ lock حتى لو وصلت رسائل أخرى بنفس اللحظة
            sess["index"] += 1

            if sess.get("timer_task"):
                sess["timer_task"].cancel()
                sess["timer_task"] = None

            await event.reply("يمك نقطه")
            await play_current_voice(chat_id)

# ==================== [ معالجة المدخلات والحذف ] ====================

@bot.on(events.NewMessage(func=lambda e: e.is_private))
async def process_inputs(event):
    if event.text and event.text.startswith("/start"):
        return

    user_id = event.sender_id
    if user_id not in db["developers"]:
        return

    state = user_states.get(user_id)
    if not state:
        return

    action = state.get("action")
    text = event.text.strip() if event.text else ""

    if action == "awaiting_voice_to_delete":
        p_id = state.get("provider_id")
        to_delete = text.strip()
        
        provider = db["providers"].get(p_id, {})
        voices_db = provider.get("voices", {})
        
        deleted_count = 0
        for cat in ["numbers", "words", "random"]:
            if cat in voices_db:
                new_list = []
                for item in voices_db[cat]:
                    if item.get("text", "").strip() == to_delete:
                        deleted_count += 1
                        if os.path.exists(item.get("file", "")):
                            try:
                                os.remove(item.get("file", ""))
                            except Exception:
                                pass
                    else:
                        new_list.append(item)
                voices_db[cat] = new_list

        save_data(db)
        user_states.pop(user_id, None)

        if deleted_count > 0:
            await event.reply(f"✅ **تم حذف {deleted_count} فويس يطابق المحتوى:** `{to_delete}`", buttons=provider_voices_keyboard(p_id))
        else:
            await event.reply(f"❌ لم يتم العثور على أي فويس بمحتوى: `{to_delete}`", buttons=provider_voices_keyboard(p_id))

    elif action == "awaiting_phone_number":
        phone = text.replace(" ", "")
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent = await client.send_code_request(phone)
            temp_clients[user_id] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}
            user_states[user_id] = {"action": "awaiting_phone_code"}
            await event.reply("📲 **تم إرسال كود التحقق.** أرسل الكود الآن:")
        except Exception as e:
            await event.reply(f"❌ خطأ عند إرسال الكود:\n`{e}`")
            user_states.pop(user_id, None)

    elif action == "awaiting_phone_code":
        code = text.replace(" ", "")
        data = temp_clients.get(user_id)
        if not data:
            user_states.pop(user_id, None)
            return await event.reply("❌ انتهت الجلسة.")
        
        client = data["client"]
        try:
            await client.sign_in(phone=data["phone"], code=code, phone_code_hash=data["phone_code_hash"])
            session_str = client.session.save()
            db["assistant_session"] = session_str
            save_data(db)
            me = await client.get_me()
            await client.disconnect()
            temp_clients.pop(user_id, None)
            user_states.pop(user_id, None)
            await event.reply(f"✅ **تم تسجيل الدخول ورابط الحساب المساعد ({me.first_name}) وحفظه بنجاح!**")
        except Exception as e:
            if "SessionPasswordNeededError" in str(e) or "two-step" in str(e).lower():
                user_states[user_id] = {"action": "awaiting_2fa_password"}
                await event.reply("🔒 **أرسل كلمة السر للتحقق بخطوتين:**")
            else:
                await event.reply(f"❌ خطأ تسجيل الدخول:\n`{e}`")
                user_states.pop(user_id, None)

    elif action == "awaiting_2fa_password":
        data = temp_clients.get(user_id)
        if not data:
            user_states.pop(user_id, None)
            return await event.reply("❌ انتهت الجلسة.")
        client = data["client"]
        try:
            await client.sign_in(password=text)
            session_str = client.session.save()
            db["assistant_session"] = session_str
            save_data(db)
            me = await client.get_me()
            await client.disconnect()
            temp_clients.pop(user_id, None)
            user_states.pop(user_id, None)
            await event.reply(f"✅ **تم تسجيل الدخول ورابط الحساب المساعد ({me.first_name}) وحفظه بنجاح!**")
        except Exception as e:
            await event.reply(f"❌ كلمة المرور غير صحيحة:\n`{e}`")
            user_states.pop(user_id, None)

    elif action == "awaiting_voice":
        if event.voice or event.audio or event.document:
            try:
                os.makedirs("voices", exist_ok=True)
                p_id = state.get("provider_id")
                v_type = state.get("voice_type")
                file_path = f"voices/{p_id}_{v_type}_{os.urandom(4).hex()}.ogg"
                await event.download_media(file=file_path)

                user_states[user_id] = {
                    "action": "awaiting_voice_text",
                    "provider_id": p_id,
                    "voice_type": v_type,
                    "file_path": file_path
                }
                await event.reply("👍 **تم استلام الصوتية!**\nالان أرسل **النص/الكلمة/الرقم** المطابق لهذه الصوتية:")
            except Exception as e:
                await event.reply(f"❌ حدث خطأ:\n`{e}`")
        else:
            await event.reply("❌ يرجى إرسال فويس صوتي.")

    elif action == "awaiting_voice_text":
        p_id = state.get("provider_id")
        v_type = state.get("voice_type")
        file_path = state.get("file_path")
        trigger_text = text

        if p_id not in db["providers"]:
            db["providers"][p_id] = {"name": p_id, "voices": {"numbers": [], "words": [], "random": []}}

        if "voices" not in db["providers"][p_id]:
            db["providers"][p_id]["voices"] = {"numbers": [], "words": [], "random": []}

        db["providers"][p_id]["voices"][v_type].append({
            "file": file_path,
            "text": trigger_text
        })
        save_data(db)

        await event.reply(f"✅ **تم ربط الفويس بنجاح مع الكلمة:** `{trigger_text}`", buttons=provider_voices_keyboard(p_id))
        user_states.pop(user_id, None)

    elif action == "awaiting_dev_id":
        try:
            new_dev = int(text)
            if new_dev not in db["developers"]:
                db["developers"].append(new_dev)
                save_data(db)
            await event.reply(f"✅ تم إضافة المطور `{new_dev}`.")
        except ValueError:
            await event.reply("❌ أرسل آيدي صحيح.")
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
            await event.reply(f"🚫 تم حظر `{target_id}`.")
        except ValueError:
            await event.reply("❌ أرسل آيدي صحيح.")
        user_states.pop(user_id, None)

    elif action == "awaiting_provider_id":
        user_states[user_id] = {"action": "awaiting_provider_name", "provider_id": text}
        await event.reply("👍 ممتاز، أرسل الآن **اسم المقدم**: ")

    elif action == "awaiting_provider_name":
        p_id = state.get("provider_id")
        p_name = text
        db["providers"][p_id] = {"name": p_name, "voices": {"numbers": [], "words": [], "random": []}}
        save_data(db)
        await event.reply(f"✅ **تم حفظ المقدم [{p_name}] بنجاح!**", buttons=provider_voices_keyboard(p_id))
        user_states.pop(user_id, None)

# ==================== [ الأزرار الشفافة Callbacks ] ====================

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")
    user_id = event.sender_id
    chat_id = event.chat_id

    try:
        if data == "close_menu":
            return await event.delete()
        elif data == "main_menu":
            await event.edit("القائمة الرئيسية للبوت:", buttons=await main_keyboard(user_id))
        elif data == "user_guide":
            guide_text = "📖 **دليل التشغيل والتدريب الصوتي:**\n\n1️⃣ أضف البوت وارفعه مشرفاً.\n2️⃣ افتح الاتصال الصوتي في الكروب.\n3️⃣ أرسل `تفعيل` ثم `ابداء التدريب الصوتي`."
            await event.edit(guide_text, buttons=[[Button.inline("🔙 رجوع", data="main_menu")]])
        elif data == "dev_settings" and user_id in db["developers"]:
            await event.edit("🛠️ **لوحة إعدادات المطورين:**", buttons=dev_keyboard())
        elif data == "assistant_menu" and user_id in db["developers"]:
            await event.edit("📱 **ربط الحساب المساعد:**", buttons=assistant_menu_keyboard())
        elif data == "login_by_phone" and user_id in db["developers"]:
            user_states[user_id] = {"action": "awaiting_phone_number"}
            await event.edit("📞 **أرسل رقم هاتف الحساب المساعد (مثال: +9647700000000):**")
        elif data == "remove_assistant" and user_id in db["developers"]:
            db["assistant_session"] = None
            save_data(db)
            await event.answer("✅ تم حذف الحساب المساعد.", alert=True)
            await event.edit("📱 **ربط الحساب المساعد:**", buttons=assistant_menu_keyboard())
        elif data == "add_dev_id" and user_id in db["developers"]:
            user_states[user_id] = {"action": "awaiting_dev_id"}
            await event.edit("📥 أرسل **آيدي الحساب (ID)**:")
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
                await bot.send_file(user_id, DATA_FILE, caption="📦 **ملف النسخة الاحتياطية.**")
                await event.answer("✅ تم إرسال النسخة الاحتياطية!", alert=True)
        elif data == "provider_settings" and user_id in db["developers"]:
            await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())
        elif data == "add_provider" and user_id in db["developers"]:
            user_states[user_id] = {"action": "awaiting_provider_id"}
            await event.edit("📥 أرسل **آيدي حساب المقدم**: ")
        elif data.startswith("manage_prov_") and user_id in db["developers"]:
            p_id = data.split("_")[2]
            await event.edit("⚙️ اختر نوع الفويس لإضافته أو حذفه للمقدم:", buttons=provider_voices_keyboard(p_id))
        elif data.startswith("delete_provider_") and user_id in db["developers"]:
            p_id = data.split("_")[2]
            if p_id in db["providers"]:
                p_name = db["providers"][p_id].get("name", p_id)
                for cat in ["numbers", "words", "random"]:
                    for item in db["providers"][p_id].get("voices", {}).get(cat, []):
                        if os.path.exists(item.get("file", "")):
                            try:
                                os.remove(item.get("file", ""))
                            except Exception:
                                pass
                del db["providers"][p_id]
                save_data(db)
                await event.answer(f"🗑️ تم حذف المقدم ({p_name}) بنجاح!", alert=True)
            await event.edit("🎙️ **إعدادات المقدمين:**", buttons=provider_settings_keyboard())
        elif data.startswith("delete_voice_") and user_id in db["developers"]:
            p_id = data.split("_")[2]
            user_states[user_id] = {"action": "awaiting_voice_to_delete", "provider_id": p_id}
            await event.edit("🗑️ أرسل **محتوى الفويس المراد حذفه** (مثلاً أرسل `56` أو الكلمة):")
        elif data.startswith("upload_voice_") and user_id in db["developers"]:
            parts = data.split("_")
            p_id, v_type = parts[2], parts[3]
            user_states[user_id] = {"action": "awaiting_voice", "provider_id": p_id, "voice_type": v_type}
            await event.edit(f"🎙️ أرسل الآن **الفويس الصوتي** لقسم ({v_type}):")
        elif data.startswith("select_prov_"):
            p_id = data.split("_")[2]
            p_name = db["providers"].get(p_id, {}).get("name", p_id)
            await event.edit(f"🎙️ **المقدم المختارات:** {p_name}\nاختر الفئة المطلوبة للتدريب:", buttons=group_types_keyboard(p_id))
        elif data.startswith("start_play_"):
            parts = data.split("_")
            p_id, category = parts[2], parts[3]

            saved_session = db.get("assistant_session")
            if not saved_session:
                return await event.answer("❌ لم يتم ربط الحساب المساعد بعد!", alert=True)

            voices_list = db.get("providers", {}).get(p_id, {}).get("voices", {}).get(category, [])
            if not voices_list:
                return await event.answer("⚠️ لا توجد فويسات مرفوعة لهذه الفئة!", alert=True)

            p_name = db.get("providers", {}).get(p_id, {}).get("name", p_id)
            category_ar = {"numbers": "الأرقام", "words": "الكلمات", "random": "العشوائي"}.get(category, category)

            await event.edit(f"🎙️ **جاري صعود الحساب المساعد للاتصال لبدء فئة ({category_ar})...**")

            try:
                if chat_id in active_sessions:
                    await stop_and_leave_call(chat_id)

                assistant = TelegramClient(StringSession(saved_session), API_ID, API_HASH)
                await assistant.connect()

                call_py = PyTgCalls(assistant)
                await call_py.start()

                active_sessions[chat_id] = {
                    "pytgcalls": call_py,
                    "assistant": assistant,
                    "queue": voices_list,
                    "index": 0,
                    "provider_name": p_name,
                    "category_name": category_ar,
                    "lock": asyncio.Lock(),
                    "timer_task": None
                }

                await play_current_voice(chat_id)
                await event.delete()
            except Exception as e:
                await event.respond(f"❌ **تعذر الانضمام للمكالمة الصوتية:**\n`{e}`")

    except MessageNotModifiedError:
        pass

# ==================== [ التشغيل الأساسي ومعالجة FloodWait ] ====================

def run_bot_safe():
    print("🚀 جاري تشغيل البوت...")
    while True:
        try:
            bot.start(bot_token=BOT_TOKEN)
            print("✅ تم اتصال البوت بنجاح ويستقبل الرسائل الان!")
            bot.run_until_disconnected()
            break
        except FloodWaitError as e:
            print(f"⚠️ تليجرام فرض انتظار لمدة {e.seconds} ثانية (FloodWaitError)...")
            time.sleep(e.seconds + 5)
        except Exception as e:
            print(f"❌ خطأ غير متوقع: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot_safe()

