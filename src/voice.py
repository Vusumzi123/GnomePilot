import io
import subprocess
import wave
from pathlib import Path

import piper


VOICE_MODEL_PATH = Path(__file__).parent.parent / "voices" / "en_US-lessac-medium.onnx"
VOICE_CONFIG_PATH = Path(__file__).parent.parent / "voices" / "en_US-lessac-medium.onnx.json"

_voice = None


def _get_voice() -> piper.PiperVoice:
    """Lazy-load the Piper TTS voice model (singleton)."""
    global _voice
    if _voice is None:
        _voice = piper.PiperVoice.load(str(VOICE_MODEL_PATH), str(VOICE_CONFIG_PATH))
    return _voice


def speak(text: str) -> None:
    """Synthesize text to speech via Piper and play through pipewire (pw-play)."""
    voice = _get_voice()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf)
    wav_data = buf.getvalue()
    subprocess.run(["pw-play", "-"], input=wav_data, capture_output=True)


def listen() -> str | None:
    """Stub for Speech-to-Text input.

    Phase 1: Returns None (not yet implemented). The CLI will fall back to text input.
    """
    return None
