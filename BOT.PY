import requests
import json
import time

# ================== تنظیمات ==================
GROQ_API_KEY = "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"
TELEGRAM_TOKEN = "8908845135:AAGXXRindnuHvUtQ0FxvYoqdV5nWh2z2Jhs"
# =============================================

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """تو یک دستیار پژوهشی وکیل دادگستری در حوزه حقوق کیفری ایران هستی.
تو قاضی نیستی، حکم صادر نمی‌کنی، نتیجه قطعی نمی‌دهی.

وظایف تو:
- واقعیت‌ها را استخراج می‌کنی
- ابهام‌ها را مشخص می‌کنی
- سوال حرفه‌ای می‌پرسی
- تحلیل حقوقی مرحله‌ای ارائه می‌دهی

قوانین غیرقابل نقض:
- هیچ چیز را حدس نزن
- اگر اطلاعات کافی نیست، تحلیل نکن
- بین «واقعیت» و «ادعا» تفکیک کن
- هیچ ماده قانونی یا رأی را جعل نکن
- اگر منبع دقیق را نمی‌دانی، صریح بگو نمی‌دانم
- نتیجه قطعی نده
- همیشه احتمال دفاع طرف مقابل را در نظر بگیر

حوزه تخصصی: خیانت در امانت (ماده ۶۷۴ قانون مجازات اسلامی)

فرآیند کار:
۱. اگر اطلاعات ناقص است فقط سوال بپرس — تحلیل نکن
۲. مصاحبه حرفه‌ای: سوال‌های هدف‌دار و کوتاه برای کشف حقیقت
۳. تفکیک داده‌ها: واقعیت قطعی / ادعای موکل / موارد نامشخص / موارد قابل اثبات
۴. تحلیل کیفری: عناوین مجرمانه محتمل، ارکان جرم، ادله لازم، ضعف‌های پرونده
۵. دفاعیات طرف مقابل: توضیح دفاع، میزان اثر، راه پاسخ
۶. راهبرد عملی: اقدامات فوری و بعدی

پاسخ‌ها به زبان فارسی حقوقی، مختصر و حرفه‌ای باشند."""

def get_groq_response(user_message):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 2000,
        "temperature": 0.7
    }
    
    response = requests.post(GROQ_URL, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"❌ خطا: {response.status_code}\n{response.text}"

def send_telegram_message(chat_id, text):
    url = f"{TELEGRAM_URL}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=data)

def get_updates(offset=None):
    url = f"{TELEGRAM_URL}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    response = requests.get(url, params=params)
    return response.json()

def main():
    print("🤖 ربات وکالت افرا راه‌اندازی شد...")
    last_update_id = 0
    
    while True:
        try:
            updates = get_updates(last_update_id + 1)
            
            if updates.get("ok"):
                for update in updates["result"]:
                    last_update_id = update["update_id"]
                    
                    if "message" in update:
                        message = update["message"]
                        chat_id = message["chat"]["id"]
                        user_text = message.get("text", "")
                        
                        send_telegram_message(chat_id, "⏳ در حال بررسی پرونده...")
                        
                        response = get_groq_response(user_text)
                        
                        send_telegram_message(chat_id, response)
                        print(f"✅ پاسخ ارسال شد به {chat_id}")
            
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ خطا: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()