import os
import re
import json
import asyncio
import subprocess
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.request import HTTPXRequest

# ==================== الإعدادات الأساسية ====================
BOT_TOKEN = "8738113127:AAFWxlU4O_PUS_18w80uibe6RdoP6S80A_E"
OWNER_ID = 7493679412  # ضع ايديك (ID) هنا كمالك أساسي للبوت
DEVELOPER_LINK = "https://t.me/XX7X6"  # رابط حسابك المباشر مع t.me/

# الـ API ID و API HASH الثابتة الخاصة بك
API_ID = 34733680  # ضع الـ API ID الخاص بك هنا
API_HASH = "dc47a14a8d693f8afbb73237d2ad7de8"  # ضع الـ API HASH الخاص بك هنا

DB_FILE = "bot_database.json"
HOST_DIR = "./hosted_bots"

if not os.path.exists(HOST_DIR):
    os.makedirs(HOST_DIR)

# ==================== إدارة قاعدة البيانات ====================
def load_db():
    default_db = {
        "developers": [OWNER_ID],
        "banned_users": [],
        "subscribers": {},    # {"user_id": "expire_date_iso"} (1 بوت)
        "vip_subscribers": {},# {"user_id": "expire_date_iso"} (3 بوتات)
        "free_mode": False,
        "force_channel": ""
    }
    
    if not os.path.exists(DB_FILE):
        save_db(default_db)
        return default_db
    
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        updated = False
        # تحويل الهياكل القديمة (القوائم) إلى قواميس لإنفاذ التواريخ إن وجدت
        if isinstance(data.get("subscribers"), list):
            data["subscribers"] = {str(uid): (datetime.now() + timedelta(days=365)).isoformat() for uid in data["subscribers"]}
            updated = True
        if isinstance(data.get("vip_subscribers"), list):
            data["vip_subscribers"] = {str(uid): (datetime.now() + timedelta(days=365)).isoformat() for uid in data["vip_subscribers"]}
            updated = True

        for key, value in default_db.items():
            if key not in data:
                data[key] = value
                updated = True
                
        if updated:
            save_db(data)
            
        return data
    except Exception:
        save_db(default_db)
        return default_db

def save_db(db_data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_data, f, ensure_ascii=False, indent=4)

db = load_db()
running_processes = {}

# ==================== الفحص والأذونات والحدود ====================
def is_dev(user_id):
    return user_id in db.get("developers", []) or user_id == OWNER_ID

def is_banned(user_id):
    return user_id in db.get("banned_users", [])

def check_subscription_expiry(user_id):
    """التحقق من صلاحية الاشتراك وإزالته إذا انتهى الوقت"""
    uid_str = str(user_id)
    now = datetime.now()
    
    # فحص الاشتراك العادي
    if uid_str in db.get("subscribers", {}):
        exp_date = datetime.fromisoformat(db["subscribers"][uid_str])
        if now > exp_date:
            del db["subscribers"][uid_str]
            save_db(db)
            return False
        return True

    # فحص اشتراك VIP
    if uid_str in db.get("vip_subscribers", {}):
        exp_date = datetime.fromisoformat(db["vip_subscribers"][uid_str])
        if now > exp_date:
            del db["vip_subscribers"][uid_str]
            save_db(db)
            return False
        return True

    return False

def is_vip(user_id):
    if is_dev(user_id):
        return True
    uid_str = str(user_id)
    if uid_str in db.get("vip_subscribers", {}):
        return check_subscription_expiry(user_id)
    return False

def is_authorized(user_id):
    if is_dev(user_id):
        return True
    if db.get("free_mode", False):
        return True
    return check_subscription_expiry(user_id)

def get_max_bots(user_id):
    if is_dev(user_id):
        return 999  # مطور (غير محدود)
    if is_vip(user_id):
        return 3    # مشترك VIP (3 بوتات)
    if is_authorized(user_id):
        return 1    # مشترك عادي أو وضع مجاني (1 بوت)
    return 0

def get_user_files(user_id):
    prefix = f"{user_id}_"
    files = []
    if os.path.exists(HOST_DIR):
        for f in os.listdir(HOST_DIR):
            if f.startswith(prefix) and f.endswith(".py"):
                files.append(f)
    return files

async def check_force_join(user_id, bot):
    if not db.get("force_channel"):
        return True
    try:
        member = await bot.get_chat_member(chat_id=db["force_channel"], user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return True

# ==================== استخراج وتثبيت المكتبات ====================
STDLIB_MODULES = {
    'os', 'sys', 'time', 'math', 'random', 'json', 're', 'asyncio', 'datetime',
    'subprocess', 'threading', 'typing', 'sqlite3', 'urllib', 'http', 'base64',
    'hashlib', 'pathlib', 'shutil', 'logging', 'traceback', 'inspect', 'functools'
}

def extract_requirements(file_path):
    modules = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        for mod in imports:
            if mod not in STDLIB_MODULES:
                modules.add(mod)
    except Exception as e:
        print(f"خطأ في الفحص: {e}")
    return list(modules)

async def install_requirements(modules):
    if not modules:
        return True
    try:
        cmd = ["pip", "install"] + modules
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        print(f"خطأ في التثبيت: {e}")
        return False

# ==================== لوحات التحكم والأزرار ====================
def get_main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("📤 إضافة ملف", callback_data="upload_file"),
         InlineKeyboardButton("📂 ملفاتي", callback_data="my_files")],
        [InlineKeyboardButton("⚡ تشغيل ملف", callback_data="run_file_menu")],
        [InlineKeyboardButton("👨‍💻 المطور", url=DEVELOPER_LINK)]
    ]
    if is_dev(user_id):
        buttons.append([InlineKeyboardButton("⚙️ إعدادات المطورين", callback_data="dev_settings")])
    return InlineKeyboardMarkup(buttons)

def get_dev_keyboard():
    free_status = "مفعل ✅" if db.get("free_mode") else "معطل ❌"
    buttons = [
        [InlineKeyboardButton("🚫 حظر / إلغاء حظر", callback_data="toggle_ban"),
         InlineKeyboardButton("📢 إذاعة", callback_data="broadcast")],
        [InlineKeyboardButton("📢 الاشتراك الإجباري", callback_data="set_force_channel")],
        [InlineKeyboardButton(f"🆓 الوضع المجاني ({free_status})", callback_data="toggle_free")],
        [InlineKeyboardButton("➕ إضافة مشترك عادي (1 بوت)", callback_data="add_sub"),
         InlineKeyboardButton("⭐ إضافة مشترك VIP (3 بوتات)", callback_data="add_vip")],
        [InlineKeyboardButton("➕ إضافة مطور", callback_data="add_dev")],
        [InlineKeyboardButton("📦 جلب نسخة احتياطية", callback_data="get_backup"),
         InlineKeyboardButton("📥 رفع نسخة احتياطية", callback_data="restore_backup")]
    ]
    return InlineKeyboardMarkup(buttons)

# ==================== معالجة الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_banned(user_id):
        await update.message.reply_text("❌ أنت محظور من استخدام البوت.")
        return

    if not await check_force_join(user_id, context.bot):
        await update.message.reply_text(f"⚠️ يرجى الاشتراك في القناة أولاً لاستخدام البوت:\n{db['force_channel']}")
        return

    await update.message.reply_text(
        "أهلاً بك في بوت الاستضافة التلقائي!\nاختر من القائمة أدناه:",
        reply_markup=get_main_keyboard(user_id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_banned(user_id):
        await query.message.reply_text("❌ أنت محظور من استخدام البوت.")
        return

    data = query.data

    # === زر إضافة ملف ===
    if data == "upload_file":
        if not is_authorized(user_id):
            await query.message.reply_text("❌ غير مصرح لك أو انتهت مدة اشتراكك، راسل المطور لتفعيل حسابك.")
            return

        max_allowed = get_max_bots(user_id)
        current_files = get_user_files(user_id)
        if len(current_files) >= max_allowed:
            await query.message.reply_text(
                f"⚠️ لقد وصلت للحد الأقصى المسموح لك بحدود اشتراكك ({max_allowed} بوت).\n"
                f"قم بحذف ملف من قائمة (📂 ملفاتي) لرفع ملف جديد."
            )
            return

        context.user_data["awaiting_file"] = True
        await query.message.reply_text("أرسل لي الآن ملف البوت/الأداة ببرمجة Python (`.py`). وسيتم إضافته فوراً إلى قائمة ملفاتك.")

    # === زر ملفاتي ===
    elif data == "my_files":
        files = get_user_files(user_id)
        if not files:
            await query.message.reply_text("📂 لا توجد لديك أي ملفات مرفوعة حالياً في قائمة ملفاتك.")
            return

        msg = "📂 **قائمة ملفاتك المخزنة:**\n\n"
        buttons = []
        for f in files:
            clean_name = f.replace(f"{user_id}_", "")
            full_path = os.path.join(HOST_DIR, f)
            status = "مشتغل ✅" if (full_path in running_processes and running_processes[full_path].poll() is None) else "متوقف ❌"
            msg += f"• `{clean_name}` - الحالة: {status}\n"
            buttons.append([InlineKeyboardButton(f"⚡ تشغيل {clean_name}", callback_data=f"run_{f}"),
                            InlineKeyboardButton(f"🗑️ حذف", callback_data=f"del_{f}")])

        buttons.append([InlineKeyboardButton("🔙 العودة", callback_data="back_main")])
        await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    # === زر تشغيل ملف ===
    elif data == "run_file_menu":
        if not is_authorized(user_id):
            await query.message.reply_text("❌ غير مصرح لك أو انتهت مدة اشتراكك، راسل المطور لتفعيل حسابك.")
            return

        files = get_user_files(user_id)
        if not files:
            await query.message.reply_text("⚠️ لا توجد لديك ملفات مخزنة لتشغيلها. قم بإضافة ملف أولاً.")
            return

        buttons = []
        for f in files:
            clean_name = f.replace(f"{user_id}_", "")
            buttons.append([InlineKeyboardButton(f"▶️ تشغيل: {clean_name}", callback_data=f"run_{f}")])

        buttons.append([InlineKeyboardButton("🔙 العودة", callback_data="back_main")])
        await query.message.reply_text("اختر الملف الذي تريد تشغيله من قائمة ملفاتك:", reply_markup=InlineKeyboardMarkup(buttons))

    # === تشغيل ملف محدد ===
    elif data.startswith("run_"):
        file_name = data.replace("run_", "")
        file_path = os.path.join(HOST_DIR, file_name)
        
        if not os.path.exists(file_path):
            await query.message.reply_text("❌ الملف غير موجود في قائمة ملفاتك.")
            return

        # إيقاف التشغيل القديم إن وجد
        if file_path in running_processes:
            try: running_processes[file_path].terminate()
            except Exception: pass

        env = os.environ.copy()
        env["API_ID"] = str(API_ID)
        env["API_HASH"] = str(API_HASH)

        try:
            process = subprocess.Popen(["python", file_path], env=env)
            running_processes[file_path] = process
            clean_name = file_name.replace(f"{user_id}_", "")
            await query.message.reply_text(f"🚀 **تم تشغيل الملف بنجاح:** `{clean_name}`", parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ حدث خطأ أثناء التشغيل:\n`{str(e)}`", parse_mode="Markdown")

    # === حذف ملف محدد ===
    elif data.startswith("del_"):
        file_name = data.replace("del_", "")
        file_path = os.path.join(HOST_DIR, file_name)

        if file_path in running_processes:
            try: running_processes[file_path].terminate()
            except Exception: pass

        if os.path.exists(file_path):
            os.remove(file_path)
            clean_name = file_name.replace(f"{user_id}_", "")
            await query.message.reply_text(f"🗑️ تم حذف الملف `{clean_name}` من قائمة ملفاتك بنجاح.", parse_mode="Markdown")
        else:
            await query.message.reply_text("❌ الملف غير موجود.")

    elif data == "back_main":
        await query.message.reply_text("القائمة الرئيسية:", reply_markup=get_main_keyboard(user_id))

    # === إعدادات المطورين ===
    elif data == "dev_settings":
        if not is_dev(user_id):
            await query.message.reply_text("❌ هذا الخيار مخصص للمطورين فقط.")
            return
        await query.message.reply_text("⚙️ **لوحة إعدادات المطورين:**", reply_markup=get_dev_keyboard(), parse_mode="Markdown")

    elif data == "toggle_free":
        if not is_dev(user_id): return
        db["free_mode"] = not db.get("free_mode", False)
        save_db(db)
        await query.message.reply_text(f"تم تغيير الوضع المجاني إلى: {db['free_mode']}")

    elif data == "get_backup":
        if not is_dev(user_id): return
        await send_backup(context.bot, user_id)

    elif data == "toggle_ban":
        if not is_dev(user_id): return
        context.user_data["action"] = "ban"
        await query.message.reply_text("أرسل الـ ID للشخص المراد حظره أو إلغاء حظره:")

    elif data == "add_sub":
        if not is_dev(user_id): return
        context.user_data["action"] = "add_sub_step1"
        await query.message.reply_text("أرسل الـ ID للشخص المراد إضافته كمشترك عادي (1 بوت):")

    elif data == "add_vip":
        if not is_dev(user_id): return
        context.user_data["action"] = "add_vip_step1"
        await query.message.reply_text("أرسل الـ ID للشخص المراد إضافته كمشترك VIP (3 بوتات):")

    elif data == "add_dev":
        if not is_dev(user_id): return
        context.user_data["action"] = "add_dev"
        await query.message.reply_text("أرسل الـ ID للشخص المراد رفعه مطور:")

    elif data == "broadcast":
        if not is_dev(user_id): return
        context.user_data["action"] = "broadcast"
        await query.message.reply_text("أرسل النص المراد إرساله للإذاعة لجميع المشتركين:")

    elif data == "set_force_channel":
        if not is_dev(user_id): return
        context.user_data["action"] = "set_force_channel"
        await query.message.reply_text("أرسل معرف القناة مع الـ @ (مثال: `@MyChannel`) أو اتركها فارغة للإلغاء:")

    elif data == "restore_backup":
        if not is_dev(user_id): return
        context.user_data["awaiting_backup_file"] = True
        await query.message.reply_text("أرسل الآن ملف النسخة الاحتياطية (`.json`).")

# ==================== استقبال الرسائل الإدارية وتحديد الأوقات ====================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id): return

    action = context.user_data.get("action")
    text = update.message.text.strip()

    if action == "ban":
        try:
            target_id = int(text)
            banned_list = db.setdefault("banned_users", [])
            if target_id in banned_list:
                banned_list.remove(target_id)
                await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم `{target_id}`.")
            else:
                banned_list.append(target_id)
                await update.message.reply_text(f"🚫 تم حظر المستخدم `{target_id}`.")
            save_db(db)
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
        context.user_data["action"] = None

    # إضافة مشترك عادي - الخطوة 1: استلام الـ ID
    elif action == "add_sub_step1":
        try:
            context.user_data["temp_target_id"] = int(text)
            context.user_data["action"] = "add_sub_step2"
            await update.message.reply_text("أدخل **مدة الاشتراك بالأيام** لهذا المشترك (مثلاً: `30`):", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال ID صحيح (أرقام فقط).")

    # إضافة مشترك عادي - الخطوة 2: تحديد وقت وتاريخ الانتهاء
    elif action == "add_sub_step2":
        try:
            days = int(text)
            target_id = context.user_data.get("temp_target_id")
            expire_date = datetime.now() + timedelta(days=days)
            
            sub_dict = db.setdefault("subscribers", {})
            sub_dict[str(target_id)] = expire_date.isoformat()
            save_db(db)

            expire_str = expire_date.strftime("%Y-%m-%d %H:%M")
            await update.message.reply_text(
                f"✅ تم إضافة المشترك العادي `{target_id}` بنجاح!\n"
                f"⏱️ المدة: {days} يوم\n"
                f"📅 ينتهي بتاريخ: `{expire_str}`",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال عدد أيام صحيح (أرقام فقط).")
        context.user_data["action"] = None

    # إضافة مشترك VIP - الخطوة 1: استلام الـ ID
    elif action == "add_vip_step1":
        try:
            context.user_data["temp_target_id"] = int(text)
            context.user_data["action"] = "add_vip_step2"
            await update.message.reply_text("أدخل **مدة الاشتراك بالأيام** للمشترك الـ VIP (مثلاً: `30`):", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال ID صحيح (أرقام فقط).")

    # إضافة مشترك VIP - الخطوة 2: تحديد وقت وتاريخ الانتهاء
    elif action == "add_vip_step2":
        try:
            days = int(text)
            target_id = context.user_data.get("temp_target_id")
            expire_date = datetime.now() + timedelta(days=days)
            
            vip_dict = db.setdefault("vip_subscribers", {})
            vip_dict[str(target_id)] = expire_date.isoformat()
            save_db(db)

            expire_str = expire_date.strftime("%Y-%m-%d %H:%M")
            await update.message.reply_text(
                f"⭐ تم إضافة المشترك الـ VIP `{target_id}` بنجاح!\n"
                f"⏱️ المدة: {days} يوم\n"
                f"📅 ينتهي بتاريخ: `{expire_str}`",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال عدد أيام صحيح (أرقام فقط).")
        context.user_data["action"] = None

    elif action == "add_dev":
        try:
            target_id = int(text)
            dev_list = db.setdefault("developers", [])
            if target_id not in dev_list:
                dev_list.append(target_id)
                save_db(db)
                await update.message.reply_text(f"✅ تم إضافة المطور `{target_id}` بنجاح.")
            else:
                await update.message.reply_text("⚠️ المستخدم مطور بالفعل.")
        except ValueError:
            await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
        context.user_data["action"] = None

    elif action == "broadcast":
        context.user_data["action"] = None
        count = 0
        all_users = set(list(db.get("subscribers", {}).keys()) + list(db.get("vip_subscribers", {}).keys()))
        for sub in all_users:
            try:
                await context.bot.send_message(chat_id=int(sub), text=f"📢 **إذاعة من إدارة البوت:**\n\n{text}", parse_mode="Markdown")
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ تم إرسال الإذاعة إلى {count} مشترك.")

    elif action == "set_force_channel":
        db["force_channel"] = text
        save_db(db)
        await update.message.reply_text(f"✅ تم تعيين قناة الاشتراك الإجباري إلى: {db['force_channel']}")
        context.user_data["action"] = None

# ==================== استقبال وتشغيل الملفات ====================
async def handle_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id): return

    doc = update.message.document
    file_name = doc.file_name

    # استعادة نسخة احتياطية
    if context.user_data.get("awaiting_backup_file"):
        if is_dev(user_id) and file_name.endswith('.json'):
            file = await context.bot.get_file(doc.file_id)
            await file.download_to_drive(DB_FILE)
            global db
            db = load_db()
            await update.message.reply_text("✅ تم استعادة قاعدة البيانات والنسخة الاحتياطية بنجاح!")
            context.user_data["awaiting_backup_file"] = False
            return

    # رفع ملف وإضافته إلى "قائمة ملفاتي"
    if context.user_data.get("awaiting_file"):
        if not is_authorized(user_id):
            await update.message.reply_text("❌ غير مصرح لك أو انتهت مدة اشتراكك، راسل المطور لتفعيل حسابك.")
            context.user_data["awaiting_file"] = False
            return

        if not file_name.endswith('.py'):
            await update.message.reply_text("❌ يرجى إرسال ملف بصيغة Python (`.py`) فقط.")
            return

        status_msg = await update.message.reply_text("⏳ جاري حفظ الملف في قائمة ملفاتك وفحص المكتبات المطلوبة...")

        file_path = os.path.join(HOST_DIR, f"{user_id}_{file_name}")
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(file_path)

        # تثبيت المكتبات تلقائياً
        modules = extract_requirements(file_path)
        if modules:
            await status_msg.edit_text(f"📦 جاري تثبيت المكتبات المطلوبة تلقائياً:\n`{', '.join(modules)}`...")
            await install_requirements(modules)

        buttons = [
            [InlineKeyboardButton(f"⚡ تشغيل الملف الآن", callback_data=f"run_{user_id}_{file_name}")],
            [InlineKeyboardButton("📂 الذهاب إلى قائمة ملفاتي", callback_data="my_files")]
        ]

        await status_msg.edit_text(
            f"✅ **تم إضافة الملف بنجاح إلى قائمة ملفاتك وتثبيت كافة المكتبات!**\n📄 **اسم الملف:** `{file_name}`\n\nيمكنك تشغيله الآن أو تشغيله لاحقاً من قائمة ملفاتك عبر زر (⚡ تشغيل ملف).",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

        context.user_data["awaiting_file"] = False

# ==================== النسخ الاحتياطي التلقائي ====================
async def send_backup(bot, target_id=OWNER_ID):
    zip_path = "hosted_bots_backup.zip"
    subprocess.run(["zip", "-r", zip_path, HOST_DIR]) if os.path.exists(HOST_DIR) else None

    if os.path.exists(DB_FILE):
        try:
            await bot.send_document(
                chat_id=target_id,
                document=open(DB_FILE, "rb"),
                caption=f"📦 **نسخة احتياطية لقاعدة البيانات**\n📅 التاريخ: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                parse_mode="Markdown"
            )
        except Exception: pass
    
    if os.path.exists(zip_path):
        try:
            await bot.send_document(
                chat_id=target_id,
                document=open(zip_path, "rb"),
                caption="📂 **نسخة احتياطية للملفات المرفوعة.**"
            )
        except Exception: pass
        os.remove(zip_path)

async def auto_backup_loop(app):
    while True:
        await asyncio.sleep(5 * 3600)
        await send_backup(app.bot, OWNER_ID)

async def post_init(app: Application):
    asyncio.create_task(auto_backup_loop(app))

# ==================== التشغيل الرئيسي ====================
def main():
    request_custom = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request_custom)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_documents))

    print("البوت يعمل الآن...")
    app.run_polling(bootstrap_retries=-1)

if __name__ == '__main__':
    main()
