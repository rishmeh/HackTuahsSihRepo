# Table Tot assembly notes

Use [CONNECTIONS.md](CONNECTIONS.md) as the electrical source of truth and
[README.md](README.md) for installation and testing.

## Mechanical layout

- Mount the camera above or beside the IPS face display and aim it at the seated
  student's face.
- The microphone and speaker remain on the laptop, so the robot enclosure needs
  no audio openings.
- Leave a service loop in the camera, display and servo cables so head motion cannot
  pull connectors.
- Put the head servo at its mechanical midpoint before attaching the horn.
- Put the body servo at its midpoint before fixing the rotating base.
- Route servo power separately from the camera and display cables.
- Mount the servo-rail capacitor near the servos.
- Vent the Pi enclosure. The Pi is lightly loaded, but its power circuitry and
  camera still produce heat.

## Safe first movement

1. Disconnect servo horns from the mechanism.
2. Start `hardware/test_servos.py` and verify both shafts move in the expected
   direction without hitting their stops.
3. Stop the service, center both shafts, and attach the horns with the head and
   body physically centered.
4. Re-run the test. If a mechanism binds, reduce the angle limits in
   `ServoController` before continuing.

The default software range is -45 to +45 degrees. Actual safe travel depends on
the printed linkage and must be measured on the assembled robot.
