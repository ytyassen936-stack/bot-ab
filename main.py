import os
from telegram.ext import Updater, CommandHandler

TOKEN = os.environ.get('BOT_TOKEN')

def start(update, context):
    update.message.reply_text('بوت قناة @w_3_vv اشتغل...')

updater = Updater(TOKEN, use_context=True)
updater.dispatcher.add_handler(CommandHandler('start', start))
updater.start_polling()
updater.idle()
