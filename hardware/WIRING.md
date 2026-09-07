# Wiring quick reference

The complete, corrected wiring guide is [CONNECTIONS.md](CONNECTIONS.md).

| Function | BCM GPIO | Physical pin |
|---|---:|---:|
| Head servo signal | 12 | 32 |
| Body servo signal | 13 | 33 |
| Shared servo/Pi ground | GND | 34 recommended |

Servos use an external regulated 5 V supply with its ground connected to Pi
ground. Connect the camera to USB or CAM/DISP0/1. Connect an HDMI IPS display
to micro-HDMI 0 and power it as specified by its manufacturer. The microphone
and speaker remain on the laptop; there is no PIR sensor.
