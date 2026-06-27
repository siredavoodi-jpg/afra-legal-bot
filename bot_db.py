import os
import sqlite3
import json
from datetime import datetime, timedelta
import time
import threading
import requests
from flask import Flask

# ================== تنظیمات ==================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# =============================================

if not GROQ_API_KEY or not TELEGRAM_TOKEN:
    print("❌ خطا: متغیرهای محیطی تنظیم نشده‌اند!")
    exit(1)

# ================== دیتابیس ==================
def get_db():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TEXT,
            trial_start TEXT,
            trial_crime TEXT,
            purchased_crimes TEXT,
            payment_history TEXT,
            pending_payment TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def create_user(user_id, username, first_name, last_name):
    conn = get_db()
    conn.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_at, purchased_crimes, payment_history)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, datetime.now().isoformat(), json.dumps([]), json.dumps([])))
    conn.commit()
    conn.close()

def start_trial(user_id, crime):
    conn = get_db()
    conn.execute('''
        UPDATE users SET trial_start = ?, trial_crime = ? WHERE user_id = ?
    ''', (datetime.now().isoformat(), crime, user_id))
    conn.commit()
    conn.close()

def get_trial_status(user_id):
    user = get_user(user_id)
    if not user or not user['trial_start']:
        return None, None
    
    trial_start = datetime.fromisoformat(user['trial_start'])
    trial_end = trial_start + timedelta(days=3)
    remaining = trial_end - datetime.now()
    
    if remaining.total_seconds() > 0:
        return user['trial_crime'], remaining
    else:
        return None, None

def add_purchased_crime(user_id, crime):
    user = get_user(user_id)
    purchased = json.loads(user['purchased_crimes'])
    if crime not in purchased:
        purchased.append(crime)
        conn = get_db()
        conn.execute('UPDATE users SET purchased_crimes = ? WHERE user_id = ?', (json.dumps(purchased), user_id))
        conn.commit()
        conn.close()

def get_purchased_crimes(user_id):
    user = get_user(user_id)
    if user:
        return json.loads(user['purchased_crimes'])
    return []

def add_payment_record(user_id, amount, method, crime):
    user = get_user(user_id)
    history = json.loads(user['payment_history'])
    history.append({
        'date': datetime.now().isoformat(),
        'amount': amount,
        'method': method,
        'crime': crime
    })
    conn = get_db()
    conn.execute('UPDATE users SET payment_history = ? WHERE user_id = ?', (json.dumps(history), user_id))
    conn.commit()
    conn.close()

def set_pending_payment(user_id, crime):
    conn = get_db()
    conn.execute('UPDATE users SET pending_payment = ? WHERE user_id = ?', (crime, user_id))
    conn.commit()
    conn.close()

def get_pending_payment(user_id):
    user = get_user(user_id)
    if user:
        return user['pending_payment']
    return None

def clear_pending_payment(user_id):
    conn = get_db()
    conn.execute('UPDATE users SET pending_payment = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ================== لیست جرایم با دسته‌بندی ==================
CRIMES = {
    # ===== جرایم کیفری =====
    'خیانت در امانت': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۶۷۴ قانون مجازات اسلامی'},
    'کلاهبرداری': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۱ قانون تشدید مجازات'},
    'فروش مال غیر': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۱ قانون مجازات'},
    'جعل و تزویر': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۵۲۳ قانون مجازات'},
    'استفاده از سند مجعول': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۵۲۷ قانون مجازات'},
    'تصرف عدوانی': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۶۹۰ قانون مجازات'},
    'تخریب عمدی': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۶۷۷ قانون مجازات'},
    'ضرب و جرح عمدی': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۶۱۴ قانون مجازات'},
    'سرقت حدی و تعزیری': {'category': 'کیفری', 'price': 25000, 'emoji': '⚖️', 'description': 'ماده ۲۶۵ قانون مجازات'},
    
    # ===== جرایم حقوقی =====
    'تنظیم قرارداد': {'category': 'حقوقی', 'price': 25000, 'emoji': '📜', 'description': 'مشاوره تنظیم قراردادهای حقوقی'},
    'مشاوره ملکی': {'category': 'حقوقی', 'price': 25000, 'emoji': '📜', 'description': 'مشاوره حقوقی املاک و مستغلات'},
    'مشاوره تجاری': {'category': 'حقوقی', 'price': 25000, 'emoji': '📜', 'description': 'مشاوره حقوقی شرکت‌ها و تجارت'},
    
    # ===== جرایم خانواده =====
    'طلاق': {'category': 'خانواده', 'price': 25000, 'emoji': '👨‍👩‍👧', 'description': 'مشاوره حقوقی طلاق و نفقه'},
    'مهریه': {'category': 'خانواده', 'price': 25000, 'emoji': '👨‍👩‍👧', 'description': 'مشاوره حقوقی مهریه و حقوق مالی'},
    'حضانت': {'category': 'خانواده', 'price': 25000, 'emoji': '👨‍👩‍👧', 'description': 'مشاوره حقوقی حضانت فرزندان'},
}

# ================== پرامپت سیستم ==================
def get_system_prompt(crime):
    prompts = {
        'خیانت در امانت': """تو یک دستیار حقوقی تخصصی در حوزه **خیانت در امانت** هستی.
چک‌لیست تخصصی:
- رابطه امانی: مال چگونه تحویل شد؟
- حدود اذن: اذن استفاده وجود داشت؟
- رفتار متهم: مال مسترد شده؟
- سوءنیت: اختلاف قبلی؟
- ادله: قرارداد، رسید، پیام‌ها""",
        
        'کلاهبرداری': """تو یک دستیار حقوقی تخصصی در حوزه **کلاهبرداری** هستی.
چک‌لیست تخصصی:
- وسایل متقلبانه: چه نوع فریب و نیرنگی؟
- نتیجه رفتار: آیا مالی برده شده؟
- سوءنیت: آیا قصد مجرمانه وجود داشته؟
- ادله: قراردادهای جعلی، چک‌های بی‌پشتوانه""",
    }
    return prompts.get(crime, "تو یک دستیار حقوقی تخصصی هستی.")

# ================== توابع کمکی ==================
def format_price(price):
    return f"{price:,}"

def get_crime_list_by_category(category):
    text = f"📋 *لیست جرایم {category}:*\n\n"
    for name, info in CRIMES.items():
        if info['category'] == category:
            text += f"{info['emoji']} *{name}*\n"
            text += f"   💰 قیمت: {format_price(info['price'])} تومان\n"
            text += f"   📌 {info['description']}\n\n"
    return text

# ================== توابع اصلی ==================
app = Flask(__name__)

def send_telegram_message(chat_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard)
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"❌ خطا در ارسال پیام: {e}")

def get_groq_response(user_message, crime):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = get_system_prompt(crime) + """
    
قوانین اساسی:
- هیچ چیز را حدس نزن
- اگر اطلاعات کافی نیست، فقط سوال بپرس
- نتیجه قطعی نده
- پاسخ‌ها به زبان فارسی حقوقی، مختصر و حرفه‌ای باشند.
"""
    
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 2000,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"❌ خطا: {response.status_code}"
    except Exception as e:
        return f"❌ خطا: {str(e)}"

def get_main_keyboard():
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚖️ جرایم کیفری", "callback_data": "category_کیفری"}],
            [{"text": "📜 جرایم حقوقی", "callback_data": "category_حقوقی"}],
            [{"text": "👨‍👩‍👧 جرایم خانواده", "callback_data": "category_خانواده"}],
            [{"text": "⏳ وضعیت آزمون من", "callback_data": "my_trial"}],
            [{"text": "🛒 خرید جرم", "callback_data": "buy_crime"}],
            [{"text": "📞 پشتیبانی", "callback_data": "support"}]
        ]
    }
    return keyboard

def get_crime_keyboard(category):
    keyboard = {"inline_keyboard": []}
    for name, info in CRIMES.items():
        if info['category'] == category:
            keyboard["inline_keyboard"].append([{"text": f"{info['emoji']} {name}", "callback_data": f"select_{name}"}])
    keyboard["inline_keyboard"].append([{"text": "🔙 بازگشت به منو", "callback_data": "back"}])
    return keyboard

def welcome_message():
    return """⚖️ *دستیار حقوقی وکلای افرا*

سلام! من یک دستیار هوشمند حقوقی هستم.

📋 *دسته‌بندی جرایم:*
⚖️ کیفری
📜 حقوقی
👨‍👩‍👧 خانواده

💡 *نحوه کار:*
• هر جرم را ۳ روز رایگان آزمایش کنید
• پس از آزمون، ۲۵,۰۰۰ تومان پرداخت کنید
• جرایم خریداری‌شده برای همیشه فعال می‌شوند

از دکمه‌های زیر شروع کنید:
"""

# ================== پردازش دکمه‌ها ==================
def handle_callback_query(chat_id, user_id, data):
    user = get_user(user_id)
    if not user:
        create_user(user_id, "", "", "")
        send_telegram_message(chat_id, welcome_message(), get_main_keyboard())
        return
    
    # بازگشت به منو
    if data == "back":
        send_telegram_message(chat_id, welcome_message(), get_main_keyboard())
        return
    
    # نمایش جرایم یک دسته
    if data.startswith("category_"):
        category = data.replace("category_", "")
        text = get_crime_list_by_category(category)
        send_telegram_message(chat_id, text, get_crime_keyboard(category))
        return
    
    # وضعیت آزمون
    if data == "my_trial":
        trial_crime, trial_remaining = get_trial_status(user_id)
        purchased = get_purchased_crimes(user_id)
        
        text = "📊 *وضعیت شما:*\n\n"
        
        if purchased:
            text += f"✅ جرایم خریداری‌شده: {', '.join(purchased)}\n\n"
        
        if trial_crime and trial_remaining and trial_remaining.total_seconds() > 0:
            days = trial_remaining.days
            hours = trial_remaining.seconds // 3600
            text += f"⏳ آزمون جرم *{trial_crime}*: {days} روز و {hours} ساعت باقی مانده"
        else:
            text += "❌ هیچ آزمون فعالی ندارید."
        
        send_telegram_message(chat_id, text, get_main_keyboard())
        return
    
    # خرید جرم
    if data == "buy_crime":
        purchased = get_purchased_crimes(user_id)
        text = "🛒 *خرید جرم*\n\n"
        text += "لطفاً از منوی زیر دسته مورد نظر را انتخاب کنید:\n"
        send_telegram_message(chat_id, text, get_main_keyboard())
        return
    
    # پشتیبانی
    if data == "support":
        text = "📞 *پشتیبانی*\n\n"
        text += "📱 تلگرام: @AfraSupport\n"
        text += "📧 ایمیل: support@afra.ir"
        send_telegram_message(chat_id, text, get_main_keyboard())
        return
    
    # انتخاب جرم
    for crime_name in CRIMES.keys():
        if data == f"select_{crime_name}":
            purchased = get_purchased_crimes(user_id)
            
            # اگر قبلاً خریداری شده
            if crime_name in purchased:
                send_telegram_message(chat_id, f"✅ شما جرم *{crime_name}* را خریداری کرده‌اید.", get_main_keyboard())
                return
            
            # بررسی آزمون فعال
            trial_crime, trial_remaining = get_trial_status(user_id)
            if trial_crime and trial_remaining and trial_remaining.total_seconds() > 0:
                if trial_crime == crime_name:
                    send_telegram_message(chat_id, f"⏳ شما در حال آزمون *{crime_name}* هستید.", get_main_keyboard())
                    return
                else:
                    send_telegram_message(chat_id, f"⚠️ شما در حال آزمون *{trial_crime}* هستید. برای آزمون جدید صبر کنید.", get_main_keyboard())
                    return
            
            # شروع آزمون جدید
            start_trial(user_id, crime_name)
            send_telegram_message(chat_id, f"✅ آزمون ۳ روزه *{crime_name}* شروع شد!", get_main_keyboard())
            
            # نمایش لینک پرداخت
            payment_text = f"""💳 *پرداخت برای {crime_name}*

پس از اتمام آزمون ۳ روزه، برای فعال‌سازی همیشگی مبلغ ۲۵,۰۰۰ تومان پرداخت کنید.

🔗 لینک پرداخت:
[پرداخت از طریق زرین‌پال](https://zarinpal.com/pay/...)

📌 پس از پرداخت، شماره پیگیری را برای ما ارسال کنید تا دسترسی شما فعال شود."""
            send_telegram_message(chat_id, payment_text, get_main_keyboard())
            return
    
    send_telegram_message(chat_id, "❌ گزینه نامعتبر.", get_main_keyboard())

# ================== پردازش پیام‌ها ==================
def handle_message(chat_id, text, user_id, username, first_name, last_name):
    user = get_user(user_id)
    if not user:
        create_user(user_id, username, first_name, last_name)
        send_telegram_message(chat_id, welcome_message(), get_main_keyboard())
        return
    
    if text.startswith('/start'):
        send_telegram_message(chat_id, welcome_message(), get_main_keyboard())
        return
    
    # بررسی شماره پیگیری پرداخت
    if text.isdigit() and len(text) >= 10:
        pending = get_pending_payment(user_id)
        if pending:
            add_purchased_crime(user_id, pending)
            clear_pending_payment(user_id)
            send_telegram_message(chat_id, f"✅ پرداخت شما تأیید شد! جرم *{pending}* فعال شد.", get_main_keyboard())
            return
        else:
            send_telegram_message(chat_id, "❌ هیچ پرداخت در انتظاری برای شما وجود ندارد.", get_main_keyboard())
            return
    
    # بررسی دسترسی کاربر
    purchased = get_purchased_crimes(user_id)
    trial_crime, trial_remaining = get_trial_status(user_id)
    
    if purchased:
        crime = purchased[0]
        send_telegram_message(chat_id, f"⏳ تحلیل پرونده بر اساس *{crime}*...")
        response = get_groq_response(text, crime)
        send_telegram_message(chat_id, response, get_main_keyboard())
        return
    
    if trial_crime and trial_remaining and trial_remaining.total_seconds() > 0:
        send_telegram_message(chat_id, f"⏳ تحلیل پرونده بر اساس *{trial_crime}*... (آزمون)")
        response = get_groq_response(text, trial_crime)
        send_telegram_message(chat_id, response, get_main_keyboard())
        return
    
    send_telegram_message(chat_id, "⚠️ شما دسترسی به هیچ جرمی ندارید.\n\nابتدا یک جرم را برای آزمون ۳ روزه انتخاب کنید.", get_main_keyboard())

# ================== Flask Routes ==================
@app.route('/')
def home():
    return "🤖 دستیار حقوقی وکلای افرا در حال اجراست!", 200

@app.route('/health')
def health():
    return "OK", 200

# ================== Polling ==================
def bot_polling():
    print("🤖 دستیار حقوقی وکلای افرا راه‌اندازی شد...")
    last_update_id = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 20, "offset": last_update_id + 1}
            response = requests.get(url, params=params, timeout=25)
            updates = response.json()
            
            if updates.get("ok"):
                for update in updates["result"]:
                    last_update_id = update["update_id"]
                    
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        user_id = msg["from"]["id"]
                        username = msg["from"].get("username", "")
                        first_name = msg["from"].get("first_name", "")
                        last_name = msg["from"].get("last_name", "")
                        text = msg.get("text", "")
                        
                        handle_message(chat_id, text, user_id, username, first_name, last_name)
                    
                    elif "callback_query" in update:
                        query = update["callback_query"]
                        chat_id = query["message"]["chat"]["id"]
                        user_id = query["from"]["id"]
                        data = query["data"]
                        handle_callback_query(chat_id, user_id, data)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ خطا: {e}")
            time.sleep(5)

# ================== اجرا ==================
if __name__ == "__main__":
    init_db()
    
    bot_thread = threading.Thread(target=bot_polling)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
