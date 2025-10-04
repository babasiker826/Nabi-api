import json
import os
import time
import threading
import asyncio
from flask import Flask, request, Response
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import TimeoutError as TelethonTimeoutError

API_ID = 21988008
API_HASH = "e059c48444174a36b60b147f1e5d4552"
STRING_SESSION = "1ApWapzMBu5mc-QLeVW8MdGXE63TVYLlKzjiXGTZkV-0G2fOO0hiApSRtKBVWBR7-u14hXcgcfzD0rAZid4s91M75ACrkyov4ZyTg-I_fewAhUKLtQ91mutw22fKqmAVfhkHX9NHf0_kO3BMsRr_yYaDWs0r-wE4B7Pa3IAJ41pRPk99kRtf8sXrJRyYABo3rqLHB1KLFCa5B8c8UE2edT7nc1yDhb416-KEXF7L0fNmByZxZHBihGnru_c7DBhIEgR2b0f9CZ34IbWsu7P7LCiU-em2rG5u2fZb31mS2dv52Rayrh4gRc-X1tdvNGPXGlHhglZdfJUO2f-ywC6j2He4UDY3GOKo="
BOT_USERNAME = "@GPT4Telegrambot"

app = Flask(__name__)

# Basit in-memory dedupe: (target, message) -> last_sent_time
recent_messages = {}
# Süre (saniye) içinde aynı mesaj tekrar gönderilirse reddedilecek
DUPLICATE_WINDOW = 3.0

# Threading lock ile aynı anda birden fazla gönderim yapılmasını engelliyoruz.
send_lock = threading.Lock()

async def create_and_use_client(message, wait_seconds=10):
    """
    Mesajı gönderir, wait_seconds süresi boyunca gelen yanıtların en sonuncusunu döndürür.
    Debounce ve tekil gönderim lock'u kullanır.
    """
    now = time.time()
    key = (BOT_USERNAME, message)

    # Dedupe kontrolü (in-memory). Çok kısa süreli tekrarları engeller.
    last = recent_messages.get(key)
    if last and now - last < DUPLICATE_WINDOW:
        return "Aynı mesaj kısa sürede tekrar gönderildi — işlem engellendi."

    # Lock: aynı anda başka bir istek gönderimi yapmasın
    acquired = send_lock.acquire(timeout=5)
    if not acquired:
        return "Sunucu meşgul, lütfen tekrar deneyin."

    # Eğer kilit alındıysa kayıt yap
    recent_messages[key] = now

    client = None
    try:
        client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
        await client.start()

        # Conversation ile gönder ve cevapları yakala.
        # conversation.get_response() ile aralıklarla gelen cevapları toplayıp sonuncusunu döndüreceğiz.
        last_text = None
        start_time = time.time()
        try:
            async with client.conversation(BOT_USERNAME, timeout=wait_seconds+2) as conv:
                await conv.send_message(message)
                # Konuşmadan gelen tüm cevapları al (zaman aşımına kadar)
                while True:
                    remaining = wait_seconds - (time.time() - start_time)
                    if remaining <= 0:
                        break
                    try:
                        # timeout olarak kalan süreyi veriyoruz
                        resp = await conv.get_response(timeout=remaining)
                        if getattr(resp, "text", None):
                            last_text = resp.text
                        # döngü devam eder: gelen her yeni mesajı alıp last_text'i güncelliyoruz
                    except (asyncio.TimeoutError, TelethonTimeoutError):
                        break
        except Exception as e_conv:
            # conversation sırasında hata oluşursa en son bildiğimiz değeri döndür
            if last_text:
                return last_text
            return f"Conversation hata: {str(e_conv)}"

        if last_text:
            return last_text
        else:
            return "Yanıt alınamadı (zaman aşımı)."

    except Exception as e:
        return f"Hata: {str(e)}"
    finally:
        # kilidi serbest bırak
        try:
            send_lock.release()
        except RuntimeError:
            pass
        if client:
            await client.disconnect()


@app.route("/", methods=["GET"])
def home():
    return Response(json.dumps({"status": "Nabi API çalışıyor ✅"}), mimetype="application/json")


@app.route("/chat", methods=["GET", "POST"])
def chat():
    try:
        # Mesajı al
        message = None
        if request.method == "POST":
            data = request.get_json(silent=True)
            if data and "message" in data:
                message = data["message"]
        else:
            message = request.args.get("message")

        if not message:
            return Response(json.dumps({"reply": "Mesaj gerekli"}, ensure_ascii=False),
                            mimetype="application/json", status=400)

        # Telethon çağrısını çalıştır
        # asyncio.run kullanıyoruz çünkü Flask sync context içinde çalışıyoruz.
        reply_text = asyncio.run(create_and_use_client(message, wait_seconds=10))

        return Response(json.dumps({"reply": reply_text}, ensure_ascii=False),
                        mimetype="application/json")

    except Exception as e:
        return Response(json.dumps({"reply": f"Hata: {str(e)}"}, ensure_ascii=False),
                        mimetype="application/json", status=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
