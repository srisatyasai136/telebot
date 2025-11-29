import os
import json
from datetime import datetime, time
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

# Load .env values (Railway also loads env automatically)
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")
if not GEMINI_KEY:
    raise ValueError("Missing GEMINI_KEY")

# Initialize Gemini client once
client = genai.Client(api_key=GEMINI_KEY)

# Basic memory storage
conversation_history = {}

def load_logs():
    try:
        with open("conversations.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_logs(data):
    try:
        with open("conversations.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def search(user_id, text, username=None, phone_number=None):
    previous = conversation_history.get(user_id, "")

    prompt = f"""
Conversation so far:
{previous}

User: {text}

System: Reply in under 150 words. Stay consistent with the conversation.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    bot_reply = response.text.strip()

    conversation_history[user_id] = previous + f"\nUser: {text}\nBot: {bot_reply}"

    logs = load_logs()
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "user_text": text,
        "ai_response": bot_reply,
        "username": username,
        "phone_number": phone_number
    })
    save_logs(logs)

    return bot_reply

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    subs = context.bot_data.setdefault("subscribers", set())
    subs.add(uid)
    await update.message.reply_text("You're subscribed for daily updates.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text
    username = update.message.from_user.username
    phone = update.message.contact.phone_number if update.message.contact else None

    reply = search(uid, text, username=username, phone_number=phone)
    await update.message.reply_text(reply)

async def daily_task(context: ContextTypes.DEFAULT_TYPE):
    subs = context.bot_data.get("subscribers", set())
    for uid in subs:
        await context.bot.send_message(uid, "Your daily scheduled message.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Daily job at 9 AM
    app.job_queue.run_daily(
        daily_task,
        time(hour=9, minute=0)
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot is running on Railway...")
    app.run_polling()

if __name__ == "__main__":
    main()
