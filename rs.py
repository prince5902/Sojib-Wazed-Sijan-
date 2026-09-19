import os
import re
import json
import asyncio
import requests
import phonenumbers
from phonenumbers import geocoder
from flask import Flask
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes
)

try:
    from telegram import CopyTextButton
except ImportError:
    CopyTextButton = None

# === CONFIGURATION ===
BOT_TOKEN = "8389209190:AAHy_K4T9CLQ2UnT24-Y1U89CVN4w-BraWU"
PANEL_API_KEY = "ZNX_ZMJG4X1QBNIUR1HDSZ1P31ED"
GROUP_ID = -1004342739367
ADMIN_USER_ID = 7270449654  # আপনার অ্যাডমিন ইউজার আইডি

# Zenex Network API Endpoint
API_BASE_URL = "https://api.zenexnetwork.com/v1/getnum"
OTP_FEED_URL = "https://zenexnetwork.com/api/otp?count=200"
POLL_INTERVAL = 3

RANGES_FILE = "ranges.json"
ACTIVE_NUMBERS_FILE = "active_numbers.json"

# Flask সার্ভার (Render-এ বট সচল রাখার জন্য)
app = Flask(__name__)

@app.route('/')
def home():
    return "Zenex Number Bot with Admin Panel is active!"

def load_ranges():
    if os.path.exists(RANGES_FILE):
        try:
            with open(RANGES_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_ranges(data):
    with open(RANGES_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_active_numbers():
    if os.path.exists(ACTIVE_NUMBERS_FILE):
        try:
            with open(ACTIVE_NUMBERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_active_numbers(data):
    with open(ACTIVE_NUMBERS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_country_info(phone_number):
    if not str(phone_number).startswith('+'):
        phone_number = '+' + str(phone_number)
    try:
        parsed = phonenumbers.parse(phone_number)
        region = phonenumbers.region_code_for_number(parsed)
        if region:
            flag = chr(ord(region[0]) + 127397) + chr(ord(region[1]) + 127397)
        else:
            flag = "🏳️"
        iso = region or "UN"
        return flag, iso
    except:
        return "🏳️", "UN"

def extract_otp(msg):
    otp_match = re.search(r'\d{3}[-\s]?\d{3,4}|\d{4,8}', str(msg))
    return otp_match.group(0) if otp_match else 'Unknown'

# ব্যাকগ্রাউন্ড লুপ: শুধুমাত্র রিয়েল-টাইম নতুন ওটিপি ট্র্যাক করে পাঠাবে
async def background_otp_forwarder(bot):
    seen_otps = set()
    is_first_run = True
    
    while True:
        try:
            resp = requests.get(OTP_FEED_URL, timeout=10).json()
            if isinstance(resp, list):
                if is_first_run:
                    for item in resp:
                        uid = f"{item[0]}_{item[1]}_{item[2]}"
                        seen_otps.add(uid)
                    is_first_run = False
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                for item in reversed(resp):
                    try:
                        service = item[0]
                        num = item[1]
                        msg = item[2]
                        uid = f"{service}_{num}_{msg}"
                        
                        if uid not in seen_otps:
                            seen_otps.add(uid)
                            
                            if len(seen_otps) > 1000:
                                list_items = list(seen_otps)
                                seen_otps = set(list_items[500:])

                            clean_num = str(num).replace("+", "").strip()
                            flag, iso = get_country_info(num)
                            otp = extract_otp(msg)
                            
                            # ১. গ্রুপে লাইভ কোড পাঠানো
                            group_text = f"{flag} <b>#{iso} 📱 {service} {num}</b> ➡️"
                            if CopyTextButton:
                                try:
                                    g_row1 = [InlineKeyboardButton(text=f"🔑 {otp}", copy_text=CopyTextButton(text=otp))]
                                except:
                                    g_row1 = [InlineKeyboardButton(text=f"🔑 {otp}", callback_data="noop")]
                            else:
                                g_row1 = [InlineKeyboardButton(text=f"🔑 {otp}", callback_data="noop")]
                                
                            group_markup = InlineKeyboardMarkup([
                                g_row1,
                                [InlineKeyboardButton(text="⚡ Zenex Panel", url="https://t.me/XclusoRPanelBot")]
                            ])
                            
                            try:
                                await bot.send_message(
                                    chat_id=GROUP_ID,
                                    text=group_text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=group_markup
                                )
                            except Exception as e:
                                print(f"❌ Failed to send to group: {e}")
                            
                            # ২. বটে (প্রাইভেটে): মেম্বার যে নাম্বার নিয়েছে তার ইনবক্সে পাঠানো
                            active_nums = load_active_numbers()
                            for user_id, saved_num in active_nums.items():
                                if clean_num == saved_num:
                                    pm_text = (
                                        f"🔔 **New OTP Received!**\n\n"
                                        f"🌐 **Service:** {service.upper()}\n"
                                        f"📱 **Number:** `{num}`\n"
                                        f"💬 **Message:** `{msg}`\n\n"
                                        f"🔑 **OTP Code:** `{otp}`"
                                    )
                                    if CopyTextButton:
                                        try:
                                            pm_row = [InlineKeyboardButton(text=f"📋 Copy OTP: {otp}", copy_text=CopyTextButton(text=otp))]
                                        except:
                                            pm_row = [InlineKeyboardButton(text=f"🔑 {otp}", callback_data="noop")]
                                    else:
                                        pm_row = [InlineKeyboardButton(text=f"🔑 {otp}", callback_data="noop")]
                                        
                                    pm_markup = InlineKeyboardMarkup([pm_row])
                                    
                                    try:
                                        await bot.send_message(
                                            chat_id=int(user_id),
                                            text=pm_text,
                                            parse_mode=ParseMode.HTML,
                                            reply_markup=pm_markup
                                        )
                                    except Exception as e:
                                        print(f"❌ Failed to send PM to user {user_id}: {e}")

                            await asyncio.sleep(0.2)
                    except Exception as inner_e:
                        print(f"Inner loop error: {inner_e}")
        except Exception as e:
            print(f"API Fetch error: {e}")
            
        await asyncio.sleep(POLL_INTERVAL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👑 **NUMBER BOT**\n\n"
        "🚀 **Welcome to Number & OTP Service**\n\n"
        "✅ Choose an option below to continue using the bot.\n\n"
        "💎 **Premium OTP Service**\n"
        "🛡️ **DEVELOPED BY SIJAN** 🛡️"
    )
    
    keyboard = [
        [InlineKeyboardButton("📱 GET NUMBER", callback_data="menu_services"), InlineKeyboardButton("🔍 Search Number", callback_data="search_num")],
        [InlineKeyboardButton("👑 TRAFFIC", callback_data="traffic"), InlineKeyboardButton("🔐 2FA ONLINE", callback_data="2fa")],
        [InlineKeyboardButton("🎁 Refer", callback_data="refer"), InlineKeyboardButton("📅 WITHDRAWAL", callback_data="withdrawal")],
        [InlineKeyboardButton("👤 SUPPORT", url="https://t.me/")]
    ]
    
    user_id = update.effective_user.id
    if user_id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel (View Ranges)", callback_data="admin_panel")])

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(welcome_text, reply_markup=markup, parse_mode="Markdown")

async def set_range_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ আপনার এই কমান্ড ব্যবহারের অনুমতি নেই!")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ সঠিক নিয়মে কমান্ড দিন:\n"
            "`/setrange <service> <range>`\n\n"
            "উদাহরণ:\n"
            "`/setrange whatsapp 4473845XXX`",
            parse_mode="Markdown"
        )
        return

    service = args[0].lower()
    range_value = args[1]

    ranges = load_ranges()
    ranges[service] = range_value
    save_ranges(ranges)

    await update.message.reply_text(f"✅ সফলভাবে **{service.upper()}** এর জন্য নতুন রেঞ্জ সেট করা হয়েছে:\n`{range_value}`", parse_mode="Markdown")

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_USER_ID:
        await query.answer("Access Denied!", show_alert=True)
        return
    
    ranges = load_ranges()
    text = "⚙️ **Admin Panel - Saved Ranges:**\n\n"
    if ranges:
        for s, r in ranges.items():
            text += f"🔹 **{s.upper()}**: `{r}`\n"
    else:
        text += "কোনো রেঞ্জ এখনো সেভ করা হয়নি।"

    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def menu_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "📍 **Select a service:**"
    keyboard = [
        [InlineKeyboardButton("💬 WHATSAPP", callback_data="get_whatsapp"), InlineKeyboardButton("✈️ TELEGRAM", callback_data="get_telegram")],
        [InlineKeyboardButton("📘 FACEBOOK", callback_data="get_facebook"), InlineKeyboardButton("📸 INSTAGRAM", callback_data="get_instagram")],
        [InlineKeyboardButton("🎵 TIKTOK", callback_data="get_tiktok"), InlineKeyboardButton("🌐 GOOGLE", callback_data="get_google")],
        [InlineKeyboardButton("❌ Close", callback_data="main_menu")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def fetch_and_show_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    data_parts = query.data.split("_")
    service = data_parts[1].lower()
    
    ranges = load_ranges()
    if service not in ranges:
        await query.answer(f"❌ {service.upper()} এর জন্য কোনো রেঞ্জ সেট করা হয়নি!", show_alert=True)
        return
    
    range_value = ranges[service]
    await query.answer("Fetching new number from Zenex...")
    
    headers = {
        "mapikey": PANEL_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "range": range_value,
        "is_national": False,
        "remove_plus": False
    }

    try:
        response = requests.post(API_BASE_URL, json=payload, headers=headers)
        res_data = response.json()

        if res_data.get("meta", {}).get("code") == 200:
            number_data = res_data.get("data", {})
            number = number_data.get("number")
            country = number_data.get("country", "Unknown")
            
            clean_num = str(number).replace("+", "").strip()
            active_nums = load_active_numbers()
            active_nums[user_id] = clean_num
            save_active_numbers(active_nums)
            
            text = (
                f"🌐 **Country:** {country}\n"
                f"🛠️ **Service:** {service.upper()}\n\n"
                f"⏳ **Waiting for OTP...**"
            )
            
            if CopyTextButton:
                try:
                    num_btn = InlineKeyboardButton(text=f"📋 {number}", copy_text=CopyTextButton(text=number))
                except:
                    num_btn = InlineKeyboardButton(text=f"📱 {number}", callback_data="noop")
            else:
                num_btn = InlineKeyboardButton(text=f"📱 {number}", callback_data="noop")

            keyboard = [
                [num_btn],
                [InlineKeyboardButton("🗑️ Remove CC", callback_data=f"removecc_{service}_{number}")],
                [InlineKeyboardButton("🔄 Change Number", callback_data=f"get_{service}")],
                [InlineKeyboardButton("🔙 Back", callback_data="menu_services")]
            ]
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            error_msg = res_data.get("meta", {}).get("message", "Unknown error")
            await query.answer(f"❌ প্যানেল এরর: {error_msg}", show_alert=True)
    except Exception as e:
        await query.answer(f"⚠️ Error: {str(e)}", show_alert=True)

async def remove_cc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data_parts = query.data.split("_")
    if len(data_parts) < 3:
        await query.answer("Invalid action", show_alert=True)
        return
    
    service = data_parts[1]
    number = data_parts[2]
    
    try:
        if not number.startswith('+'):
            num_parse = '+' + number
        else:
            num_parse = number
        parsed = phonenumbers.parse(num_parse)
        national_number = str(parsed.national_number)
    except:
        national_number = number.replace("+", "")
        
    await query.answer("✅ কান্ট্রি কোড সফলভাবে রিমুভ করা হয়েছে!", show_alert=True)
    
    if CopyTextButton:
        try:
            num_btn = InlineKeyboardButton(text=f"📋 {national_number} (No CC)", copy_text=CopyTextButton(text=national_number))
        except:
            num_btn = InlineKeyboardButton(text=f"📱 {national_number}", callback_data="noop")
    else:
        num_btn = InlineKeyboardButton(text=f"📱 {national_number}", callback_data="noop")

    keyboard = [
        [num_btn],
        [InlineKeyboardButton("✅ CC Removed", callback_data="noop")],
        [InlineKeyboardButton("🔄 Change Number", callback_data=f"get_{service}")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_services")]
    ]
    
    try:
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "main_menu":
        await start(update, context)
    elif data == "menu_services":
        await menu_services(update, context)
    elif data.startswith("get_"):
        await fetch_and_show_number(update, context)
    elif data.startswith("removecc_"):
        await remove_cc_handler(update, context)
    elif data == "admin_panel":
        await admin_panel_handler(update, context)
    else:
        await query.answer("এই ফিচারটি শীঘ্রই আসছে!", show_alert=True)

async def post_init(application):
    application.create_task(background_otp_forwarder(application.bot))

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setrange", set_range_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Zenex Number Bot is running smoothly...")
    application.run_polling()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    
    main()
