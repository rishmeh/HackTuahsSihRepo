# Table Tot hardware connections

The current Raspberry Pi 5 assembly has four peripherals:

1. One camera
2. One head servo
3. One body servo
4. One IPS face display

The laptop uses its own microphone and speakers. There is no PIR sensor or
Pi-connected audio device in this version.

## Raspberry Pi 5 wiring

GPIO values in the software are BCM numbers.

| Part | Wire | Pi connection |
|---|---|---|
| Head servo | Signal, usually orange/yellow/white | GPIO12, physical pin 32 |
| Body servo | Signal, usually orange/yellow/white | GPIO13, physical pin 33 |
| Both servos | Ground, usually brown/black | External supply GND joined to Pi GND pin 34 |
| Both servos | Positive, usually red | External regulated 5 V supply only |
| CSI camera | 15-to-22-pin camera cable | CAM/DISP0 or CAM/DISP1 |
| USB camera alternative | USB cable | One Pi USB port |
| HDMI IPS display video | Micro-HDMI cable | Pi micro-HDMI 0, next to USB-C power |
| IPS display power | Display USB power input | Separate rated supply or powered USB hub |
| Touch, if the panel has it | Display USB touch port | Pi USB; optional and unused by the face renderer |
| Network | Ethernet preferred | Same LAN as the laptop |
| Pi power | USB-C | Official-class 5 V, 5 A supply |

Do not connect the external servo supply's positive terminal to a Pi 5 V pin.
Only the grounds are joined. Use a supply rated for the combined stall current;
5 V at 3 A is a practical starting point for two SG90/MG90S servos. Place a
470 to 1000 uF electrolytic capacitor across the servo power rail near the
servos and observe capacitor polarity.

```text
External regulated 5 V + ----+---- head servo red
                              +---- body servo red

External supply GND ----------+---- head servo brown/black
                              +---- body servo brown/black
                              +---- Pi physical pin 34 GND

Pi physical pin 32 / GPIO12 ------- head servo signal
Pi physical pin 33 / GPIO13 ------- body servo signal
```

## Camera

Set one camera mode in `hardware/.env.pi`:

```dotenv
CAMERA_TYPE=auto
CAMERA_INDEX=0
```

`auto` tries Picamera2/CSI first and then a USB webcam. Raspberry Pi 5 uses a
22-pin mini camera connector, so most standard camera modules require a
15-to-22-pin cable. Turn off the Pi before connecting or disconnecting it.

The Pi captures 640 x 480 frames and JPEG-encodes them at quality 70. It does
not run OpenCV inference or store face images.

## IPS display

The active software supports an HDMI IPS display through Pygame:

1. Connect Pi micro-HDMI 0 to the display's HDMI input.
2. Power the display through its marked USB power connector. Prefer a separate
   supply or powered hub instead of loading the Pi's USB power budget.
3. If the panel includes touch, connect its USB touch cable only when needed.
   The current face renderer does not use touch input.
4. Set `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` in `hardware/.env.pi` to the
   panel's native resolution. The supplied default is 800 x 480.

This wiring applies to an HDMI IPS panel. A bare SPI/GPIO or DSI panel uses a
different connection and driver; identify its exact model before wiring it.

## Laptop hardware

- Select the laptop microphone as the operating system's default input.
- Select the laptop speakers or connected headphones as the default output.
- The laptop can show the dashboard while the animated face appears on the Pi
  IPS display.
- Keep speaker volume moderate so its greeting does not immediately retrigger
  the laptop microphone.

## Network

1. Put the laptop and Pi on the same trusted LAN.
2. Prefer Ethernet for the Pi; Wi-Fi works at the configured 2 frames/second.
3. Reserve the laptop IP address in the router if possible.
4. Allow incoming TCP port 8000 on the laptop's private-network firewall.
5. Set `LAPTOP_URL=http://<laptop-ip>:8000` in `hardware/.env.pi`.
6. From the Pi, run `curl http://<laptop-ip>:8000/health`.

See [DATA_FLOW.md](DATA_FLOW.md) for every request and response exchanged
between the two machines.

## Power-on order

1. With power disconnected, check the two signal wires and shared ground.
2. Power the external servo rail and IPS display.
3. Power the Pi with its own USB-C supply.
4. Start `bash run.sh` on the laptop.
5. Start `bash hardware/run.sh` on the Pi.
6. Run the test sequence in [README.md](README.md).
