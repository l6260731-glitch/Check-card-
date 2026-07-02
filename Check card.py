import os
import asyncio
import httpx
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========= CONFIG =========

API_TOKEN = "8407490230:AAFEnKQAZ9sREuVY3UJ7Rf2yil23TCp7eRg"
API_URL = "http://gatescheck.duckdns.org:7000/check"
CARD = "5108750403664279|02|2028|402"

# ⚠️ ضع الأيدي (ID) الخاص بك هنا لحماية البوت
ADMIN_ID = 6843321125

# الرسالة الترحيبية التعريفية بالردود الشغالة
WELCOME_MESSAGE = """
🤖 أهلاً بك في بوت فحص الروابط المتطور!

هذا البوت مخصص لإرسال الروابط الـ (Live) فقط.
الروابط التي تعتبر شغالة (Live) ويتم إرسالها هي التي تعطي الردود التالية فقط:
✅ Unknown
✅ INSUFFICIENT_FUNDS
✅ GATE ERROR TOKEN
✅ Payer cannot pay for this transaction...

أي ردود أخرى أو أخطاء في الاتصال سيتم استبعادها وتجاهلها تلقائياً.
"""

# ========= HELPERS & SECURITY =========

def is_admin(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم هو الأدمن"""
    return user_id == ADMIN_ID

def clean_url(url: str):
    url = url.strip()
    if not url:
        return None
    if not url.startswith("http"):
        url = "http://" + url
    return url

def is_link_live(result_text: str) -> bool:
    """
    المنطق البرمجي الصحيح:
    البوت يعبر الرابط (Live) فقط إذا كانت النتيجة تحتوي على أحد الردود المطلوبة.
    """
    live_signals = [
        "Unknown",
        "INSUFFICIENT_FUNDS",
        "GATE ERROR TOKEN",
        "Payer cannot pay for this transaction"
    ]
    
    # إذا كانت النتيجة تحتوي على أي كلمة من القائمة المحددة، يُعتبر الرابط لايف وشغال
    for signal in live_signals:
        if signal.lower() in result_text.lower():
            return True
            
    # أي نتيجة أخرى تعتبر غير صالحة (Dead)
    return False

# ========= API CHECK =========

async def check_url_async(client, url):
    url = clean_url(url)
    if not url:
        return "❌ Empty"

    try:
        params = {
            "url": url,
            "card": CARD,
            "amount": 0.01
        }

        # retry بسيط
        for _ in range(2):
            try:
                r = await client.get(API_URL, params=params, timeout=12)
                data = r.json()
                result = data.get("result", "Unknown")
                return result
            except:
                continue

        return "API Error"

    except:
        return "Connection Error"

# ========= FILE READER =========

def read_links_file(filename):
    links = []
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            url = clean_url(line)
            if url:
                links.append(url)
    return links

# ========= COMMANDS =========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مستقبل أمر /start مع حماية الأدمن والرسالة الترحيبية"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ حسابك مش متفعل.")
        return
        
    await update.message.reply_text(WELCOME_MESSAGE)

async def site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ حسابك مش متفعل.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /site example.com")
        return

    url = " ".join(context.args)
    await update.message.reply_text("🔍 Checking...")

    async with httpx.AsyncClient() as client:
        result = await check_url_async(client, url)

    # التحقق هل لايف بناءً على الفلترة الجديدة
    if is_link_live(result):
        await update.message.reply_text(f"✅ Live Link:\n{url} ➜ {result}")
    else:
        await update.message.reply_text(f"❌ الرابط مش لايف (تم التجاهل بسبب الرد: {result})")

# ========= FILE HANDLER =========

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ حسابك مش متفعل.")
        return

    document: Document = update.message.document

    if not document.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please upload .txt file")
        return

    await update.message.reply_text("📥 Processing file...")

    file = await document.get_file()
    file_path = "links.txt"
    await file.download_to_drive(file_path)

    links = read_links_file(file_path)

    total = len(links)
    live_count = 0
    dead_count = 0

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in links:
            result = await check_url_async(client, url)

            # يرسل الرابط فقط إذا كانت نتيجته تطابق الردود المطلوبة (Live)
            if is_link_live(result):
                live_count += 1
                await update.message.reply_text(f"✅ Live:\n{url} ➜ {result}")
            else:
                dead_count += 1
                # يتم تجاهل الروابط الميتة تماماً ولا يرسلها في الشات

            await asyncio.sleep(3)  # 🐢 delay 3 ثواني لكل رابط

    stats = (
        f"\n📊 RESULTS SUMMARY\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 Total Processed: {total}\n"
        f"✅ Live Sent (Matches your list): {live_count}\n"
        f"❌ Ignored (Other Responses): {dead_count}"
    )

    await update.message.reply_text(stats)
    os.remove(file_path)

# ========= RUN =========

if __name__ == "__main__":
    app = ApplicationBuilder().token(API_TOKEN).build()

    # إضافة الموزعات (Handlers)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("site", site_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    # لحظر غير الأدمن من إرسال أي رسائل عشوائية للبوت
    @app.on_message(filters.TEXT & ~filters.COMMAND)
    async def block_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ حسابك مش متفعل.")

    print("Bot Started...")
    app.run_polling()
