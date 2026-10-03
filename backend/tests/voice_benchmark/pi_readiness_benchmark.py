#!/usr/bin/env python3
"""
Pi Zero 2 W Readiness Benchmark for Home_auto Voice Pipeline

Tests the current production Vosk voice pipeline to determine if it's
lightweight enough to realistically run on a Raspberry Pi Zero 2 W.

DOES NOT modify any production code. Only measures the existing pipeline.

Run with: python backend/tests/voice_benchmark/pi_readiness_benchmark.py
"""

import sys
import os
import time
import json
import wave
import struct
import threading
import statistics
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

import psutil
import numpy as np

# Try to import audio libraries; handle gracefully if not available
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

from backend.config import config
from backend.input.voice import (
    VoiceInput,
    parse_command,
    normalize_asr,
    is_valid_command_transcript,
    VoiceParserError,
    COMMAND_GRAMMAR,
    GRAMMAR_JSON,
)
from backend.input.asr_normalizer import normalize_asr as normalize_asr_fn


@dataclass
class SystemSpecs:
    cpu_model: str
    cpu_cores: int
    cpu_threads: int
    ram_total_gb: float
    python_version: str
    vosk_model_path: str
    vosk_model_size_mb: float


@dataclass
class BenchmarkMetrics:
    model_load_time_sec: float = 0.0
    peak_ram_mb: float = 0.0
    avg_ram_mb: float = 0.0
    idle_cpu_percent: float = 0.0
    active_cpu_percent: float = 0.0
    peak_cpu_percent: float = 0.0
    avg_recognition_latency_ms: float = 0.0
    p95_recognition_latency_ms: float = 0.0
    p99_recognition_latency_ms: float = 0.0
    avg_transcript_to_parse_ms: float = 0.0
    avg_total_latency_ms: float = 0.0
    real_time_factor: float = 0.0
    sustained_listening_ok: bool = False
    ram_growth_mb: float = 0.0
    cpu_growth_percent: float = 0.0
    parsed_commands: int = 0
    rejected_unk: int = 0
    rejected_invalid: int = 0
    audio_buffer_overflows: int = 0
    recognizer_errors: int = 0
    crashes: int = 0


@dataclass
class SegmentResult:
    segment_name: str
    audio_duration_sec: float
    recognition_latency_ms: float
    transcript_to_parse_ms: float
    total_latency_ms: float
    transcript: str
    parsed_success: bool
    had_unk: bool
    error: Optional[str] = None


class ResourceMonitor:
    """Monitors CPU and RAM usage in a background thread."""
    
    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.process = psutil.Process()
        self.cpu_samples: List[float] = []
        self.ram_samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        self._running = True
        self.cpu_samples = []
        self.ram_samples = []
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
    
    def _monitor(self):
        # First call to cpu_percent() returns 0, so prime it
        self.process.cpu_percent()
        while self._running:
            cpu = self.process.cpu_percent()
            ram = self.process.memory_info().rss / (1024 * 1024)  # MB
            self.cpu_samples.append(cpu)
            self.ram_samples.append(ram)
            time.sleep(self.interval)
    
    def get_stats(self) -> Dict[str, float]:
        if not self.cpu_samples:
            return {"avg_cpu": 0.0, "peak_cpu": 0.0, "avg_ram": 0.0, "peak_ram": 0.0}
        return {
            "avg_cpu": statistics.mean(self.cpu_samples),
            "peak_cpu": max(self.cpu_samples),
            "avg_ram": statistics.mean(self.ram_samples),
            "peak_ram": max(self.ram_samples),
        }


def get_system_specs() -> SystemSpecs:
    """Detect laptop specifications automatically."""
    cpu_info = psutil.cpu_freq()
    cpu_model = "Unknown"
    try:
        import platform
        cpu_model = platform.processor() or "Unknown"
    except:
        pass
    
    # Try to get more detailed CPU info on Windows
    if sys.platform == "win32":
        try:
            import wmi
            c = wmi.WMI()
            for processor in c.Win32_Processor():
                cpu_model = processor.Name.strip()
                break
        except:
            pass
    
    ram_total = psutil.virtual_memory().total / (1024**3)  # GB
    
    model_path = config.vosk.model_path
    model_size_mb = 0.0
    if os.path.exists(model_path):
        model_size_mb = sum(
            f.stat().st_size for f in Path(model_path).rglob("*") if f.is_file()
        ) / (1024 * 1024)
    
    return SystemSpecs(
        cpu_model=cpu_model,
        cpu_cores=psutil.cpu_count(logical=False) or 0,
        cpu_threads=psutil.cpu_count(logical=True) or 0,
        ram_total_gb=round(ram_total, 1),
        python_version=sys.version.split()[0],
        vosk_model_path=model_path,
        vosk_model_size_mb=round(model_size_mb, 1),
    )


def load_wav_duration(path: Path) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / rate


def run_model_load_benchmark() -> tuple[float, Model, float]:
    """Benchmark Vosk model loading time and initial RAM."""
    process = psutil.Process()
    ram_before = process.memory_info().rss / (1024 * 1024)
    
    start = time.perf_counter()
    model = Model(config.vosk.model_path)
    load_time = time.perf_counter() - start
    
    ram_after = process.memory_info().rss / (1024 * 1024)
    ram_used = ram_after - ram_before
    
    return load_time, model, ram_used


def run_segment_benchmark(model: Model, monitor: ResourceMonitor) -> List[SegmentResult]:
    """Run benchmark on the 209 WAV segments."""
    seg_dir = Path(r"B:\Home_auto\data\voice_benchmark\segments")
    seg_files = sorted(seg_dir.glob("segment_*.wav"))
    
    if len(seg_files) != 209:
        print(f"WARNING: Expected 209 segments, found {len(seg_files)}")
    
    results = []
    grammar_json = json.dumps(COMMAND_GRAMMAR)
    
    for seg_path in seg_files:
        # Load audio
        with wave.open(str(seg_path), "rb") as wf:
            assert wf.getsampwidth() == 2 and wf.getnchannels() == 1
            sr = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        
        audio_duration = len(audio) / sr
        
        # Resample if needed
        if sr != 16000:
            from scipy.signal import resample_poly
            import math
            up, down = 16000, sr
            g = math.gcd(up, down)
            audio = resample_poly(audio.astype(np.float32) / 32768.0, up // g, down // g)
            audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        
        pcm = audio.tobytes()
        
        # Create recognizer with constrained grammar
        rec = KaldiRecognizer(model, 16000, grammar_json)
        
        # Measure recognition latency
        rec_start = time.perf_counter()
        chunk_size = 4000
        for i in range(0, len(pcm), chunk_size):
            rec.AcceptWaveform(pcm[i:i + chunk_size])
        result = json.loads(rec.FinalResult())
        transcript = result.get("text", "").strip()
        recognition_latency = (time.perf_counter() - rec_start) * 1000  # ms
        
        # Measure transcript -> parse latency
        parse_start = time.perf_counter()
        had_unk = "[unk]" in transcript
        parsed_success = False
        error = None
        
        if is_valid_command_transcript(transcript):
            try:
                normalized = normalize_asr_fn(transcript)
                cmd = parse_command(normalized)
                parsed_success = True
            except VoiceParserError as e:
                error = str(e)
        else:
            error = "Invalid transcript (empty or [unk])"
        
        transcript_to_parse_ms = (time.perf_counter() - parse_start) * 1000
        total_latency = recognition_latency + transcript_to_parse_ms
        
        results.append(SegmentResult(
            segment_name=seg_path.name,
            audio_duration_sec=audio_duration,
            recognition_latency_ms=recognition_latency,
            transcript_to_parse_ms=transcript_to_parse_ms,
            total_latency_ms=total_latency,
            transcript=transcript,
            parsed_success=parsed_success,
            had_unk=had_unk,
            error=error,
        ))
        
        if had_unk:
            monitor.cpu_samples.append(0)  # placeholder for tracking
    
    return results


def run_sustained_listening_test(model: Model, duration_sec: int = 300) -> Dict[str, Any]:
    """Run sustained continuous listening test for specified duration."""
    print(f"\nRunning sustained listening test for {duration_sec} seconds...")
    print("Speak commands into microphone or press Ctrl+C to skip...")
    
    if not PYAUDIO_AVAILABLE:
        print("PyAudio not available, skipping live microphone test")
        return {
            "completed": False,
            "reason": "PyAudio not installed",
            "duration_sec": 0,
            "ram_start_mb": 0,
            "ram_end_mb": 0,
            "ram_growth_mb": 0,
            "cpu_start": 0,
            "cpu_end": 0,
            "cpu_growth_percent": 0,
            "commands_parsed": 0,
            "rejected_unk": 0,
            "rejected_invalid": 0,
            "buffer_overflows": 0,
            "recognizer_errors": 0,
            "crashes": 0,
        }
    
    grammar_json = json.dumps(COMMAND_GRAMMAR)
    rec = KaldiRecognizer(model, 16000, grammar_json)
    
    p = pyaudio.PyAudio()
    stream = None
    try:
        stream = p.open(
            rate=16000,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=4000,
        )
    except Exception as e:
        print(f"Could not open audio stream: {e}")
        p.terminate()
        return {
            "completed": False,
            "reason": f"Audio stream error: {e}",
            "duration_sec": 0,
            "ram_start_mb": 0,
            "ram_end_mb": 0,
            "ram_growth_mb": 0,
            "cpu_start": 0,
            "cpu_end": 0,
            "cpu_growth_percent": 0,
            "commands_parsed": 0,
            "rejected_unk": 0,
            "rejected_invalid": 0,
            "buffer_overflows": 0,
            "recognizer_errors": 0,
            "crashes": 0,
        }
    
    process = psutil.Process()
    ram_start = process.memory_info().rss / (1024 * 1024)
    cpu_start = process.cpu_percent()
    
    start_time = time.time()
    commands_parsed = 0
    rejected_unk = 0
    rejected_invalid = 0
    buffer_overflows = 0
    recognizer_errors = 0
    crashes = 0
    
    print("Listening... (speak commands or wait for timeout)")
    
    try:
        while time.time() - start_time < duration_sec:
            try:
                data = stream.read(4000, exception_on_overflow=False)
            except OSError as e:
                if "overflow" in str(e).lower():
                    buffer_overflows += 1
                    continue
                raise
            
            try:
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    
                    if is_valid_command_transcript(text):
                        try:
                            normalized = normalize_asr_fn(text)
                            parse_command(normalized)
                            commands_parsed += 1
                            print(f"  [OK] Parsed: {text}")
                        except VoiceParserError:
                            rejected_invalid += 1
                            print(f"  [FAIL] Rejected (parse failed): {text}")
                    elif text and "[unk]" in text:
                        rejected_unk += 1
                        print(f"  [FAIL] Rejected ([unk]): {text}")
                    elif text:
                        rejected_invalid += 1
                        print(f"  [FAIL] Rejected (invalid): {text}")
            except Exception as e:
                recognizer_errors += 1
                print(f"  Recognizer error: {e}")
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        elapsed = time.time() - start_time
        stream.stop_stream()
        stream.close()
        p.terminate()
    
    ram_end = process.memory_info().rss / (1024 * 1024)
    cpu_end = process.cpu_percent()
    
    return {
        "completed": elapsed >= duration_sec * 0.9,  # Allow 10% tolerance
        "reason": "completed" if elapsed >= duration_sec * 0.9 else "interrupted",
        "duration_sec": round(elapsed, 1),
        "ram_start_mb": round(ram_start, 1),
        "ram_end_mb": round(ram_end, 1),
        "ram_growth_mb": round(ram_end - ram_start, 1),
        "cpu_start": round(cpu_start, 1),
        "cpu_end": round(cpu_end, 1),
        "cpu_growth_percent": round(cpu_end - cpu_start, 1),
        "commands_parsed": commands_parsed,
        "rejected_unk": rejected_unk,
        "rejected_invalid": rejected_invalid,
        "buffer_overflows": buffer_overflows,
        "recognizer_errors": recognizer_errors,
        "crashes": crashes,
    }


def calculate_real_time_factor(results: List[SegmentResult]) -> float:
    """Calculate real-time factor (processing time / audio duration)."""
    total_processing = sum(r.recognition_latency_ms for r in results) / 1000.0
    total_audio = sum(r.audio_duration_sec for r in results)
    if total_audio > 0:
        return total_processing / total_audio
    return 0.0


def compute_percentiles(values: List[float], percentiles: List[int]) -> Dict[int, float]:
    """Compute percentiles from a list of values."""
    if not values:
        return {p: 0.0 for p in percentiles}
    sorted_vals = sorted(values)
    result = {}
    for p in percentiles:
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        result[p] = sorted_vals[idx]
    return result


def assess_readiness(metrics: BenchmarkMetrics, specs: SystemSpecs) -> str:
    """
    Preliminary assessment for Pi Zero 2 W readiness.
    
    Pi Zero 2 W specs: 4x Cortex-A53 @ 1GHz, 512MB RAM
    This is a SCREENING TEST - laptop performance != Pi performance.
    """
    # Conservative thresholds based on Pi Zero 2 W constraints
    # 512MB RAM total, so we need <200MB for voice pipeline to leave room for OS/other
    # 1GHz single-thread performance ~1/10 of laptop Ryzen 7
    
    ram_ok = metrics.peak_ram_mb < 200  # Must fit in ~200MB on Pi
    cpu_ok = metrics.active_cpu_percent < 30  # Should use <30% of one core on laptop
    rtf_ok = metrics.real_time_factor < 0.3  # Must be well under real-time on laptop
    latency_ok = metrics.avg_total_latency_ms < 500  # <500ms total latency on laptop
    sustained_ok = metrics.sustained_listening_ok
    no_growth_ok = metrics.ram_growth_mb < 10 and metrics.cpu_growth_percent < 5
    no_crashes = metrics.crashes == 0 and metrics.recognizer_errors == 0
    
    score = sum([
        ram_ok, cpu_ok, rtf_ok, latency_ok, 
        sustained_ok, no_growth_ok, no_crashes
    ])
    
    if score >= 6:
        return "GREEN"
    elif score >= 4:
        return "YELLOW"
    else:
        return "RED"


def main():
    print("=" * 70)
    print("Pi Zero 2 W Readiness Benchmark - Home_auto Voice Pipeline")
    print("=" * 70)
    print("\n[WARNING] IMPORTANT: This is a PRE-Pi SCREENING TEST.")
    print("   Laptop performance is NOT equivalent to Pi Zero 2 W performance.")
    print("   Purpose: Identify obvious CPU/RAM/latency problems before buying hardware.\n")
    
    if not VOSK_AVAILABLE:
        print("ERROR: Vosk not installed. Run: pip install vosk")
        sys.exit(1)
    
    # 1. System specs
    print("Detecting system specifications...")
    specs = get_system_specs()
    print(f"  CPU: {specs.cpu_model} ({specs.cpu_cores}C/{specs.cpu_threads}T)")
    print(f"  RAM: {specs.ram_total_gb} GB")
    print(f"  Python: {specs.python_version}")
    print(f"  Vosk Model: {specs.vosk_model_path} ({specs.vosk_model_size_mb} MB)")
    
    # 2. Model load benchmark
    print("\n[1/5] Benchmarking Vosk model load time...")
    load_time, model, ram_used = run_model_load_benchmark()
    print(f"  Load time: {load_time:.2f} sec")
    print(f"  RAM used by model: {ram_used:.1f} MB")
    
    # 3. Segment benchmark (209 WAV files)
    print("\n[2/5] Running 209-segment recognition benchmark...")
    monitor = ResourceMonitor(interval=0.05)
    monitor.start()
    
    segment_results = run_segment_benchmark(model, monitor)
    monitor.stop()
    
    resource_stats = monitor.get_stats()
    
    # Compute metrics from segment results
    recognition_latencies = [r.recognition_latency_ms for r in segment_results]
    transcript_to_parse = [r.transcript_to_parse_ms for r in segment_results]
    total_latencies = [r.total_latency_ms for r in segment_results]
    audio_durations = [r.audio_duration_sec for r in segment_results]
    
    parsed_count = sum(1 for r in segment_results if r.parsed_success)
    unk_count = sum(1 for r in segment_results if r.had_unk)
    invalid_count = sum(1 for r in segment_results if not r.parsed_success and not r.had_unk)
    
    percentiles = compute_percentiles(recognition_latencies, [50, 95, 99])
    rtf = calculate_real_time_factor(segment_results)
    
    print(f"  Segments processed: {len(segment_results)}")
    print(f"  Parsed successfully: {parsed_count}")
    print(f"  Rejected ([unk]): {unk_count}")
    print(f"  Rejected (invalid): {invalid_count}")
    print(f"  Avg recognition latency: {statistics.mean(recognition_latencies):.1f} ms")
    print(f"  P95 recognition latency: {percentiles[95]:.1f} ms")
    print(f"  P99 recognition latency: {percentiles[99]:.1f} ms")
    print(f"  Avg transcript->parse: {statistics.mean(transcript_to_parse):.1f} ms")
    print(f"  Avg total latency: {statistics.mean(total_latencies):.1f} ms")
    print(f"  Real-time factor: {rtf:.3f}")
    print(f"  Avg CPU during benchmark: {resource_stats['avg_cpu']:.1f}%")
    print(f"  Peak CPU during benchmark: {resource_stats['peak_cpu']:.1f}%")
    print(f"  Avg RAM during benchmark: {resource_stats['avg_ram']:.1f} MB")
    print(f"  Peak RAM during benchmark: {resource_stats['peak_ram']:.1f} MB")
    
    # 4. Idle CPU measurement
    print("\n[3/5] Measuring idle CPU (listening, no speech)...")
    idle_monitor = ResourceMonitor(interval=0.1)
    idle_monitor.start()
    
    # Simulate idle listening with constrained grammar recognizer
    grammar_json = json.dumps(COMMAND_GRAMMAR)
    rec = KaldiRecognizer(model, 16000, grammar_json)
    
    # Feed silence for 10 seconds
    silence = b'\x00' * (16000 * 2 * 10)  # 10 seconds of 16-bit mono silence
    chunk_size = 4000
    for i in range(0, len(silence), chunk_size):
        rec.AcceptWaveform(silence[i:i + chunk_size])
        time.sleep(0.01)
    
    idle_monitor.stop()
    idle_stats = idle_monitor.get_stats()
    print(f"  Idle CPU: {idle_stats['avg_cpu']:.1f}% (avg), {idle_stats['peak_cpu']:.1f}% (peak)")
    print(f"  Idle RAM: {idle_stats['avg_ram']:.1f} MB (avg), {idle_stats['peak_ram']:.1f} MB (peak)")
    
    # 5. Sustained listening test
    print("\n[4/5] Sustained continuous listening test (5 minutes)...")
    sustained_result = run_sustained_listening_test(model, duration_sec=300)
    
    print(f"  Completed: {sustained_result['completed']}")
    print(f"  Duration: {sustained_result['duration_sec']:.1f} sec")
    print(f"  RAM growth: {sustained_result['ram_growth_mb']:.1f} MB")
    print(f"  CPU growth: {sustained_result['cpu_growth_percent']:.1f}%")
    print(f"  Commands parsed: {sustained_result['commands_parsed']}")
    print(f"  Rejected [unk]: {sustained_result['rejected_unk']}")
    print(f"  Rejected invalid: {sustained_result['rejected_invalid']}")
    print(f"  Buffer overflows: {sustained_result['buffer_overflows']}")
    print(f"  Recognizer errors: {sustained_result['recognizer_errors']}")
    print(f"  Crashes: {sustained_result['crashes']}")
    
    # 6. Active CPU measurement (during actual recognition)
    print("\n[5/5] Measuring active CPU during recognition...")
    active_monitor = ResourceMonitor(interval=0.01)
    active_monitor.start()
    
    # Process a few segments rapidly to measure active CPU
    grammar_json = json.dumps(COMMAND_GRAMMAR)
    for r in segment_results[:20]:
        # Re-process to measure CPU
        with wave.open(str(Path(r"B:\Home_auto\data\voice_benchmark\segments") / r.segment_name), "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        pcm = audio.tobytes()
        rec = KaldiRecognizer(model, 16000, grammar_json)
        chunk_size = 4000
        for i in range(0, len(pcm), chunk_size):
            rec.AcceptWaveform(pcm[i:i + chunk_size])
        rec.FinalResult()
    
    active_monitor.stop()
    active_stats = active_monitor.get_stats()
    print(f"  Active CPU: {active_stats['avg_cpu']:.1f}% (avg), {active_stats['peak_cpu']:.1f}% (peak)")
    
    # Compile final metrics
    metrics = BenchmarkMetrics(
        model_load_time_sec=round(load_time, 2),
        peak_ram_mb=round(resource_stats['peak_ram'], 1),
        avg_ram_mb=round(resource_stats['avg_ram'], 1),
        idle_cpu_percent=round(idle_stats['avg_cpu'], 1),
        active_cpu_percent=round(active_stats['avg_cpu'], 1),
        peak_cpu_percent=round(max(resource_stats['peak_cpu'], active_stats['peak_cpu']), 1),
        avg_recognition_latency_ms=round(statistics.mean(recognition_latencies), 1),
        p95_recognition_latency_ms=round(percentiles[95], 1),
        p99_recognition_latency_ms=round(percentiles[99], 1),
        avg_transcript_to_parse_ms=round(statistics.mean(transcript_to_parse), 1),
        avg_total_latency_ms=round(statistics.mean(total_latencies), 1),
        real_time_factor=round(rtf, 3),
        sustained_listening_ok=sustained_result['completed'],
        ram_growth_mb=round(sustained_result['ram_growth_mb'], 1),
        cpu_growth_percent=round(sustained_result['cpu_growth_percent'], 1),
        parsed_commands=parsed_count + sustained_result['commands_parsed'],
        rejected_unk=unk_count + sustained_result['rejected_unk'],
        rejected_invalid=invalid_count + sustained_result['rejected_invalid'],
        audio_buffer_overflows=sustained_result['buffer_overflows'],
        recognizer_errors=sustained_result['recognizer_errors'],
        crashes=sustained_result['crashes'],
    )
    
    # Assessment
    assessment = assess_readiness(metrics, specs)
    
    # Print final report
    print("\n" + "=" * 70)
    print("PI ZERO 2 W READINESS REPORT")
    print("=" * 70)
    print(f"\nSystem Under Test (Laptop):")
    print(f"  CPU: {specs.cpu_model} ({specs.cpu_cores}C/{specs.cpu_threads}T)")
    print(f"  RAM: {specs.ram_total_gb} GB")
    print(f"  Python: {specs.python_version}")
    
    print(f"\nVosk Model:")
    print(f"  Path: {specs.vosk_model_path}")
    print(f"  Size: {specs.vosk_model_size_mb} MB")
    print(f"  Load Time: {metrics.model_load_time_sec} sec")
    
    print(f"\nResource Usage (on laptop):")
    print(f"  Peak RAM: {metrics.peak_ram_mb} MB")
    print(f"  Avg RAM: {metrics.avg_ram_mb} MB")
    print(f"  Idle CPU: {metrics.idle_cpu_percent}%")
    print(f"  Active CPU: {metrics.active_cpu_percent}%")
    print(f"  Peak CPU: {metrics.peak_cpu_percent}%")
    
    print(f"\nLatency (on laptop):")
    print(f"  Avg Recognition Latency: {metrics.avg_recognition_latency_ms} ms")
    print(f"  P95 Recognition Latency: {metrics.p95_recognition_latency_ms} ms")
    print(f"  P99 Recognition Latency: {metrics.p99_recognition_latency_ms} ms")
    print(f"  Avg Transcript->Parse: {metrics.avg_transcript_to_parse_ms} ms")
    print(f"  Avg Total Latency: {metrics.avg_total_latency_ms} ms")
    print(f"  Real-Time Factor: {metrics.real_time_factor}")
    
    print(f"\nSustained Listening (5 min):")
    print(f"  Completed: {'Yes' if metrics.sustained_listening_ok else 'No'}")
    print(f"  RAM Growth: {metrics.ram_growth_mb} MB")
    print(f"  CPU Growth: {metrics.cpu_growth_percent}%")
    
    print(f"\nCommand Processing:")
    print(f"  Parsed Commands: {metrics.parsed_commands}")
    print(f"  Rejected [unk]: {metrics.rejected_unk}")
    print(f"  Rejected Invalid: {metrics.rejected_invalid}")
    print(f"  Audio Buffer Overflows: {metrics.audio_buffer_overflows}")
    print(f"  Recognizer Errors: {metrics.recognizer_errors}")
    print(f"  Crashes: {metrics.crashes}")
    
    print(f"\n{'=' * 70}")
    print(f"PRELIMINARY ASSESSMENT: {assessment}")
    print(f"{'=' * 70}")
    
    if assessment == "GREEN":
        print("[GREEN] No obvious blockers. Proceed to Pi Zero 2 W testing.")
    elif assessment == "YELLOW":
        print("[YELLOW] Some concerns. Review metrics before purchasing Pi.")
    else:
        print("[RED] Significant issues. Optimize pipeline before Pi testing.")
    
    print("\n[REMINDER] Laptop performance != Pi Zero 2 W performance.")
    print("   This is a PRE-SCREENING test only. Actual Pi testing required.")
    
    # Save detailed results
    report = {
        "timestamp": datetime.now().isoformat(),
        "system_specs": asdict(specs),
        "metrics": asdict(metrics),
        "assessment": assessment,
        "segment_results": [asdict(r) for r in segment_results],
        "sustained_listening": sustained_result,
    }
    
    report_path = Path(__file__).parent / f"pi_readiness_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_path}")
    
    return 0 if assessment != "RED" else 1


if __name__ == "__main__":
    sys.exit(main())