import json
import os
import asyncio
import time
from flask import Flask, request, Response
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 21988008
API_HASH = "e059c48444174a36b60b147f1e5d4552"
STRING_SESSION = "1ApWapzMBu5mc-QLeVW8MdGXE63TVYLlKzjiXGTZkV-0G2fOO0hiApSRtKBVWBR7-u14hXcgcfzD0rAZid4s91M75ACrkyov4ZyTg-I_fewAhUKLtQ91mutw22fKqmAVfhkHX9NHf0_kO3BMsRr_yYaDWs0r-wE4B7Pa3IAJ41pRPk99kRtf8sXrJRyYABo3rqLHB1KLFCa5B8c8UE2edT7nc1yDhb416-KEXF7L0fNmByZxZHBihGnru_c7DBhIEgR2b0f9CZ34IbWsu7P7LCiU-em2rG5u2fZb31mS2dv52Rayrh4gRc-X1tdvNGPXGlHhglZdfJUO2f-ywC6j2He4UDY3GOKo="
BOT_USERNAME = "@GPT4Telegrambot"

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
        message, future = await message_queue.get()
        try:
            now = time.time()
            # Tekrarlanan mesaj kontrolü
            if message in latest_sent and now - latest_sent[message] < DUPLICATE_WINDOW:
                future.set_result("⚠️ Aynı mesaj kısa sürede tekrar gönderildi, engellendi.")
                message_queue.task_done()
                continue

            latest_sent[message] = now

            sent_msg = await client.send_message(BOT_USERNAME, message)
            last_reply = None
            start_time = time.time()

            # 🔥 10 saniye boyunca cevapları dinle
            while time.time() - start_time < WAIT_SECONDS:
                async for msg in client.iter_messages(BOT_USERNAME, min_id=sent_msg.id, limit=5):
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
            message_queue.task_done()


# ----------- MESAJ GÖNDERME -----------
async def send_message_queue(message: str):
    """Mesajı kuyruğa atar, işlenince sonucu döndürür."""
    future = loop.create_future()
    await message_queue.put((message, future))
    return await future


# ----------- FLASK ROUTES -----------
@app.route("/", methods=["GET"])
def home():
    return Response(json.dumps({"status": "Nabi API çalışıyor ✅"}), mimetype="application/json")


@app.route("/chat", methods=["GET", "POST"])
def chat():
    try:
        if request.method == "POST":
            data = request.get_json(silent=True)
            message = data.get("message") if data else None
        else:
            message = request.args.get("message")

        if not message:
            return Response(json.dumps({"reply": "Mesaj gerekli"}, ensure_ascii=False),
                            mimetype="application/json", status=400)

        reply_text = loop.run_until_complete(send_message_queue(message))

        return Response(json.dumps({"reply": reply_text}, ensure_ascii=False),
                        mimetype="application/json")

    except Exception as e:
        return Response(json.dumps({"reply": f"Hata: {str(e)}"}, ensure_ascii=False),
                        mimetype="application/json", status=500)


# ----------- ÇALIŞTIRICI -----------
if __name__ == "__main__":
    # Telegram worker’ı arka planda başlat
    loop.create_task(telegram_worker())
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Flask API başlatılıyor...")
    app.run(host="0.0.0.0", port=port, debug=False)
