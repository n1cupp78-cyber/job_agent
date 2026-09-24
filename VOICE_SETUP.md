# Voice Setup — whisper.cpp + espeak-ng

This wires up push-to-talk voice control for the job agent: press Enter,
speak a command, it transcribes locally and speaks back a summary.

Everything here runs **locally on your machine** — no audio leaves your
computer. (job_agent.py's own AI scoring step still talks to the Anthropic
API if you've enabled it, but that's separate from voice.)

## 1. Install system packages

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install -y build-essential cmake git alsa-utils espeak-ng
```

**Fedora (e.g. Fedora 35):**
```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y cmake git alsa-utils espeak-ng
```

- `alsa-utils` gives you `arecord` (mic capture) and `aplay` (audio playback)
- `espeak-ng` is a fallback text-to-speech engine (robotic but zero extra setup)

## 1b. Install Piper TTS (recommended — much more natural voice)

Piper is a local neural text-to-speech engine. Still fully offline, but
sounds like a real voice instead of a robot.

```bash
pip install piper-tts
```

(this installs into your venv — run it with the venv activated, same as
`pip install -r requirements.txt`)

Then download a voice model. `en_US-lessac-medium` is a good general-purpose
one to start with:

```bash
mkdir -p ~/piper_voices
cd ~/piper_voices
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Test it directly:

```bash
echo "any new jobs today" | piper --model ~/piper_voices/en_US-lessac-medium.onnx --output_file test.wav
aplay test.wav
```

If that plays back clearly, you're set — `voice_agent.py` uses Piper by
default and only falls back to `espeak-ng` if the model file isn't found.

**Browse more voices/accents:** https://rhasspy.github.io/piper-samples/ —
pick any voice, then substitute its name in the two `curl` URLs above (they
follow the pattern `.../en/LOCALE/VOICE_NAME/QUALITY/VOICE_NAME-QUALITY.onnx`
and the matching `.onnx.json`).

To switch back to espeak-ng at any time without removing Piper, set in `.env`:
```
TTS_ENGINE=espeak
```

## 2. Build whisper.cpp

```bash
cd ~
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build --config Release
```

## 3. Download a speech model

`base.en` is a good balance of speed vs. accuracy for short commands on a
normal laptop/desktop CPU:

```bash
cd ~/whisper.cpp
bash ./models/download-ggml-model.sh base.en
```

This creates `~/whisper.cpp/models/ggml-base.en.bin`.

(If your machine is slower, use `tiny.en` instead — faster, slightly less
accurate, plenty good for short commands like "any new jobs".)

## 4. Check your microphone works

```bash
arecord -l          # confirm a capture device is listed
arecord -d 3 -f S16_LE -r 16000 test.wav && aplay test.wav
```

You should hear back what you just said. If not, fix mic/ALSA setup before
continuing — the voice agent depends on `arecord` working.

## 5. Point the voice agent at your whisper build

The script defaults to `~/whisper.cpp/build/bin/whisper-cli` and
`~/whisper.cpp/models/ggml-base.en.bin`. If yours differ, set env vars
(e.g. in your `.env` file alongside your other keys):

```bash
export WHISPER_BIN=~/whisper.cpp/build/bin/whisper-cli
export WHISPER_MODEL=~/whisper.cpp/models/ggml-base.en.bin
```

## 6. Run it

```bash
cd job_agent
source venv/bin/activate     # if you set up the venv from the main README
python3 voice_agent.py
```

Press Enter, then say something like:
- **"Any new jobs?"** → reads back a short summary of the latest saved report
- **"Run a search"** → kicks off a fresh search (takes a bit longer, hits the job APIs)
- **"List reports"** → lists saved report dates
- **"Stop"** → exits

Full report text always stays on screen too — the spoken version is just a
short summary (top 3 matches) so it doesn't ramble.

## Notes / next steps

- This is **push-to-talk**, not always-listening wake-word detection. That's
  intentional — a true "hey agent" wake word needs a background listener
  (e.g. [openWakeWord](https://github.com/dscripka/openWakeWord) or
  Porcupine) constantly sampling the mic, which is more setup and more
  false-triggers. Push-to-talk is simpler and more reliable to start with.
- If you want always-on wake-word later, the natural next step is running
  openWakeWord in a background loop that calls `voice_agent.py`'s recording
  step once it detects the wake phrase — happy to build that once you've
  used push-to-talk for a bit and know it's worth the extra complexity.
- Recording length defaults to 5 seconds (`VOICE_RECORD_SECONDS` env var to
  change it) — enough for short commands, but if you find yourself getting
  cut off, bump it up.
