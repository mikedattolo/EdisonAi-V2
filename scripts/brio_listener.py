#!/usr/bin/env python3
"""On-box voice listener: captures the Brio mic, detects "hey edison", transcribes
the command with Whisper, and POSTs it to Edison's voice bridge. Runs as the
edison-brio systemd service (needs the audio group)."""

import json
import os
import subprocess
import time
import urllib.request

import numpy as np
import webrtcvad
from faster_whisper import WhisperModel

API = os.environ.get("EDISON_API", "http://127.0.0.1:8000")
DEVICE = os.environ.get("BRIO_ALSA", "plughw:CARD=BRIO")
RATE = 16000
FRAME_MS = 30
FRAME_BYTES = int(RATE * FRAME_MS / 1000) * 2  # 480 samples * 2 bytes = 960
SILENCE_FRAMES = int(0.8 * 1000 / FRAME_MS)     # ~0.8s of trailing silence ends an utterance
WAKE_PHRASES = ("hey edison", "hey, edison", "hey addison", "a edison", "hey edson", "hey eddison", "okay edison")


def post(path: str, payload: dict, timeout: float = 200.0):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f"{API}{path}", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except Exception as error:  # noqa: BLE001
        print("post error:", error, flush=True)
        return None


def ffmpeg_stream() -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "alsa", "-i", DEVICE,
        "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


def extract_command(text: str) -> str | None:
    low = text.lower()
    for phrase in WAKE_PHRASES:
        idx = low.find(phrase)
        if idx != -1:
            return text[idx + len(phrase):].strip(" ,.-!?")
    return None


def transcribe(model: WhisperModel, audio: bytes) -> str:
    samples = np.frombuffer(audio, dtype=np.int16).astype("float32") / 32768.0
    segments, _info = model.transcribe(samples, language="en", vad_filter=False)
    return " ".join(segment.text for segment in segments).strip()


def main() -> None:
    print("loading whisper base model...", flush=True)
    model = WhisperModel("base", device="cpu", compute_type="int8")
    vad = webrtcvad.Vad(2)
    proc = ffmpeg_stream()
    print(f"listening on {DEVICE}", flush=True)

    voiced: list[bytes] = []
    in_speech = False
    silence = 0
    pending_wake = False
    last_ping = 0.0

    while True:
        chunk = proc.stdout.read(FRAME_BYTES) if proc.stdout else b""
        if not chunk or len(chunk) < FRAME_BYTES:
            time.sleep(0.5)
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            proc = ffmpeg_stream()
            voiced, in_speech, silence = [], False, 0
            continue

        now = time.time()
        if now - last_ping > 20:
            post("/api/v1/voice/heartbeat", {}, timeout=10)
            last_ping = now

        try:
            speech = vad.is_speech(chunk, RATE)
        except Exception:  # noqa: BLE001
            speech = False

        if speech:
            voiced.append(chunk)
            in_speech = True
            silence = 0
            continue
        if not in_speech:
            continue

        voiced.append(chunk)
        silence += 1
        if silence <= SILENCE_FRAMES:
            continue

        # Utterance finished.
        audio = b"".join(voiced)
        voiced, in_speech, silence = [], False, 0
        if len(audio) < FRAME_BYTES * 10:
            continue
        text = transcribe(model, audio)
        if not text:
            continue
        print("heard:", text, flush=True)

        command = extract_command(text)
        if command is not None:
            if command:
                print("-> command:", command, flush=True)
                post("/api/v1/voice/brio", {"transcript": command, "source": "brio"})
                pending_wake = False
            else:
                pending_wake = True
                print("-> wake heard, awaiting command", flush=True)
        elif pending_wake:
            print("-> command (after wake):", text, flush=True)
            post("/api/v1/voice/brio", {"transcript": text, "source": "brio"})
            pending_wake = False


if __name__ == "__main__":
    main()
