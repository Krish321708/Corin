# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: audio_engine.py
# ROLE: Hybrid sound system. Loads pre-recorded WAV files from assets/sounds/
#       with full procedural synthesis fallback if files are missing.
#       Manages 4 sound categories + procedural generation algorithms.
#       Handles orb-mode audio cues, alert sounds, UI interaction sounds,
#       and mode-switch confirmation tones. Thread-safe playback queue.
# =============================================================================

import os
import sys
import math
import time
import random
import threading
import queue
import struct
import wave
import io
from typing import Dict, List, Optional, Tuple

# Pygame mixer import (required for playback)
try:
    import pygame
    import pygame.mixer
    import pygame.sndarray
    PYGAME_AVAILABLE: bool = True
except ImportError:
    PYGAME_AVAILABLE: bool = False

# Numpy for waveform synthesis
try:
    import numpy as np
    NUMPY_AVAILABLE: bool = True
except ImportError:
    NUMPY_AVAILABLE: bool = False

from Backhand_code.config import (
    SOUND_ACCESS_GRANTED,
    SOUND_THINKING_MACHINE,
    SOUND_DEEP_SPACE_PING,
    SOUND_ALERT_ALARM,
    SOUNDS_DIR,
    UIMode,
)

# =============================================================================
# SECTION 1: AUDIO CONSTANTS
# =============================================================================

SAMPLE_RATE:    int   = 44100    # Hz
CHANNELS:       int   = 2        # Stereo
BIT_DEPTH:      int   = 16       # bits per sample
MAX_AMPLITUDE:  int   = 32767    # 16-bit signed max
MIXER_BUFFER:   int   = 512      # pygame mixer buffer size (samples)

# Sound category integer constants (match config file numbering)
SOUND_CAT_ACCESS_GRANTED:   int = 1
SOUND_CAT_THINKING_MACHINE: int = 2
SOUND_CAT_DEEP_SPACE_PING:  int = 3
SOUND_CAT_ALERT_ALARM:      int = 4

# Additional UI event sound sub-categories (generated procedurally)
SOUND_CAT_MODE_SWITCH:      int = 5    # mode switch confirmation
SOUND_CAT_ORB_ACTIVATE:     int = 6    # orb interaction
SOUND_CAT_TERMINAL_OPEN:    int = 7    # terminal expand
SOUND_CAT_TERMINAL_CLOSE:   int = 8    # terminal collapse
SOUND_CAT_NEWS_CLICK:       int = 9    # news item selected
SOUND_CAT_GLOBE_CLICK:      int = 10   # globe pin selected
SOUND_CAT_COMMIT_PUSH:      int = 11   # GitHub commit success
SOUND_CAT_BRAINSTORM_ENTER: int = 12   # enter brainstorm mode
SOUND_CAT_BRAINSTORM_EXIT:  int = 13   # exit brainstorm mode
SOUND_CAT_MESSAGE_RECEIVE:  int = 14   # social message notification
SOUND_CAT_MESSAGE_SENT:     int = 15   # social message sent

# Volume levels (0.0 to 1.0)
VOLUME_MASTER:  float = 0.75
VOLUME_ALERT:   float = 1.00
VOLUME_UI:      float = 0.55
VOLUME_AMBIENT: float = 0.35

# =============================================================================
# SECTION 2: PROCEDURAL WAVEFORM SYNTHESIS PRIMITIVES
# =============================================================================

def _make_sine_wave(
    frequency:   float,
    duration:    float,
    amplitude:   float  = 1.0,
    sample_rate: int    = SAMPLE_RATE,
    phase:       float  = 0.0,
) -> List[float]:
    """
    Generates a pure sine wave as a list of normalized float samples [-1, 1].

    y(t) = amplitude * sin(2π * frequency * t + phase)

    Args:
        frequency:   Tone frequency in Hz.
        duration:    Duration in seconds.
        amplitude:   Peak amplitude scalar [0.0, 1.0].
        sample_rate: Samples per second.
        phase:       Initial phase offset in radians.

    Returns:
        List of float samples in range [-amplitude, +amplitude].
    """
    num_samples = int(duration * sample_rate)
    samples     = []
    two_pi_f    = 2.0 * math.pi * frequency
    for i in range(num_samples):
        t = i / sample_rate
        samples.append(amplitude * math.sin(two_pi_f * t + phase))
    return samples


def _make_sawtooth_wave(
    frequency:   float,
    duration:    float,
    amplitude:   float = 1.0,
    sample_rate: int   = SAMPLE_RATE,
) -> List[float]:
    """
    Generates a sawtooth wave — harsh, mechanical, used for Hudson tones.

    y(t) = amplitude * (2 * (f*t mod 1) - 1)

    Args:
        frequency:   Tone frequency in Hz.
        duration:    Duration in seconds.
        amplitude:   Peak amplitude scalar.
        sample_rate: Samples per second.

    Returns:
        List of float samples in range [-amplitude, +amplitude].
    """
    num_samples = int(duration * sample_rate)
    samples     = []
    period      = 1.0 / frequency
    for i in range(num_samples):
        t    = i / sample_rate
        phase = (t % period) / period
        samples.append(amplitude * (2.0 * phase - 1.0))
    return samples


def _make_square_wave(
    frequency:   float,
    duration:    float,
    amplitude:   float = 1.0,
    sample_rate: int   = SAMPLE_RATE,
    duty:        float = 0.5,
) -> List[float]:
    """
    Generates a square wave with configurable duty cycle.
    Used for alert alarm components.

    Args:
        frequency:   Tone frequency in Hz.
        duration:    Duration in seconds.
        amplitude:   Peak amplitude scalar.
        sample_rate: Samples per second.
        duty:        Duty cycle [0.0, 1.0]. 0.5 = symmetric square wave.

    Returns:
        List of float samples.
    """
    num_samples = int(duration * sample_rate)
    samples     = []
    period      = 1.0 / frequency
    for i in range(num_samples):
        t     = i / sample_rate
        phase = (t % period) / period
        samples.append(amplitude if phase < duty else -amplitude)
    return samples


def _make_noise_burst(
    duration:    float,
    amplitude:   float = 1.0,
    sample_rate: int   = SAMPLE_RATE,
    seed:        int   = 0,
) -> List[float]:
    """
    Generates white noise — used for static/click textures in
    Thinking Machine sounds and Alert alarms.

    Args:
        duration:    Duration in seconds.
        amplitude:   Peak amplitude scalar.
        sample_rate: Samples per second.
        seed:        Random seed for reproducibility (0 = time-seeded).

    Returns:
        List of float samples in range [-amplitude, +amplitude].
    """
    rng         = random.Random(seed if seed != 0 else int(time.time() * 1000))
    num_samples = int(duration * sample_rate)
    return [amplitude * (rng.random() * 2.0 - 1.0) for _ in range(num_samples)]


def _apply_envelope(
    samples:        List[float],
    attack_secs:    float,
    decay_secs:     float,
    sustain_level:  float,
    release_secs:   float,
    sample_rate:    int = SAMPLE_RATE,
) -> List[float]:
    """
    Applies an ADSR amplitude envelope to a sample buffer.

    ADSR Envelope:
        Attack:  Linear ramp from 0.0 to 1.0 over attack_secs.
        Decay:   Linear ramp from 1.0 to sustain_level over decay_secs.
        Sustain: Constant sustain_level for the middle section.
        Release: Linear ramp from sustain_level to 0.0 over release_secs.

    Args:
        samples:       Input sample list.
        attack_secs:   Attack phase duration in seconds.
        decay_secs:    Decay phase duration in seconds.
        sustain_level: Sustain amplitude level [0.0, 1.0].
        release_secs:  Release phase duration in seconds.
        sample_rate:   Samples per second.

    Returns:
        Envelope-shaped sample list (same length as input).
    """
    total      = len(samples)
    attack_n   = int(attack_secs  * sample_rate)
    decay_n    = int(decay_secs   * sample_rate)
    release_n  = int(release_secs * sample_rate)
    sustain_n  = max(0, total - attack_n - decay_n - release_n)

    envelope: List[float] = []

    # Attack phase: 0 → 1
    for i in range(min(attack_n, total)):
        envelope.append(i / max(1, attack_n))

    # Decay phase: 1 → sustain_level
    for i in range(min(decay_n, total - len(envelope))):
        t = i / max(1, decay_n)
        envelope.append(1.0 - (1.0 - sustain_level) * t)

    # Sustain phase: constant
    for _ in range(min(sustain_n, total - len(envelope))):
        envelope.append(sustain_level)

    # Release phase: sustain_level → 0
    for i in range(min(release_n, total - len(envelope))):
        t = i / max(1, release_n)
        envelope.append(sustain_level * (1.0 - t))

    # Pad with zeros if needed
    while len(envelope) < total:
        envelope.append(0.0)

    return [s * e for s, e in zip(samples, envelope[:total])]


def _apply_reverb(
    samples:     List[float],
    decay:       float = 0.4,
    delay_ms:    float = 80.0,
    sample_rate: int   = SAMPLE_RATE,
) -> List[float]:
    """
    Applies a simple comb-filter reverb to the sample buffer.
    Creates the echoing tail effect used in Deep Space Ping sounds.

    Algorithm:
        output[n] = input[n] + decay * output[n - delay_samples]

    Args:
        samples:     Input sample list.
        decay:       Echo decay factor [0.0, 1.0]. Higher = longer tail.
        delay_ms:    Delay between echo taps in milliseconds.
        sample_rate: Samples per second.

    Returns:
        Reverb-processed sample list (same length as input).
    """
    delay_n = int((delay_ms / 1000.0) * sample_rate)
    output  = list(samples)

    for i in range(delay_n, len(output)):
        output[i] += decay * output[i - delay_n]

    # Normalize to prevent clipping
    max_val = max(abs(s) for s in output) if output else 1.0
    if max_val > 1.0:
        inv = 1.0 / max_val
        output = [s * inv for s in output]

    return output


def _apply_lowpass_filter(
    samples:     List[float],
    cutoff_hz:   float,
    sample_rate: int = SAMPLE_RATE,
) -> List[float]:
    """
    Applies a single-pole IIR lowpass filter to the sample buffer.
    Smooths harsh high-frequency content for more cinematic tones.

    Transfer function (discrete):
        y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
        alpha = 2π * cutoff / (2π * cutoff + sample_rate)

    Args:
        samples:     Input sample list.
        cutoff_hz:   Filter cutoff frequency in Hz.
        sample_rate: Samples per second.

    Returns:
        Lowpass-filtered sample list.
    """
    two_pi_fc = 2.0 * math.pi * cutoff_hz
    alpha     = two_pi_fc / (two_pi_fc + sample_rate)
    output    = []
    prev      = 0.0

    for s in samples:
        prev = alpha * s + (1.0 - alpha) * prev
        output.append(prev)

    return output


def _apply_highpass_filter(
    samples:     List[float],
    cutoff_hz:   float,
    sample_rate: int = SAMPLE_RATE,
) -> List[float]:
    """
    Applies a single-pole IIR highpass filter.
    Used to give Alert sounds an aggressive, cutting edge.

    Transfer function (discrete):
        y[n] = alpha * (y[n-1] + x[n] - x[n-1])
        alpha = sample_rate / (2π * cutoff + sample_rate)

    Args:
        samples:     Input sample list.
        cutoff_hz:   Highpass cutoff frequency in Hz.
        sample_rate: Samples per second.

    Returns:
        Highpass-filtered sample list.
    """
    two_pi_fc = 2.0 * math.pi * cutoff_hz
    alpha     = sample_rate / (two_pi_fc + sample_rate)
    output    = []
    prev_out  = 0.0
    prev_in   = 0.0

    for s in samples:
        y = alpha * (prev_out + s - prev_in)
        output.append(y)
        prev_out = y
        prev_in  = s

    return output


def _mix_samples(*sample_lists: List[float]) -> List[float]:
    """
    Mixes multiple sample lists together by averaging their values.
    All lists are zero-padded to the length of the longest.

    Args:
        *sample_lists: Variable number of sample lists to mix.

    Returns:
        Mixed sample list (length = max input length).
    """
    if not sample_lists:
        return []

    max_len = max(len(s) for s in sample_lists)
    count   = len(sample_lists)
    mixed   = []

    for i in range(max_len):
        total = 0.0
        for sl in sample_lists:
            if i < len(sl):
                total += sl[i]
        mixed.append(total / count)

    return mixed


def _samples_to_pygame_sound(
    samples:     List[float],
    sample_rate: int = SAMPLE_RATE,
) -> Optional["pygame.mixer.Sound"]:
    """
    Converts a normalized float sample list to a pygame.mixer.Sound object.

    Process:
        1. Clamp all samples to [-1.0, 1.0].
        2. Scale to 16-bit signed integer range [-32767, 32767].
        3. Duplicate for stereo (left = right channel).
        4. Pack as little-endian signed 16-bit integers.
        5. Wrap in pygame.mixer.Sound via buffer.

    Args:
        samples:     Normalized float samples in range [-1.0, 1.0].
        sample_rate: Sample rate (must match pygame mixer init rate).

    Returns:
        pygame.mixer.Sound object, or None if pygame unavailable.
    """
    if not PYGAME_AVAILABLE:
        return None

    if NUMPY_AVAILABLE:
        arr = np.array(samples, dtype=np.float32)
        arr = np.clip(arr, -1.0, 1.0)
        arr_int = (arr * MAX_AMPLITUDE).astype(np.int16)
        # Stereo: duplicate column
        stereo = np.column_stack([arr_int, arr_int])
        sound = pygame.sndarray.make_sound(stereo)
        return sound
    else:
        # Pure Python path — build raw bytes manually
        raw_bytes = bytearray()
        for s in samples:
            clamped   = max(-1.0, min(1.0, s))
            val       = int(clamped * MAX_AMPLITUDE)
            # Pack as little-endian signed 16-bit, stereo (L+R)
            packed    = struct.pack("<hh", val, val)
            raw_bytes.extend(packed)

        try:
            sound = pygame.mixer.Sound(buffer=bytes(raw_bytes))
            return sound
        except Exception:
            return None


def _concatenate_samples(
    *sample_lists: List[float],
    gap_secs: float = 0.0,
    sample_rate: int = SAMPLE_RATE,
) -> List[float]:
    """
    Concatenates multiple sample lists sequentially with optional silence gaps.

    Args:
        *sample_lists: Sample lists to join in order.
        gap_secs:      Seconds of silence to insert between each list.
        sample_rate:   Samples per second (for gap calculation).

    Returns:
        Concatenated sample list.
    """
    gap_samples = [0.0] * int(gap_secs * sample_rate)
    result: List[float] = []

    for idx, sl in enumerate(sample_lists):
        result.extend(sl)
        if gap_secs > 0.0 and idx < len(sample_lists) - 1:
            result.extend(gap_samples)

    return result


# =============================================================================
# SECTION 3: PROCEDURAL SOUND GENERATORS (4 CINEMATIC ARCHETYPES)
# =============================================================================

def _generate_access_granted_chirp(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the "Access Granted" ascending double-tone chirp.
    Sound profile: bi-LIP! — fast, encouraging, efficient.

    Architecture:
        Tone 1: 880 Hz sine, 0.06s, fast attack, sharp decay
        Brief silence: 0.015s
        Tone 2: 1320 Hz sine (perfect fifth above), 0.09s, faster decay
        Soft harmonic layer: 440 Hz at 0.15 amplitude blended under both
        Lowpass at 3500 Hz for warmth

    Returns:
        Normalized float sample list.
    """
    # First chirp — lower tone
    chirp1_raw = _make_sine_wave(880.0, 0.065, amplitude=1.0,
                                  sample_rate=sample_rate)
    chirp1     = _apply_envelope(
        chirp1_raw,
        attack_secs=0.004,
        decay_secs=0.020,
        sustain_level=0.6,
        release_secs=0.041,
        sample_rate=sample_rate,
    )

    # Harmonic undertone for chirp1
    under1 = _make_sine_wave(440.0, 0.065, amplitude=0.15,
                              sample_rate=sample_rate)

    # Blend chirp + undertone
    layer1 = _mix_samples(chirp1, under1)

    # Second chirp — higher tone (ascending)
    chirp2_raw = _make_sine_wave(1320.0, 0.095, amplitude=1.0,
                                  sample_rate=sample_rate)
    chirp2     = _apply_envelope(
        chirp2_raw,
        attack_secs=0.003,
        decay_secs=0.015,
        sustain_level=0.5,
        release_secs=0.077,
        sample_rate=sample_rate,
    )

    # Harmonic overtone for chirp2
    over2 = _make_sine_wave(2640.0, 0.095, amplitude=0.08,
                             sample_rate=sample_rate)
    layer2 = _mix_samples(chirp2, over2)

    # Concatenate with tiny silence gap
    full = _concatenate_samples(layer1, layer2, gap_secs=0.015,
                                  sample_rate=sample_rate)

    # Warm lowpass
    return _apply_lowpass_filter(full, cutoff_hz=3500.0,
                                   sample_rate=sample_rate)


def _generate_thinking_machine_click(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the "Thinking Machine" ultra-fast click series + soft chime.
    Sound profile: t-t-t-t-t-chime — computing millions of possibilities.

    Architecture:
        32 micro-clicks: white noise burst (0.004s each) at 14ms intervals
            with slight frequency-rising pitch on each click
        Final chime: 1760 Hz sine (bright, crystalline), 0.18s
        Gentle reverb tail on the chime only
        Highpass at 200 Hz to cut mud

    Returns:
        Normalized float sample list.
    """
    click_duration = 0.004    # seconds per click
    click_interval = 0.014    # seconds between click starts
    num_clicks     = 32

    # Build rapid click sequence
    click_seq: List[float] = []
    silence_between = [0.0] * int((click_interval - click_duration) * sample_rate)

    for i in range(num_clicks):
        # Each click: white noise burst with very tight envelope
        # Slight amplitude increase as "thinking" builds
        amp       = 0.3 + (i / num_clicks) * 0.45
        noise     = _make_noise_burst(click_duration, amplitude=amp,
                                        sample_rate=sample_rate,
                                        seed=i + 100)
        enveloped = _apply_envelope(
            noise,
            attack_secs=0.0005,
            decay_secs=0.0015,
            sustain_level=0.2,
            release_secs=0.002,
            sample_rate=sample_rate,
        )
        click_seq.extend(enveloped)
        if i < num_clicks - 1:
            click_seq.extend(silence_between)

    # Final resolution chime
    chime_raw = _make_sine_wave(1760.0, 0.18, amplitude=0.85,
                                 sample_rate=sample_rate)
    chime_harmonic = _make_sine_wave(2640.0, 0.18, amplitude=0.25,
                                       sample_rate=sample_rate)
    chime_blend = _mix_samples(chime_raw, chime_harmonic)
    chime_env   = _apply_envelope(
        chime_blend,
        attack_secs=0.008,
        decay_secs=0.04,
        sustain_level=0.5,
        release_secs=0.132,
        sample_rate=sample_rate,
    )
    chime_reverb = _apply_reverb(chime_env, decay=0.25, delay_ms=45.0,
                                   sample_rate=sample_rate)

    # Short silence before chime
    pre_chime_silence = [0.0] * int(0.02 * sample_rate)

    # Full sequence: clicks → silence → chime
    full = click_seq + pre_chime_silence + chime_reverb

    # Highpass to cut low mud from noise clicks
    return _apply_highpass_filter(full, cutoff_hz=180.0,
                                    sample_rate=sample_rate)


def _generate_deep_space_ping(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the "Deep Space Ping" haunting resonant sonar tone.
    Sound profile: Piiiiiiing... — lonely sonar, massive decaying echo.

    Architecture:
        Primary tone: 220 Hz sine (deep, metallic), 1.8s
        Secondary: 165 Hz (below, darker resonance), 1.8s, 0.35 amplitude
        Third harmonic: 440 Hz, 0.8s, 0.15 amplitude (quick decay)
        Reverb: high decay (0.65), long delay (120ms) — deep cave echo
        Lowpass at 800 Hz — removes brightness, adds depth/loneliness

    Returns:
        Normalized float sample list.
    """
    duration = 1.8

    # Primary ping tone
    primary_raw = _make_sine_wave(220.0, duration, amplitude=1.0,
                                   sample_rate=sample_rate)
    primary     = _apply_envelope(
        primary_raw,
        attack_secs=0.012,
        decay_secs=0.08,
        sustain_level=0.7,
        release_secs=1.708,
        sample_rate=sample_rate,
    )

    # Deep resonance layer
    resonance_raw = _make_sine_wave(165.0, duration, amplitude=0.35,
                                      sample_rate=sample_rate)
    resonance     = _apply_envelope(
        resonance_raw,
        attack_secs=0.025,
        decay_secs=0.1,
        sustain_level=0.6,
        release_secs=1.675,
        sample_rate=sample_rate,
    )

    # Quick-decay harmonic overtone
    harmonic_raw = _make_sine_wave(440.0, 0.8, amplitude=0.15,
                                    sample_rate=sample_rate)
    harmonic     = _apply_envelope(
        harmonic_raw,
        attack_secs=0.005,
        decay_secs=0.05,
        sustain_level=0.1,
        release_secs=0.745,
        sample_rate=sample_rate,
    )
    # Pad harmonic to full duration
    harmonic.extend([0.0] * (int(duration * sample_rate) - len(harmonic)))

    # Blend all layers
    blended = _mix_samples(primary, resonance, harmonic)

    # Deep reverb — long echo tail (space-like)
    reverbed = _apply_reverb(blended, decay=0.65, delay_ms=120.0,
                               sample_rate=sample_rate)

    # Lowpass for dark, lonely timbre
    return _apply_lowpass_filter(reverbed, cutoff_hz=800.0,
                                   sample_rate=sample_rate)


def _generate_alert_alarm(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the aggressive Alert Alarm — futuristic submarine leak alarm.
    Sound profile: FULL BUZZER + pulsing siren + digital scream.

    Architecture:
        Layer 1: Rapid square wave buzz (80 Hz, duty=0.6) — deep hull vibration
        Layer 2: Siren sweep — LFO-modulated sine rising from 400→1200 Hz
                 repeating 4 times over 2.4 seconds
        Layer 3: White noise bursts gated at 8 Hz — urgency texture
        Layer 4: High sawtooth (1800 Hz) aggressive digital scream component
        Highpass at 60 Hz to prevent speaker distortion
        Slight overdrive (soft clip at 0.85) for aggression

    Returns:
        Normalized float sample list.
    """
    duration   = 2.4
    num_samples = int(duration * sample_rate)

    # Layer 1: Deep hull-vibration square wave buzz
    buzz_raw = _make_square_wave(80.0, duration, amplitude=0.8,
                                   sample_rate=sample_rate, duty=0.6)
    buzz     = _apply_envelope(
        buzz_raw,
        attack_secs=0.008,
        decay_secs=0.02,
        sustain_level=0.85,
        release_secs=0.15,
        sample_rate=sample_rate,
    )

    # Layer 2: Siren sweep — LFO frequency-modulated sine
    # Frequency sweeps 400→1200 Hz repeatedly (4 cycles in 2.4s)
    siren_samples: List[float] = []
    siren_cycles   = 4
    cycle_dur      = duration / siren_cycles
    freq_low       = 400.0
    freq_high      = 1200.0
    phase_acc      = 0.0

    for i in range(num_samples):
        t_in_cycle = (i / sample_rate) % cycle_dur
        t_norm     = t_in_cycle / cycle_dur
        # Exponential sweep for more aggressive rise
        freq       = freq_low * ((freq_high / freq_low) ** t_norm)
        phase_acc  += 2.0 * math.pi * freq / sample_rate
        siren_samples.append(0.7 * math.sin(phase_acc))

    siren = _apply_envelope(
        siren_samples,
        attack_secs=0.01,
        decay_secs=0.02,
        sustain_level=0.9,
        release_secs=0.2,
        sample_rate=sample_rate,
    )

    # Layer 3: Gated noise bursts at 8 Hz
    noise_base  = _make_noise_burst(duration, amplitude=0.5,
                                      sample_rate=sample_rate, seed=77)
    gate_freq   = 8.0
    noise_gated = []
    for i, s in enumerate(noise_base):
        t     = i / sample_rate
        gate  = 1.0 if math.sin(2.0 * math.pi * gate_freq * t) > 0.0 else 0.0
        noise_gated.append(s * gate)

    # Layer 4: Digital scream sawtooth
    scream_raw = _make_sawtooth_wave(1800.0, duration, amplitude=0.35,
                                       sample_rate=sample_rate)
    scream     = _apply_envelope(
        scream_raw,
        attack_secs=0.005,
        decay_secs=0.01,
        sustain_level=0.85,
        release_secs=0.15,
        sample_rate=sample_rate,
    )

    # Ensure all layers same length
    target_len = num_samples
    for layer in [buzz, siren, noise_gated, scream]:
        while len(layer) < target_len:
            layer.append(0.0)

    buzz       = buzz[:target_len]
    siren      = siren[:target_len]
    noise_gated = noise_gated[:target_len]
    scream     = scream[:target_len]

    # Mix all 4 layers
    blended = []
    for i in range(target_len):
        val = (buzz[i] * 0.35 +
               siren[i] * 0.40 +
               noise_gated[i] * 0.15 +
               scream[i] * 0.10)
        blended.append(val)

    # Soft clip overdrive at threshold 0.85 (tanh-based)
    driven = []
    threshold = 0.85
    for s in blended:
        if abs(s) <= threshold:
            driven.append(s)
        else:
            sign  = 1.0 if s > 0 else -1.0
            excess = abs(s) - threshold
            driven.append(sign * (threshold + math.tanh(excess * 3.0) * 0.15))

    # Highpass to prevent deep sub-bass distortion
    return _apply_highpass_filter(driven, cutoff_hz=55.0,
                                    sample_rate=sample_rate)


# =============================================================================
# SECTION 4: UI-SPECIFIC PROCEDURAL SOUNDS
# =============================================================================

def _generate_mode_switch_sound(
    mode:        str,
    sample_rate: int = SAMPLE_RATE,
) -> List[float]:
    """
    Generates a mode-switch confirmation tone tailored to the target mode.

    ARCHER mode: Ascending clean chord (pure tones, crystalline)
    HUDSON mode: Descending mechanical tone (sawtooth blend)
    BOTH mode:   Dual-chord harmonic convergence

    Args:
        mode:        UIMode string ("ARCHER", "HUDSON", or "BOTH").
        sample_rate: Samples per second.

    Returns:
        Normalized float sample list.
    """
    if mode == UIMode.ARCHER:
        # Clean ascending: 660 → 880 → 1100 Hz
        t1_raw = _make_sine_wave(660.0,  0.07, 0.8, sample_rate)
        t2_raw = _make_sine_wave(880.0,  0.09, 0.8, sample_rate)
        t3_raw = _make_sine_wave(1100.0, 0.11, 0.6, sample_rate)
        t1 = _apply_envelope(t1_raw, 0.003, 0.01, 0.6, 0.057, sample_rate)
        t2 = _apply_envelope(t2_raw, 0.003, 0.01, 0.6, 0.077, sample_rate)
        t3 = _apply_envelope(t3_raw, 0.003, 0.01, 0.5, 0.097, sample_rate)
        seq = _concatenate_samples(t1, t2, t3, gap_secs=0.01,
                                     sample_rate=sample_rate)
        return _apply_lowpass_filter(seq, 3000.0, sample_rate)

    elif mode == UIMode.HUDSON:
        # Descending mechanical: 440 → 330 Hz with sawtooth blend
        s1_saw = _make_sawtooth_wave(440.0, 0.09, 0.3, sample_rate)
        s1_sin = _make_sine_wave(440.0,    0.09, 0.7, sample_rate)
        s1_raw = _mix_samples(s1_saw, s1_sin)
        s1 = _apply_envelope(s1_raw, 0.005, 0.02, 0.55, 0.065, sample_rate)

        s2_saw = _make_sawtooth_wave(330.0, 0.12, 0.3, sample_rate)
        s2_sin = _make_sine_wave(330.0,    0.12, 0.7, sample_rate)
        s2_raw = _mix_samples(s2_saw, s2_sin)
        s2 = _apply_envelope(s2_raw, 0.005, 0.02, 0.5, 0.095, sample_rate)

        seq = _concatenate_samples(s1, s2, gap_secs=0.012,
                                     sample_rate=sample_rate)
        return _apply_lowpass_filter(seq, 2000.0, sample_rate)

    else:
        # BOTH mode: simultaneous dual-chord convergence
        cyan_raw  = _make_sine_wave(880.0,  0.15, 0.6, sample_rate)
        amber_raw = _make_sine_wave(660.0,  0.15, 0.6, sample_rate)
        merge_raw = _make_sine_wave(1100.0, 0.08, 0.4, sample_rate)
        merge_raw.extend([0.0] * (int(0.15 * sample_rate) - len(merge_raw)))

        blend = _mix_samples(cyan_raw, amber_raw, merge_raw)
        env   = _apply_envelope(blend, 0.01, 0.03, 0.6, 0.11, sample_rate)
        rev   = _apply_reverb(env, decay=0.2, delay_ms=30.0,
                                sample_rate=sample_rate)
        return _apply_lowpass_filter(rev, 2800.0, sample_rate)


def _generate_terminal_open_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the terminal panel expand sound.
    Profile: Mechanical slide downward — low to high 'whoosh' ending in click.
    """
    # Downward frequency sweep (220 → 110 Hz) = panel sliding down
    slide_samples: List[float] = []
    duration    = 0.12
    num_samples = int(duration * sample_rate)
    freq_start  = 380.0
    freq_end    = 180.0
    phase_acc   = 0.0

    for i in range(num_samples):
        t_norm    = i / num_samples
        freq      = freq_start + (freq_end - freq_start) * t_norm
        phase_acc += 2.0 * math.pi * freq / sample_rate
        slide_samples.append(0.7 * math.sin(phase_acc))

    slide = _apply_envelope(slide_samples, 0.005, 0.01, 0.7, 0.1, sample_rate)

    # Terminal click at end
    click_noise = _make_noise_burst(0.008, 0.6, sample_rate, seed=42)
    click       = _apply_envelope(click_noise, 0.001, 0.002, 0.3, 0.005,
                                   sample_rate)

    full = _concatenate_samples(slide, click, gap_secs=0.005,
                                  sample_rate=sample_rate)
    return _apply_lowpass_filter(full, 2500.0, sample_rate)


def _generate_terminal_close_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the terminal panel collapse sound.
    Profile: Upward 'snap' — reverse of open sound.
    """
    slide_samples: List[float] = []
    duration    = 0.10
    num_samples = int(duration * sample_rate)
    freq_start  = 180.0
    freq_end    = 420.0
    phase_acc   = 0.0

    for i in range(num_samples):
        t_norm    = i / num_samples
        freq      = freq_start + (freq_end - freq_start) * t_norm
        phase_acc += 2.0 * math.pi * freq / sample_rate
        slide_samples.append(0.6 * math.sin(phase_acc))

    slide = _apply_envelope(slide_samples, 0.003, 0.008, 0.65, 0.089,
                              sample_rate)
    click_noise = _make_noise_burst(0.006, 0.5, sample_rate, seed=99)
    click       = _apply_envelope(click_noise, 0.001, 0.001, 0.2, 0.004,
                                   sample_rate)

    full = _concatenate_samples(slide, click, gap_secs=0.003,
                                  sample_rate=sample_rate)
    return _apply_lowpass_filter(full, 3000.0, sample_rate)


def _generate_news_click_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the news item / globe pin click sound.
    Profile: Access-granted variant — single clean ascending chirp.
    """
    chirp_raw = _make_sine_wave(1047.0, 0.055, 0.85, sample_rate)
    harmonic  = _make_sine_wave(2093.0, 0.055, 0.12, sample_rate)
    blended   = _mix_samples(chirp_raw, harmonic)
    env       = _apply_envelope(blended, 0.003, 0.01, 0.55, 0.042, sample_rate)
    return _apply_lowpass_filter(env, 4000.0, sample_rate)


def _generate_brainstorm_enter_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the brainstorm mode entry sound.
    Profile: Deep space ping variant — everything fades to focus.
    Lower frequency, slower onset for dramatic effect.
    """
    primary   = _make_sine_wave(165.0, 1.2, 0.9, sample_rate)
    secondary = _make_sine_wave(110.0, 1.2, 0.4, sample_rate)
    tertiary  = _make_sine_wave(220.0, 0.5, 0.2, sample_rate)
    tertiary.extend([0.0] * (int(1.2 * sample_rate) - len(tertiary)))

    blended = _mix_samples(primary, secondary, tertiary)
    env     = _apply_envelope(blended, 0.03, 0.1, 0.6, 1.07, sample_rate)
    reverbed = _apply_reverb(env, decay=0.55, delay_ms=100.0, sample_rate=sample_rate)
    return _apply_lowpass_filter(reverbed, 600.0, sample_rate)


def _generate_brainstorm_exit_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the brainstorm mode exit sound.
    Profile: Systems coming back online — rising from deep to bright.
    """
    sweep_samples: List[float] = []
    duration    = 0.35
    num_samples = int(duration * sample_rate)
    freq_start  = 165.0
    freq_end    = 880.0
    phase_acc   = 0.0

    for i in range(num_samples):
        t_norm    = i / num_samples
        # Exponential sweep upward
        freq      = freq_start * ((freq_end / freq_start) ** t_norm)
        phase_acc += 2.0 * math.pi * freq / sample_rate
        sweep_samples.append(0.75 * math.sin(phase_acc))

    env = _apply_envelope(sweep_samples, 0.01, 0.03, 0.7, 0.31, sample_rate)
    return _apply_lowpass_filter(env, 5000.0, sample_rate)


def _generate_message_receive_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the incoming social message notification sound.
    Profile: Soft two-tone chime — friendly, non-intrusive.
    """
    t1_raw = _make_sine_wave(880.0, 0.08, 0.6, sample_rate)
    t2_raw = _make_sine_wave(1108.0, 0.1, 0.6, sample_rate)
    t1 = _apply_envelope(t1_raw, 0.004, 0.015, 0.5, 0.061, sample_rate)
    t2 = _apply_envelope(t2_raw, 0.004, 0.015, 0.5, 0.081, sample_rate)
    full = _concatenate_samples(t1, t2, gap_secs=0.02, sample_rate=sample_rate)
    return _apply_lowpass_filter(full, 3500.0, sample_rate)


def _generate_message_sent_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the outgoing message sent confirmation sound.
    Profile: Access granted variant, slightly higher — success confirmation.
    """
    t1_raw = _make_sine_wave(1047.0, 0.06, 0.7, sample_rate)
    t2_raw = _make_sine_wave(1319.0, 0.08, 0.7, sample_rate)
    t1 = _apply_envelope(t1_raw, 0.003, 0.012, 0.55, 0.045, sample_rate)
    t2 = _apply_envelope(t2_raw, 0.003, 0.012, 0.55, 0.065, sample_rate)
    full = _concatenate_samples(t1, t2, gap_secs=0.015, sample_rate=sample_rate)
    return _apply_lowpass_filter(full, 4000.0, sample_rate)


def _generate_commit_push_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the GitHub commit+push success sound.
    Profile: Thinking machine variant + final resolution chord.
    """
    # Quick click burst (abbreviated thinking machine)
    click_seq: List[float] = []
    for i in range(8):
        noise = _make_noise_burst(0.004, 0.35, sample_rate, seed=i + 200)
        env   = _apply_envelope(noise, 0.0005, 0.001, 0.2, 0.0025, sample_rate)
        click_seq.extend(env)
        if i < 7:
            click_seq.extend([0.0] * int(0.012 * sample_rate))

    # Resolution chord
    chord1 = _make_sine_wave(523.0, 0.18, 0.5, sample_rate)
    chord2 = _make_sine_wave(659.0, 0.18, 0.5, sample_rate)
    chord3 = _make_sine_wave(784.0, 0.18, 0.4, sample_rate)
    chord  = _mix_samples(chord1, chord2, chord3)
    chord_env = _apply_envelope(chord, 0.01, 0.03, 0.6, 0.14, sample_rate)

    full = _concatenate_samples(click_seq, chord_env, gap_secs=0.02,
                                  sample_rate=sample_rate)
    return _apply_lowpass_filter(full, 3500.0, sample_rate)


def _generate_orb_activate_sound(sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Generates the orb activation / click sound.
    Profile: Soft resonant tap — like tapping a glass sphere.
    """
    tap_raw   = _make_sine_wave(1760.0, 0.12, 0.7, sample_rate)
    undertone = _make_sine_wave(880.0,  0.12, 0.2, sample_rate)
    blended   = _mix_samples(tap_raw, undertone)
    env       = _apply_envelope(blended, 0.001, 0.005, 0.3, 0.114, sample_rate)
    reverbed  = _apply_reverb(env, decay=0.15, delay_ms=35.0, sample_rate=sample_rate)
    return _apply_lowpass_filter(reverbed, 5000.0, sample_rate)


# =============================================================================
# SECTION 5: SOUND BANK — CACHE & LOADER
# =============================================================================

class SoundBank:
    """
    Manages the complete library of loaded and generated sounds.
    On initialization:
        1. Attempts to load WAV files from assets/sounds/ (sound1-4.wav).
        2. Falls back to procedural generation for any missing file.
        3. Pre-generates all UI sound subcategories procedurally.
        4. Stores everything as pygame.mixer.Sound objects in a cache dict.

    Provides get(category) for O(1) sound retrieval.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self._sample_rate: int                              = sample_rate
        self._cache:       Dict[int, "pygame.mixer.Sound"] = {}
        self._load_errors: Dict[int, str]                  = {}
        self._generated:   Dict[int, bool]                 = {}

    def load_all(self) -> None:
        """
        Loads all sounds into the cache.
        File-backed sounds (1-4) attempt WAV load first.
        All UI sub-sounds are generated procedurally.
        """
        # --- Primary 4 sounds: try file load, fallback to procedural ---

        file_map: Dict[int, str] = {
            SOUND_CAT_ACCESS_GRANTED:   SOUND_ACCESS_GRANTED,
            SOUND_CAT_THINKING_MACHINE: SOUND_THINKING_MACHINE,
            SOUND_CAT_DEEP_SPACE_PING:  SOUND_DEEP_SPACE_PING,
            SOUND_CAT_ALERT_ALARM:      SOUND_ALERT_ALARM,
        }

        generator_map: Dict[int, callable] = {
            SOUND_CAT_ACCESS_GRANTED:   _generate_access_granted_chirp,
            SOUND_CAT_THINKING_MACHINE: _generate_thinking_machine_click,
            SOUND_CAT_DEEP_SPACE_PING:  _generate_deep_space_ping,
            SOUND_CAT_ALERT_ALARM:      _generate_alert_alarm,
        }

        for cat, filepath in file_map.items():
            loaded = self._try_load_wav(cat, filepath)
            if not loaded:
                # Procedural fallback
                samples = generator_map[cat](self._sample_rate)
                sound   = _samples_to_pygame_sound(samples, self._sample_rate)
                if sound is not None:
                    self._cache[cat]     = sound
                    self._generated[cat] = True
                else:
                    self._load_errors[cat] = "Failed to create pygame Sound"

        # --- UI subcategory sounds: all procedural ---
        ui_generators: Dict[int, callable] = {
            SOUND_CAT_MODE_SWITCH:      lambda: _generate_mode_switch_sound(
                                            UIMode.ARCHER, self._sample_rate),
            SOUND_CAT_ORB_ACTIVATE:     lambda: _generate_orb_activate_sound(
                                            self._sample_rate),
            SOUND_CAT_TERMINAL_OPEN:    lambda: _generate_terminal_open_sound(
                                            self._sample_rate),
            SOUND_CAT_TERMINAL_CLOSE:   lambda: _generate_terminal_close_sound(
                                            self._sample_rate),
            SOUND_CAT_NEWS_CLICK:       lambda: _generate_news_click_sound(
                                            self._sample_rate),
            SOUND_CAT_GLOBE_CLICK:      lambda: _generate_news_click_sound(
                                            self._sample_rate),
            SOUND_CAT_COMMIT_PUSH:      lambda: _generate_commit_push_sound(
                                            self._sample_rate),
            SOUND_CAT_BRAINSTORM_ENTER: lambda: _generate_brainstorm_enter_sound(
                                            self._sample_rate),
            SOUND_CAT_BRAINSTORM_EXIT:  lambda: _generate_brainstorm_exit_sound(
                                            self._sample_rate),
            SOUND_CAT_MESSAGE_RECEIVE:  lambda: _generate_message_receive_sound(
                                            self._sample_rate),
            SOUND_CAT_MESSAGE_SENT:     lambda: _generate_message_sent_sound(
                                            self._sample_rate),
        }

        for cat, gen_fn in ui_generators.items():
            try:
                samples = gen_fn()
                sound   = _samples_to_pygame_sound(samples, self._sample_rate)
                if sound is not None:
                    self._cache[cat]     = sound
                    self._generated[cat] = True
                else:
                    self._load_errors[cat] = "pygame Sound creation failed"
            except Exception as exc:
                self._load_errors[cat] = str(exc)

    def load_mode_sounds(self) -> None:
        """
        Generates and caches mode-specific switch sounds for HUDSON and BOTH.
        Called after initial load_all() to add remaining mode variants.
        """
        mode_map = {
            101: UIMode.ARCHER,
            102: UIMode.HUDSON,
            103: UIMode.BOTH,
        }
        for cat, mode in mode_map.items():
            try:
                samples = _generate_mode_switch_sound(mode, self._sample_rate)
                sound   = _samples_to_pygame_sound(samples, self._sample_rate)
                if sound is not None:
                    self._cache[cat]     = sound
                    self._generated[cat] = True
            except Exception as exc:
                self._load_errors[cat] = str(exc)

    def _try_load_wav(self, category: int, filepath: str) -> bool:
        """
        Attempts to load a WAV file into the pygame mixer.

        Args:
            category: Sound category integer key.
            filepath: Absolute path to the WAV file.

        Returns:
            True if loaded successfully, False otherwise.
        """
        if not PYGAME_AVAILABLE:
            return False
        if not os.path.isfile(filepath):
            return False
        try:
            sound = pygame.mixer.Sound(filepath)
            self._cache[category]     = sound
            self._generated[category] = False
            return True
        except Exception as exc:
            self._load_errors[category] = f"WAV load error: {exc}"
            return False

    def get(self, category: int) -> Optional["pygame.mixer.Sound"]:
        """
        Retrieves a cached sound by category.

        Args:
            category: Sound category integer constant.

        Returns:
            pygame.mixer.Sound object, or None if not cached.
        """
        return self._cache.get(category, None)

    def get_load_report(self) -> Dict[str, any]:
        """
        Returns a diagnostic report of load results.

        Returns:
            Dict with keys: loaded_count, generated_count, error_count, errors.
        """
        file_loaded   = sum(1 for v in self._generated.values() if not v)
        gen_loaded    = sum(1 for v in self._generated.values() if v)
        return {
            "loaded_count":    file_loaded,
            "generated_count": gen_loaded,
            "error_count":     len(self._load_errors),
            "errors":          dict(self._load_errors),
            "total_cached":    len(self._cache),
        }

    def __repr__(self) -> str:
        report = self.get_load_report()
        return (f"SoundBank("
                f"cached={report['total_cached']}, "
                f"file_loaded={report['loaded_count']}, "
                f"generated={report['generated_count']}, "
                f"errors={report['error_count']})")


# =============================================================================
# SECTION 6: PLAYBACK REQUEST
# =============================================================================

class PlaybackRequest:
    """
    Encapsulates a single sound playback request with volume and channel info.
    Placed into the playback queue by the event bus handler.
    """

    __slots__ = ("category", "volume", "loops", "timestamp")

    def __init__(
        self,
        category: int,
        volume:   float = VOLUME_MASTER,
        loops:    int   = 0,
    ) -> None:
        """
        Args:
            category: Sound category integer constant.
            volume:   Playback volume [0.0, 1.0].
            loops:    Number of additional loops (0 = play once).
        """
        self.category:  int   = category
        self.volume:    float = max(0.0, min(1.0, volume))
        self.loops:     int   = loops
        self.timestamp: float = time.time()

    def __repr__(self) -> str:
        return (f"PlaybackRequest(cat={self.category}, "
                f"vol={self.volume:.2f}, loops={self.loops})")


# =============================================================================
# SECTION 7: AUDIO ENGINE — MAIN CONTROLLER
# =============================================================================

class AudioEngine:
    """
    Central audio controller for Project HERMES.

    Responsibilities:
        - Initializes pygame.mixer with correct parameters.
        - Owns the SoundBank (load + cache all sounds).
        - Provides play(category) for immediate main-thread playback.
        - Maintains a thread-safe playback queue for cross-thread requests.
        - Manages mute state globally.
        - Handles mode-switch sound variants (Archer/Hudson/Both).
        - Provides volume control per category group.

    Designed to be called from the main pygame thread for actual playback.
    Background daemons push PlaybackRequest objects into the queue.
    The main frame loop calls drain_queue() once per frame.
    """

    def __init__(self) -> None:
        self._initialized:    bool                  = False
        self._muted:          bool                  = False
        self._master_volume:  float                 = VOLUME_MASTER
        self._sound_bank:     SoundBank             = SoundBank(SAMPLE_RATE)
        self._play_queue:     queue.Queue           = queue.Queue(maxsize=50)
        self._active_channels: Dict[int, any]       = {}
        self._last_play_time: Dict[int, float]      = {}
        self._debounce_secs:  float                 = 0.05   # 50ms debounce

        # Currently looping alert channel (for stopping alerts)
        self._alert_channel:  Optional[any]         = None
        self._alert_active:   bool                  = False

    def initialize(self) -> bool:
        """
        Initializes the pygame mixer and loads the sound bank.
        Must be called after pygame.init() and before any playback.

        Returns:
            True if initialization succeeded, False on failure.
        """
        if not PYGAME_AVAILABLE:
            print("[AudioEngine] pygame not available — audio disabled.")
            return False

        try:
            pygame.mixer.pre_init(
                frequency=SAMPLE_RATE,
                size=-BIT_DEPTH,         # negative = signed
                channels=CHANNELS,
                buffer=MIXER_BUFFER,
            )
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)   # 16 concurrent channels

            self._sound_bank.load_all()
            self._sound_bank.load_mode_sounds()

            report = self._sound_bank.get_load_report()
            print(
                f"[AudioEngine] Initialized. "
                f"Cached={report['total_cached']} sounds "
                f"({report['loaded_count']} from file, "
                f"{report['generated_count']} procedural, "
                f"{report['error_count']} errors)."
            )

            if report["errors"]:
                for cat, err in report["errors"].items():
                    print(f"  [AudioEngine] Sound cat {cat} error: {err}")

            self._initialized = True
            return True

        except Exception as exc:
            print(f"[AudioEngine] Initialization failed: {exc}")
            self._initialized = False
            return False

    def play(
        self,
        category: int,
        volume:   Optional[float] = None,
        loops:    int             = 0,
        force:    bool            = False,
    ) -> bool:
        """
        Immediately plays a sound by category on the calling thread.
        Must be called from the main pygame thread.

        Debouncing: Repeated calls for the same category within
        _debounce_secs are silently ignored (prevents audio spam).

        Args:
            category: Sound category integer constant.
            volume:   Override volume [0.0, 1.0]. None = use category default.
            loops:    Additional play loops (0 = once).
            force:    If True, bypass debounce check.

        Returns:
            True if sound was played, False if skipped/failed.
        """
        if not self._initialized or self._muted:
            return False

        # Debounce check
        now = time.time()
        if not force:
            last = self._last_play_time.get(category, 0.0)
            if now - last < self._debounce_secs:
                return False

        sound = self._sound_bank.get(category)
        if sound is None:
            return False

        # Determine volume
        vol = volume if volume is not None else self._get_category_volume(category)
        vol = max(0.0, min(1.0, vol * self._master_volume))

        try:
            sound.set_volume(vol)
            channel = sound.play(loops=loops)
            if channel is not None:
                self._active_channels[category] = channel
                if category == SOUND_CAT_ALERT_ALARM:
                    self._alert_channel = channel
                    self._alert_active  = True
            self._last_play_time[category] = now
            return True
        except Exception as exc:
            print(f"[AudioEngine] Playback error (cat={category}): {exc}")
            return False

    def play_mode_switch(self, mode: str) -> bool:
        """
        Plays the mode-specific switch confirmation sound.

        Args:
            mode: UIMode string ("ARCHER", "HUDSON", or "BOTH").

        Returns:
            True if played successfully.
        """
        mode_cat_map = {
            UIMode.ARCHER: 101,
            UIMode.HUDSON: 102,
            UIMode.BOTH:   103,
        }
        cat = mode_cat_map.get(mode, SOUND_CAT_ACCESS_GRANTED)
        return self.play(cat, volume=VOLUME_UI, force=True)

    def stop_alert(self) -> None:
        """
        Stops the currently playing alert alarm sound.
        Called when an alert is dismissed.
        """
        if self._alert_channel is not None:
            try:
                self._alert_channel.stop()
            except Exception:
                pass
            self._alert_channel = None
            self._alert_active  = False

    def enqueue(
        self,
        category: int,
        volume:   Optional[float] = None,
        loops:    int             = 0,
    ) -> None:
        """
        Adds a PlaybackRequest to the thread-safe queue.
        Called from background daemon threads.
        The main frame loop drains this queue via drain_queue().

        Args:
            category: Sound category integer constant.
            volume:   Override volume. None = use category default.
            loops:    Additional play loops.
        """
        vol = volume if volume is not None else self._get_category_volume(category)
        req = PlaybackRequest(category=category, volume=vol, loops=loops)
        try:
            self._play_queue.put_nowait(req)
        except queue.Full:
            pass   # Drop if queue full — audio is non-critical

    def drain_queue(self) -> int:
        """
        Processes all pending PlaybackRequests from the queue.
        Must be called once per frame from the main pygame thread.

        Returns:
            Number of sounds played in this drain cycle.
        """
        played = 0
        while True:
            try:
                req = self._play_queue.get_nowait()
                if self.play(req.category, volume=req.volume,
                              loops=req.loops):
                    played += 1
            except queue.Empty:
                break
        return played

    def set_muted(self, muted: bool) -> None:
        """
        Sets the global mute state.
        When muted, all play() calls return False immediately.

        Args:
            muted: True to mute, False to unmute.
        """
        self._muted = muted
        if muted and PYGAME_AVAILABLE and self._initialized:
            # Stop all currently playing sounds
            pygame.mixer.stop()
        print(f"[AudioEngine] {'MUTED' if muted else 'UNMUTED'}")

    def set_master_volume(self, volume: float) -> None:
        """
        Sets the master volume scalar applied to all playback.

        Args:
            volume: Master volume [0.0, 1.0].
        """
        self._master_volume = max(0.0, min(1.0, volume))

    def is_muted(self) -> bool:
        """Returns True if audio is currently muted."""
        return self._muted

    def is_initialized(self) -> bool:
        """Returns True if the mixer was successfully initialized."""
        return self._initialized

    def is_alert_active(self) -> bool:
        """Returns True if an alert alarm is currently playing."""
        return self._alert_active

    def _get_category_volume(self, category: int) -> float:
        """
        Returns the default volume for a given sound category.

        Args:
            category: Sound category integer constant.

        Returns:
            Default volume float [0.0, 1.0].
        """
        if category == SOUND_CAT_ALERT_ALARM:
            return VOLUME_ALERT
        if category in (SOUND_CAT_DEEP_SPACE_PING,
                         SOUND_CAT_BRAINSTORM_ENTER,
                         SOUND_CAT_BRAINSTORM_EXIT):
            return VOLUME_AMBIENT
        return VOLUME_UI

    def shutdown(self) -> None:
        """
        Cleanly shuts down the audio engine.
        Stops all playback and quits the mixer.
        Called during application exit sequence.
        """
        if not self._initialized:
            return
        try:
            pygame.mixer.stop()
            pygame.mixer.quit()
        except Exception:
            pass
        self._initialized = False
        print("[AudioEngine] Shutdown complete.")

    def get_diagnostics(self) -> Dict[str, any]:
        """
        Returns a diagnostic snapshot of the audio engine state.

        Returns:
            Dict with keys: initialized, muted, master_volume,
            queue_depth, alert_active, cached_sounds.
        """
        report = self._sound_bank.get_load_report()
        return {
            "initialized":    self._initialized,
            "muted":          self._muted,
            "master_volume":  self._master_volume,
            "queue_depth":    self._play_queue.qsize(),
            "alert_active":   self._alert_active,
            "cached_sounds":  report["total_cached"],
            "load_errors":    report["error_count"],
        }

    def __repr__(self) -> str:
        return (f"AudioEngine("
                f"initialized={self._initialized}, "
                f"muted={self._muted}, "
                f"vol={self._master_volume:.2f}, "
                f"bank={self._sound_bank})")


# =============================================================================
# SECTION 8: MODULE-LEVEL SINGLETON
# =============================================================================

# Single global instance shared across all modules.
# Import directly: from audio_engine import audio_engine
audio_engine: AudioEngine = AudioEngine()


# =============================================================================
# END OF audio_engine.py
# =============================================================================