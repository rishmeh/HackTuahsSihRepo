"""TableTot Pi Alarm Server — Flask, port 5000.

Deploy to the Raspberry Pi.  Advertises itself as ``tabletot-pi.local``
via mDNS (using the system avahi-daemon) so the laptop can always find
the Pi without a static IP or manual hostname lookup.

mDNS setup
----------
avahi-daemon must be running on the Pi (it is by default on Raspberry Pi OS):

    sudo systemctl enable --now avahi-daemon

The Pi's hostname must be set to ``tabletot-pi`` for the .local name to work:

    sudo hostnamectl set-hostname tabletot-pi
    # then reboot or restart avahi: sudo systemctl restart avahi-daemon

After that the laptop can reach this server at http://tabletot-pi.local:5000
and the bridge reaches the laptop at http://tabletot-laptop.local:8000
(configure the laptop's hostname with the same hostnamectl command).
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_server")

app = Flask(__name__)

ALARM_WAV = Path(__file__).parent / "alarm.wav"
PI_TOKEN  = os.getenv("PI_TOKEN", "")
PI_FLASK_PORT = int(os.getenv("PI_FLASK_PORT", "5000"))

# ---------------------------------------------------------------------------
# mDNS advertisement via zeroconf (pure-Python fallback to avahi)
# ---------------------------------------------------------------------------
# The Pi's avahi-daemon already broadcasts <hostname>.local automatically,
# so this block is a belt-and-suspenders extra that works even when avahi
# is not running (e.g. on a headless minimal install).
#
# Install with:  pip install zeroconf

def _start_mdns() -> None:
    """Advertise tabletot-pi.local:PI_FLASK_PORT via zeroconf in a daemon thread."""
    try:
        import socket
        from zeroconf import ServiceInfo, Zeroconf

        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        info = ServiceInfo(
            "_http._tcp.local.",
            f"tabletot-pi._http._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=PI_FLASK_PORT,
            properties={
                "device": "tabletot-pi",
                "version": "1.0",
            },
            server=f"{hostname}.local.",
        )
        zc = Zeroconf()
        zc.register_service(info)
        logger.info(
            "mDNS: advertising tabletot-pi._http._tcp.local at %s:%d",
            local_ip, PI_FLASK_PORT,
        )
        # Keep the Zeroconf instance alive (it runs its own thread).
        # Store it as a module-level reference so it isn't GC'd.
        global _zeroconf_instance
        _zeroconf_instance = zc
    except ImportError:
        logger.info(
            "zeroconf package not installed — relying on avahi-daemon for .local mDNS. "
            "Install with: pip install zeroconf"
        )
    except Exception as exc:
        logger.warning("mDNS advertisement failed (non-fatal): %s", exc)


_zeroconf_instance = None  # keep alive

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _check_token() -> bool:
    return not PI_TOKEN or request.headers.get("X-Pi-Token") == PI_TOKEN


def _play() -> None:
    try:
        if ALARM_WAV.exists():
            subprocess.Popen(["aplay", str(ALARM_WAV)])
        else:
            subprocess.Popen(["speaker-test", "-t", "sine", "-f", "880", "-l", "1"])
    except Exception as e:
        logger.error("Audio error: %s", e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    import socket
    return jsonify({
        "status": "ok",
        "device": "raspberry_pi",
        "hostname": socket.gethostname(),
        "mdns": f"{socket.gethostname()}.local",
    })


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Start mDNS advertisement before Flask blocks on serve.
    threading.Thread(target=_start_mdns, daemon=True).start()
    logger.info("Starting Pi server on port %d", PI_FLASK_PORT)
    app.run(host="0.0.0.0", port=PI_FLASK_PORT)
