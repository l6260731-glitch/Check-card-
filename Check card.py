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
        return "💎 Lifetime Premium (Owner)"
    if user_str in db and db[user_str].get("expires_at"):
        expire_time = datetime.fromisoformat(db[user_str]["expires_at"])
        remaining = expire_time - datetime.now()
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return f"⏳ {days} Days, {hours} Hours, {minutes} Mins"
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
        await update.message.reply_text("⛔ *ACCESS DENIED*\nYour account has been blacklisted by the Administrator.", parse_mode="Markdown")
        return
    elif status == "expired":
        await update.message.reply_text(
            f"⚠️ *SUBSCRIPTION EXPIRED OR NOT FOUND*\n\n"
            f"Your account status is currently: *Inactive*\n"
            f"🔑 Your Telegram ID: `{user_id}`\n\n"
            f"Please forward your ID to the Administrator to grant access.", 
            parse_mode="Markdown"
        )
        return

    time_left = get_remaining_time(user_id)
    welcome_text = (
        f"👑 *HYDRA GATEWAY CORE v2.0*\n"
        f"═\n"
        f"🔮 *Account Access:* `Premium Registered`\n"
        f"⏱️ *Time Remaining:* `{time_left}`\n"
        f"═\n"
        f"⚡ _Engine Status: Online & operational. Upload a .txt file for automated high-speed live filtering._\n\n"
        f"💡 Type /help to open the advanced commands matrix."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ System lock active. Subscription required.")
        return

    help_text = (
        f"⚜️ *HYDRA TERMINAL COMMANDS* ⚜️\n"
        f"═\n"
        f"• `/start` ➜ Re-initialize core and check time\n"
        f"• `/help` ➜ Request commands manual\n"
        f"• `/site <url>` ➜ Inject single URL for instant check\n"
        f"• 📂 *Bulk Engine:* Drop `.txt` list directly to initialize background scanning\n"
    )

    if is_admin(user_id):
        help_text += (
            f"═\n"
            f"👑 *EXECUTIVE OVERRIDE CONTROLS* 👑\n"
            f"• `/admin` ➜ Open system telemetry dashboard\n"
            f"• `/activate <id> <time> <d/h>` ➜ Grant access token\n"
            f"  _Example: `/activate 12345 30 d` (30 Days)_\n"
            f"• `/block <id>` ➜ Hard ban user from database\n"
            f"• `/unblock <id>` ➜ Revoke active blacklist ban\n"
            f"• `/revoke <id>` ➜ Purge subscription timeline"
        )

    await update.message.reply_text(help_text, parse_mode="Markdown")

async def site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ System lock active. Subscription required.")
        return

    if not context.args:
        await update.message.reply_text("⚡ *Usage:* `/site domain.com`", parse_mode="Markdown")
        return

    url = " ".join(context.args)
    status_msg = await update.message.reply_text("📡 *Infiltrating target gateway... Please hold...*", parse_mode="Markdown")

    async with httpx.AsyncClient() as client:
        result = await check_url_async(client, url)

    STATS["total_checked"] += 1
    if is_link_live(result):
        STATS["total_live"] += 1
        await status_msg.edit_text(
            f"🟢 *TARGET MATRIX: LIVE*\n"
            f"═\n"
            f"🔗 *URL:* {url}\n"
            f"📟 *Response:* `{result}`", 
            parse_mode="Markdown"
        )
    else:
        STATS["total_dead"] += 1
        await status_msg.edit_text(f"🔴 *TARGET REJECTED* ➜ (Filtered with status: `{result}`)", parse_mode="Markdown")

# ========= ADVANCED EXECUTIVE CONTROL PANEL =========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Override rejected. Unauthorized node.")
        return

    total_users = len(db)
    blocked_users = sum(1 for u in db.values() if u.get("blocked", False))

    admin_panel_text = (
        f"🎛️ *SYSTEM CONTROL EXECUTIVE DASHBOARD*\n"
        f"═\n"
        f"📊 *Core Network Telemetry:*\n"
        f" ├ 🌐 Total Links Parsed: `{STATS['total_checked']}`\n"
        f" ├ ✅ Total Live Forwarded: `{STATS['total_live']}`\n"
        f" └ ❌ Total Dead Eliminated: `{STATS['total_dead']}`\n"
        f"═\n"
        f"👥 *User Database Intelligence:*\n"
        f" ├ 📈 Total Accounts Registered: `{total_users}`\n"
        f" └ 🚫 Accounts Currently Blacklisted: `{blocked_users}`\n"
        f"═\n"
        f"💎 *Node Status:* `All Systems Operational [Railway Cloud]`"
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
            f"⚜️ *ACCESS TOKEN GRANTED*\n"
            f"User `{user_target}` has been successfully activated for *{amount} {unit_str}*.\n"
            f"📅 *Expiry Window:* `{expire_date.strftime('%Y-%m-%d %H:%M:%S')}`", 
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ *Format Error.* Use: `/activate <id> <amount> <d/h>`", parse_mode="Markdown")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) not in db: db[str(user_target)] = {}
    db[str(user_target)]["blocked"] = True
    save_db(db)
    await update.message.reply_text(f"🖤 *BLACKLIST ENFORCED* ➜ Account `{user_target}` dropped from database permissions.", parse_mode="Markdown")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) in db:
        db[str(user_target)]["blocked"] = False
        save_db(db)
        await update.message.reply_text(f"🟢 *BLACKLIST REVOKED* ➜ Account `{user_target}` access restored.", parse_mode="Markdown")

async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_target = context.args[0]
    if str(user_target) in db:
        db[str(user_target)]["expires_at"] = None
        save_db(db)
        await update.message.reply_text(f"⚠️ *TIMELINE PURGED* ➜ Subscription data erased for user `{user_target}`.", parse_mode="Markdown")

# ========= FILE HANDLER WITH LIVE COUNTER PANEL =========

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = check_user_status(user_id)
    
    if status in ["blocked", "expired"]:
        await update.message.reply_text("❌ System lock active. Subscription required.")
        return

    document: Document = update.message.document
    if not document.file_name.endswith(".txt"):
        await update.message.reply_text("❌ *Transmission Rejected.* Please submit a plain text (.txt) list.", parse_mode="Markdown")
        return

    initial_msg = await update.message.reply_text("⚡ *Establishing secured uplink... Downloading batch payload...*", parse_mode="Markdown")

    file = await document.get_file()
    file_path = f"links_{user_id}.txt"
    await file.download_to_drive(file_path)

    links = read_links_file(file_path)
    total = len(links)
    
    live_count = 0
    dead_count = 0
    current_index = 0

    await initial_msg.edit_text("⚙️ *Compiling data streams... Executing batch filters.*")

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
                    f"🌟 *HIT DETECTED: LIVE NODE*\n"
                    f" ├ 🔗 *Target:* {url}\n"
                    f" └ 📟 *Response:* `{result}`", 
                    parse_mode="Markdown"
                )
            else:
                dead_count += 1
                STATS["total_dead"] += 1

            # HUD Display Refresh
            if current_index % 1 == 0 or current_index == total:
                panel_text = (
                    f"🛰️ *LIVE HUD TERMINAL DISPLAY*\n"
                    f"═\n"
                    f"🔄 Batch Progress: `[{current_index}/{total}]` targets\n"
                    f"📡 Last Stream Intercepted: `{result}`\n"
                    f"═\n"
                    f"👑 Hits Mapped (Sent): `[ {live_count} ]` \n"
                    f"🗑️ Cleaned/Silent Nodes: `[ {dead_count} ]`"
                )
                try:
                    await initial_msg.edit_text(panel_text, parse_mode="Markdown")
                except:
                    pass

            await asyncio.sleep(3)

    final_stats = (
        f"🏁 *OPERATION COMPLETED SUCCESSFUL*\n"
        f"═\n"
        f"📦 Total Scanned Entities: `{total}`\n"
        f"💎 Valid Live Nodes Extracted: `{live_count}`\n"
        f"🛡️ Security Blocked/Dead: `{dead_count}`"
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
            await update.message.reply_text("⛔ Access denied. Identity flagged.")
        elif status == "expired":
            await update.message.reply_text(f"⚠️ License missing or expired. Your identification: `{user_id}`", parse_mode="Markdown")

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

    print("Hydra Core Gateway Started...")
    app.run_polling()
