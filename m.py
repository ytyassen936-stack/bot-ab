import os
import sys
import subprocess
import threading
import time
import telebot
from telebot import types

# إعدادات البوت والمطور
TOKEN = "8942894582:AAGpIB2ZPoFGUm0VFMcJApZ1hrWNl9Ry9mU"
OWNER_ID = 7493679412

bot = telebot.TeleBot(TOKEN)

# مجلد حفظ وتشغيل البوتات المرفوعة
HOSTING_DIR = "hosted_bots"
if not os.path.exists(HOSTING_DIR):
    os.makedirs(HOSTING_DIR)

# قاموس لتتبع العمليات الجارية للمستخدمين
user_states = {}
# قاموس لتخزين عمليات التشغيل (Processes) للبوتات
running_bots = {}

def is_owner(user_id):
    return user_id == OWNER_ID

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "عذراً، هذا البوت مخصص للمطور فقط.")
        return

    text = """══════════════════════

- اهلا بك في بوت استضافة بوتات تيليجرام

══════════════════════"""

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("اضافه ملف", callback_data="add_file")
    btn2 = types.InlineKeyboardButton("تثبيت مكتبه", callback_data="install_lib")
    btn3 = types.InlineKeyboardButton("عرض البوتات", callback_data="list_bots")
    btn4 = types.InlineKeyboardButton("حذف ملف", callback_data="delete_file")
    markup.add(btn1, btn2, btn3, btn4)

    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "هذا البوت للمطور فقط!", show_alert=True)
        return

    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if call.data == "add_file":
        user_states[chat_id] = "waiting_for_py_file"
        text = """══════════════════════
ارسل الملف لتشغسله علا السيرفر
══════════════════════"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("الغاء", callback_data="cancel"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

    elif call.data == "install_lib":
        user_states[chat_id] = "waiting_for_lib_name"
        text = """══════════════════════

ارسل لي اسم المكتبه لتثبيتها 

══════════════════════"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("الغاء", callback_data="cancel"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

    elif call.data == "list_bots":
        files = [f for f in os.listdir(HOSTING_DIR) if f.endswith('.py')]
        text = "قائمة البوتات المرفوعة:\n\n"
        if not files:
            text += "لا توجد بوتات مرفوعة حالياً."
        
        for file in files:
            # التحقق مما إذا كان البوت يعمل حالياً
            if file in running_bots and running_bots[file].poll() is None:
                status = "🟢 (يعمل)"
            else:
                status = "🔴 (متوقف)"
            text += f"- {file} : {status}\n"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("القائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

    elif call.data == "delete_file":
        files = [f for f in os.listdir(HOSTING_DIR) if f.endswith('.py')]
        if not files:
            bot.answer_callback_query(call.id, "لا توجد ملفات لحذفها!", show_alert=True)
            return
        
        text = "اختر الملف المراد حذفه:"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for file in files:
            markup.add(types.InlineKeyboardButton(f"حذف: {file}", callback_data=f"del_{file}"))
        markup.add(types.InlineKeyboardButton("القائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

    elif call.data.startswith("del_"):
        file_to_delete = call.data.replace("del_", "")
        file_path = os.path.join(HOSTING_DIR, file_to_delete)
        
        # إيقاف العملية إذا كانت تعمل
        if file_to_delete in running_bots:
            try:
                running_bots[file_to_delete].terminate()
                del running_bots[file_to_delete]
            except Exception:
                pass

        # حذف الملف
        if os.path.exists(file_path):
            os.remove(file_path)
            bot.answer_callback_query(call.id, f"تم حذف {file_to_delete} بنجاح.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "الملف غير موجود!", show_alert=True)

        # العودة لقائمة الحذف أو الرئيسية
        call.data = "delete_file"
        callback_query(call)

    elif call.data == "cancel":
        if chat_id in user_states:
            del user_states[chat_id]
        
        text = """══════════════════════

- اهلا بك في بوت استضافة بوتات تيليجرام

══════════════════════"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("اضافه ملف", callback_data="add_file")
        btn2 = types.InlineKeyboardButton("تثبيت مكتبه", callback_data="install_lib")
        btn3 = types.InlineKeyboardButton("عرض البوتات", callback_data="list_bots")
        btn4 = types.InlineKeyboardButton("حذف ملف", callback_data="delete_file")
        markup.add(btn1, btn2, btn3, btn4)
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

    elif call.data == "main_menu":
        if chat_id in user_states:
            del user_states[chat_id]
        text = """══════════════════════

- اهلا بك في بوت استضافة بوتات تيليجرام

══════════════════════"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("اضافه ملف", callback_data="add_file")
        btn2 = types.InlineKeyboardButton("تثبيت مكتبه", callback_data="install_lib")
        btn3 = types.InlineKeyboardButton("عرض البوتات", callback_data="list_bots")
        btn4 = types.InlineKeyboardButton("حذف ملف", callback_data="delete_file")
        markup.add(btn1, btn2, btn3, btn4)
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

@bot.message_handler(content_types=['document', 'text'])
def handle_user_input(message):
    if not is_owner(message.from_user.id):
        return

    chat_id = message.chat.id
    state = user_states.get(chat_id)

    if state == "waiting_for_py_file":
        if message.document:
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name

            if not file_name.endswith('.py'):
                bot.reply_to(message, "عذراً، يجب أن يكون الملف بصيغة .py فقط.")
                return

            downloaded_file = bot.download_file(file_info.file_path)
            file_path = os.path.join(HOSTING_DIR, file_name)

            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # تشغيل البوت في مسار منفصل
            try:
                process = subprocess.Popen([sys.executable, file_path])
                running_bots[file_name] = process
                bot.reply_to(message, f"تم رفع الملف وتشغيله بنجاح على السيرفر! 🟢\nاسم الملف: {file_name}")
            except Exception as e:
                bot.reply_to(message, f"تم رفع الملف ولكن حدث خطأ أثناء تشغيله:\n{str(e)}")

            if chat_id in user_states:
                del user_states[chat_id]
        else:
            bot.reply_to(message, "الرجاء إرسال ملف بصيغة .py")

    elif state == "waiting_for_lib_name":
        lib_name = message.text.strip()
        msg = bot.reply_to(message, f"جاري تثبيت المكتبة: `{lib_name}`...", parse_mode="Markdown")
        
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install", lib_name], 
                                    capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                bot.edit_message_text(f"✅ تمت عملية التثبيت بنجاح للمكتبة: `{lib_name}`", 
                                      chat_id, msg.message_id, parse_mode="Markdown")
            else:
                bot.edit_message_text(f"❌ حدث خطأ أثناء التثبيت:\n```\n{result.stderr}\n```", 
                                      chat_id, msg.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"❌ حدث خطأ غير متوقع:\n`{str(e)}`", 
                                  chat_id, msg.message_id, parse_mode="Markdown")

        if chat_id in user_states:
            del user_states[chat_id]

print("Bot is running...")
bot.infinity_polling()
