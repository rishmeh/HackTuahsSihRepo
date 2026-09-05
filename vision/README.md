# Face Detection & Recognition

On-device face pipeline for **Table Tot**, built on two **pretrained** models
from OpenCV Zoo. Nothing is trained here — enrolling a student stores a few
vectors, and recognition is a nearest-neighbour lookup.

This package sits at the repository root, outside `ml/`, so it can run
standalone on the robot. Its HTTP endpoints are mounted into the ml API by
`ml/main.py`.

## Setup (once)

```bash
pip install -e .                      # makes `vision` importable from anywhere
python -m vision.download_models      # ~39 MB of weights, one time
```

The editable install matters. Without it, `python -m vision.camera` only works
when the current directory happens to be the repository root — that being the
only place `vision/` lands on `sys.path`. Installing it removes that trap.

## Use

```bash
python -m vision.camera enroll --student asha
python -m vision.camera watch
python -m vision.camera list
python -m vision.camera delete --student asha

tabletot-vision watch                 # same thing, via the console script
```

```bash
pytest vision/tests/ -q               # 117 tests, no camera needed
pytest                                # all 145 (vision + ml)
```

Once installed, these run from **any directory**.

---

| Stage | Model | Size | Job |
|---|---|---|---|
| Detect | YuNet | 233 KB | Find faces + 5 landmarks per frame |
| Recognise | SFace | 38 MB | Turn an aligned face into a 128-d embedding |

```
vision/
├── config.py           # thresholds, paths (self-contained)
├── models.py           # FaceBox, EnrolledFace, MatchResult + API schemas
├── detector.py         # YuNet wrapper (cv2.FaceDetectorYN)
├── recognizer.py       # SFace wrapper (cv2.FaceRecognizerSF)
├── matching.py         # Cosine similarity + gallery lookup (pure maths)
├── face_store.py       # SQLite embedding DB — embeddings only, never images
├── presence.py         # Temporal smoothing → "arrived" / "departed" events
├── pipeline.py         # Orchestrates detect → embed → match → smooth
├── factory.py          # Builds a pipeline from config.py
├── routes.py           # FastAPI endpoints
├── camera.py           # Webcam CLI (swap one class for Picamera2 on the Pi)
├── download_models.py  # Fetches both ONNX files
├── weights/            # ONNX files (gitignored)
├── data/faces.db       # embeddings (gitignored)
└── tests/              # 117 tests
```

### Setup

```bash
python -m vision.download_models   # ~39 MB, one time
```

### Try it on a webcam

```bash
python -m vision.camera enroll --student asha   # SPACE to capture, q to quit
python -m vision.camera watch                   # live recognition
python -m vision.camera list
python -m vision.camera delete --student asha
```

Vary your pose and lighting between enrolment captures — that variation is what
makes recognition survive a real desk instead of only the enrolment pose.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/vision/face/detect` | Is anyone there? (detection only) |
| POST | `/vision/face/identify` | Who is there? |
| POST | `/vision/face/enroll` | Teach a new face (multipart, several frames) |
| GET | `/vision/face/students` | Who does it know? |
| DELETE | `/vision/face/students/{id}` | Forget a student entirely |

### How recognition works

SFace maps any aligned face crop to a 128-number vector, trained so the same
person lands in the same direction. Identity is then a nearest-neighbour lookup
by **cosine similarity** — the angle between two vectors, which ignores
brightness scaling.

Measured on the test fixtures (two different real people):

| Pair | Score |
|---|---|
| Same person, mirrored | 0.944 |
| Same person, brightened | 0.99 |
| **Different people** | **0.198** |

`FACE_MATCH_THRESHOLD` sits at **0.45**, inside that gap. OpenCV's published
figure is 0.363; ours is stricter deliberately — a false reject costs one spoken
"who are you?", while a false accept silently loads another student's persona,
progress and revision queue.

### Calibrating the detector threshold

`FACE_DETECT_THRESHOLD` is bracketed from both sides by measurement:

| Measurement | Score |
|---|---|
| Worst false positive on a faceless image (star field) | 0.585 |
| Live face, median confidence while moving | 0.833 |

The usable range is roughly 0.59–0.83, and the default sits at **0.70**.

This one matters more than it looks. At 0.9 the detector still *found* the face
in 100% of live frames but reported confidence below the threshold in most of
them — which presents as the robot losing the student every time they shift in
their chair. Measured on 225 live frames of normal movement:

| Threshold | Frames detected |
|---|---|
| 0.90 | 18–80% (swings with how much you move) |
| **0.70** | **100%, zero false departures** |

Raising it towards 0.9 loses a moving student; dropping it below ~0.59 invents
faces in textures. Both bounds have tests.

Two details of the OpenCV API that are easy to get wrong (both pinned by tests):

1. `detect()` returns `None`, not an empty array, when there is no face.
2. The detector's input size must be updated on every resolution change, or
   YuNet returns wrong boxes silently instead of raising.

### Why smoothing matters

Per-frame recognition is noisy — a blink or motion blur flips a single frame.
`PresenceTracker` requires `FACE_CONFIRM_FRAMES` (3) consecutive agreeing frames
before announcing an arrival, and `FACE_FORGET_FRAMES` (5) empty frames before a
departure, so glancing down at a book is not treated as leaving the desk.

### Privacy

The `faces` table holds `student_id`, a float32 embedding BLOB, and a timestamp.
There is no image column and no code path that writes a frame to disk — a test
asserts this. An embedding cannot be reversed into a photograph. `DELETE
/vision/face/students/{id}` is a real erasure.

**Known limitation:** SFace is not liveness-aware — a photo held up to the
camera will match. Anti-spoofing is a separate model and is out of scope; the
mitigation is that this is a desk companion in the student's own room, and an
unknown face falls back to a spoken confirmation rather than silent access.

### Measured performance (laptop CPU, 640x480)

| Step | Time |
|---|---|
| Detect | 8.6 ms/frame |
| Embed | 6.2 ms/face |
| **Full recognition** | **14.8 ms (~68 fps)** |

A Pi 5 runs roughly 5–10x slower, so ~7–13 fps — above the 5 fps
`VISION_FPS` target, leaving CPU for speech and the SLM.

### Config

| Variable | Default | Meaning |
|---|---|---|
| `FACE_DETECT_THRESHOLD` | 0.70 | Detector confidence. Calibrated — see below. |
| `FACE_MATCH_THRESHOLD` | 0.45 | Cosine similarity required to accept an identity |
| `FACE_CONFIRM_FRAMES` | 3 | Frames before announcing arrival |
| `FACE_FORGET_FRAMES` | 5 | Frames before announcing departure |
| `FACE_DB_PATH` | `vision/data/faces.db` | Embedding database |
| `CAMERA_INDEX` | 0 | Webcam index for `cv2.VideoCapture` |
| `VISION_FPS` | 5 | Target loop rate |

### Tests

```bash
pytest vision/tests/ -q             # 117 tests, no camera needed
```

Face images come from `scikit-image` sample data (two different real people),
so same-person and different-person claims are measured rather than assumed.
