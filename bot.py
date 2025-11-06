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
STRING_SESSION = "1BJWap1sBu3eQHFPobqYETfcj_FqUqQw8JYWu-NHgpMV88zhkqB_dNNLJPrb58xZi3gEzkAT6COK8AJZZKVhVoN9SWlK1GwGvXkVe_Ll5J-mOiajSHHwJQMQTILOZFrM34IV0xrtF4gpC2oK8DPxlrUOydCa7Wj3PxP0kzh66SQ80v2Ai3g-A2mNz2P1v0vPyJF8EMiwM0sD_euqWKVdptWcXf9_TVmAeUq1X-39HKubeSvHmOtbFoQHwWuMKRSUo7LpcwAU9VAHto-pIVWBnX2qcHGb377nhDZgGv43k0XSktJfBHWrKlgNHUuE2ImOL0T4n-i7LoePmiRiIadfeRjtBy3NePoY="

# Bot modelleri
BOT_MODELS = {
    "gpt4mini": "@GPT4Tbot",
    "deepseek": "@GPT4Telegrambot",
    "gemini1.5pro": "@ChatGPT_General_Bot",
    "gpt5model": "@gpt3_unlim_chatbot",
    "sorgu": "@BedavaaSorguPaneli_Bot",
    "miyavrem": "@Miyavrem_bot"
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
                "GPT5 Model": "/gpt5model?message=merhaba",
                "TC Sorgu": "/sorgu/tcpro?tc=11111111110",
                "İş Arkadaşı Sorgu": "/sorgu/isarkadasi?tc=11111111110",
                "Operatör Sorgu": "/sorgu/operator?numara=5555555555",
                "Plaka Sorgu": "/sorgu/plaka?plaka=34ABC123",
                "TC-Plaka Sorgu": "/sorgu/tcplaka?tc=11111111110", 
                "Vesika Sorgu": "/sorgu/vesika?tc=11111111110"
            }
        }, ensure_ascii=False),
        mimetype="application/json"
    )

# ----------- AKILLI CHAT ENDPOINT'İ -----------
@app.route("/chat", methods=["GET", "POST"])
def chat():
    """Akıllı endpoint - komutları otomatik tanır ve ilgili bot'a yönlendirir"""
    try:
        if request.method == "POST":
            data = request.get_json(silent=True)
            message = data.get("message") if data else None
        else:
            message = request.args.get("message")

        if not message:
            return Response(json.dumps({"reply": "Mesaj gerekli"}, ensure_ascii=False),
                            mimetype="application/json", status=400)

        # Komutları kontrol et ve ilgili bot'a yönlendir
        message_lower = message.strip().lower()
        
        if message_lower.startswith("/tcpro"):
            tc = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/tcpro {tc}"))
        elif message_lower.startswith("/isarkadasi"):
            tc = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/isarkadasi {tc}"))
        elif message_lower.startswith("/operator"):
            numara = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/operator {numara}"))
        elif message_lower.startswith("/plaka"):
            plaka = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/plaka {plaka}"))
        elif message_lower.startswith("/tcplaka"):
            tc = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/tcplaka {tc}"))
        elif message_lower.startswith("/vesika"):
            tc = message.split()[-1] if len(message.split()) > 1 else ""
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/vesika {tc}"))
        else:
            # Normal mesajlar deepseek'e gider
            reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["deepseek"], message))

        return Response(json.dumps({"reply": reply_text}, ensure_ascii=False),
                        mimetype="application/json")

    except Exception as e:
        return Response(json.dumps({"reply": f"Hata: {str(e)}"}, ensure_ascii=False),
                        mimetype="application/json", status=500)

# ----------- YAPAY ZEKA ENDPOINT'LERİ -----------
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

# ----------- RESTful SORGU ENDPOINT'LERİ -----------
@app.route("/sorgu/tcpro", methods=["GET"])
def sorgu_tcpro():
    """TC Sorgu"""
    tc = request.args.get("tc", "").strip()
    if not tc:
        return Response(
            json.dumps({"error": "TC kimlik numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/tcpro {tc}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "tcpro",
            "tc": tc,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/sorgu/isarkadasi", methods=["GET"])
def sorgu_isarkadasi():
    """İş Arkadaşı Sorgu"""
    tc = request.args.get("tc", "").strip()
    if not tc:
        return Response(
            json.dumps({"error": "TC kimlik numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/isarkadasi {tc}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "isarkadasi",
            "tc": tc,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/sorgu/operator", methods=["GET"])
def sorgu_operator():
    """Operatör Sorgu"""
    numara = request.args.get("numara", "").strip()
    if not numara:
        return Response(
            json.dumps({"error": "Telefon numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["sorgu"], f"/operator {numara}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "operator",
            "numara": numara,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/sorgu/plaka", methods=["GET"])
def sorgu_plaka():
    """Plaka Sorgu"""
    plaka = request.args.get("plaka", "").strip()
    if not plaka:
        return Response(
            json.dumps({"error": "Plaka numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/plaka {plaka}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "plaka",
            "plaka": plaka,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/sorgu/tcplaka", methods=["GET"])
def sorgu_tcplaka():
    """TC-Plaka Sorgu"""
    tc = request.args.get("tc", "").strip()
    if not tc:
        return Response(
            json.dumps({"error": "TC kimlik numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/tcplaka {tc}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "tcplaka",
            "tc": tc,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
    )

@app.route("/sorgu/vesika", methods=["GET"])
def sorgu_vesika():
    """Vesika Sorgu"""
    tc = request.args.get("tc", "").strip()
    if not tc:
        return Response(
            json.dumps({"error": "TC kimlik numarası gerekli"}, ensure_ascii=False),
            mimetype="application/json",
            status=400
        )
    
    reply_text = run_async_in_worker_thread(send_message_queue(BOT_MODELS["miyavrem"], f"/vesika {tc}"))
    
    return Response(
        json.dumps({
            "sorgu_tipi": "vesika",
            "tc": tc,
            "sonuc": reply_text
        }, ensure_ascii=False),
        mimetype="application/json"
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
    print("🎯 RESTful Sorgu Endpoint'leri:")
    print("   - GET /sorgu/tcpro?tc=11111111110")
    print("   - GET /sorgu/isarkadasi?tc=11111111110") 
    print("   - GET /sorgu/operator?numara=5555555555")
    print("   - GET /sorgu/plaka?plaka=34ABC123")
    print("   - GET /sorgu/tcplaka?tc=11111111110")
    print("   - GET /sorgu/vesika?tc=11111111110")
    print(f"🔑 API ID: {API_ID}")
    print("⏳ Telegram client başlatılıyor...")
    app.run(host="0.0.0.0", port=port, debug=False)
