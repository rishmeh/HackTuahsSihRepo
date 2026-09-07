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
import argparse, os, sys, queue, urllib.request, warnings
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

from learner.policy import default_settings
from persona.phrases import PhraseBook, Situation
from persona.voice import voice_params
from voice_commands.intent import parse as parse_intent
from voice_commands.dispatcher import dispatch as dispatch_intent

_SETTINGS = default_settings(age=10)
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

# Profile ID of the active user (0 = guest/unknown).
# Set this to the recognised student's ID when face recognition identifies them.
ACTIVE_PROFILE_ID: int = 0

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

audio_queue: queue.Queue = queue.Queue()


def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(indata.copy())


def speak_text(text: str):
    print(f"Agent: {text}")
    stream = (
        tts_voice.synthesize(text, syn_config=_SYN_CONFIG)
        if _SYN_CONFIG
        else tts_voice.synthesize(text)
    )
    audio_bytes = b"".join(c.audio_int16_bytes for c in stream)
    if not audio_bytes:
        return
    sd.play(np.frombuffer(audio_bytes, dtype=np.int16), samplerate=22050)
    sd.wait()


API_URL    = "http://127.0.0.1:8000/chat"
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

    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                        blocksize=CHUNK, callback=audio_callback):
        while True:
            chunk = audio_queue.get()

            if state == "WAKEWORD":
                pred = oww_model.predict(chunk.flatten())
                if any(s > 0.5 for s in pred.values()):
                    print("\n[Wakeword Detected! Listening...]")
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
                                # Step 1: deterministic intent (instant, no LLM)
                                intent = parse_intent(transcription)
                                quick_reply = dispatch_intent(intent, profile_id=ACTIVE_PROFILE_ID)

                                if quick_reply:
                                    speak_text(quick_reply)
                                else:
                                    # Step 2: fall through to LLM
                                    speak_text(_say("thinking", Situation.THINKING))
                                    print("Sending to LLM backend...")
                                    payload = {
                                        "query": transcription,
                                        "student": {
                                            "name": "Voice User", "age": 10,
                                            "grade": "5th grade",
                                            "personality_traits": ["curious"],
                                            "interests": [], "language_level": "intermediate",
                                        },
                                        "session_id": SESSION_ID,
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

                    ready_msg = "Speak again." if _ARGS.mode == "continuous" else "Say 'Hey Jarvis'."
                    print(f"\nReady. {ready_msg}")
                    state = "RECORDING" if _ARGS.mode == "continuous" else "WAKEWORD"
                    oww_model.reset()
                    while not audio_queue.empty():
                        audio_queue.get()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)
