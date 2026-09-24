#!/usr/bin/env python3
"""
Voice front-end for job_agent.py
=================================
Push-to-talk voice interface: press Enter, speak your command, it transcribes
locally with whisper.cpp, matches it to an action, runs job_agent.py, and
speaks the result back with espeak-ng.

Everything runs locally — no audio or transcript is sent to any cloud service
for the voice part itself (only job_agent.py's own AI scoring step, if
enabled, talks to the Anthropic API).

Recognized commands (said naturally, matched by keywords):
    "search" / "run a search" / "find jobs"      -> runs a fresh job search
    "latest" / "any new jobs" / "read report"     -> reads back latest report
    "list reports" / "what reports do you have"   -> lists saved report dates
    "quit" / "exit" / "stop"                      -> exits the voice loop

Setup: see VOICE_SETUP.md. Requires:
    - whisper.cpp built locally (whisper-cli binary + a downloaded model)
    - espeak-ng and arecord (alsa-utils) installed
No extra Python packages needed beyond what's in requirements.txt.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JOB_AGENT = BASE_DIR / "job_agent.py"
PYTHON_BIN = sys.executable

# --- configure these for your machine (or set as env vars) -----------------
WHISPER_BIN = os.environ.get("WHISPER_BIN", str(Path.home() / "whisper.cpp/build/bin/whisper-cli"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", str(Path.home() / "whisper.cpp/models/ggml-base.en.bin"))
RECORD_SECONDS = int(os.environ.get("VOICE_RECORD_SECONDS", "5"))

# --- TTS engine: piper (natural, recommended) or espeak-ng (fallback) ------
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")            # "piper" or "espeak"
PIPER_BIN = os.environ.get("PIPER_BIN", "piper")              # usually just "piper" if pip-installed
PIPER_MODEL = os.environ.get("PIPER_MODEL", str(Path.home() / "piper_voices/en_US-lessac-medium.onnx"))
ESPEAK_VOICE = os.environ.get("ESPEAK_VOICE", "en-us")         # e.g. en-gb, en-us+f3
ESPEAK_SPEED = os.environ.get("ESPEAK_SPEED", "160")
ESPEAK_PITCH = os.environ.get("ESPEAK_PITCH", "50")
# -----------------------------------------------------------------------------

SEARCH_WORDS = ["search", "find job", "find work", "run a search", "check for job", "look for job"]
LATEST_WORDS = ["latest", "any new job", "read report", "what have you found", "any jobs", "update me"]
LIST_WORDS = ["list report", "what reports", "past reports", "history"]
QUIT_WORDS = ["quit", "exit", "stop", "goodbye", "that's all"]


def speak(text: str):
    """Speak text aloud, preferring Piper (natural neural voice) and falling
    back to espeak-ng if Piper isn't set up or TTS_ENGINE=espeak is set."""
    print(f"\n🗣️  {text}\n")

    if TTS_ENGINE == "piper":
        if _speak_piper(text):
            return
        print("[voice_agent] Piper unavailable, falling back to espeak-ng. "
              "See VOICE_SETUP.md to set up Piper.", file=sys.stderr)

    _speak_espeak(text)


def _speak_piper(text: str) -> bool:
    """Synthesize with Piper to a temp wav and play it. Returns False on failure
    so speak() can fall back to espeak-ng."""
    if not Path(PIPER_MODEL).exists():
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = str(Path(tmp) / "out.wav")
            proc = subprocess.run(
                [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", wav_path],
                input=text, capture_output=True, text=True,
            )
            if proc.returncode != 0 or not Path(wav_path).exists():
                return False
            subprocess.run(["aplay", "-q", wav_path], check=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except FileNotFoundError:
        return False


def _speak_espeak(text: str):
    try:
        subprocess.run(
            ["espeak-ng", "-v", ESPEAK_VOICE, "-s", ESPEAK_SPEED, "-p", ESPEAK_PITCH, text],
            check=False,
        )
    except FileNotFoundError:
        print("[voice_agent] espeak-ng not installed either — continuing with "
              "text-only output.", file=sys.stderr)


def record_audio(path: str, seconds: int):
    """Record from the default mic to a wav file using arecord (ALSA)."""
    print(f"🎙️  Listening for {seconds}s... (speak now)")
    subprocess.run(
        ["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(seconds), path],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def transcribe(wav_path: str) -> str:
    """Run whisper.cpp on the recorded wav and return the transcript text."""
    if not Path(WHISPER_BIN).exists():
        speak("Whisper isn't set up yet. Check VOICE_SETUP.md for install steps.")
        return ""
    if not Path(WHISPER_MODEL).exists():
        speak("Whisper model file not found. Check VOICE_SETUP.md for the download step.")
        return ""

    out_stem = wav_path.replace(".wav", "")
    subprocess.run(
        [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav_path, "-nt", "-otxt", "-of", out_stem],
        capture_output=True, text=True,
    )
    txt_path = out_stem + ".txt"
    if Path(txt_path).exists():
        return Path(txt_path).read_text().strip()
    return ""


def match_command(transcript: str) -> str:
    t = transcript.lower()
    if any(w in t for w in QUIT_WORDS):
        return "quit"
    if any(w in t for w in LIST_WORDS):
        return "list"
    if any(w in t for w in SEARCH_WORDS):
        return "search"
    if any(w in t for w in LATEST_WORDS):
        return "latest"
    return "unknown"


def run_job_agent(*args) -> str:
    result = subprocess.run(
        [PYTHON_BIN, str(JOB_AGENT), *args],
        capture_output=True, text=True,
    )
    return (result.stdout or result.stderr).strip()


def summarize_for_voice(report_text: str, max_items: int = 3) -> str:
    """Turn a markdown report into a short spoken summary (full text stays on screen)."""
    if not report_text or "No matching" in report_text:
        return "No matching jobs found in the latest report."
    headers = re.findall(r"^## (.+)$", report_text, flags=re.MULTILINE)
    if not headers:
        return "I have a report, but couldn't summarize it — check the screen for details."
    top = headers[:max_items]
    return f"I found {len(headers)} matches. Top {len(top)}: " + "; ".join(top) + "."


def main_loop():
    speak("Job agent voice interface ready. Press Enter, then speak a command.")
    while True:
        try:
            input("\n[Press Enter to talk, or Ctrl+C to quit] > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        with tempfile.TemporaryDirectory() as tmp:
            wav_path = str(Path(tmp) / "cmd.wav")
            record_audio(wav_path, RECORD_SECONDS)
            transcript = transcribe(wav_path)

        if not transcript:
            speak("I didn't catch that. Try again.")
            continue

        print(f"📝 Heard: {transcript}")
        action = match_command(transcript)

        if action == "quit":
            speak("Okay, stopping.")
            break
        elif action == "search":
            speak("Running a fresh job search now. This may take a minute.")
            run_job_agent()
            latest = BASE_DIR / "reports" / "latest.md"
            speak("Search complete. " + summarize_for_voice(latest.read_text() if latest.exists() else ""))
        elif action == "latest":
            report_path = BASE_DIR / "reports" / "latest.md"
            report_text = report_path.read_text() if report_path.exists() else ""
            speak(summarize_for_voice(report_text))
        elif action == "list":
            out = run_job_agent("--list-reports")
            speak("Saved reports: " + (out.replace("\n", ", ") if out else "none yet"))
        else:
            speak("I didn't recognize that command. Try 'search for jobs' or 'any new jobs'.")


if __name__ == "__main__":
    main_loop()
