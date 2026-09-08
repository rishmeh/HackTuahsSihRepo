# Raspberry Pi 5 camera, display and servo bridge

The Pi has one camera, an IPS face display and two servos. The laptop handles
its own microphone and speaker plus every AI and application workload.

## Pi installation

Use 64-bit Raspberry Pi OS Bookworm:

```bash
sudo apt update
sudo apt install -y python3-venv python3-picamera2 python3-opencv \
  python3-gpiozero python3-lgpio python3-pil python3-spidev

cd ~/TableTot
python3 -m venv --system-site-packages .venv-pi
source .venv-pi/bin/activate
pip install httpx numpy
cp hardware/.env.pi.example hardware/.env.pi
```

Edit `hardware/.env.pi` and set the laptop IP. The
`--system-site-packages` option exposes the Raspberry Pi OS Picamera2 and GPIO
packages inside the environment.

For the pictured 240x320 GMT020-02-8P ST7789V SPI panel, enable SPI once and
reboot. Keep `DISPLAY_DRIVER=st7789v` in `hardware/.env.pi`. It uses the
working panel initialization from the supplied `file.py`, with a horizontal
black-and-cyan pixel-art face controlled by the laptop's robot state.

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

`python3-pygame` is needed only for the separate HDMI backend, not for this
ST7789V SPI display.

## Laptop installation and startup

```bash
cd TableTot
python3 -m venv .venv-laptop
source .venv-laptop/bin/activate
pip install -r ml/requirements.txt
pip install -e .
python -m vision.download_models
cp ml/.env.example ml/.env
bash ml/run.sh
```

Allow microphone access when the operating system asks. The voice worker uses
the laptop's default input and output devices.

## Start the Pi

```bash
cd ~/TableTot
bash hardware/run.sh
```

The bridge captures camera frames, renders the commanded face, moves the
servos and reports telemetry. It reconnects automatically when the laptop
temporarily disappears.

## Face enrolment

Run this on the Pi so enrollment uses the robot's mounted camera:

```bash
LAPTOP_URL=http://<LAPTOP_IP>:8000 python3 hardware/enroll_face.py student-42
```

Use the same ID as the learner profile.

## Test order

Run on the Pi after the laptop reports healthy:

```bash
python3 hardware/test_servos.py
python3 hardware/test_camera.py
# For DISPLAY_DRIVER=st7789v:
python3 hardware/test_st7789v_faces.py
# For DISPLAY_DRIVER=hdmi instead:
python3 hardware/test_display.py --fullscreen
python3 hardware/test_state_poll.py
```

Then run the integrated check:

1. Start `ml/run.sh` on the laptop and `hardware/run.sh` on the Pi.
2. Sit in front of the camera. Three matching frames should trigger the happy
   nod/body sway and happy face once.
3. The greeting should play from the laptop speaker.
4. Say "Hey Jarvis" into the laptop microphone. Listening, thinking and
   speaking states should produce matching face and servo movements.
5. Leave the camera view. After five missing frames, both servos return to
   neutral.

## Active API contract

| Endpoint | Direction | Purpose |
|---|---|---|
| `POST /hardware/process-frame` | Pi to laptop | JPEG frame; laptop returns recognition and servo command |
| `GET /hardware/state` | Laptop to Pi | Current versioned face and servo command |
| `POST /hardware/state/set` | Pi to laptop | Camera, display and servo telemetry |
| `GET /hardware/events` | Laptop-local | Recognition events for the laptop voice worker |
| `POST /hardware/control` | Laptop-local | Voice/UI updates the robot state |
| `GET /hardware/status` | Diagnostic | Current command plus Pi telemetry |

Read [CONNECTIONS.md](CONNECTIONS.md) for wiring and [DATA_FLOW.md](DATA_FLOW.md)
for the request-by-request data path.
