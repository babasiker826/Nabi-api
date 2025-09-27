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
BOT_USERNAME = "@chatsgpts_bot"

app = Flask(__name__)

# Global client ve event loop
client = None
loop = None

def initialize_client():
    """Client'ı bir kere başlat"""
    global client, loop
    if client is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
        loop.run_until_complete(client.start())
        print("Telegram client başlatıldı")

# Uygulama başladığında client'ı başlat
initialize_client()

async def send_and_wait_followup(message: str, wait_seconds=10):
    """Mesaj gönder ve yanıtı bekle"""
    try:
        sent_msg = await client.send_message(BOT_USERNAME, message)
        sent_id = sent_msg.id

        # İlk yanıtı bekle
        first_response = None
        attempts = 0
        while not first_response and attempts < 20:  # Max 10 saniye bekle
            async for msg in client.iter_messages(BOT_USERNAME, min_id=sent_id, limit=10):
                if not msg.out and msg.text:
                    first_response = msg.text
                    break
            await asyncio.sleep(0.5)
            attempts += 1

        if not first_response:
            return "Yanıt alınamadı, lütfen tekrar deneyin."

        # Ek mesajları bekle
        extra_response = None
        start_time = time.time()
        last_id = sent_id
        
        while time.time() - start_time < wait_seconds:
            async for msg in client.iter_messages(BOT_USERNAME, min_id=last_id + 1, limit=5):
                if not msg.out and msg.text:
                    extra_response = msg.text
                    last_id = msg.id
                    break
            await asyncio.sleep(0.5)

        return extra_response if extra_response else first_response

    except Exception as e:
        return f"Hata oluştu: {str(e)}"

@app.route("/", methods=["GET"])
def home():
    return Response(json.dumps({"status": "Nabi API çalışıyor ✅"}), 
                    mimetype="application/json")

@app.route("/chat", methods=["GET", "POST"])
def chat():
    try:
        # Mesajı al
        message = None
        if request.method == "POST":
            data = request.get_json()
            if data and "message" in data:
                message = data["message"]
        else:
            message = request.args.get("message")

        if not message:
            return Response(
                json.dumps({"error": "Mesaj gerekli"}, ensure_ascii=False),
                mimetype="application/json", 
                status=400
            )

        # Event loop'u kontrol et ve mesajı gönder
        if loop is None or loop.is_closed():
            initialize_client()

        # Asenkron fonksiyonu çalıştır
        reply = loop.run_until_complete(send_and_wait_followup(message, wait_seconds=10))
        
        return Response(
            json.dumps({"reply": reply}, ensure_ascii=False),
            mimetype="application/json"
        )

    except Exception as e:
        error_msg = f"The asyncio event loop must not change after connection (see the FAQ for details): {str(e)}"
        return Response(
            json.dumps({"error": error_msg}, ensure_ascii=False),
            mimetype="application/json", 
            status=500
        )

@app.route("/health", methods=["GET"])
def health_check():
    """Sağlık kontrolü endpoint'i"""
    try:
        if client and client.is_connected():
            return Response(
                json.dumps({"status": "healthy", "connected": True}),
                mimetype="application/json"
            )
        else:
            return Response(
                json.dumps({"status": "unhealthy", "connected": False}),
                mimetype="application/json",
                status=503
            )
    except Exception as e:
        return Response(
            json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status=503
        )

# Uygulama kapatılırken client'ı durdur
@app.teardown_appcontext
def shutdown_client(exception=None):
    if client and client.is_connected():
        loop.run_until_complete(client.disconnect())
        print("Telegram client durduruldu")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    # Production için debug=False
    debug_mode = os.environ.get("DEBUG", "False").lower() == "true"
    
    app.run(host="0.0.0.0", port=port, debug=debug_mode, threaded=True)
