"""Configuration constants for recass audio recording and transcription."""

import os

# Audio Processing Configuration
WHISPER_SAMPLE_RATE = 16000  # 16kHz ist obligatorisch für Whisper
CHUNK_SECONDS = 15.0  # Wie viele Sekunden Audio pro Chunk an Whisper gesendet werden
MIX_SAMPLE_RATE = 48000  # Abtastrate für die gemischte Audiodatei

# --- Diarization Configuration ---
# You need a Hugging Face Access Token to use pyannote.audio.
# 1. Visit hf.co/pyannote/speaker-diarization-3.1 and hf.co/pyannote/segmentation-3.0
#    and accept the user conditions.
# 2. Visit hf.co/settings/tokens to create an access token.
# 3. Set it as an environment variable: export HUGGING_FACE_TOKEN="your_token_here"
#    Or create a .env file with HUGGING_FACE_TOKEN="your_token_here"
HF_TOKEN = os.environ.get("HUGGING_FACE_TOKEN")

# --- User settings persistence ---
import json
from pathlib import Path

# Use XDG config dir if available, otherwise ~/.config/recass
_XDG = os.environ.get('XDG_CONFIG_HOME')
if _XDG:
	_CONFIG_DIR = Path(_XDG) / 'recass'
else:
	_CONFIG_DIR = Path.home() / '.config' / 'recass'

_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_SETTINGS_FILE = _CONFIG_DIR / 'user_settings.json'


def load_user_settings():
	"""Load persisted user settings from disk. Returns a dict."""
	try:
		if _SETTINGS_FILE.exists():
			with open(_SETTINGS_FILE, 'r', encoding='utf-8') as f:
				return json.load(f)
	except Exception:
		pass
	# sensible defaults
	return {
		'screenshot_target': 'all',
		'screenshot_disabled': False,
		# default transcription language (use 'auto' to let Whisper detect)
		'transcription_language': 'en',
		# whether AI analysis/recording of meetings is enabled
		'ai_record_meeting': True,
		# default Ollama URL for chat/analysis
		'ollama_url': 'http://localhost:11434',
		# stored Hugging Face token (falls back to env var set at module import)
		'hf_token': HF_TOKEN,
	}


def save_user_settings(settings: dict):
	"""Persist user settings to disk (best-effort)."""
	try:
		with open(_SETTINGS_FILE, 'w', encoding='utf-8') as f:
			json.dump(settings, f, indent=2)
		return True
	except Exception:
		return False
