import json
import os
import asyncio
import time
import random
from flask import Flask, request, Response
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 21988008
API_HASH = "e059c48444174a36b60b147f1e5d4552"
STRING_SESSION = "1ApWapzMBu5mc-QLeVW8MdGXE63TVYLlKzjiXGTZkV-0G2fOO0hiApSRtKBVWBR7-u14hXcgcfzD0rAZid4s91M75ACrkyov4ZyTg-I_fewAhUKLtQ91mutw22fKqmAVfhkHX9NHf0_kO3BMsRr_yYaDWs0r-wE4B7Pa3IAJ41pRPk99kRtf8sXrJRyYABo3rqLHB1KLFCa5B8c8UE2edT7nc1yDhb416-KEXF7L0fNmByZxZHBihGnru_c7DBhIEgR2b0f9CZ34IbWsu7P7LCiU-em2rG5u2fZb31mS2dv52Rayrh4gRc-X1tdvNGPXGlHhglZdfJUO2f-ywC6j2He4UDY3GOKo="

# Bot modelleri
BOT_MODELS = {
    "gpt4mini": "@GPT4Tbot",
    "deepseek": "@GPT4Telegrambot", 
    "gemini1.5pro": "@ChatGPT_General_Bot",
    "gpt5model": "@gpt3_unlim_chatbot"
}

app = Flask(__name__)

# ----------- GLOBALLER -----------
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
message_queue = asyncio.Queue()
latest_sent = {}
loop = asyncio.get_event_loop()

# Aynı mesajın tekrarını engelleme süresi
DUPLICATE_WINDOW = 3
# Bekleme süresi
WAIT_SECONDS = 10


# ----------- TELEGRAM WORKER -----------
async def telegram_worker():
    """Kuyruktaki mesajları tek tek işler."""
    await client.start()
    print("✅ Telegram client başlatıldı")

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

            sent_msg = await client.send_message(bot_username, message)
            last_reply = None
            start_time = time.time()

            # 🔥 10 saniye boyunca cevapları dinle
            while time.time() - start_time < WAIT_SECONDS:
                async for msg in client.iter_messages(bot_username, min_id=sent_msg.id, limit=5):
                    if not msg.out and getattr(msg, "text", None):
                        last_reply = msg.text
                await asyncio.sleep(0.7)

            if last_reply:
                future.set_result(last_reply)
            else:
                future.set_result("⏳ Yanıt alınamadı (10 saniye içinde cevap gelmedi).")

        except Exception as e:
            future.set_result(f"❌ Hata: {str(e)}")
        finally:
            # Request ID'yi temizle (opsiyonel, bellek için)
            if request_id in latest_sent:
                del latest_sent[request_id]
            message_queue.task_done()


# ----------- MESAJ GÖNDERME -----------
async def send_message_queue(bot_username: str, message: str):
    """Mesajı kuyruğa atar, işlenince sonucu döndürür."""
    future = loop.create_future()
    # Her istek için unique ID oluştur (timestamp + random)
    request_id = f"{time.time()}_{random.randint(1000, 9999)}"
    await message_queue.put((request_id, bot_username, message, future))
    return await future


# ----------- FLASK ROUTES -----------
@app.route("/", methods=["GET"])
def home():
    models_list = "\n".join([f"- {model}: {BOT_MODELS[model]}" for model in BOT_MODELS])
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
        reply_text = loop.run_until_complete(send_message_queue(BOT_MODELS["deepseek"], message))

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

        reply_text = loop.run_until_complete(send_message_queue(bot_username, message))

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


# ----------- ÇALIŞTIRICI -----------
if __name__ == "__main__":
    # Telegram worker'ı arka planda başlat
    loop.create_task(telegram_worker())
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Flask API başlatılıyor...")
    print("📋 Kullanılabilir modeller:")
    for model, bot in BOT_MODELS.items():
        print(f"   - {model}: {bot}")
    app.run(host="0.0.0.0", port=port, debug=False)
