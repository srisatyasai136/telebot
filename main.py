import os
from datetime import time
from dotenv import load_dotenv
from google import genai
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Load .env file (LOCAL development)
load_dotenv()

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is missing. Add it to your .env or Render environment.")

if not GEMINI_KEY:
    raise ValueError("GEMINI_KEY is missing. Add it to your .env or Render environment.")

# Initialize Gemini client once
client = genai.Client(api_key=GEMINI_KEY)

# In-memory conversation history
conversation_history = {}


def search(user_id, user_text):
    previous = conversation_history.get(user_id, "")

    prompt = f"""
Conversation so far:
{previous}

User: {user_text}

System: Reply in under 150 words. Stay consistent with the previous conversation.
"""

    # Gemini API call
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    bot_reply = response.text.strip()

    # Save updated conversation
    conversation_history[user_id] = previous + f"\nUser: {user_text}\nBot: {bot_reply}"

    return bot_reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # Save user for daily messages
    subscribers = context.bot_data.setdefault("subscribers", set())
    subscribers.add(user_id)

    await update.message.reply_text("You're subscribed for daily updates. Ask me anything.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    reply = search(user_id, text)
    await update.message.reply_text(reply)


# Daily scheduled job
async def daily_task(context: ContextTypes.DEFAULT_TYPE):
    subscribers = context.bot_data.get("subscribers", set())
    for uid in subscribers:
        await context.bot.send_message(uid, "Your daily scheduled update.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Daily message at 9:00 AM (server time)
    app.job_queue.run_daily(
        daily_task,
        time(hour=9, minute=0)
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
