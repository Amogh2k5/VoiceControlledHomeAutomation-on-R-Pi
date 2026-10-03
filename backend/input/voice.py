from dataclasses import dataclass
import re
import json
from typing import Optional, List, Dict, Tuple
from backend.config import config
from .models import InputCommand
from .asr_normalizer import normalize_asr


class VoiceParserError(Exception):
    def __init__(self, message: str, raw_text: str):
        self.raw_text = raw_text
        super().__init__(message)


# Known appliance vocabulary (canonical names)
KNOWN_APPLIANCES = [
    "light",
    "fan",
    "tv",
    "ac",
    "plug",
    "geyser",
    "exhaust",
    "garden lights",
]

# Known action vocabulary
KNOWN_ACTIONS = [
    "switch",
    "on",
    "off",
]

# Mapping from aliases/transcription variants to canonical appliance names
APPLIANCE_ALIASES = {
    "light": "light",
    "lights": "light",
    "lite": "light",
    "line": "light",
    "like": "light",
    "fan": "fan",
    "fun": "fan",
    "feb": "fan",
    "fann": "fan",
    "tv": "tv",
    "t v": "tv",
    "television": "tv",
    "ac": "ac",
    "a c": "ac",
    "air conditioner": "ac",
    "airconditioner": "ac",
    "plug": "plug",
    "outlet": "plug",
    "geyser": "geyser",
    "water heater": "geyser",
    "exhaust": "exhaust",
    "exhaust fan": "exhaust",
    "garden lights": "garden lights",
    "garden light": "garden lights",
    "outside light": "garden lights",
    "outdoor light": "garden lights",
}

VALID_APPLIANCES = set(APPLIANCE_ALIASES.values())

ACTION_ALIASES = {
    "switch on": "on",
    "turn on": "on",
    "switch off": "off",
    "turn off": "off",
    "on": "on",
    "off": "off",
}

VALID_ACTIONS = set(ACTION_ALIASES.values())

# ---------------------------------------------------------------------
# Constrained Vosk grammar (proven by the 209-segment benchmark experiment
# in backend/tests/voice_benchmark/vosk_grammar_experiment.py).
#
# Contains ONLY vocabulary actually supported by this parser. Note that
# "oven"/"bulb" are deliberately absent: they are not supported devices.
# ---------------------------------------------------------------------
COMMAND_GRAMMAR = [
    # action phrases (multi-word)
    "switch on",
    "switch off",
    "turn on",
    "turn off",
    # bare action words
    "on",
    "off",
    # single-word appliances
    "light",
    "lights",
    "fan",
    "tv",
    "television",
    "ac",
    "plug",
    "geyser",
    "exhaust",
    # multi-word appliance aliases supported by the parser
    "a c",
    "t v",
    "garden lights",
    "garden light",
    "exhaust fan",
    "water heater",
    "air conditioner",
    # unknown-token fallback so out-of-grammar audio still decodes
    "[unk]",
]

GRAMMAR_JSON = json.dumps(COMMAND_GRAMMAR)


def is_valid_command_transcript(text: Optional[str]) -> bool:
    """
    Safety guard for transcripts coming out of the constrained Vosk
    recognizer. Rejects empty/low-information text and anything where the
    recognizer fell back to the grammar's [unk] token. [unk] means the
    audio did not match any supported command vocabulary and must NEVER
    be executed as a command.
    """
    if not text:
        return False
    text = text.strip()
    if not text:
        return False
    if "[unk]" in text:
        return False
    return True

DELAY_PATTERN = re.compile(r"\b(?:in|after)\s+(\d+)\s*(?:min|mins|minute|minutes)\b", re.IGNORECASE)


# ===== Phonetic/Fuzzy Normalization Layer =====

# Known vocabulary for fuzzy matching (lowercase)
_APPLIANCE_VOCAB = KNOWN_APPLIANCES.copy()
_ACTION_VOCAB = KNOWN_ACTIONS.copy()

# Configuration for fuzzy matching
_FUZZY_APPLIANCE_THRESHOLD = 0.65
_FUZZY_ACTION_THRESHOLD = 0.75
_FUZZY_MAX_EDIT_DISTANCE = 3
_MIN_MARGIN = 0.12  # Minimum margin between best and second-best match


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _similarity_ratio(s1: str, s2: str) -> float:
    """Compute similarity ratio (0-1) based on Levenshtein distance."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    dist = _levenshtein_distance(s1, s2)
    return 1.0 - (dist / max_len)


def _normalize_phonetic(word: str) -> str:
    """Normalize word using phonetic rules that handle common speech recognition errors."""
    word = word.lower().strip()
    # Remove non-alphabetic
    word = re.sub(r'[^a-z]', '', word)
    if not word:
        return ""
    
    # Vowel canonicalization for common confusions
    # Only collapse similar vowels, keep some distinction
    # e <-> i confusion common, o <-> u confusion common
    # But keep a distinct from e/i/o/u
    vowel_map = {
        'a': 'a',
        'e': 'e', 'i': 'e',  # e <-> i confusion
        'o': 'o', 'u': 'o',  # o <-> u confusion
        # Keep 'a' distinct
    }
    word = ''.join(vowel_map.get(c, c) for c in word)
    
    # Consonant normalization
    result = []
    i = 0
    while i < len(word):
        if i + 1 < len(word) and word[i:i+2] in {'th', 'ng', 'sh', 'ch', 'ph', 'kh', 'gh'}:
            result.append({'th': 't', 'ng': 'n', 'sh': 'sh', 'ch': 'ch', 'ph': 'f', 'kh': 'k', 'gh': 'g'}[word[i:i+2]])
            i += 2
        elif word[i] in {'b', 'p', 'f', 'v', 'c', 'k', 'g', 'j', 'd', 't', 'l', 'r', 'm', 'n', 's', 'z', 'w', 'y', 'h'}:
            result.append({'b': 'b', 'p': 'b', 'f': 'f', 'v': 'f', 'c': 'k', 'k': 'k', 'g': 'g', 'j': 'j',
                          'd': 'd', 't': 't', 'l': 'l', 'r': 'r', 'm': 'm', 'n': 'n', 's': 's', 'z': 's',
                          'w': 'w', 'y': 'y', 'h': 'h'}[word[i]])
            i += 1
        else:
            result.append(word[i])
            i += 1
    
    # Remove consecutive duplicates
    simplified = []
    for c in result:
        if not simplified or simplified[-1] != c:
            simplified.append(c)
    return ''.join(simplified)


def _vowel_normalize(word: str) -> str:
    """Canonicalize vowels to handle common vowel confusions."""
    vowel_map = {
        'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u',
        # Common vowel confusions: canonicalize to reduce false mismatches
        # Don't be too aggressive - keep some distinction
    }
    return ''.join(vowel_map.get(c, c) for c in word)


def _appliance_similarity(s1: str, s2: str) -> float:
    """Compute appliance similarity using multiple strategies."""
    if not s1 or not s2:
        return 0.0
    
    # Strategy 1: Exact match on original
    if s1.lower() == s2.lower():
        return 1.0
    
    # Strategy 2: Phonetic normalized similarity
    s1_phon = _normalize_phonetic(s1)
    s2_phon = _normalize_phonetic(s2)
    phon_score = _similarity_ratio(s1_phon, s2_phon) if s1_phon and s2_phon else 0.0
    
    # Strategy 3: Edit distance on original (for short words)
    orig_score = _similarity_ratio(s1.lower(), s2.lower())
    
    # Strategy 3: Phonetic with vowel normalization (for vowel confusions)
    s1_vowel = _normalize_phonetic(s1)
    s2_vowel = _normalize_phonetic(s2)
    vowel_score = _similarity_ratio(s1_vowel, s2_vowel) if s1_vowel and s2_vowel else 0.0
    
    # Strategy 4: Consonant skeleton (remove vowels, compare consonants)
    s1_cons = ''.join(c for c in _normalize_phonetic(s1) if c not in 'aeiou')
    s2_cons = ''.join(c for c in _normalize_phonetic(s2) if c not in 'aeiou')
    cons_score = _similarity_ratio(s1_cons, s2_cons) if s1_cons and s2_cons else 0.0
    
    # Strategy 5: Start-type penalty (vowel vs consonant start)
    start_penalty = 1.0
    if s1_phon and s2_phon:
        s1_starts_vowel = s1_phon[0] in 'aeiou'
        s2_starts_vowel = s2_phon[0] in 'aeiou'
        if s1_starts_vowel != s2_starts_vowel:
            start_penalty = 0.75  # Penalize different starting types
    
    # Take the best score across strategies
    best_score = max(phon_score, orig_score, vowel_score, cons_score)
    
    # Apply start-type penalty
    return best_score * start_penalty


def _find_best_appliance_match(appliance_text: str) -> Tuple[Optional[str], float, float]:
    """
    Find the best matching appliance for the given text.
    Returns (best_match, best_score, margin) where margin is the gap to second-best.
    Returns (None, 0, 0) if no good match.
    """
    if not appliance_text or not appliance_text.strip():
        return (None, 0.0, 0.0)
    
    candidates = []
    for appliance in KNOWN_APPLIANCES:
        score = _appliance_similarity(appliance_text, appliance)
        candidates.append((appliance, score))
    
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    if not candidates or candidates[0][1] < 0.65:
        return (None, 0.0, 0.0)
    
    best_match, best_score = candidates[0]
    second_best_score = candidates[1][1] if len(candidates) > 1 else 0.0
    margin = best_score - second_best_score
    
    return (best_match, best_score, margin)


def _fuzzy_match_action(word: str) -> Optional[str]:
    """Fuzzy match action word against known actions."""
    if not word:
        return None
    word_norm = re.sub(r'[^a-z]', '', word.lower())
    if not word_norm:
        return None
    
    best_match = None
    best_score = 0.0
    for action in KNOWN_ACTIONS:
        action_norm = re.sub(r'[^a-z]', '', action.lower())
        if not action_norm:
            continue
        score = _similarity_ratio(word_norm, action_norm)
        if score > best_score:
            best_score = score
            best_match = action
    
    if best_score >= 0.80:
        return best_match
    return None


def normalize_transcription(text: str) -> str:
    """Normalize Vosk transcription quirks before parsing."""
    text = text.lower().strip()
    # Normalize "t v" -> "tv"
    text = re.sub(r"\bt\s+v\b", "tv", text)
    # Normalize "t.v." -> "tv"
    text = text.replace("t.v.", "tv")
    # Normalize extra whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_appliance_phrase(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """
    Extract appliance phrase from command text using command-aware parsing.
    Returns (action, appliance_phrase, delay_minutes, remaining_text_after_appliance)
    """
    text = text.lower().strip()
    
    # Extract delay first
    delay_minutes = None
    delay_match = DELAY_PATTERN.search(text)
    if delay_match:
        try:
            delay_minutes = int(delay_match.group(1))
        except ValueError:
            pass
    text_no_delay = DELAY_PATTERN.sub("", text).strip()
    
    # Try to match command structure: action_phrase + appliance
    # Priority: switch on/off, turn on/off
    action = None
    appliance_phrase = None
    
    # Check for "switch on/off" first (preferred grammar)
    for action_phrase in ["switch on", "switch off", "turn on", "turn off"]:
        if text_no_delay.startswith(action_phrase):
            # Require a space after the action phrase to separate from appliance
            if len(text_no_delay) > len(action_phrase) and text_no_delay[len(action_phrase)] == ' ':
                action = "on" if "on" in action_phrase else "off"
                appliance_phrase = text_no_delay[len(action_phrase):].strip()
                break
            else:
                # No space after action phrase - this could be a false match like "switch online"
                continue
    
    # Check for "turn the X on/off"
    if appliance_phrase is None and text_no_delay.startswith("turn the "):
        rest = text_no_delay[9:].strip()  # len("turn the ") = 9
        words = rest.split()
        if len(words) >= 2 and words[-1] in ["on", "off"]:
            action = words[-1]
            appliance_phrase = " ".join(words[:-1])
    
    # Fallback: ends with " on" or " off"
    if appliance_phrase is None:
        if text_no_delay.endswith(" on"):
            action = "on"
            appliance_phrase = text_no_delay[:-3].strip()
        elif text_no_delay.endswith(" off"):
            action = "off"
            appliance_phrase = text_no_delay[:-4].strip()
    
    # Remove "the " prefix if present
    if appliance_phrase and appliance_phrase.startswith("the "):
        appliance_phrase = appliance_phrase[4:].strip()
    
    return action, appliance_phrase, delay_minutes, ""


def _normalize_appliance_phrase(appliance_phrase: str) -> str:
    """
    Normalize appliance phrase using alias lookup first, then fuzzy matching.
    Returns the canonical appliance name or None if no good match.
    """
    if not appliance_phrase:
        return None
    
    phrase = appliance_phrase.lower().strip()
    
    # Direct alias lookup first (exact match)
    if phrase in APPLIANCE_ALIASES:
        return APPLIANCE_ALIASES[phrase]
    
    # Try fuzzy matching against known appliances
    match, score, margin = _find_best_appliance_match(phrase)
    
    # Require minimum score and clear margin
    if match and score >= 0.68 and margin >= 0.12:
        return match
    
    return None


def normalize_appliance(text: str) -> Optional[str]:
    text = text.lower().strip()
    return APPLIANCE_ALIASES.get(text)


def normalize_action(text: str) -> Optional[str]:
    text = text.lower().strip()
    return ACTION_ALIASES.get(text)


def extract_delay(text: str) -> Optional[int]:
    match = DELAY_PATTERN.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def parse_command(text: str) -> InputCommand:
    if not text or not text.strip():
        raise VoiceParserError("Empty command", text)

    original_text = text.strip()
    text_lower = original_text.lower()

    delay_minutes = extract_delay(text_lower)
    if delay_minutes is not None and delay_minutes < 0:
        raise VoiceParserError(f"Invalid delay: {delay_minutes} minutes", original_text)

    text_no_delay = DELAY_PATTERN.sub("", text_lower).strip()

    # Normalize transcription quirks (e.g., "t v" -> "tv")
    text_no_delay = normalize_transcription(text_no_delay)

    words = text_no_delay.split()
    if len(words) < 2:
        raise VoiceParserError("Command too short", original_text)

    action = None
    appliance = None

    # Primary: "switch on/off" as preferred grammar
    for action_phrase in ["switch on", "switch off", "turn on", "turn off", "turn the", "on", "off"]:
        if text_no_delay.startswith(action_phrase):
            # Require a space after the action phrase to separate from appliance
            if len(text_no_delay) > len(action_phrase) and text_no_delay[len(action_phrase)] == ' ':
                if action_phrase == "turn the":
                    words_after = text_no_delay[len(action_phrase):].strip().split()
                    if len(words_after) >= 2 and words_after[-1] in ["on", "off"]:
                        action = normalize_action(words_after[-1])
                        appliance = normalize_appliance(" ".join(words_after[:-1]))
                    break
                action = normalize_action(action_phrase)
                remaining = text_no_delay[len(action_phrase):].strip()
                appliance = normalize_appliance(remaining)
                break
            else:
                # No space after action phrase - this could be a false match like "switch online"
                continue

    if action is None:
        for action_word in ["on", "off"]:
            if text_no_delay.endswith(f" {action_word}") or text_no_delay == action_word:
                action = normalize_action(action_word)
                remaining = text_no_delay[:-len(action_word)].strip()
                remaining = remaining.replace("the ", "").strip()
                appliance = normalize_appliance(remaining)
                break

    if appliance is None:
        # Use word-boundary matching to avoid substring matches like "line" in "online"
        words = set(text_no_delay.split())
        for alias, normalized in APPLIANCE_ALIASES.items():
            # Check if alias is a complete word in the text
            if alias in words or (len(alias.split()) > 1 and alias in text_no_delay):
                appliance = normalized
                # Remove the matched alias from text for action parsing
                # Use word-boundary replacement
                text_no_delay = re.sub(rf'\b{re.escape(alias)}\b', '', text_no_delay).strip()
                action = normalize_action(text_no_delay)
                break

    if appliance is None or action is None:
        raise VoiceParserError(f"Could not parse appliance/action from: {original_text}", original_text)

    if appliance not in VALID_APPLIANCES:
        raise VoiceParserError(f"Unknown appliance: {appliance}", original_text)

    return InputCommand(appliance=appliance, action=action, delay_minutes=delay_minutes)


class VoiceInput:
    def __init__(
        self,
        porcupine_access_key: str = "",
        vosk_model_path: str = "",
        audio_device_index: Optional[int] = None,
        sample_rate: int = 16000,
        frame_length: int = 512,
        test_mode: bool = False,
    ):
        self.test_mode = test_mode
        self.porcupine = None
        self.vosk_model = None
        self.recognizer = None
        self.audio_stream = None
        self.pyaudio = None

        if not test_mode:
            self._init_porcupine(porcupine_access_key or config.porcupine.access_key)
            self._init_vosk(vosk_model_path or config.vosk.model_path, sample_rate)
            self._init_audio(audio_device_index, sample_rate, frame_length)

    def _init_porcupine(self, access_key: str):
        try:
            import pvporcupine
            if not access_key:
                raise ValueError("Porcupine access key not provided")
            keyword_paths = config.porcupine.keyword_paths
            sensitivities = config.porcupine.sensitivities
            self.porcupine = pvporcupine.create(
                access_key=access_key,
                keyword_paths=keyword_paths,
                sensitivities=sensitivities,
            )
        except ImportError:
            raise RuntimeError("pvporcupine not installed. Run: pip install pvporcupine")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Porcupine: {e}")

    def _init_vosk(self, model_path: str, sample_rate: int):
        try:
            from vosk import Model, KaldiRecognizer
            import os
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Vosk model not found at: {model_path}")
            self.vosk_model = Model(model_path)
            if config.vosk.use_grammar:
                # Constrained grammar (benchmark-proven): restricts decoding
                # to the supported command vocabulary. [unk] fallback is
                # filtered out by is_valid_command_transcript().
                self.recognizer = KaldiRecognizer(
                    self.vosk_model, sample_rate, GRAMMAR_JSON
                )
            else:
                self.recognizer = KaldiRecognizer(self.vosk_model, sample_rate)

            # Legacy vocabulary-file override (default: False)
            if config.vosk.use_vocabulary:
                vocab_path = config.vosk.vocabulary_file
                if os.path.exists(vocab_path):
                    with open(vocab_path, 'r') as f:
                        vocabulary = json.load(f)
                    self.recognizer.SetGrammar(json.dumps(vocabulary))
                    print(f"Loaded restricted vocabulary from {vocab_path}")
                else:
                    print(f"Warning: Vocabulary file not found at {vocab_path}")
        except ImportError:
            raise RuntimeError("vosk not installed. Run: pip install vosk")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Vosk: {e}")

    def _init_audio(self, device_index: Optional[int], sample_rate: int, frame_length: int):
        try:
            import pyaudio
            self.pyaudio = pyaudio.PyAudio()
            self.audio_stream = self.pyaudio.open(
                rate=sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=frame_length,
            )
        except ImportError:
            raise RuntimeError("pyaudio not installed. Run: pip install pyaudio")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize audio: {e}")

    def listen_for_wake_word(self) -> bool:
        if self.test_mode:
            return True

        import struct
        while True:
            pcm = self.audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
            keyword_index = self.porcupine.process(pcm)
            if keyword_index >= 0:
                return True

    def listen_for_command(self, timeout_seconds: float = 5.0) -> Optional[str]:
        if self.test_mode:
            return None

        import json
        import time

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            data = self.audio_stream.read(4000, exception_on_overflow=False)
            if self.recognizer.AcceptWaveform(data):
                result = json.loads(self.recognizer.Result())
                text = result.get("text", "").strip()
                # Safety guard: never hand empty/low-information/[unk]
                # transcripts downstream; keep listening for real speech.
                if is_valid_command_transcript(text):
                    return text
        return None

    def parse_text(self, text: str) -> InputCommand:
        normalized = normalize_asr(text)
        return parse_command(normalized)

    def listen(self) -> InputCommand:
        if self.test_mode:
            raise RuntimeError("Cannot listen in test_mode. Use parse_text() directly.")

        self.listen_for_wake_word()
        text = self.listen_for_command()
        if not text:
            raise VoiceParserError("No speech recognized", "")
        return self.parse_text(text)

    def close(self):
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.pyaudio:
            self.pyaudio.terminate()
        if self.porcupine:
            self.porcupine.delete()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()