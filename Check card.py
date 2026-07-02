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
        await update.message.reply_text("⛔ *ACCESS DENIED*\nYour account has been blocked by the Admin.", parse_mode="Markdown")
        return
    elif status == "expired":
        await update.message.reply_text(
            f"⚠️ *ACCOUNT NOT ACTIVATED*\n\n"
            f"Your account status is currently: *Inactive*\n"
            f"🔑 Your Telegram ID: `{user_id}`\n\n"
            f"Please send your ID to the Admin to activate your account.", 
            parse_mode="Markdown"
        )
        return

    time_left = get_remaining_time(user_id)
    welcome_text = (
        f"👑 *WELCOME TO URL CHECKER BOT* 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔮 *Status:* `Active Premium`\n"
        f"⏳ *Time Left:* `{time_left}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ _Upload a .txt file to start bulk checking seamlessly._\n\n"
        f"💡 Type /help to see all available commands."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ Subscription required to use this bot.")
        return

    help_text = (
        f"📖 *BOT COMMANDS MENU* 📖\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• `/start` ➜ Check your subscription status\n"
        f"• `/help` ➜ View this help menu\n"
        f"• `/site <url>` ➜ Check a single URL status\n"
        f"• 📂 *Bulk File Check:* Drop any `.txt` file containing your links to check\n"
    )

    if is_admin(user_id):
        help_text += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 *ADMIN MANAGEMENT CONTROLS* 👑\n"
            f"• `/admin` ➜ Open Admin control panel & bot stats\n"
            f"• `/activate <id> <time> <d/h>` ➜ Activate user\n"
            f"  _Example: `/activate 1234567 7 d` (Activates for 7 Days)_\n"
            f"• `/block <id>` ➜ Block user from using the bot\n"
            f"• `/unblock <id>` ➜ Unblock user\n"
            f"• `/revoke <id>` ➜ Delete user subscription time"
        )

    await update.message.reply_text(help_text, parse_mode="Markdown")

async def site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ Subscription required.")
        return

    if not context.args:
        await update.message.reply_text("⚡ *Usage:* `/site domain.com`", parse_mode="Markdown")
        return

    url = " ".join(context.args)
    status_msg = await update.message.reply_text("📡 *Checking target URL... Please wait...*", parse_mode="Markdown")

    async with httpx.AsyncClient() as client:
        result = await check_url_async(client, url)

    STATS["total_checked"] += 1
    if is_link_live(result):
        STATS["total_live"] += 1
        await status_msg.edit_text(
            f"🟢 *RESULT: LIVE LINK*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 *URL:* {url}\n"
            f"📟 *Response:* `{result}`", 
            parse_mode="Markdown"
        )
    else:
        STATS["total_dead"] += 1
        await status_msg.edit_text(f"🔴 *RESULT: DEAD/FILTERED* ➜ (Response: `{result}`)", parse_mode="Markdown")

# ========= ADMIN DASHBOARD =========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    total_users = len(db)
    blocked_users = sum(1 for u in db.values() if u.get("blocked", False))

    admin_panel_text = (
        f"⚙️ *ADMIN CONTROL DASHBOARD* ⚙️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Bot Statistics:*\n"
        f" • Total Checked Links: `{STATS['total_checked']}`\n"
        f" • Total Live Links Found: `{STATS['total_live']}`\n"
        f" • Total Dead Links Filtered: `{STATS['total_dead']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *User Management Statistics:*\n"
        f" • Total Registered Users: `{total_users}`\n"
        f" • Total Blocked Users: `{blocked_users}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 *Server Status:* `Running Smoothly on Railway`"
    )
    await update.message.reply_text(admin_panel_text, parse_mode="Markdown")

async def activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        user_target = context.args[0]
        amount = int(context.args[1])
        unit = context.args[2].lower()

        if unit == 'd':
            expire_date = datetime.now() + timedelta(days=amount)
            unit_str = "Days"
        elif unit == 'h':
            expire_date = datetime.now() + timedelta(hours=amount)
            unit_str = "Hours"
        else:
            raise ValueError

        db[str(user_target)] = {
            "expires_at": expire_date.isoformat(),
            "blocked": False
        }
        save_db(db)
        await update.message.reply_text(
            f"✅ *USER ACTIVATED SUCCESSFULLY*\n"
            f"User `{user_target}` has been activated for *{amount} {unit_str}*.\n"
            f"📅 *Expiry Date:* `{expire_date.strftime('%Y-%m-%d %H:%M:%S')}`", 
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ *Wrong Format.* Use: `/activate <id> <amount> <d/h>`", parse_mode="Markdown")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) not in db: db[str(user_target)] = {}
    db[str(user_target)]["blocked"] = True
    save_db(db)
    await update.message.reply_text(f"🚫 *USER BLOCKED* ➜ ID `{user_target}` has been blacklisted.", parse_mode="Markdown")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) in db:
        db[str(user_target)]["blocked"] = False
        save_db(db)
        await update.message.reply_text(f"🟢 *USER UNBLOCKED* ➜ ID `{user_target}` access restored.", parse_mode="Markdown")

async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) in db:
        db[str(user_target)]["expires_at"] = None
        save_db(db)
        await update.message.reply_text(f"⚠️ *SUBSCRIPTION REVOKED* ➜ Subscription wiped for ID `{user_target}`.", parse_mode="Markdown")

# ========= FILE HANDLER WITH LIVE PANEL & PROGRESS COUNTER =========

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ Subscription required.")
        return

    document: Document = update.message.document
    if not document.file_name.endswith(".txt"):
        await update.message.reply_text("❌ *Invalid File.* Please upload a .txt file format.", parse_mode="Markdown")
        return

    initial_msg = await update.message.reply_text("📥 *Downloading and parsing file links...*", parse_mode="Markdown")

    file = await document.get_file()
    file_path = f"links_{user_id}.txt"
    await file.download_to_drive(file_path)

    links = read_links_file(file_path)
    total = len(links)
    
    live_count = 0
    dead_count = 0
    current_index = 0

    await initial_msg.edit_text("⚙️ *Starting bulk checking process...*")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in links:
            current_index += 1
            result = await check_url_async(client, url)
            
            STATS["total_checked"] += 1

            if is_link_live(result):
                live_count += 1
                STATS["total_live"] += 1
                # Forward ONLY premium live hits
                await update.message.reply_text(
                    f"🌟 *LIVE HIT FOUND* 🌟\n"
                    f" ├ 🔗 *URL:* {url}\n"
                    f" └ 📟 *Response:* `{result}`", 
                    parse_mode="Markdown"
                )
            else:
                dead_count += 1
                STATS["total_dead"] += 1

            # 📊 العداد المباشر لتحديث تقدم الفحص خطوة بخطوة 
            if current_index % 1 == 0 or current_index == total:
                panel_text = (
                    f"📊 *LIVE CHECKING MONITOR* 📊\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔄 Progress Counter: `[{current_index}/{total}]` Checked\n"
                    f"📡 Last Website Response: `{result}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Live Sent: `[ {live_count} ]` \n"
                    f"❌ Filtered (Silent): `[ {dead_count} ]`"
                )
                try:
                    await initial_msg.edit_text(panel_text, parse_mode="Markdown")
                except:
                    pass

            await asyncio.sleep(3)

    final_stats = (
        f"🏁 *BULK CHECK COMPLETED* 🏁\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total Scanned Links: `{total}`\n"
        f"💎 Total Live Forwarded: `{live_count}`\n"
        f"🛡️ Total Filtered/Dead: `{dead_count}`"
    )
    await update.message.reply_text(final_stats, parse_mode="Markdown")
    try: os.remove(file_path)
    except: pass

# ========= RUN ENGINE =========

if __name__ == "__main__":
    app = ApplicationBuilder().token(API_TOKEN).build()

    async def block_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        status = check_user_status(user_id)
        if status == "blocked":
            await update.message.reply_text("⛔ Access denied. You are blocked.")
        elif status == "expired":
            await update.message.reply_text(f"⚠️ Account not activated. Your ID: `{user_id}`", parse_mode="Markdown")

    # Hooking Modules
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("site", site_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("activate", activate_user))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("revoke", revoke_user))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, block_text))

    print("Bot Core Engine Started...")
    app.run_polling()
