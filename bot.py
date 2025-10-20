import json
import os
import asyncio
import time
import random
from flask import Flask, request, Response
from telethon import TelegramClient
from telethon.sessions import StringSession
import threading

API_ID = 24179304
API_HASH = "6fdbaf87f6fa54a1a8a51603bf38c2d1"
STRING_SESSION ="1BJWap1wBu8TcaDLsZN7HS_1iRSV-xzZQvWHhhThOny0A8ozLPIGQ2ZfgTQCCD4OlVlv2nHMOvYjGryL_jaEvO8QzcpdHaWO5B0dWQfyEqTSI_kCXpiN8HMEPJoaInb9Q32H5dDCVv2EqZe_D5_Hq-icRU1C8URX3f1J7-tz2K9cf9ioom489ZgXfRVJ-ciHvn3wpuQorb161luHqdI2Kb7ct_XskVOx-ZJ_5l5ispdWouVT8NsggTdC867gOWTqfHY9i4iuLwHq2RL9J1rJWqw3pQ9cKJtP4BE_CqbsLQTNFayM8QPO7wykPPWzr4XzSHzF0-oXFidn9akWIKaip41zxTDVFMYE="

# Bot modelleri
BOT_MODELS = {
    "gpt4mini": "@GPT4Tbot",
    "deepseek": "@GPT4Telegrambot", 
    "gemini1.5pro": "@ChatGPT_General_Bot",
    "gpt5model": "@gpt3_unlim_chatbot"
}

app = Flask(__name__)

# ----------- GLOBALLER -----------
client = None
message_queue = asyncio.Queue()
latest_sent = {}
client_lock = asyncio.Lock()

# Aynı mesajın tekrarını engelleme süresi
DUPLICATE_WINDOW = 3
# Bekleme süresi
WAIT_SECONDS = 10

# Client bağlantısını kontrol et ve yeniden başlat
async def ensure_client_connected():
    global client
    async with client_lock:
        if client is None:
            client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
            await client.start()
            print("✅ Yeni Telegram client başlatıldı")
        elif not client.is_connected():
            try:
                await client.disconnect()
            except:
                pass
            client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
            await client.start()
            print("🔄 Telegram client yeniden başlatıldı")
        return client

# Asenkron loop için thread
class TelegramWorkerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        
    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.telegram_worker())
    
    async def telegram_worker(self):
        """Kuyruktaki mesajları tek tek işler."""
        print("🔄 Telegram worker başlatılıyor...")
        
        while True:
            request_id, bot_username, message, future = await message_queue.get()
            try:
                now = time.time()
                
                # Sadece aynı request_id için spam kontrolü yap
                if request_id in latest_sent and now - latest_sent[request_id] < DUPLICATE_WINDOW:
                    future.set_result("⚠️ Aynı istek kısa sürede tekrar gönderildi, engellendi.")
                    message_queue.task_done()
                    continue

                latest_sent[request_id] = now

                # Client bağlantısını garanti et
                current_client = await ensure_client_connected()
                
                print(f"📤 Mesaj gönderiliyor: {bot_username} -> {message[:50]}...")
                sent_msg = await current_client.send_message(bot_username, message)
                last_reply = None
                start_time = time.time()

                # 🔥 10 saniye boyunca cevapları dinle
                while time.time() - start_time < WAIT_SECONDS:
                    try:
                        async for msg in current_client.iter_messages(bot_username, min_id=sent_msg.id, limit=5):
                            if not msg.out and getattr(msg, "text", None):
                                last_reply = msg.text
                                print(f"📥 Yanıt alındı: {last_reply[:50]}...")
                    except Exception as e:
                        print(f"⚠️ Mesaj dinleme hatası: {e}")
                        break
                    await asyncio.sleep(0.7)

                if last_reply:
                    future.set_result(last_reply)
                else:
                    future.set_result("⏳ Yanıt alınamadı (10 saniye içinde cevap gelmedi).")

            except Exception as e:
                print(f"❌ Worker hatası: {e}")
                # Client'ı sıfırla
                global client
                async with client_lock:
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
                        client = None
                
                future.set_result(f"❌ Hata: {str(e)}")
            finally:
                # Request ID'yi temizle (opsiyonel, bellek için)
                if request_id in latest_sent:
                    del latest_sent[request_id]
                message_queue.task_done()

# Worker thread'i başlat
worker_thread = TelegramWorkerThread()
worker_thread.start()

# Flask için asenkron fonksiyonları çalıştıracak yardımcı
def run_async_in_worker_thread(coro):
    """Asenkron fonksiyonu worker thread'in loop'unda çalıştırır"""
    try:
        future = asyncio.run_coroutine_threadsafe(coro, worker_thread.loop)
        return future.result(WAIT_SECONDS + 10)  # Timeout süresi
    except Exception as e:
        return f"❌ İstek işlenirken hata: {str(e)}"

# ----------- MESAJ GÖNDERME -----------
async def send_message_queue(bot_username: str, message: str):
    """Mesajı kuyruğa atar, işlenince sonucu döndürür."""
    future = worker_thread.loop.create_future()
    # Her istek için unique ID oluştur (timestamp + random)
    request_id = f"{time.time()}_{random.randint(1000, 9999)}"
    await message_queue.put((request_id, bot_username, message, future))
    return await future

# ----------- FLASK ROUTES -----------
@app.route("/", methods=["GET"])
def home():
    return Response(
        json.dumps({
            "status": "Nabi API çalışıyor ✅",
            "available_models": BOT_MODELS,
            "endpoints": {
                "Ana endpoint": "/chat?message=merhaba",
                "GPT4 Mini": "/gpt4mini?message=merhaba",
                "DeepSeek": "/deepseek?message=merhaba", 
                "Gemini 1.5 Pro": "/gemini1.5pro?message=merhaba",
                "GPT5 Model": "/gpt5model?message=merhaba"
            }
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/chat", methods=["GET", "POST"])
def chat():
    """Varsayılan endpoint (mevcut çalışmayı koru)"""
    try:
        if request.method == "POST":
            data = request.get_json(silent=True)
            message = data.get("message") if data else None
        else:
            message = request.args.get("message")

        if not message:
            return Response(json.dumps({"reply": "Mesaj gerekli"}, ensure_ascii=False),
                            mimetype="application/json", status=400)

        # Varsayılan olarak deepseek botunu kullan
        reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["deepseek"], message))

        return Response(json.dumps({"reply": reply_text}, ensure_ascii=False),
                        mimetype="application/json")

    except Exception as e:
        return Response(json.dumps({"reply": f"Hata: {str(e)}"}, ensure_ascii=False),
                        mimetype="application/json", status=500)

# ----------- MODEL SPESİFİK ENDPOINT'LER -----------
@app.route("/gpt4mini", methods=["GET", "POST"])
def gpt4mini():
    return handle_model_request("gpt4mini")

@app.route("/deepseek", methods=["GET", "POST"])
def deepseek():
    return handle_model_request("deepseek")

@app.route("/gemini1.5pro", methods=["GET", "POST"])
def gemini15pro():
    return handle_model_request("gemini1.5pro")

@app.route("/gpt5model", methods=["GET", "POST"])
def gpt5model():
    return handle_model_request("gpt5model")

def handle_model_request(model_name):
    """Model isteğini işleyen ortak fonksiyon"""
    try:
        if request.method == "POST":
            data = request.get_json(silent=True)
            message = data.get("message") if data else None
        else:
            message = request.args.get("message")

        if not message:
            return Response(
                json.dumps({"reply": "Mesaj gerekli", "model": model_name}, ensure_ascii=False),
                mimetype="application/json", 
                status=400
            )

        bot_username = BOT_MODELS.get(model_name)
        if not bot_username:
            return Response(
                json.dumps({"reply": "Geçersiz model", "model": model_name}, ensure_ascii=False),
                mimetype="application/json", 
                status=400
            )

        reply_text = run_async_in_worker_thread(send_message_queue(bot_username, message))

        return Response(
            json.dumps({
                "reply": reply_text,
                "model": model_name,
                "bot": bot_username
            }, ensure_ascii=False),
            mimetype="application/json"
        )

    except Exception as e:
        return Response(
            json.dumps({
                "reply": f"Hata: {str(e)}",
                "model": model_name
            }, ensure_ascii=False),
            mimetype="application/json", 
            status=500
        )

# ----------- HEALTH CHECK -----------
@app.route("/health", methods=["GET"])
def health():
    """Sağlık kontrolü endpoint'i"""
    try:
        # Basit bir test mesajı gönder
        test_result = run_async_in_worker_thread(send_message_queue(BOT_MODELS["deepseek"], "ping"))
        status = "healthy" if "ping" not in test_result.lower() else "degraded"
        
        return Response(
            json.dumps({
                "status": status,
                "test_result": test_result[:100] + "..." if len(test_result) > 100 else test_result
            }, ensure_ascii=False),
            mimetype="application/json"
        )
    except Exception as e:
        return Response(
            json.dumps({"status": "unhealthy", "error": str(e)}),
            mimetype="application/json",
            status=500
        )

# ----------- ÇALIŞTIRICI -----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Flask API başlatılıyor...")
    print("📋 Kullanılabilir modeller:")
    for model, bot in BOT_MODELS.items():
        print(f"   - {model}: {bot}")
    print(f"🔑 Yeni API ID: {API_ID}")
    print("⏳ Telegram client başlatılıyor...")
    app.run(host="0.0.0.0", port=port, debug=False)
