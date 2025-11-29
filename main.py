import os
import json
from datetime import datetime, time
from dotenv import load_dotenv
from google import genai
from telegram import Update
from flask import Flask
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
flask_app = Flask(__name__)
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


def _ensure_json_file(path: str):
    """Ensure the JSON file exists and is a list container."""
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        except Exception:
            # If we can't create the file, ignore; callers will handle errors.
            pass


def save_conversation_entry(user_id, user_text, ai_response, full_prompt=None, username=None, phone_number=None, file_path="conversations.json"):
    """Append a conversation entry to a JSON file.

    Each entry contains: timestamp, user_id, user_text, full_prompt, ai_response, model
    """
    _ensure_json_file(file_path)

    # Use local timezone-aware timestamp with millisecond precision
    try:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    except TypeError:
        # Older Python versions may not support timespec param; fall back to full isoformat
        timestamp = datetime.now().astimezone().isoformat()

    entry = {
        "timestamp": timestamp,
        "user_id": user_id,
        "user_text": user_text,
        "full_prompt": full_prompt,
        "username": username,
        "phone_number": phone_number,
        "ai_response": ai_response,
        "model": "gemini-2.5-flash",
    }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = []
    except Exception:
        data = []

    data.append(entry)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # If writing fails, don't crash the bot; swallow the exception.
        pass


def search(user_id, user_text, username=None, phone_number=None):
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

    # Persist the interaction (user prompt + AI response) to JSON
    try:
        save_conversation_entry(
            user_id=user_id,
            user_text=user_text,
            ai_response=bot_reply,
            full_prompt=prompt,
            username=username,
            phone_number=phone_number,
        )
    except Exception:
        # Ignore logging errors to avoid interrupting bot flow
        pass

    return bot_reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # Save user for daily messages
    subscribers = context.bot_data.setdefault("subscribers", set())
    subscribers.add(user_id)

    await update.message.reply_text("You're subscribed for daily updates. Ask me anything.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Extract message text and optional contact info
    text = update.message.text
    user = update.message.from_user
    username = getattr(user, "username", None)

    # If the user shared a contact, capture phone number
    phone_number = None
    if update.message.contact:
        phone_number = update.message.contact.phone_number

    reply = search(user_id, text, username=username, phone_number=phone_number)
    await update.message.reply_text(reply)


# Daily scheduled job
async def daily_task(context: ContextTypes.DEFAULT_TYPE):
    subscribers = context.bot_data.get("subscribers", set())
    for uid in subscribers:
        await context.bot.send_message(uid, "Your daily scheduled update.")

def create_telegram_application():
    """Build and return the `telegram.ext.Application` with handlers configured.

    This does NOT call `run_polling()` so you can control startup externally
    and avoid multiple simultaneous getUpdates calls.
    """
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Daily message at 9:00 AM (server time)
    application.job_queue.run_daily(
        daily_task,
        time(hour=9, minute=0)
    )

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    return application


@flask_app.route('/')
def health_check():
    return "OK"


if __name__ == "__main__":
    bot_app = create_telegram_application()
    print("Bot is running...")
    bot_app.run_polling()
