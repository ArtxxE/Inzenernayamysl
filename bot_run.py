import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
TOKEN = "8397235255:AAHIC3lzoSTaP9fJBA0cIJ9JcOHQ2_xZhnA"  
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "#Poderzkabotainzenernayamysl")  
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/hizackuaeu")
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎓 Купить курс", callback_data="BUY")],
        [InlineKeyboardButton("🆘 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("📣 Подписаться на канал", url=CHANNEL_LINK)]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Привет! Бот на связи. Выбери действие:", reply_markup=main_menu_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды: /start, /help", reply_markup=main_menu_kb())

async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "BUY":
        await q.edit_message_text(
            "Тут будет список курсов (позже добавим оплату).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="BACK_HOME")]])
        )
    elif q.data == "BACK_HOME":
        await q.edit_message_text("Главное меню:", reply_markup=main_menu_kb())

def main():
    if not TOKEN:
        raise SystemExit("Не найден TOKEN в переменных окружения")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_cb))
    print("🚀 Bot started (polling)…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()