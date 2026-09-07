"""
voice_agent.py - Voice Interface for the ML Backend

Uses:
- openWakeWord ("hey_jarvis") for wakeword detection (placeholder for "Table Tot")
- Moonshine Tiny for STT
- Piper TTS for voice responses
- Connected to local /chat endpoint
"""

import os
import sys
import queue
import time
from contextlib import contextmanager
import urllib.request
import warnings
import numpy as np
import requests

# Suppress warnings from openwakeword / onnxruntime
warnings.filterwarnings("ignore")

print("Initializing Voice Agent...")

# Try importing required libraries
try:
    import sounddevice as sd
    from piper import PiperVoice
    import openwakeword
    from openwakeword.model import Model
    from moonshine_voice.transcriber import Transcriber as MoonshineTranscriber
    from moonshine_voice.moonshine_api import ModelArch
    from moonshine_voice.download import find_model_info, download_model_from_info
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install requirements using: pip install -r requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------
# 0. Persona — Tot's spoken filler lines and voice pace.
#    The voice agent does not yet know which student is at the desk, so it
#    uses the safe default persona (sarcasm off). The backend decorates the
#    actual answers; these lines cover the moments before an answer exists.
# ---------------------------------------------------------
from learner.policy import default_settings
from persona.phrases import PhraseBook, Situation
from persona.voice import voice_params

_SETTINGS = default_settings(age=10)
_PHRASES = PhraseBook()
_VOICE = voice_params(_SETTINGS)


def _say(kind: str, situation: Situation) -> str:
    return _PHRASES.pick(
        kind,
        arm=_SETTINGS.encouragement_arm,
        situation=situation,
        sarcasm_allowed=_SETTINGS.sarcasm_allowed,
    )


def _synthesis_config():
    """Piper's SynthesisConfig from the persona's pace, if this Piper has one."""
    try:
        from piper import SynthesisConfig
    except ImportError:
        return None
    kw = _VOICE.synthesis_kwargs()
    try:
        return SynthesisConfig(
            length_scale=kw["length_scale"],
            noise_scale=kw["noise_scale"],
            noise_w_scale=kw["noise_w"],
        )
    except TypeError:
        # Older SynthesisConfig without the noise fields.
        return SynthesisConfig(length_scale=kw["length_scale"])


_SYN_CONFIG = _synthesis_config()

# ---------------------------------------------------------
# 1. Check and download Piper TTS model
# ---------------------------------------------------------
PIPER_MODEL_NAME = "en_US-lessac-medium.onnx"
PIPER_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
PIPER_JSON_URL = PIPER_MODEL_URL + ".json"

if not os.path.exists(PIPER_MODEL_NAME):
    print(f"Downloading Piper TTS model ({PIPER_MODEL_NAME})...")
    urllib.request.urlretrieve(PIPER_MODEL_URL, PIPER_MODEL_NAME)
    urllib.request.urlretrieve(PIPER_JSON_URL, PIPER_MODEL_NAME + ".json")

print("Loading Piper TTS...")
tts_voice = PiperVoice.load(PIPER_MODEL_NAME)

# ---------------------------------------------------------
# 2. Initialize openWakeWord
# ---------------------------------------------------------
print("Loading openWakeWord (hey_jarvis)...")
openwakeword.utils.download_models() # Ensures default models are downloaded
oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

# ---------------------------------------------------------
# 3. Initialize Moonshine Tiny STT (ONNX, no PyTorch)
# ---------------------------------------------------------
print("Loading Moonshine Tiny STT (ONNX)...")
# download_model_from_info caches the model to the user's AppData on first run
# and returns the path immediately on subsequent runs.
_model_info = find_model_info("en", ModelArch.TINY)
_model_path, _model_arch = download_model_from_info(_model_info)
moonshine_model = MoonshineTranscriber(
    model_path=_model_path,
    model_arch=_model_arch,
)

# ---------------------------------------------------------
# 4. Audio Configuration
# ---------------------------------------------------------
RATE = 16000
CHUNK = 1280
VAD_THRESHOLD = 500  # RMS energy threshold to consider as speech
SILENCE_DURATION = 1.5  # Seconds of silence to trigger STT

audio_queue = queue.Queue()
API_BASE_URL = os.getenv("ML_API_URL", "http://127.0.0.1:8000").rstrip("/")
CURRENT_STUDENT_ID = None

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    # Store int16 audio
    audio_queue.put(indata.copy())

# ---------------------------------------------------------
# 5. Playback Helper
# ---------------------------------------------------------
def speak_text(text: str):
    print(f"Agent: {text}")
    # Synthesize returns an iterator of AudioChunk. Pace comes from the persona.
    audio_stream = (
        tts_voice.synthesize(text, syn_config=_SYN_CONFIG)
        if _SYN_CONFIG is not None
        else tts_voice.synthesize(text)
    )
    
    audio_bytes = b"".join(chunk.audio_int16_bytes for chunk in audio_stream)
    if not audio_bytes:
        return
        
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
    
    sd.play(audio_array, samplerate=22050)
    sd.wait()


def set_robot_state(state: str) -> None:
    """Keep the Pi servos synchronized with laptop voice work."""
    try:
        requests.post(
            f"{API_BASE_URL}/hardware/control",
            json={"face_state": state, "servo_state": state},
            timeout=2,
        )
    except requests.RequestException:
        pass


@contextmanager
def audio_source():
    """Yield PCM chunks captured directly from the laptop microphone."""
    with sd.InputStream(
        samplerate=RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK,
        callback=audio_callback,
    ):
        yield audio_queue.get


def handle_robot_event() -> None:
    """Speak face-recognition greetings through the laptop speaker."""
    global CURRENT_STUDENT_ID
    try:
        response = requests.get(f"{API_BASE_URL}/hardware/events", timeout=0.2)
        if response.status_code == 204:
            return
        response.raise_for_status()
        event = response.json()
    except requests.RequestException:
        return

    if event.get("event") == "departed":
        CURRENT_STUDENT_ID = None
        return
    if event.get("event") != "arrived" or not event.get("student_id"):
        return
    CURRENT_STUDENT_ID = str(event["student_id"])

    # The recognition command already started the happy/nod gesture on the Pi.
    time.sleep(0.85)
    try:
        greeting = requests.post(
            f"{API_BASE_URL}/hardware/greet",
            json={"student_id": event["student_id"]},
            timeout=120,
        )
        greeting.raise_for_status()
        set_robot_state("speaking")
        speak_text(greeting.json().get("answer", "Hello!"))
    except requests.RequestException:
        set_robot_state("speaking")
        speak_text("Hello!")
    finally:
        set_robot_state("idle")
        while not audio_queue.empty():
            audio_queue.get()

# ---------------------------------------------------------
# 6. Filler lines while the backend is processing come from the persona's
#    "thinking" pool — see _say() above.
# ---------------------------------------------------------

# ---------------------------------------------------------
# 7. Main Loop
# ---------------------------------------------------------
API_URL = f"{API_BASE_URL}/chat"
SESSION_ID = "voice-session-1"

def main():
    print("\n" + "="*50)
    print("Voice Agent Started!")
    print("Say 'Hey Jarvis' to wake it up.")
    print("="*50 + "\n")
    
    state = "WAKEWORD" # WAKEWORD -> RECORDING -> PROCESSING
    recorded_frames = []
    silence_frames = 0
    max_silence_frames = int(RATE / CHUNK * SILENCE_DURATION)
    
    print("Audio input: laptop microphone; audio output: laptop speaker")
    with audio_source() as next_chunk:
        while True:
            chunk = next_chunk()
            handle_robot_event()
            
            if state == "WAKEWORD":
                prediction = oww_model.predict(chunk.flatten())
                
                # Check if wakeword confidence exceeds threshold
                confidence = 0.0
                for model_name, score in prediction.items():
                    del model_name
                    # openWakeWord versions return either a scalar or a
                    # one-element ndarray. Normalise both before comparison.
                    score_value = float(np.max(score))
                    if score_value > confidence:
                        confidence = score_value
                
                if confidence > 0.5:
                    print("\n[Wakeword Detected! Listening...]")
                    set_robot_state("listening")
                    speak_text(_say("listening", Situation.LISTENING))
                    
                    state = "RECORDING"
                    recorded_frames = []
                    silence_frames = 0
                    
                    # Flush the queue to drop old audio before listening to the actual query
                    while not audio_queue.empty():
                        audio_queue.get()
                        
            elif state == "RECORDING":
                # Compute RMS energy for simple VAD
                rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
                recorded_frames.append(chunk)
                
                if rms < VAD_THRESHOLD:
                    silence_frames += 1
                else:
                    silence_frames = 0
                
                # If we've hit enough silence, stop recording and process
                if silence_frames > max_silence_frames:
                    print("[Silence detected, processing speech...]")
                    state = "PROCESSING"
                    set_robot_state("thinking")
                    
                    full_audio = np.concatenate(recorded_frames, axis=0).flatten()
                    float_audio = full_audio.astype(np.float32) / 32768.0
                    
                    # Ensure minimum duration before attempting STT
                    if len(float_audio) > RATE * 0.5:
                        try:
                            # 1. STT — transcribe_without_streaming returns a Transcript
                            print("Transcribing...")
                            # Accepts List[float] or float32 numpy array at 16kHz
                            transcript = moonshine_model.transcribe_without_streaming(
                                float_audio.tolist(), sample_rate=RATE
                            )
                            transcription = " ".join(line.text for line in transcript.lines).strip()
                                
                            print(f"You said: {transcription}")
                            
                            if transcription:
                                # 2. Play filler phrase immediately so the user hears
                                #    something while the backend processes the request.
                                speak_text(_say("thinking", Situation.THINKING))

                                # 3. Send to backend
                                print("Sending to backend...")
                                payload = {
                                    "query": transcription,
                                    "student": {
                                        "name": "Voice User",
                                        "age": 10,
                                        "grade": "5th grade",
                                        "personality_traits": ["curious"],
                                        "interests": [],
                                        "language_level": "intermediate"
                                    },
                                    "student_id": CURRENT_STUDENT_ID,
                                    "session_id": SESSION_ID
                                }

                                try:
                                    response = requests.post(API_URL, json=payload, timeout=150)
                                    if response.status_code == 200:
                                        body = response.json()
                                        answer = body.get("answer", "No answer found.")
                                        # 4. TTS — speak the answer
                                        set_robot_state("speaking")
                                        speak_text(answer)
                                    else:
                                        print(f"API Error: {response.status_code} - {response.text}")
                                        speak_text(_say("error", Situation.ERROR))
                                except requests.exceptions.RequestException as e:
                                    print(f"Connection Error: {e}")
                                    speak_text(_say("error", Situation.ERROR))
                        except Exception as e:
                            print(f"Error during processing: {e}")
                            speak_text(_say("error", Situation.ERROR))
                    else:
                        print("Audio too short, ignoring.")
                        
                    print("\nReturning to wakeword mode. Say 'Hey Jarvis' to wake it up.")
                    set_robot_state("idle")
                    state = "WAKEWORD"
                    oww_model.reset()
                    
                    # Flush queue to reset
                    while not audio_queue.empty():
                        audio_queue.get()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting voice agent.")
        sys.exit(0)
