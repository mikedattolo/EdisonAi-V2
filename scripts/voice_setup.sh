#!/usr/bin/env bash
# Set up the on-box voice listener stack (Whisper STT) and prove Brio capture works.
set -uxo pipefail

VOICE=/srv/edison-data/voice
mkdir -p "$VOICE"
cd "$VOICE"

# Dedicated venv (system python 3.11) so audio/whisper deps stay isolated from the API.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
PY=.venv/bin/python
"$PY" -m pip install --upgrade pip wheel >/dev/null

# faster-whisper (CTranslate2) runs on CPU int8 - reliable and fast enough for short commands.
"$PY" -m pip install faster-whisper webrtcvad numpy requests
"$PY" -c "import faster_whisper, webrtcvad, numpy, requests; print('VOICE_DEPS_OK')"

# Capture 4s from the Brio mic and transcribe it (proves the end-to-end audio path).
echo "=== capturing 4s from Brio ==="
ffmpeg -hide_banner -loglevel error -f alsa -i plughw:CARD=BRIO -ac 1 -ar 16000 -t 4 -y /tmp/brio_test.wav || echo "CAPTURE_FAILED"
ls -l /tmp/brio_test.wav 2>/dev/null

echo "=== transcribing (downloads base model on first run) ==="
"$PY" - <<'PY'
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = model.transcribe("/tmp/brio_test.wav", language="en")
text = " ".join(s.text for s in segments).strip()
print("TRANSCRIPT:", text or "(silence / no speech)")
PY

echo VOICE_SETUP_DONE
