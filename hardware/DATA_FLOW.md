# Laptop and Raspberry Pi data exchange

## Transport

The current implementation uses ordinary HTTP over the local network. The
laptop runs FastAPI on TCP port 8000. The Pi always initiates the connection,
so the laptop does not need to know the Pi's address.

There is no raw camera stream, audio stream or AI model on the Pi. Each camera
frame is an independent JPEG request. All other messages are small JSON
objects.

## Camera path: Pi to laptop

Every 500 ms, `hardware/bridge.py`:

1. Captures a 640 x 480 frame from Picamera2 or a USB webcam.
2. JPEG-encodes it at quality 70.
3. Sends `POST /hardware/process-frame` as `multipart/form-data` with one field
   named `image`.
4. Waits up to five seconds. A late frame is discarded instead of queued.

The laptop decodes the JPEG and runs face detection plus recognition. It
debounces identity across three agreeing frames before declaring an arrival.

Typical JPEG size depends on lighting and detail. At roughly 30 to 100 KB per
frame and two frames/second, the expected camera traffic is about 0.5 to
1.6 Mbit/s plus HTTP overhead. This is an estimate, not a fixed limit.

## Immediate servo response: laptop to Pi

The frame response contains both recognition information and the current robot
command:

```json
{
  "face_count": 1,
  "student_id": "student-42",
  "score": 0.91,
  "event": "arrived",
  "command": {
    "servo_state": "happy",
    "revision": 8
  }
}
```

The Pi maps `happy` to a head nod and body sway. Other mappings are:

| Laptop state | Pi movement |
|---|---|
| `idle` or `sleeping` | Both servos return to neutral |
| `happy` | Recognition nod and body sway |
| `listening` | Head tilts toward the student |
| `thinking` | Head/body thinking pose |
| `speaking` | Short head/body speaking motion |
| `focus` | Forward study pose |

The response also contains `face_state` and optional overlay text. The Pi draws
that state locally with Pygame. Face graphics are not streamed from the laptop.
Only state names, text and a revision cross the return path. PWM timing is
generated on the Pi by `hardware/gpio.py`; the laptop never sends individual
PWM pulses.

## Recovery command path

The Pi also requests `GET /hardware/state` every 250 ms. This makes the command
path recover from a dropped frame response and carries face-display plus voice
gesture states generated on the laptop. Revisions prevent the Pi from replaying
the same gesture on every poll.

If twelve consecutive polls fail, the Pi commands both servos and the face
display to idle. When the laptop becomes reachable again, polling resumes
without restarting the Pi.

## Recognition and laptop audio

When the laptop confirms an arrival:

1. The state machine places an `arrived` event in a laptop-local queue.
2. `ml/voice_agent.py` reads `GET /hardware/events` through localhost.
3. The laptop generates the personalized greeting.
4. Piper synthesizes it on the laptop.
5. The laptop speaker plays it directly.
6. The voice worker changes the robot state to `speaking`; the Pi receives the
   speaking face and servo state on its next poll.

For normal conversation, the laptop microphone feeds openWakeWord and
Moonshine directly. No audio bytes travel to or from the Pi.

## Pi telemetry

Once per second, the Pi sends `POST /hardware/state/set` with its camera type,
camera availability, display state, applied servo state and most recently
observed student ID. `GET /hardware/status` returns this telemetry beside the
laptop's current command for diagnosis.

## Data ownership and security

- The Pi holds frames only long enough to encode and upload them.
- Face embeddings, learner profiles and conversation data stay on the laptop.
- The API has no authentication in the prototype. Bind it only to a trusted
  private LAN and do not expose TCP port 8000 to the internet.
