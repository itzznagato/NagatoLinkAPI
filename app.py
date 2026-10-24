
import os
import secrets
import time
from threading import Lock

from flask import Flask, jsonify, request

app = Flask(__name__)

API_SECRET = os.environ.get("API_SECRET")
codes = {}
links = {}
verified_queue = []
lock = Lock()

CODE_LIFETIME = 300


@app.get("/")
def home():
    return jsonify({
        "service": "Nagato MC Link API",
        "status": "online"
    })


def authorized():
    return bool(
        API_SECRET
        and request.headers.get("X-API-Secret") == API_SECRET
    )


@app.post("/create-code")
def create_code():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    discord_id = str(data.get("discord_id", ""))

    if not discord_id.isdigit():
        return jsonify({"error": "Invalid Discord ID"}), 400

    with lock:
        code = secrets.token_hex(4).upper()
        codes[code] = {
            "discord_id": discord_id,
            "expires": time.time() + CODE_LIFETIME
        }

    return jsonify({
        "code": code,
        "expires_in": CODE_LIFETIME
    })


@app.post("/verify-code")
def verify_code():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).upper()
    minecraft_uuid = str(data.get("minecraft_uuid", ""))

    if not minecraft_uuid:
        return jsonify({"error": "Missing Minecraft UUID"}), 400

    with lock:
        entry = codes.get(code)

        if not entry or entry["expires"] < time.time():
            codes.pop(code, None)
            return jsonify({
                "error": "Invalid or expired code"
            }), 400

        discord_id = entry["discord_id"]
        codes.pop(code, None)
        links[minecraft_uuid] = discord_id

    return jsonify({
        "success": True,
        "discord_id": discord_id,
        "minecraft_uuid": minecraft_uuid
    })


@app.post("/check-link")
def check_link():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    minecraft_uuid = str(data.get("minecraft_uuid", "")).strip()

    if not minecraft_uuid:
        return jsonify({
            "error": "Missing Minecraft UUID"
        }), 400

    with lock:
        linked = minecraft_uuid in links

    return jsonify({
        "linked": linked
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
    
