"""TableTot Pi Alarm Server — Flask, port 5000. Deploy to the Raspberry Pi."""
from __future__ import annotations
import os, subprocess, threading, logging
from pathlib import Path
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_server")
app = Flask(__name__)

ALARM_WAV = Path(__file__).parent / "alarm.wav"
PI_TOKEN  = os.getenv("PI_TOKEN", "")


def _check_token():
    return not PI_TOKEN or request.headers.get("X-Pi-Token") == PI_TOKEN


def _play():
    try:
        if ALARM_WAV.exists():
            subprocess.Popen(["aplay", str(ALARM_WAV)])
        else:
            subprocess.Popen(["speaker-test", "-t", "sine", "-f", "880", "-l", "1"])
    except Exception as e:
        logger.error("Audio error: %s", e)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "device": "raspberry_pi"})


@app.route("/alarm/ring", methods=["POST"])
def ring():
    if not _check_token():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    threading.Thread(target=_play, daemon=True).start()
    return jsonify({"triggered": True, "label": data.get("label", "")})


@app.route("/timer/start", methods=["POST"])
def timer_start():
    return ring()


if __name__ == "__main__":
    port = int(os.getenv("PI_FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
