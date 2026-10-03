"""Unit tests for the ASR normalizer and its integration in the Vosk path."""

import pytest
from backend.input.asr_normalizer import normalize_asr
from backend.input.voice import VoiceInput, VoiceParserError


@pytest.fixture
def voice():
    return VoiceInput(test_mode=True)


def test_exact_commands_unchanged():
    assert normalize_asr("switch on light") == "switch on light"
    assert normalize_asr("switch off fan") == "switch off fan"
    assert normalize_asr("switch on tv") == "switch on tv"
    assert normalize_asr("switch off ac") == "switch off ac"
    assert normalize_asr("switch on garden lights") == "switch on garden lights"


@pytest.mark.parametrize("raw,expected", [
    ("switch on t v", "switch on tv"),
    ("switch on lite", "switch on light"),
    ("switch on line", "switch on light"),
    ("switch on fun", "switch on fan"),
    ("switch on fann", "switch on fan"),
    ("switch on exha", "switch on exhaust"),
    ("switch on exh", "switch on exhaust"),
    ("switch on gither", "switch on garden lights"),
    ("switch on a c", "switch on ac"),
    ("switch on air conditioner", "switch on ac"),
])
def test_known_asr_substitutions(raw, expected):
    assert normalize_asr(raw) == expected


def test_single_letter_not_converted():
    # single 't' or 'v' must stay unchanged (unsafe to map)
    assert normalize_asr("t") == "t"
    assert normalize_asr("v") == "v"
    assert normalize_asr("switch on t") == "switch on t"
    assert normalize_asr("switch on v") == "switch on v"


def test_invalid_ambiguous_input_unchanged():
    # words not in map should pass through
    assert normalize_asr("switch on blah") == "switch on blah"
    assert normalize_asr("random words") == "random words"


def test_on_off_actions_preserved():
    assert normalize_asr("turn on light") == "turn on light"
    assert normalize_asr("turn off fan") == "turn off fan"
    assert normalize_asr("switch on tv") == "switch on tv"
    assert normalize_asr("switch off ac") == "switch off ac"


def test_multiple_variants_in_one_utterance():
    assert normalize_asr("switch on t v and switch off fun") == "switch on tv and switch off fan"


def test_case_insensitivity():
    assert normalize_asr("SWITCH ON LITE") == "switch on light"
    assert normalize_asr("Switch On T V") == "switch on tv"


# ----------------------------------------------------------------------
# Integration: Vosk parse_text pipeline (normalize_asr -> parse_command)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,appliance,action", [
    ("switch on light", "light", "on"),        # exact command unchanged
    ("switch off fan", "fan", "off"),          # exact command unchanged
    ("switch on t v", "tv", "on"),             # TV variant
    ("switch on lite", "light", "on"),         # light variant
    ("switch off line", "light", "off"),       # light variant, OFF action
    ("switch on fun", "fan", "on"),            # fan variant
    ("switch off exha", "exhaust", "off"),     # exhaust variant, OFF action
    ("switch on a c", "ac", "on"),             # AC variant
    ("switch off air conditioner", "ac", "off"),  # AC phrase variant
])
def test_voice_input_parses_normalized_vosk(voice, raw, appliance, action):
    cmd = voice.parse_text(raw)
    assert cmd.appliance == appliance
    assert cmd.action == action


def test_voice_input_rejects_unrelated_single_letter(voice):
    # single letters must NOT turn into a TV command
    with pytest.raises(VoiceParserError):
        voice.parse_text("switch on t")
    with pytest.raises(VoiceParserError):
        voice.parse_text("switch on v")


def test_voice_input_rejects_ambiguous_or_unrelated(voice):
    with pytest.raises(VoiceParserError):
        voice.parse_text("switch on blah")       # unknown appliance
    with pytest.raises(VoiceParserError):
        voice.parse_text("fan")                  # too short / no action
    with pytest.raises(VoiceParserError):
        voice.parse_text("that was fun")         # 'fun'->'fan' alone is not a command