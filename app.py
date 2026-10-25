import os
import secrets
import time
import re
from threading import Lock
from flask import Flask, jsonify, request

app = Flask(__name__)
API_SECRET = os.environ.get("API_SECRET")

codes = {}
links = {}
join_requests = {}
verified_queue = []
lock = Lock()

CODE_LIFETIME = 300


def authorized():
    return bool(
        API_SECRET
        and request.headers.get("X-API-Secret") == API_SECRET
    )


@app.get("/")
def home():
    return jsonify({
        "service": "Nagato MC Link API",
        "status": "online"
    })


@app.post("/join-code")
def join_code():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    minecraft_uuid = str(data.get("minecraft_uuid", "")).strip()
    username = str(data.get("username", "")).strip()

    if not minecraft_uuid or not re.fullmatch(r"[A-Za-z0-9_.]{3,16}", username):
        return jsonify({"error": "Invalid Minecraft identity"}), 400

    with lock:
        if minecraft_uuid in links:
            return jsonify({"error": "Already linked"}), 409

        pending = join_requests.get(username.lower())
        if not pending or pending["expires"] < time.time():
            return jsonify({"error": "No Discord /link request for this username"}), 400

        code = secrets.token_hex(4).upper()
        codes[code] = {
            "discord_id": pending["discord_id"],
            "minecraft_uuid": minecraft_uuid,
            "username": username,
            "expires": time.time() + CODE_LIFETIME
        }
        join_requests.pop(username.lower(), None)

    return jsonify({"code": code, "expires_in": CODE_LIFETIME})


@app.post("/create-link-request")
def create_link_request():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    discord_id = str(data.get("discord_id", "")).strip()
    username = str(data.get("username", "")).strip()

    if not discord_id.isdigit() or not re.fullmatch(r"[A-Za-z0-9_]{3,16}", username):
        return jsonify({"error": "Invalid Discord ID or Minecraft username"}), 400

    with lock:
        join_requests[username.lower()] = {
            "discord_id": discord_id,
            "expires": time.time() + CODE_LIFETIME
        }

    return jsonify({"success": True, "expires_in": CODE_LIFETIME})


@app.post("/verify-code")
def verify_code():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()

    with lock:
        entry = codes.get(code)

        if not entry or entry["expires"] < time.time():
            codes.pop(code, None)
            return jsonify({"error": "Invalid or expired code"}), 400

        discord_id = entry["discord_id"]
        minecraft_uuid = entry["minecraft_uuid"]

        if minecraft_uuid in links:
            return jsonify({"error": "Minecraft account already linked"}), 409

        links[minecraft_uuid] = discord_id
        codes.pop(code, None)
        verified_queue.append({
            "discord_id": discord_id,
            "minecraft_uuid": minecraft_uuid
        })

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

    with lock:
        linked = minecraft_uuid in links

    return jsonify({"linked": linked})


@app.post("/pending-verifications")
def pending_verifications():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    with lock:
        return jsonify({"verifications": list(verified_queue)})


@app.post("/ack-verification")
def ack_verification():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    discord_id = str(data.get("discord_id", "")).strip()
    minecraft_uuid = str(data.get("minecraft_uuid", "")).strip()

    with lock:
        for index, item in enumerate(verified_queue):
            if item["discord_id"] == discord_id and item["minecraft_uuid"] == minecraft_uuid:
                verified_queue.pop(index)
                return jsonify({"success": True})

    return jsonify({"success": False, "error": "Not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
