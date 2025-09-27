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
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

async def send_and_wait_followup(message: str, wait_seconds=10):
    await client.start()
    sent_msg = await client.send_message(BOT_USERNAME, message)
    sent_id = sent_msg.id

    # İlk yanıt
    first_response = None
    while not first_response:
        async for msg in client.iter_messages(BOT_USERNAME, min_id=sent_id):
            if not msg.out:
                first_response = msg.text
                break
        await asyncio.sleep(0.5)

    # Ek mesajları bekle
    extra_response = None
    start_time = time.time()
    last_id = sent_id
    while time.time() - start_time < wait_seconds:
        async for msg in client.iter_messages(BOT_USERNAME, min_id=last_id+1):
            if not msg.out:
                extra_response = msg.text
                last_id = msg.id
                break
        await asyncio.sleep(0.5)

    if not extra_response:
        extra_response = "Ek mesaj yok."
    return extra_response

@app.route("/", methods=["GET"])
def home():
    return Response(json.dumps({"status": "API çalışıyor ✅"}), 
                    mimetype="application/json")

@app.route("/chat", methods=["GET", "POST"])
def chat():
    message = None
    if request.method == "POST":
        data = request.get_json()
        if data and "message" in data:
            message = data["message"]
    else:
        message = request.args.get("message")

    if not message:
        return Response(json.dumps({"error":"Message missing"}, ensure_ascii=False),
                        mimetype="application/json", status=400)
    try:
        reply = asyncio.run(send_and_wait_followup(message, wait_seconds=10))
        return Response(json.dumps({"reply": reply}, ensure_ascii=False),
                        mimetype="application/json")
    except Exception as e:
        return Response(json.dumps({"error": str(e)}, ensure_ascii=False),
                        mimetype="application/json", status=500)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
