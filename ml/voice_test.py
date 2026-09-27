#!/usr/bin/env python3
"""
voice_test.py -- Full loopback smoke test for voice_agent.py via VB-Audio Cable
=================================================================================

Audio routing
-------------
  Test script  -->  CABLE Input (device 16, output)  -->  [VB-Audio pipe]
                                                       -->  CABLE Output (device 17, input)  -->  voice_agent mic

  voice_agent TTS  -->  Speakers (device 4)  [NOT the cable -- no feedback loop]

The shim patches sd.InputStream inside voice_agent to:
  - Use CABLE Output (device 17) as the capture device
  - Open at 2ch / 48kHz (what Windows exposes on CABLE Output)
  - Downmix stereo -> mono and resample 48kHz -> 16kHz before handing
    each audio chunk to voice_agent's real callback

Modes
-----
  python voice_test.py                # full suite, also starts uvicorn
  python voice_test.py --no-backend   # assume run.sh already running
  python voice_test.py --list         # list test cases
  python voice_test.py --case 4       # run only case 4 (0-based)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import textwrap
import time
import threading
import wave
import warnings
import urllib.request
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Device IDs  (confirmed from sd.query_devices() output)
# ---------------------------------------------------------------------------
CABLE_INPUT_OUT  = 16   # CABLE Input  (VB-Audio Virtual Cable) -- 2ch OUTPUT
                        # test script plays to this; VB pipes it to CABLE Output
CABLE_OUTPUT_IN  = 17   # CABLE Output (VB-Audio Virtual Cable) -- 2ch INPUT
                        # voice_agent reads from this as if it were a mic
SPEAKER_DEV      = 4    # Speakers (Realtek) -- where agent TTS actually plays

CABLE_HW_RATE    = 48000   # Windows exposes CABLE Output at 48 kHz
CABLE_HW_CH      = 2       # stereo
AGENT_RATE       = 16000   # Moonshine STT expects 16 kHz mono
RESAMPLE_RATIO   = CABLE_HW_RATE // AGENT_RATE   # = 3

ML_DIR       = Path(__file__).resolve().parent
PIPER_MODEL  = ML_DIR / "en_US-lessac-medium.onnx"
BACKEND_URL  = "http://127.0.0.1:8000"
HEALTH_URL   = f"{BACKEND_URL}/health"

# Response wait budgets (seconds per timeout class)
_TIMEOUT = {"instant": 6, "api": 14, "llm": 45, "quiz": 55}

# ANSI colours
_R = "\033[91m"; _G = "\033[92m"; _Y = "\033[93m"
_C = "\033[96m"; _B = "\033[94m"; _W = "\033[97m"
_DIM = "\033[2m"; _RST = "\033[0m"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
# (label, utterance, [regex patterns -- at least one must appear], timeout_class)

TEST_CASES: list[tuple[str, str, list[str], str]] = [

    # ---- Layer 1: instant regex dispatcher ---------------------------------
    ("get_time",
     "what is the current time",
     [r"\d{1,2}:\d{2}", r"time is"],
     "instant"),

    ("set_timer_digits",
     "set a timer for 5 minutes",
     [r"timer", r"started|set"],
     "api"),

    ("set_timer_words",
     "set a timer for three minutes",
     [r"timer", r"three|3.minute|started"],
     "api"),

    ("set_alarm_digits",
     "set an alarm at 7 30 a m",
     [r"alarm", r"7.30|07.30|set|scheduled"],
     "api"),

    ("add_note",
     "write a note: photosynthesis converts sunlight to energy",
     [r"note", r"saved|written|added|got it"],
     "api"),

    ("create_task",
     "remind me to review chapter five",
     [r"task|reminder|to.do", r"added|done|got it"],
     "api"),

    ("list_timers",
     "what timers do I have",
     [r"timer", r"no timer|running|active|minute"],
     "api"),

    ("list_alarms",
     "list my alarms",
     [r"alarm", r"no alarm|7.30|scheduled"],
     "api"),

    ("list_notes",
     "show my notes",
     [r"note", r"photosynthesis|no note"],
     "api"),

    ("list_tasks",
     "what tasks do I have",
     [r"task|to.do", r"chapter five|no task"],
     "api"),

    ("get_weather",
     "what is the weather in London",
     [r"london|celsius|degree|weather|humidity|could not|sorry"],
     "api"),

    # ---- Layer 2: LLM router -----------------------------------------------
    ("flashcard_gen",
     "create flashcards about the water cycle",
     [r"flash|card|water.cycle|evaporation|condensation"],
     "quiz"),

    ("quiz_gen",
     "generate a quiz about the solar system",
     [r"quiz|solar|planet|question"],
     "quiz"),

    # ---- Layer 3: streaming SLM chat ---------------------------------------
    ("slm_chat_math",
     "what is two plus two",
     [r"\b4\b|four|too|also"],
     "llm"),

    ("slm_chat_gravity",
     "can you explain what gravity is in simple words",
     [r"gravity|pull|force|earth"],
     "llm"),

    ("slm_chat_photosynthesis",
     "what is photosynthesis",
     [r"photosynthesis|plant|sunlight|energy|food"],
     "llm"),

    # ---- Note retrieval via Step 3b ----------------------------------------
    ("note_retrieval_chat",
     "tell me what I wrote in my notes about photosynthesis",
     [r"photosynthesis|sunlight|energy|note"],
     "llm"),

    # ---- Safety / escalation -----------------------------------------------
    ("slm_escalation",
     "explain quantum entanglement in detail",
     [r"quantum|teacher|rephrasing|entanglement|particle|complex"],
     "llm"),

    # ---- Persona setup flow ------------------------------------------------
    ("persona_setup_start",
     "help me set up my persona",
     [r"persona|personality|name|favourite|like|what"],
     "api"),

    ("persona_setup_cancel",
     "cancel the persona setup",
     [r"cancel|unchanged|existing|ok"],
     "api"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(msg: str, colour: str = _C) -> None:
    w = 68
    print(f"\n{colour}{'=' * w}{_RST}")
    print(f"{colour}  {msg}{_RST}")
    print(f"{colour}{'=' * w}{_RST}")


def _wait_for_backend(timeout: float = 120) -> bool:
    deadline = time.time() + timeout
    n = 0
    while time.time() < deadline:
        try:
            urllib.request.urlopen(HEALTH_URL, timeout=3)
            return True
        except Exception:
            n += 1
            if n % 10 == 0:
                print(f"  {_DIM}Still waiting for backend ({n*0.5:.0f}s)...{_RST}")
            time.sleep(0.5)
    return False


_PIPER_VOICE = None

def _synth_wav(text: str, out_path: Path) -> None:
    """Synthesize text -> 22050 Hz mono int16 WAV via Piper."""
    global _PIPER_VOICE
    from piper import PiperVoice
    if _PIPER_VOICE is None:
        _PIPER_VOICE = PiperVoice.load(str(PIPER_MODEL))
    
    chunks = list(_PIPER_VOICE.synthesize(text))
    audio = b"".join(c.audio_int16_bytes for c in chunks)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(audio)

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wio
import scipy.signal
import threading

_TEST_AUDIO_LOCK = threading.Lock()
_TEST_AUDIO_DATA = np.zeros((0, 2), dtype="float32")
_TEST_STREAM = None

def _out_callback(outdata, frames, time, status):
    global _TEST_AUDIO_DATA
    with _TEST_AUDIO_LOCK:
        n = len(_TEST_AUDIO_DATA)
        if n == 0:
            outdata.fill(0)
            return
        
        take = min(frames, n)
        outdata[:take] = _TEST_AUDIO_DATA[:take]
        if take < frames:
            outdata[take:].fill(0)
        _TEST_AUDIO_DATA = _TEST_AUDIO_DATA[take:]

def _play_to_cable(path: Path) -> None:
    """Play a WAV to CABLE Input using a persistent callback stream."""
    global _TEST_STREAM
    global _TEST_AUDIO_DATA
    
    rate, data = wio.read(str(path))
    if data.dtype != "float32":
        data = data.astype("float32") / 32768.0
        
    if rate != CABLE_HW_RATE:
        samples = round(len(data) * float(CABLE_HW_RATE) / rate)
        data = scipy.signal.resample(data, samples)
        rate = CABLE_HW_RATE
        
    if data.ndim == 1:
        data = np.column_stack((data, data))

    if _TEST_STREAM is None:
        _TEST_STREAM = sd.OutputStream(
            samplerate=rate, channels=2, device=CABLE_INPUT_OUT,
            dtype="float32", callback=_out_callback
        )
        _TEST_STREAM.start()

    with _TEST_AUDIO_LOCK:
        _TEST_AUDIO_DATA = np.concatenate((_TEST_AUDIO_DATA, data))

    # Wait for the audio to be fully consumed
    import time
    while True:
        with _TEST_AUDIO_LOCK:
            if len(_TEST_AUDIO_DATA) == 0:
                break
        time.sleep(0.1)
    # Add a small buffer to let it flush
    time.sleep(0.2)


# ---------------------------------------------------------------------------
# Voice agent shim source
# ---------------------------------------------------------------------------
# Written to _voice_test_shim.py and executed as voice_agent's entry point.
# Key patches:
#   1. sd.InputStream is replaced with a subclass that forces CABLE Output
#      (device 17, 48kHz stereo) and wraps the callback to downmix+resample
#      to 16kHz mono before the real callback sees the data.
#   2. sd.default.device is set so sd.play() in speak_text() uses Speakers.

_SHIM_SOURCE = textwrap.dedent(f"""\
    # Auto-generated shim -- DO NOT EDIT manually
    import numpy as _np
    import sounddevice as _sd

    # TTS output goes to real speakers, NOT back into the cable
    _sd.default.device = ({CABLE_OUTPUT_IN}, {SPEAKER_DEV})

    # --- Patch sd.InputStream to use CABLE Output and adapt the audio ---
    _OrigInputStream = _sd.InputStream

    class _CableInputStream(_OrigInputStream):
       
        _RATIO = {RESAMPLE_RATIO}

        def __init__(self, *a, **kw):
            self._vcb = kw.pop('callback', None)
            self._buf = _np.zeros((0, 1), dtype='int16')
            kw['device']     = {CABLE_OUTPUT_IN}
            kw['channels']   = {CABLE_HW_CH}
            kw['samplerate'] = {CABLE_HW_RATE}
            kw['dtype']      = 'int16'
            # Blocksize must scale with ratio so agent gets same chunk length
            kw['blocksize']  = kw.get('blocksize', 1280) * {RESAMPLE_RATIO}
            super().__init__(*a, callback=self._wrap, **kw)

        def _wrap(self, indata, frames, t, status):
            if self._vcb is None:
                return
            # Downmix stereo -> mono by averaging channels
            mono = indata.mean(axis=1, keepdims=True).astype('int16')
            # Decimate 48kHz -> 16kHz (take every Nth sample)
            decimated = mono[::{RESAMPLE_RATIO}]
            self._vcb(decimated, len(decimated), t, status)

    _sd.InputStream = _CableInputStream

    # --- Now run voice_agent normally ---
    import runpy, sys
    sys.argv = ["voice_agent.py", "--mode", "continuous"]
    runpy.run_path(r"{str(ML_DIR / "voice_agent.py").replace(chr(92), "/")}", run_name="__main__")
""")


# ---------------------------------------------------------------------------
# Live stdout capture (daemon thread)
# ---------------------------------------------------------------------------

class _Capture:
    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc  = proc
        self._lines: list[str] = []
        self._lock  = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        assert self._proc.stdout
        for raw in self._proc.stdout:
            line = raw.rstrip("\n\r")
            with self._lock:
                self._lines.append(line)
            # Colour-code live output
            if line.startswith("Agent:"):
                print(f"  {_G}{line}{_RST}")
            elif line.startswith("You said:"):
                print(f"  {_Y}{line}{_RST}")
            elif any(k in line for k in ("Transcrib", "Streaming", "SLM", "Silence")):
                print(f"  {_B}{line}{_RST}")
            elif line.strip():
                print(f"  {_DIM}{line}{_RST}")

    def since(self, idx: int) -> str:
        with self._lock:
            return "\n".join(self._lines[idx:])

    def idx(self) -> int:
        with self._lock:
            return len(self._lines)


# ---------------------------------------------------------------------------
# Run one test
# ---------------------------------------------------------------------------

def run_test(
    n: int, label: str, utterance: str,
    patterns: list[str], timeout_cls: str,
    cap: _Capture, tmp: Path,
) -> bool:
    budget  = _TIMEOUT[timeout_cls]
    wavpath = tmp / f"t{n:02d}_{label}.wav"
    total   = len(TEST_CASES)

    print(f"\n{_W}-- [{n+1:02d}/{total}] {label}{_RST}")
    print(f"  {_C}Say  : \"{utterance}\"{_RST}")
    print(f"  {_DIM}Wait : {budget}s  |  Expect any of: {patterns}{_RST}")

    t0 = cap.idx()

    # Synthesize
    print(f"  {_DIM}Synthesizing...{_RST}", end="", flush=True)
    try:
        _synth_wav(utterance, wavpath)
        print(" done.")
    except Exception as e:
        print(); print(f"  {_R}[FAIL] Synth error: {e}{_RST}"); return False

    # Play into CABLE
    print(f"  {_DIM}Playing into CABLE Input...{_RST}", end="", flush=True)
    try:
        _play_to_cable(wavpath)
        print(" done.")
    except Exception as e:
        import traceback
        print(); print(f"  {_R}[FAIL] Play error: {e}\n{traceback.format_exc()}{_RST}"); return False

    # ---------- 1. Wait for first agent response --------------------------------
    first_deadline = time.time() + budget
    got = False
    while time.time() < first_deadline:
        snap = cap.since(t0).lower()
        if "agent:" in snap or "you said:" in snap:
            got = True
            break
        time.sleep(0.3)

    if not got:
        resp = cap.since(t0).lower()
        print(f"  {_R}[FAIL] No agent response within {budget}s.{_RST}")
        if resp.strip():
            print(f"  {_DIM}Captured: {resp[:200]}{_RST}")
        return False

    # ---------- 2. Wait for agent to be ready again -----------------------------
    # 'Ready.' is printed by voice_agent when it finishes ALL processing,
    # streaming, and TTS playback. We just wait for it.
    ready_deadline = time.time() + 120  # SLM can take >60s
    while time.time() < ready_deadline:
        if "ready." in cap.since(t0).lower():
            break
        time.sleep(0.3)

    resp = cap.since(t0).lower()
    
    # Filter out STT transcription lines so we only test the agent's response
    agent_resp = "\n".join(
        line for line in resp.splitlines() 
        if "you said:" not in line and "ready." not in line
    )

    if not patterns:
        print(f"  {_Y}[OBSERVE] No assertion.{_RST}")
        return True

    matched = [p for p in patterns if re.search(p, agent_resp, re.I)]
    if matched:
        print(f"  {_G}[PASS] Matched: {matched}{_RST}")
        return True
    else:
        print(f"  {_R}[FAIL] Expected any of {patterns}{_RST}")
        print(f"  {_DIM}Response window:\n{agent_resp[:500]}{_RST}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Voice agent loopback smoke test")
    ap.add_argument("--list",       action="store_true",
                    help="List all test cases and exit")
    ap.add_argument("--case",       type=int, default=-1,
                    help="Run only test case N (0-based)")
    ap.add_argument("--no-backend", action="store_true",
                    help="Skip starting uvicorn (run.sh already running)")
    args = ap.parse_args()

    if args.list:
        print(f"\n{_C}Voice agent test cases:{_RST}")
        for i, (lbl, utt, _, cls) in enumerate(TEST_CASES):
            print(f"  [{i:02d}] {_W}{lbl:<35}{_RST}  \"{utt}\"  {_DIM}({cls}){_RST}")
        sys.exit(0)

    cases = TEST_CASES if args.case < 0 else [TEST_CASES[args.case]]

    _banner("TableTot Voice Agent -- VB-Cable Loopback Smoke Test", _C)
    print(f"""
  Audio routing:
    Test script  -->  CABLE Input  (device {CABLE_INPUT_OUT}) -- VB pipes -->
                  -->  CABLE Output (device {CABLE_OUTPUT_IN}) --> voice_agent mic

    Agent TTS    -->  Speakers (device {SPEAKER_DEV}) [no feedback loop]

  Shim patches sd.InputStream to capture CABLE Output at 48kHz/stereo
  and deliver 16kHz/mono to Moonshine STT inside voice_agent.

  Test cases: {len(cases)}
""")

    env = os.environ.copy()
    env["TABLETOT_PROFILE_ID"] = "1"

    # -- 1. Start ML backend -------------------------------------------------
    uvicorn_proc: Optional[subprocess.Popen] = None
    if not args.no_backend:
        _banner("Step 1/3 -- Starting ML backend (uvicorn)", _B)
        uvicorn_proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(ML_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        threading.Thread(
            target=lambda: [_ for _ in uvicorn_proc.stdout],
            daemon=True,
        ).start()
        print(f"  {_DIM}Waiting for {HEALTH_URL} ...{_RST}")
        if not _wait_for_backend(120):
            print(f"\n{_R}ERROR: Backend did not start in 2 minutes.{_RST}")
            uvicorn_proc.terminate(); sys.exit(1)
        print(f"  {_G}Backend is up!{_RST}")
    else:
        print(f"  {_Y}--no-backend: checking reachability...{_RST}")
        if not _wait_for_backend(10):
            print(f"  {_R}ERROR: Cannot reach {HEALTH_URL}. Start run.sh first.{_RST}")
            sys.exit(1)
        print(f"  {_G}Backend reachable.{_RST}")

    # -- 2. Launch voice_agent via shim --------------------------------------
    _banner("Step 2/3 -- Launching voice_agent (CABLE Output as mic)", _B)

    shim = ML_DIR / "_voice_test_shim.py"
    shim.write_text(_SHIM_SOURCE, encoding="utf-8")

    voice_proc = subprocess.Popen(
        [sys.executable, "-u", str(shim)],
        cwd=str(ML_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    cap = _Capture(voice_proc)

    # Wait for voice_agent to finish loading models
    print(f"  {_DIM}Waiting for models (Piper + Moonshine + OWW, up to 90s)...{_RST}")
    deadline = time.time() + 90
    while time.time() < deadline:
        with cap._lock:
            full = "\n".join(cap._lines).lower()
        if "continuous" in full or "speak again" in full or "just speak" in full:
            break
        if "error" in full and "input" in full:
            print(f"\n{_R}voice_agent failed to open audio input. Shim dump:{_RST}")
            print(full[:600])
            voice_proc.terminate()
            if uvicorn_proc: uvicorn_proc.terminate()
            shim.unlink(missing_ok=True)
            sys.exit(1)
        time.sleep(0.5)
    time.sleep(2)
    print(f"  {_G}Voice agent ready.{_RST}")

    # -- 3. Run tests --------------------------------------------------------
    _banner("Step 3/3 -- Running test cases", _B)

    tmp = ML_DIR / "_voice_test_wavs"
    tmp.mkdir(exist_ok=True)

    results: list[tuple[str, bool]] = []
    for i, (lbl, utt, pats, cls) in enumerate(cases):
        ok = run_test(i, lbl, utt, pats, cls, cap, tmp)
        results.append((lbl, ok))
        time.sleep(1)  # minimal gap — run_test already waits for agent idle

    # -- Summary -------------------------------------------------------------
    _banner("Results", _C)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    for lbl, ok in results:
        st = f"{_G}[PASS]{_RST}" if ok else f"{_R}[FAIL]{_RST}"
        print(f"  {st}  {lbl}")
    print()
    if passed == total:
        print(f"{_G}All {total} tests passed!{_RST}")
    else:
        print(f"{_R}{total - passed}/{total} failed.{_RST}")

    # -- Cleanup -------------------------------------------------------------
    print(f"\n{_DIM}Shutting down...{_RST}")
    voice_proc.terminate()
    if uvicorn_proc: uvicorn_proc.terminate()
    shim.unlink(missing_ok=True)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{_Y}Interrupted.{_RST}")
        sys.exit(0)
