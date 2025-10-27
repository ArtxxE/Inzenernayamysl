import datetime
import os
import re
from typing import Any

from openai import OpenAI
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)


TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

FREE_DAILY = int(os.getenv("FREE_DAILY", "30"))
UNLIMIT_PRICE_STARS = int(os.getenv("UNLIMIT_PRICE_STARS", "400"))
PRO_PRODUCT_TITLE = os.getenv(
    "PRO_PRODUCT_TITLE", "Безлимитные вопросы GPT (на 30 дней)"
)
PRO_PRODUCT_DESC = os.getenv(
    "PRO_PRODUCT_DESC", "Безлимитные ответы GPT в этом боте. Действует 30 дней."
)
CURRENCY = os.getenv("CURRENCY", "XTR")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "poderzkabotainzenernayamysl")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/hizackuaeu")

oai = OpenAI(api_key=OPENAI_API_KEY)

user_state: dict[str, int] = {}
conversation_history: dict[int, list[dict[str, str]]] = {}

MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "8"))
if MAX_HISTORY_MESSAGES < 2:
    MAX_HISTORY_MESSAGES = 2
elif MAX_HISTORY_MESSAGES % 2:
    MAX_HISTORY_MESSAGES -= 1

redis = None
try:
    import redis as _redis

    if os.getenv("REDIS_URL"):
        redis = _redis.from_url(os.getenv("REDIS_URL"))
except Exception:
    redis = None


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎓 Купить курс", callback_data="BUY")],
            [InlineKeyboardButton("📣 Подписаться на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🆘 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME}")],
            [InlineKeyboardButton("⭐ Безлимит GPT", callback_data="BUY_PRO")],
        ]
    )


async def inc_and_get_count(user_id: int) -> int:
    """Увеличивает счётчик запросов пользователя на сегодня."""

    key = f"qcount:{user_id}:{datetime.date.today().isoformat()}"
    if redis:
        return int(redis.incr(key, 1))

    user_state.setdefault(key, 0)
    user_state[key] += 1
    return user_state[key]


async def get_count(user_id: int) -> int:
    key = f"qcount:{user_id}:{datetime.date.today().isoformat()}"
    if redis:
        value = redis.get(key)
        return int(value) if value else 0

    return user_state.get(key, 0)


def has_pro(user_id: int) -> bool:
    key = f"pro:{user_id}"
    if redis:
        return redis.ttl(key) > 0
    return False


def grant_pro(user_id: int, days: int = 30) -> None:
    key = f"pro:{user_id}"
    if redis:
        redis.setex(key, days * 86400, "1")


def wants_image(text: str) -> bool:
    triggers = [
        "сгенерируй",
        "сгенерировать",
        "нарисуй",
        "сделай",
        "сделай картинку",
        "картинку",
        "картинка",
        "изображение",
        "фото",
        "згенеруй",
    ]
    lowered = text.lower()
    return any(trigger in lowered for trigger in triggers)


def extract_image_prompt(text: str) -> str:
    return (
        re.sub(
            r"^(?:/image|сгенерируй|сгенерировать|нарисуй|сделай(?:\s+картинку)?|)\s*",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        ).strip()
        or text.strip()
    )


def build_system_prompt(user_lang: str | None) -> str:
    base_prompt = (
        "Ты дружелюбный помощник Telegram-бота. "
        "Определи язык сообщения пользователя и отвечай на том же языке, "
        "подбирая естественные выражения и стиль. Если язык определить нельзя, "
        "используй русский. Отвечай ясно и по существу."
    )

    if user_lang:
        base_prompt += (
            " Учти, что Telegram сообщил код языка пользователя "
            f"'{user_lang}'. Если он отличается от языка сообщения, "
            "ориентируйся на текст пользователя."
        )

    return base_prompt


def get_history(user_id: int) -> list[dict[str, str]]:
    return conversation_history.get(user_id, [])


def remember_interaction(user_id: int, user_text: str, assistant_text: str) -> None:
    history = conversation_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[:-MAX_HISTORY_MESSAGES]


def build_messages(user_id: int, text: str, user_lang: str | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(user_lang)}
    ]
    messages.extend(get_history(user_id))
    messages.append({"role": "user", "content": text})
    return messages


async def ask_gpt(user_id: int, text: str, user_lang: str | None) -> str:
    response = oai.chat.completions.create(
        model=MODEL_NAME,
        messages=build_messages(user_id, text, user_lang),
    )
    return (response.choices[0].message.content or "").strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "✅ Привет! Я отвечаю на вопросы с GPT.\n"
        f"Бесплатно сегодня: {FREE_DAILY} вопросов. Для безлимита — «⭐ Безлимит GPT».",
        reply_markup=main_menu_kb(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start — меню\n"
        "/ask <вопрос> — спросить GPT\n"
        "/limit — показать остаток\n"
        "/buy — купить безлимит",
        reply_markup=main_menu_kb(),
    )


async def show_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    used = await get_count(update.effective_user.id)
    left: Any = "∞" if has_pro(update.effective_user.id) else max(0, FREE_DAILY - used)
    await update.message.reply_text(f"Остаток на сегодня: {left}")


async def paywall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Бесплатные вопросы закончились.\n"
        "Купи ⭐ Безлимит GPT на 30 дней и задавай сколько угодно."
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Купить за ⭐", callback_data="BUY_PRO")]]
    )
    await update.message.reply_text(text, reply_markup=kb)


async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    question = " ".join(context.args).strip() if context.args else None
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
        answer = await ask_gpt(
            user_id, question, update.effective_user.language_code
        )
    except Exception as exc:  # pragma: no cover - API/network errors
        answer = f"Ошибка OpenAI: {exc}"

    cleaned_answer = answer or "пустой ответ :("
    await update.message.reply_text(cleaned_answer)
    if answer:
        remember_interaction(user_id, question, cleaned_answer)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Здесь можно добавить генерацию картинок. Пока всегда отвечаем текстом.
    await update.message.chat.send_action("typing")
    try:
        answer = await ask_gpt(
            update.effective_user.id, text, update.effective_user.language_code
        )
    except Exception as exc:  # pragma: no cover - API/network errors
        answer = f"⚠️ Ошибка GPT: {exc}"

    cleaned_answer = answer or "⚠️ Нет ответа от модели."
    await update.message.reply_text(cleaned_answer)
    if answer:
        remember_interaction(update.effective_user.id, text, cleaned_answer)


async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "BUY":
        await query.edit_message_text(
            "Каталог курсов позже добавим.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="BACK_HOME")]]
            ),
        )
    elif query.data == "BUY_PRO":
        prices = [LabeledPrice(label=PRO_PRODUCT_TITLE, amount=UNLIMIT_PRICE_STARS)]
        await query.message.reply_invoice(
            title=PRO_PRODUCT_TITLE,
            description=PRO_PRODUCT_DESC,
            payload="pro_30days",
            provider_token="",
            currency=CURRENCY,
            prices=prices,
        )
    elif query.data == "BACK_HOME":
        await query.edit_message_text("Главное меню:", reply_markup=main_menu_kb())


async def pre_checkout_q(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    grant_pro(user_id, days=30)
    await update.message.reply_text(
        "🎉 Оплата получена! Безлимит активирован на 30 дней. Пиши /ask вопрос."
    )


def main() -> None:
    if not TOKEN or not OPENAI_API_KEY:
        raise SystemExit("Нужны TOKEN и OPENAI_API_KEY в переменных окружения.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("limit", show_limit))
    app.add_handler(CommandHandler("buy", lambda u, c: paywall(u, c)))

    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    app.add_handler(text_handler)

    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_q))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🚀 Bot started (polling)…")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
