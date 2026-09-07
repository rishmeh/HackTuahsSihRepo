# Starting Table Tot

Table Tot has two computers, so two processes must be running. The supplied
scripts start all robot-critical software on each machine.

## Before the first run

Complete the laptop and Pi installation in `hardware/README.md`. On the Pi,
copy and edit the environment file:

```bash
cd ~/TableTot
cp hardware/.env.pi.example hardware/.env.pi
nano hardware/.env.pi
```

Set `LAPTOP_URL` to the laptop's LAN address and set the IPS panel's native
resolution.

## Every time you turn on the robot

1. Power the servo supply and IPS display.
2. Power the Raspberry Pi.
3. Connect the laptop and Pi to the same network.
4. On the laptop:

   ```bash
   cd /path/to/TableTot
   bash run.sh
   ```

   This starts FastAPI and the laptop voice worker. Leave the terminal open.

5. On the Pi:

   ```bash
   cd ~/TableTot
   bash hardware/run.sh
   ```

   This one process starts the camera, fullscreen face display, command polling
   and both servo drivers. Leave the terminal open.

6. Verify from the Pi:

   ```bash
   curl http://<LAPTOP_IP>:8000/health
   ```

7. Sit in front of the camera. The display should change to the happy face,
   both servos should perform the recognition gesture, and the laptop should
   speak the greeting.

Press Ctrl+C in each terminal to stop cleanly. The Pi bridge centers/detaches
the servos and closes the camera/display during shutdown.

## First hardware test

Before fitting servo horns to the mechanism, run:

```bash
python3 hardware/test_display.py --fullscreen
python3 hardware/test_servos.py
python3 hardware/test_camera.py
```

If the display remains blank, confirm the panel is set to HDMI input and that
`DISPLAY_WIDTH` and `DISPLAY_HEIGHT` match its native resolution. The current
driver targets HDMI displays. SPI and DSI panels require model-specific setup.
