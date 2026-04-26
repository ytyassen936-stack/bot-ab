import telebot
from telebot import types
import time
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, WELCOME_MSG
from database import init_db, add_user, add_group, get_all_groups

bot = telebot.TeleBot(BOT_TOKEN)
init_db()

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user = message.from_user
    add_user(user.id, user.username, user.first_name)
    
    if message.chat.type == 'private':
        bot.reply_to(message, WELCOME_MSG.format(name=user.first_name))
    else:
        bot.reply_to(message, "هلا والله، اني اشتغل 🌚")

@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            add_group(message.chat.id, message.chat.title, message.from_user.id)
            bot.send_message(message.chat.id, f"شكراً {message.from_user.first_name} على اضافتي ❤️")
        else:
            bot.send_message(message.chat.id, WELCOME_MSG.format(name=member.first_name))

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        return
    
    if message.chat.type != 'private':
        bot.reply_to(message, "الامر يشتغل بالخاص بس")
        return
    
    text = message.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(message, "اكتب الرسالة بعد الامر\nمثال:\n/broadcast مرحبا شباب")
        return
    
    groups = get_all_groups()
    sent = 0
    for group_id in groups:
        try:
            bot.send_message(group_id, text)
            sent += 1
            time.sleep(0.5)
        except:
            continue
    
    bot.reply_to(message, f"تم الارسال لـ {sent} كروب ✅")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if not is_admin(message.from_user.id):
        return
    
    groups = get_all_groups()
    bot.reply_to(message, f"عدد الكروبات: {len(groups)}")

print("Bot is running...")
bot.infinity_polling()