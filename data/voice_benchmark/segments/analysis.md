# Voice Benchmark Analysis (AIML_training.wav)

**Generated:** 2026‑09‑04  
**Segments:** 209 (average 2.2 s, max 7.3 s)  
**Models evaluated:** Vosk (offline Kaldi) vs. Sherpa‑ONNX (streaming Zipformer)  
**Parser:** shared `parse_command` (no modifications)

---

## 1. High‑level numbers
| Metric | Value |
|--------|-------|
| Total segments | 209 |
| Vosk non‑empty transcriptions | 173 |
| Sherpa non‑empty transcriptions | 44 |
| Vosk parse‑success | **3** |
| Sherpa parse‑success | **1** |
| Both parse‑success | 0 |
| Transcription agreement (exact string match) | 35 / 209 (≈ 17 %) |
| Segments where they disagree | 174 |

> **Interpretation:** Both models produce a lot of noise on this mixed‑speaker recording; only a handful of utterances are clean enough for the parser to succeed.

---

## 2. Token frequency overview
### Vosk (top 30 tokens)
| Token | Count |
|-------|-------|
| on | 120 |
| switch | 106 |
| off | 76 |
| of | 40 |
| and | 21 |
| light | 16 |
| such | 16 |
| exhaust | 16 |
| a | 14 |
| or | 13 |
| … | … |

### Sherpa‑ONNX (top 30 tokens)
| Token | Count |
|-------|-------|
| on | 31 |
| which | 17 |
| of | 10 |
| 's | 8 |
| light | 6 |
| off | 5 |
| switch | 4 |
| garden | 4 |
| … | … |

*Vosk emits many more “function” words (on/off/switch) while Sherpa leans heavily on the filler “which” and possessive fragments.*

---

## 3. Device‑keyword coverage
| Device | Vosk segments containing keyword | Sherpa segments containing keyword |
|--------|--------------------------------|-----------------------------------|
| light / lights | 19 / 6 | 7 / 1 |
| fan | 9 | 2 |
| exhaust | 11 | 2 |
| garden | 2 | 3 |
| kitchen | 3 | 1 |
| bedroom | 5 | 2 |
| water / pump | 2 / 3 | 0 / 0 |
| guard / hall / room | 4 / 2 / 5 | 1 / 1 / 3 |
| ac / plug / geyser | 1 / 1 / 1 | 1 / 0 / 0 |

*Vosk recognises the target appliance vocabulary far more often, but still rarely produces a complete, parsable command.*

---

## 4. Action‑keyword coverage
| Action | Vosk | Sherpa |
|--------|------|--------|
| on | 96 | 25 |
| off | 67 | 6 |
| switch | 70 | 4 |
| turn | 2 | 1 |

*Vosk frequently emits “switch on/off” patterns; Sherpa rarely produces a clear action word.*

---

## 5. Common vs. unique tokens
* **Common tokens (both models)** – `on`, `switch`, `off`, `which`, `of`, `a`, `light`, `fan`, `exhaust` – appear in both outputs, indicating they capture the same acoustic cues.
* **Unique to Vosk** – huge surplus of `on`, `switch`, `off`, `such`, `or`, `right`, `the`, `fun`, `night`, `sean`.  Many are recogniser hallucinations or speaker‑specific artefacts.
* **Unique to Sherpa** – `'s`, `which`, `garden`, `her`, `rich`, `tch`, `o'eren`, `oft`, `gither`, `ulate`.  These look like phoneme‑level confusions typical of the Zipformer streaming decoder.

---

## 6. Parse‑failure patterns (representative examples)

### Vosk
| Segment | Transcription | Parser error |
|---------|---------------|--------------|
| segment_001.wav | `sean` | Command too short |
| segment_006.wav | `switch off` | Could not parse appliance/action |
| segment_009.wav | `switch on overnight switch off over` | Could not parse appliance/action |
| segment_010.wav | `search on switch off burma` | Could not parse appliance/action |
| segment_013.wav | `rich or light switch off night` | Could not parse appliance/action |
| segment_018.wav | `sean over switch over to switch on bus` | Could not parse appliance/action |
| segment_024.wav | `switch on the switch off switch on a c` | Could not parse appliance/action |
| segment_068.wav | `switch on blog switch off blog switch on engage us switch` | Could not parse appliance/action |
| segment_144.wav | `switch on kitchen light switch off good sunlight` | Could not parse appliance/action |

*Common theme:* Vosk often produces **action words** (`switch on/off`) but the appliance noun is missing, garbled, or merged with filler (`search`, `overnight`, `blog`). Short utterances (< 1 s) are rejected as “Command too short”.

### Sherpa‑ONNX
| Segment | Transcription | Parser error |
|---------|---------------|--------------|
| segment_009.wav | `FOR` | Command too short |
| segment_010.wav | `T OFF` | Could not parse appliance/action |
| segment_024.wav | `'S RICH ON ACC` | Could not parse appliance/action |
| segment_057.wav | `T OF O'EREN WHICH UNB` | Could not parse appliance/action |
| segment_068.wav | `UE SEARCH OF ROGUE SWITCH ON GITHERS WHICH` | Could not parse appliance/action |
| segment_069.wav | `'D VIRTUAL EXHA` | Could not parse appliance/action |
| segment_074.wav | `IN WHICH OTHELLEC SWITCH ON DE WAYS WHICH` | Could not parse appliance/action |
| segment_076.wav | `'S WHICH` | Could not parse appliance/action |
| segment_080.wav | `T ON LECO'S WHICH OFT LOVES WHICH ON GITHER FIT OF THITHER` | Could not parse appliance/action |
| segment_144.wav | `ON KITCHEN LIGHTS WHICH OFF KITCHEN LIGHT` | Could not parse appliance/action |

*Common theme:* Sherpa outputs are **highly fragmented**, often consisting of sub‑word pieces (`'S`, `T`, `OF`, `WHICH`) and rarely produce a full appliance name. The parser therefore receives unusable strings.

---

## 7. Recurring substitution / confusion patterns
| Target | Vosk variants observed | Sherpa variants observed |
|--------|------------------------|--------------------------|
| **TV** | `t v`, `tv`, `t`, `v` | `t`, `v`, `tv` |
| **Light / Lights** | `light`, `lights`, `lite`, `line` | `light`, `lights`, `late` |
| **Fan** | `fan`, `fun`, `fann` | `fan`, `fann` |
| **Exhaust** | `exhaust`, `exhaust fan`, `exhausted` | `exhaust`, `exha`, `exh` |
| **AC** | `a c`, `ac` | `a c` |
| **Guard / Garden** | `guard`, `garden`, `garage` | `garden`, `gither`, `garden lights` |
| **Kitchen** | `kitchen` | `kitchen`, `kitch` |

Both models confuse acoustically similar words; Vosk tends to keep the whole word, Sherpa often breaks it into sub‑word tokens.

---

## 8. What the numbers tell us
1. **Segmentation is now at command granularity** (≈ 2 s avg, no > 10 s segments).  
2. **Vosk produces far more candidate tokens** (especially actions) but still rarely yields a complete *appliance + action* pair.  
3. **Sherpa‑ONNX is far less verbose**; its output is dominated by the filler token “which” and broken fragments, making parsing almost impossible.  
3. **Parser is not the bottleneck** – it succeeds on the few clean utterances (3 Vosk, 1 Sherpa). The failure is upstream ASR quality on this noisy, multi‑speaker recording.  
4. **No ground‑truth labels** exist; we can only quantify relative behaviour.

---

## 9. Recommended next engineering steps (data‑driven)
| Step | Rationale |
|------|-----------|
| **Collect a small labelled set** (≈ 30‑50 clean commands) from the same microphone to compute WER per model. | Needed to decide whether to fine‑tune, switch models, or improve front‑end. |
| **Add a lightweight VAD front‑end** (e.g., Silero) before ASR to drop non‑speech frames; current energy VAD still lets many short noisy fragments through. | Reduces “Command too short” and hallucinated filler. |
| **Domain‑adapt Vosk language model** with the known appliance/action vocabulary (already supported via `SetGrammar`). | Vosk already emits the right action words; a constrained grammar should raise parse‑success dramatically. |
| **Investigate Sherpa‑ONNX decoder settings** – increase `rule1_min_trailing_silence`, enable external LM, or try the larger 60 M Zipformer. | Sherpa currently emits sub‑word soup; better endpointing / LM may produce full words. |
| **Speaker‑adaptation / noise‑robust front‑end** (spectral subtraction, RNNoise) – the recording contains background chatter and music. | Both models degrade heavily in non‑clean speech. |
| **Ensemble / voting** – run both models and accept a command only when both agree on appliance+action. | Current agreement is only 17 %; an ensemble would be very conservative but could be useful for safety‑critical actions. |

---

## 10. Files produced
* `analysis.json` – machine‑readable summary (counts, top tokens, error examples, substitution tables).  
* `analysis.md` – this human‑readable report.

Both live under `data\voice_benchmark\segments\`.

--- 

*End of analysis.*