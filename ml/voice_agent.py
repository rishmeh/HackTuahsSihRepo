"""
voice_agent.py - Voice Interface for the ML Backend

Uses:
- openWakeWord ("hey_jarvis") for wakeword detection
- Moonshine Tiny for STT
- Piper TTS for voice responses
- Intent parser handles time/weather/timers/alarms/notes/tasks locally
- Falls through to /chat for everything else

Run modes:
  python voice_agent.py                   # wakeword mode — say "Hey Jarvis" first
  python voice_agent.py --mode continuous # always listening, no wake word needed
"""

import os
import sys
import queue
import urllib.request
import warnings
import numpy as np
import requests

warnings.filterwarnings("ignore")

_parser = argparse.ArgumentParser(description="TableTot Voice Agent")
_parser.add_argument(
    "--mode", choices=["wakeword", "continuous"], default="wakeword",
    help="wakeword (default): say 'Hey Jarvis' first. continuous: always listening.",
)
_ARGS = _parser.parse_args()

print("Initializing Voice Agent...")

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
    sys.exit(1)

from learner.policy import default_settings, derive_settings
from learner.profile_store import ProfileStore
from learner import config as learner_config
from persona.phrases import PhraseBook, Situation
from persona.voice import voice_params
from voice_commands.intent import parse as parse_intent
from voice_commands.dispatcher import dispatch as dispatch_intent
from voice_commands.router import llm_route
from persona_setup import sessions as persona_sessions
from quiz_sessions import sessions as quiz_sessions

# Profile ID of the active user. Defaults to 1 (the first created student profile)
# so local testing syncs properly with the dashboard.
ACTIVE_PROFILE_ID: int = int(os.getenv("TABLETOT_PROFILE_ID", "1"))

_store = ProfileStore(learner_config.LEARNER_DB_PATH)
_stored_profile = _store.get(str(ACTIVE_PROFILE_ID))

if _stored_profile:
    _SETTINGS = derive_settings(_stored_profile.profile)
    _STUDENT_AGE = _stored_profile.profile.age
else:
    _SETTINGS = default_settings(age=10)
    _STUDENT_AGE = 10

_PHRASES  = PhraseBook()
_VOICE    = voice_params(_SETTINGS)


def _say(kind, situation):
    return _PHRASES.pick(
        kind, arm=_SETTINGS.encouragement_arm,
        situation=situation, sarcasm_allowed=_SETTINGS.sarcasm_allowed,
    )


def _synthesis_config():
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
        return SynthesisConfig(length_scale=kw["length_scale"])


_SYN_CONFIG = _synthesis_config()

PIPER_MODEL_NAME = "en_US-lessac-medium.onnx"
PIPER_MODEL_URL  = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    "/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
)

if not os.path.exists(PIPER_MODEL_NAME):
    print("Downloading Piper TTS model...")
    urllib.request.urlretrieve(PIPER_MODEL_URL, PIPER_MODEL_NAME)
    urllib.request.urlretrieve(PIPER_MODEL_URL + ".json", PIPER_MODEL_NAME + ".json")

print("Loading Piper TTS...")
tts_voice = PiperVoice.load(PIPER_MODEL_NAME)

print("Loading openWakeWord (hey_jarvis)...")
openwakeword.utils.download_models()
oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

print("Loading Moonshine Tiny STT...")
_model_info = find_model_info("en", ModelArch.TINY)
_model_path, _model_arch = download_model_from_info(_model_info)
moonshine_model = MoonshineTranscriber(model_path=_model_path, model_arch=_model_arch)

RATE             = 16000
CHUNK            = 1280
VAD_THRESHOLD    = 500
SILENCE_DURATION = 1.5

audio_queue = queue.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(indata.copy())


def set_robot_state(state_name: str):
    """Tell the FastAPI backend to update the robot face/servos."""
    try:
        requests.post("http://127.0.0.1:8000/hardware/control", json={
            "face_state": state_name,
            "servo_state": state_name
        }, timeout=2)
    except requests.exceptions.RequestException as e:
        pass  # Fail silently if backend is down

def speak_text(text: str):
    print(f"Agent: {text}")
    set_robot_state("speaking")
    stream = (
        tts_voice.synthesize(text, syn_config=_SYN_CONFIG)
        if _SYN_CONFIG
        else tts_voice.synthesize(text)
    )
    audio_bytes = b"".join(c.audio_int16_bytes for c in stream)
    if not audio_bytes:
        set_robot_state("listening")
        return
        
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
    
    # Play synchronously (Piper lessac-medium is 22050 Hz)
    sd.play(audio_array, samplerate=22050)
    sd.wait()
    set_robot_state("listening")

# ---------------------------------------------------------
# 6. Filler lines while the backend is processing come from the persona's
#    "thinking" pool — see _say() above.
# ---------------------------------------------------------

# ---------------------------------------------------------
# 7. Main Loop
# ---------------------------------------------------------
API_URL = "http://127.0.0.1:8000/chat"
SESSION_ID = "voice-session-1"


def main():
    print("\n" + "=" * 50)
    if _ARGS.mode == "continuous":
        print("Voice Agent — CONTINUOUS mode (no wake word needed).")
        print("Just speak. Pause 1.5 s to submit.")
    else:
        print("Voice Agent — WAKEWORD mode. Say 'Hey Jarvis' to activate.")
    print("=" * 50 + "\n")

    # Continuous mode: skip the wakeword loop entirely
    state = "RECORDING" if _ARGS.mode == "continuous" else "WAKEWORD"
    recorded_frames, silence_frames = [], 0
    max_silence_frames = int(RATE / CHUNK * SILENCE_DURATION)
    
    with sd.InputStream(samplerate=RATE, channels=1, dtype='int16', blocksize=CHUNK, callback=audio_callback):
        while True:
            chunk = audio_queue.get()
            
            if state == "WAKEWORD":
                prediction = oww_model.predict(chunk.flatten())
                
                # Check if wakeword confidence exceeds threshold
                confidence = 0.0
                for model_name, score in prediction.items():
                    if score > 0.5:
                        confidence = score
                
                if confidence > 0.5:
                    print("\n[Wakeword Detected! Listening...]")
                    set_robot_state("listening")
                    speak_text(_say("listening", Situation.LISTENING))
                    state = "RECORDING"
                    recorded_frames = []
                    silence_frames = 0
                    while not audio_queue.empty():
                        audio_queue.get()

            elif state == "RECORDING":
                rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))
                recorded_frames.append(chunk)
                silence_frames = 0 if rms >= VAD_THRESHOLD else silence_frames + 1

                if silence_frames > max_silence_frames:
                    print("[Silence detected, processing...]")
                    state = "PROCESSING"
                    
                    full_audio = np.concatenate(recorded_frames, axis=0).flatten()
                    float_audio = full_audio.astype(np.float32) / 32768.0

                    if len(float_audio) > RATE * 0.5:
                        try:
                            print("Transcribing...")
                            transcript = moonshine_model.transcribe_without_streaming(
                                float_audio.tolist(), sample_rate=RATE
                            )
                            transcription = " ".join(l.text for l in transcript.lines).strip()
                            print(f"You said: {transcription}")

                            if transcription:
                                profile_key = str(ACTIVE_PROFILE_ID)
                                intent = parse_intent(transcription)

                                # Quiz session owns the next utterance while active.
                                if quiz_sessions.is_active(profile_key):
                                    if intent.name == "cancel_quiz":
                                        quiz_sessions.cancel(profile_key)
                                        speak_text("Quiz cancelled. Come back anytime!")
                                    else:
                                        reply, done = quiz_sessions.answer(profile_key, transcription)
                                        speak_text(reply)

                                # Persona setup owns the next utterance until it completes
                                # or the user explicitly cancels it. This prevents answers
                                # being misrouted into the normal command/chat path.
                                elif persona_sessions.is_active(profile_key):
                                    if intent.name == "cancel_persona_setup":
                                        persona_sessions.cancel(profile_key)
                                        speak_text("Okay, I cancelled persona setup. Your existing persona is unchanged.")
                                    else:
                                        _, reply, _ = persona_sessions.answer(
                                            profile_key, transcription, age=10
                                        )
                                        speak_text(reply)
                                elif intent.name == "start_persona_setup":
                                    speak_text(persona_sessions.start(profile_key, age=10))
                                else:
                                    # Layer 1: regex intent parser (instant)
                                    quick_reply = dispatch_intent(intent, profile_id=ACTIVE_PROFILE_ID) \
                                        if intent.name != "unknown" else None

                                    if quick_reply:
                                        speak_text(quick_reply)
                                    else:
                                        # Layer 2: LLM router (fast structured Ollama call).
                                        # voice_agent is synchronous, so asyncio.run() is safe here.
                                        import asyncio as _asyncio
                                        set_robot_state("thinking")
                                        routed = _asyncio.run(llm_route(transcription))
                                        router_reply = (
                                            dispatch_intent(routed, profile_id=ACTIVE_PROFILE_ID)
                                            if routed and routed.name != "unknown"
                                            else None
                                        )

                                        if router_reply:
                                            speak_text(router_reply)
                                        else:
                                            # Layer 3: full LLM chat
                                            speak_text(_say("thinking", Situation.THINKING))
                                            set_robot_state("thinking")
                                            print("Sending to LLM backend...")
                                            payload = {
                                                "query": transcription,
                                                "student": {
                                                    "name": "Voice User", "age": _STUDENT_AGE,
                                                    "grade": f"{_STUDENT_AGE - 5}th grade" if _STUDENT_AGE > 5 else "unknown",
                                                    "personality_traits": ["curious"],
                                                    "interests": [], "language_level": "intermediate",
                                                },
                                                "session_id": SESSION_ID,
                                                "student_id": profile_key,
                                            }
                                            try:
                                                r = requests.post(API_URL, json=payload, timeout=150)
                                                if r.status_code == 200:
                                                    speak_text(r.json().get("answer", "No answer found."))
                                                else:
                                                    print(f"API Error: {r.status_code}")
                                                    speak_text(_say("error", Situation.ERROR))
                                            except requests.exceptions.RequestException as e:
                                                print(f"Connection Error: {e}")
                                                speak_text(_say("error", Situation.ERROR))

                        except Exception as e:
                            print(f"Error during processing: {e}")
                            speak_text(_say("error", Situation.ERROR))
                    else:
                        print("Audio too short, ignoring.")

                    in_session = quiz_sessions.is_active(str(ACTIVE_PROFILE_ID)) or persona_sessions.is_active(str(ACTIVE_PROFILE_ID))
                    is_continuous = _ARGS.mode == "continuous" or in_session
                    
                    ready_msg = "Speak again." if is_continuous else "Say 'Hey Jarvis'."
                    print(f"\nReady. {ready_msg}")
                    state = "RECORDING" if is_continuous else "WAKEWORD"
                    
                    if state == "WAKEWORD":
                        set_robot_state("idle")
                    else:
                        set_robot_state("listening")
                        
                    recorded_frames = []
                    silence_frames = 0
                    
                    oww_model.reset()
                    while not audio_queue.empty():
                        audio_queue.get()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)
