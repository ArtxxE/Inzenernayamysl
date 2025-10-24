import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
TOKEN = os.getenv("TOKEN")  
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

    main()
import os, asyncio, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from openai import OpenAI


TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FREE_DAILY = int(os.getenv("FREE_DAILY", "10"))   
UNLIMIT_PRICE_STARS = int(os.getenv("UNLIMIT_PRICE_STARS", "400"))  
PRO_PRODUCT_TITLE = "Безлимитные вопросы GPT (на 30 дней)"
PRO_PRODUCT_DESC  = "Безлимитные ответы GPT в этом боте. Действует 30 дней."
CURRENCY = "XTR"  
oai = OpenAI(api_key=OPENAI_API_KEY)
user_state = {}  

redis = None
try:
    import redis as _redis
    if os.getenv("REDIS_URL"):
        redis = _redis.from_url(os.getenv("REDIS_URL"))
except Exception:
    redis = None

async def inc_and_get_count(user_id: int) -> int:
    """Увеличивает счётчик на сегодня и возвращает текущее значение."""
    key = f"qcount:{user_id}:{datetime.date.today().isoformat()}"
    if redis:
        return int(redis.incr(key, 1))
    
    user_state.setdefault(key, 0)
    user_state[key] += 1
    return user_state[key]

async def get_count(user_id: int) -> int:
    key = f"qcount:{user_id}:{datetime.date.today().isoformat()}"
    if redis:
        val = redis.get(key)
        return int(val) if val else 0
    return int(user_state.get(key, 0))

def has_pro(user_id: int) -> bool:
    key = f"pro:{user_id}"
    if redis:
        return redis.ttl(key) > 0  
    return False  

def grant_pro(user_id: int, days: int = 30):
    key = f"pro:{user_id}"
    if redis:
        redis.setex(key, days * 86400, "1")

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎓 Купить курс", callback_data="BUY")],
        [InlineKeyboardButton("🧠 Спросить GPT", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("⭐ Безлимит GPT", callback_data="BUY_PRO")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Привет! Я отвечаю на вопросы с GPT.\n"
        f"Бесплатно сегодня: {FREE_DAILY} вопросов. Для безлимита — «⭐ Безлимит GPT».",
        reply_markup=main_menu_kb()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — меню\n"
        "/ask <вопрос> — спросить GPT\n"
        "/limit — показать остаток\n"
        "/buy — купить безлимит",
        reply_markup=main_menu_kb()
    )

async def show_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    used = await get_count(update.effective_user.id)
    left = "∞" if has_pro(update.effective_user.id) else max(0, FREE_DAILY - used)
    await update.message.reply_text(f"Остаток на сегодня: {left}")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    question = " ".join(context.args) if context.args else None
    if not question:
        await update.message.reply_text("Напиши так: /ask твой вопрос")
        return

    if not has_pro(user_id):
        used = await get_count(user_id)
        if used >= FREE_DAILY:
            await paywall(update, context)
            return
        await inc_and_get_count(user_id)

    await update.message.chat.send_action("typing")
    try:
       
        resp = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Отвечай кратко и понятно."},
                {"role": "user", "content": question},
            ],
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"Ошибка OpenAI: {e}"

    await update.message.reply_text(answer or "пустой ответ :(")

async def paywall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = ("Бесплатные вопросы закончились.\n"
           "Купи ⭐ Безлимит GPT на 30 дней и задавай сколько угодно.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Купить за ⭐", callback_data="BUY_PRO")]])
    await update.message.reply_text(txt, reply_markup=kb)

async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "BUY":
        await q.edit_message_text("Каталог курсов позже добавим.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="BACK_HOME")]]))
    elif q.data == "BUY_PRO":
        prices = [LabeledPrice(label=PRO_PRODUCT_TITLE, amount=UNLIMIT_PRICE_STARS)]
        await q.message.reply_invoice(
            title=PRO_PRODUCT_TITLE,
            description=PRO_PRODUCT_DESC,
            payload="pro_30days",
            provider_token="",   
            currency=CURRENCY,  
            prices=prices
        )
    elif q.data == "BACK_HOME":
        await q.edit_message_text("Главное меню:", reply_markup=main_menu_kb())

async def pre_checkout_q(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    grant_pro(user_id, days=30)
    await update.message.reply_text("🎉 Оплата получена! Безлимит активирован на 30 дней. Пиши /ask вопрос.")

def main():
    if not TOKEN or not OPENAI_API_KEY:
        raise SystemExit("Нужны TOKEN и OPENAI_API_KEY в переменных окружения.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("limit", show_limit))
    app.add_handler(CommandHandler("buy", lambda u, c: paywall(u, c)))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.StatusUpdate.PRE_CHECKOUT_QUERY, pre_checkout_q))

    print("🚀 Bot started (polling)…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()



