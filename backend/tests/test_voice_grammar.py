"""Production-path tests for the constrained Vosk grammar integration.

Covers:
- grammar contents = only actually-supported vocabulary
- grammar wiring into the Vosk recognizer
- [unk] safety guard (never executed)
- empty/low-information rejection
- garbage/ambiguous rejection ("switch on t", "switch on v",
  "switch on blah", "that was fun", multi-command text)
- all supported appliances, ON/OFF actions
"""

import sys
import types

import pytest

from backend.input.voice import (
    COMMAND_GRAMMAR,
    VoiceInput,
    VoiceParserError,
    is_valid_command_transcript,
    parse_command,
    VALID_APPLIANCES,
)


# ---------------------------------------------------------------------
# Grammar contents
# ---------------------------------------------------------------------

def test_grammar_contains_supported_vocabulary():
    for phrase in ["switch on", "switch off", "turn on", "turn off",
                   "fan", "light", "tv", "ac", "plug", "geyser",
                   "exhaust", "garden lights", "[unk]"]:
        assert phrase in COMMAND_GRAMMAR


def test_grammar_excludes_unsupported_devices():
    # oven/bulb are NOT supported by the parser; they must not be added.
    for phrase in COMMAND_GRAMMAR:
        words = phrase.split()
        assert "oven" not in words
        assert "bulb" not in words


def test_grammar_multiword_phrases_present():
    assert "garden lights" in COMMAND_GRAMMAR
    assert "exhaust fan" in COMMAND_GRAMMAR
    assert "water heater" in COMMAND_GRAMMAR


# ---------------------------------------------------------------------
# [unk] safety guard
# ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    None,
    "",
    "   ",
    "[unk]",
    "[unk] fan",
    "switch on [unk]",
])
def test_invalid_transcripts_rejected(text):
    assert is_valid_command_transcript(text) is False


@pytest.mark.parametrize("text", [
    "switch on fan",
    "turn off light",
    "switch on garden lights",
])
def test_valid_transcripts_accepted(text):
    assert is_valid_command_transcript(text) is True


def test_unk_never_parses_through_production_path():
    vi = VoiceInput(test_mode=True)
    for text in ["[unk]", "[unk] fan", "switch on [unk] fan"]:
        # The production listen path filters these before parsing; and
        # even if one slipped through, the parser must not execute it.
        assert is_valid_command_transcript(text) is False


# ---------------------------------------------------------------------
# Valid commands: ON/OFF for every supported appliance
# ---------------------------------------------------------------------

@pytest.mark.parametrize("text,appliance,action", [
    ("switch on fan", "fan", "on"),
    ("switch off fan", "fan", "off"),
    ("switch on light", "light", "on"),
    ("turn off light", "light", "off"),
    ("switch on tv", "tv", "on"),
    ("turn off tv", "tv", "off"),
    ("switch on ac", "ac", "on"),
    ("turn off ac", "ac", "off"),
    ("switch on plug", "plug", "on"),
    ("turn off plug", "plug", "off"),
    ("switch on geyser", "geyser", "on"),
    ("turn off geyser", "geyser", "off"),
    ("switch on exhaust", "exhaust", "on"),
    ("turn off exhaust", "exhaust", "off"),
    ("switch on garden lights", "garden lights", "on"),
    ("turn off garden lights", "garden lights", "off"),
])
def test_all_appliances_on_off(text, appliance, action):
    vi = VoiceInput(test_mode=True)
    cmd = vi.parse_text(text)
    assert cmd.appliance == appliance
    assert cmd.action == action


def test_multiword_aliases_parse():
    vi = VoiceInput(test_mode=True)
    assert vi.parse_text("switch on exhaust fan").appliance == "exhaust"
    assert vi.parse_text("turn on water heater").appliance == "geyser"
    assert vi.parse_text("switch on television").appliance == "tv"


# ---------------------------------------------------------------------
# Garbage / ambiguous input must be rejected (grammar must not
# bypass parser safety checks)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "switch on t",
    "switch on v",
    "switch on blah",
    "that was fun",
    "switch on",            # action with no appliance
    "fan",                  # appliance with no action
    "hello world",
])
def test_garbage_rejected(text):
    vi = VoiceInput(test_mode=True)
    with pytest.raises(VoiceParserError):
        vi.parse_text(text)


@pytest.mark.parametrize("text", [
    "switch on fan switch off light",       # conflicting multi-command
    "switch on fan and switch off tv",      # multiple devices/actions
])
def test_ambiguous_multicommand_rejected(text):
    vi = VoiceInput(test_mode=True)
    with pytest.raises(VoiceParserError):
        vi.parse_text(text)


# ---------------------------------------------------------------------
# Grammar wiring into the recognizer
# ---------------------------------------------------------------------

def test_grammar_passed_to_vosk_recognizer(monkeypatch):
    """VoiceInput must construct KaldiRecognizer with the constrained
    grammar when config.vosk.use_grammar is enabled."""
    captured = {}

    class FakeKaldiRecognizer:
        def __init__(self, model, sample_rate, grammar=None):
            captured["grammar"] = grammar

    class FakeModel:
        def __init__(self, path):
            pass

    fake_vosk = types.ModuleType("vosk")
    fake_vosk.Model = FakeModel
    fake_vosk.KaldiRecognizer = FakeKaldiRecognizer
    monkeypatch.setitem(sys.modules, "vosk", fake_vosk)

    # Mock filesystem check
    monkeypatch.setattr("os.path.exists", lambda p: True)

    from backend.config import config
    monkeypatch.setattr(config.vosk, "use_grammar", True)
    monkeypatch.setattr(config.vosk, "use_vocabulary", False)

    # Use test_mode=True to skip hardware init, then call _init_vosk directly
    vi = VoiceInput(test_mode=True)
    vi._init_vosk("dummy-model-path-does-not-matter", 16000)

    import json
    assert json.loads(captured["grammar"]) == COMMAND_GRAMMAR


def test_grammar_can_be_disabled(monkeypatch):
    """use_grammar=False keeps the previous unrestricted recognizer."""
    captured = {}

    class FakeKaldiRecognizer:
        def __init__(self, model, sample_rate, grammar=None):
            captured["grammar"] = grammar

    class FakeModel:
        def __init__(self, path):
            pass

    fake_vosk = types.ModuleType("vosk")
    fake_vosk.Model = FakeModel
    fake_vosk.KaldiRecognizer = FakeKaldiRecognizer
    monkeypatch.setitem(sys.modules, "vosk", fake_vosk)

    monkeypatch.setattr("os.path.exists", lambda p: True)

    from backend.config import config
    monkeypatch.setattr(config.vosk, "use_grammar", False)
    monkeypatch.setattr(config.vosk, "use_vocabulary", False)

    vi = VoiceInput(test_mode=True)
    vi._init_vosk("dummy-model-path-does-not-matter", 16000)

    assert captured["grammar"] is None


def test_listen_for_command_filters_unk(monkeypatch):
    """Recognized results containing [unk] must not be returned."""
    # bypass hardware init for the class
    monkeypatch.setattr(VoiceInput, "_init_porcupine", lambda *a, **k: None)
    monkeypatch.setattr(VoiceInput, "_init_audio", lambda *a, **k: None)
    monkeypatch.setattr(VoiceInput, "_init_vosk", lambda *a, **k: None)

    vi = VoiceInput(test_mode=False)

    results = iter([
        '{"text": "[unk]"}',
        '{"text": "switch on [unk]"}',
        '{"text": "switch on fan"}',
    ])

    class FakeRecognizer:
        def AcceptWaveform(self, data):
            return True

        def Result(self):
            return next(results)

    vi.recognizer = FakeRecognizer()
    vi.audio_stream = types.SimpleNamespace(
        read=lambda *a, **k: b"\x00" * 8000)

    assert vi.listen_for_command(timeout_seconds=10) == "switch on fan"


def test_listen_for_command_returns_none_when_only_garbage(monkeypatch):
    monkeypatch.setattr(VoiceInput, "_init_porcupine", lambda *a, **k: None)
    monkeypatch.setattr(VoiceInput, "_init_audio", lambda *a, **k: None)
    monkeypatch.setattr(VoiceInput, "_init_vosk", lambda *a, **k: None)

    vi = VoiceInput(test_mode=False)

    class FakeRecognizer:
        def AcceptWaveform(self, data):
            return True

        def Result(self):
            return '{"text": "[unk]"}'

    vi.recognizer = FakeRecognizer()
    vi.audio_stream = types.SimpleNamespace(
        read=lambda *a, **k: b"\x00" * 8000)

    assert vi.listen_for_command(timeout_seconds=0.2) is None
