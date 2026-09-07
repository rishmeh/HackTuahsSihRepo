# Table Tot implementation plan

## Deployment contract

- The laptop runs FastAPI, learner data, Ollama, face recognition, wake word,
  Moonshine STT and Piper TTS. It uses its own microphone and speakers.
- The Raspberry Pi 5 captures camera frames, renders the face on an HDMI IPS
  display and drives exactly two servos.
- There is no PIR, Pi microphone or Pi speaker in this build.
- The laptop decides every robot state. The Pi applies received display/servo
  commands and reports peripheral health.

## Runtime flow

1. The Pi captures a 640 x 480 camera frame and JPEG-encodes it.
2. It sends the JPEG to the laptop with `POST /hardware/process-frame`.
3. The laptop runs YuNet/SFace and debounces three agreeing recognitions.
4. The HTTP response returns an `arrived` event plus a versioned `happy` face
   and servo command.
5. The Pi renders the happy face and performs the recognition nod/body sway.
6. The laptop voice worker receives the arrival event locally and speaks the
   greeting through the laptop speaker.
7. Voice states update the laptop state machine. The Pi receives them by
   polling `GET /hardware/state` every 250 ms; the same response updates the
   IPS face.
8. Five missing face frames confirm departure and return both servos to neutral.

The complete protocol is in `hardware/DATA_FLOW.md`.

## Laptop workstream

- Start FastAPI and the local voice worker with `bash ml/run.sh`.
- Select the required laptop microphone and speaker as OS defaults.
- Store face embeddings and learner profiles under the same student ID.
- Keep `ml/robot_state.py` as the only owner of state transitions.
- Bind FastAPI to `0.0.0.0:8000`, restricted to the trusted private LAN.
- Configure the dashboard Node server with `ML_API_URL=http://127.0.0.1:8000`.

## Pi workstream

- Run only `hardware/bridge.py` through `bash hardware/run.sh`.
- Use `CAMERA_TYPE=auto` to prefer CSI and fall back to USB.
- Drive head servo signal from GPIO12/physical pin 32.
- Drive body servo signal from GPIO13/physical pin 33.
- Power the servos separately and join the external ground to Pi ground.
- Connect the HDMI IPS display to micro-HDMI 0 and configure its resolution in
  `hardware/.env.pi`.
- Use the Pi 5 `lgpio` backend for GPIO Zero.

## Acceptance tests

- `/health` responds from the Pi.
- Camera frames reach `/hardware/process-frame` at about two frames/second.
- A known face produces exactly one arrival event and recognition gesture.
- An unknown face never loads another student's profile.
- Laptop microphone input reaches wake word detection and STT.
- Laptop TTS plays through the laptop speaker.
- Listening, thinking and speaking states update the IPS face and Pi servos.
- Departure returns both servos to neutral.
- When the laptop link remains unavailable, the Pi returns servos to neutral;
  reconnecting resumes camera upload and command polling.

## Hardware gate

Software tests validate state transitions and payloads, but final acceptance
requires the assembled robot. Test the servos with horns disconnected first,
then record safe mechanical angles before increasing travel.
