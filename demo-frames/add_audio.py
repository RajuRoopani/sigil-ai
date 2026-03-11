#!/usr/bin/env python3
"""
Add professional narration + ambient background music to sigil-demo.mp4.
Output: sigil-demo-narrated.mp4

Pipeline:
  1. Generate per-segment narration using macOS `say -v Samantha`
  2. Each clip padded with silence to segment duration (no speedup > 1.15×)
  3. Concatenate into a single narration track
  4. Synthesize a cinematic ambient pad (numpy)
  5. Mix narration (100%) + music (14%) with ffmpeg
  6. Mux audio with existing video
"""

import subprocess, wave
from pathlib import Path
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = Path(__file__).parent
ROOT      = HERE.parent
VIDEO_IN  = ROOT / "sigil-demo.mp4"
VIDEO_OUT = ROOT / "sigil-demo-narrated.mp4"
TMP       = HERE / "_tmp_audio"
TMP.mkdir(exist_ok=True)

SAMPLE_RATE = 44100
VOICE       = "Samantha"
RATE        = 165   # measured, human-paced (Apple Keynote style)

# ── Narration script ───────────────────────────────────────────────────────────
# Scripts trimmed to ~70 % of each segment so they land with natural breathing room.
# At rate=165, effective pace ≈ 1.5–1.6 words/sec including punctuation pauses.
# Atempo ceiling: 1.15× (barely perceptible even in headphones).
NARRATION = [
    # (segment_dur_sec, narration_text)

    (3.5,  "Sigil. The Developer Intelligence Platform."),

    (4.0,  "Engineers carry invisible expertise. "
           "It vanishes when they leave."),

    (3.5,  "Sigil captures it. Any repo. Complete AI replica."),

    (3.5,  "Enter a GitHub or Azure DevOps repo "
           "and a developer username."),

    (3.0,  "GitHub, Azure DevOps — all repos supported."),

    (4.5,  "Claude reads every commit, diff, pull request, "
           "and review thread."),

    (4.0,  "The Skill Sigil — a radial map of every competency."),

    (4.0,  "Every skill scored from real commit evidence. "
           "Not self-reported."),

    (3.5,  "Every commit links back to source. Fully auditable."),

    (3.5,  "One click — any profile becomes a live AI agent."),

    (3.0,  "Their identity loads as the agent's system prompt."),

    (2.5,  "Ask it anything."),

    (5.5,  "It responds in their voice, vocabulary, and depth. "
           "Expertise that never has to leave."),

    (4.0,  "Output: identity and soul files. "
           "Drop into any system."),

    (4.0,  "Your whole team's expertise — "
           "cached and queryable on demand."),

    (4.5,  "Seven signals. Three artifacts. Infinite agents."),

    (5.0,  "Clone the repo today. "
           "The best engineers leave traces everywhere. "
           "Sigil reads them."),
]

# ── 1. Generate per-segment narration WAVs ────────────────────────────────────
def generate_narration_clips():
    clips = []
    for i, (dur, text) in enumerate(NARRATION):
        aiff   = TMP / f"narr_{i:03d}.aiff"
        wav    = TMP / f"narr_{i:03d}.wav"
        padded = TMP / f"narr_{i:03d}_padded.wav"

        # macOS say → AIFF
        subprocess.run(
            ["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text],
            check=True, capture_output=True
        )

        # AIFF → stereo WAV 44.1 kHz
        subprocess.run([
            "ffmpeg", "-y", "-i", str(aiff),
            "-ar", str(SAMPLE_RATE), "-ac", "2", str(wav)
        ], check=True, capture_output=True)

        # Measure actual narration length
        probe = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(wav)
        ], capture_output=True, text=True)
        narr_dur = float(probe.stdout.strip())

        ratio = narr_dur / dur   # > 1 means narration ran long

        if ratio <= 1.0:
            # Fits — pad with trailing silence to exact segment duration
            subprocess.run([
                "ffmpeg", "-y", "-i", str(wav),
                "-af", f"apad=pad_dur={dur - narr_dur:.3f}",
                "-t", str(dur), str(padded)
            ], check=True, capture_output=True)
            flag = "✓"

        elif ratio <= 1.15:
            # Slight stretch (imperceptible) — atempo then pad
            trim_to = dur * 0.96   # leave 4 % silence after narration
            r = narr_dur / trim_to
            af = f"atempo={r:.4f},afade=t=out:st={trim_to - 0.15:.3f}:d=0.15," \
                 f"apad=pad_dur={dur - trim_to:.3f}"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(wav),
                "-af", af, "-t", str(dur), str(padded)
            ], check=True, capture_output=True)
            flag = f"~{r:.2f}×"

        else:
            # Script still too long — hard trim with fade and pad
            # (shouldn't happen with the calibrated scripts above)
            trim_to = dur * 0.92
            af = f"atrim=0:{trim_to},afade=t=out:st={trim_to - 0.25:.3f}:d=0.25," \
                 f"apad=pad_dur={dur - trim_to:.3f}"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(wav),
                "-af", af, "-t", str(dur), str(padded)
            ], check=True, capture_output=True)
            flag = f"TRIM({ratio:.2f}×)"

        clips.append(padded)
        print(f"  [{i+1:2d}/{len(NARRATION)}] {narr_dur:.2f}s / {dur}s  {flag}")

    return clips


# ── 2. Concatenate narration clips ────────────────────────────────────────────
def concat_narration(clips):
    lst = TMP / "narr_list.txt"
    lst.write_text("\n".join(f"file '{c}'" for c in clips))
    out = TMP / "narration_full.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-ar", str(SAMPLE_RATE), "-ac", "2", str(out)
    ], check=True, capture_output=True)
    return out


# ── 3. Synthesise cinematic ambient pad ───────────────────────────────────────
def make_ambient_music(duration_sec: float) -> Path:
    """
    Am9 voicing (A·C·E·G·B) layered across three octaves.
    Slow LFO tremolo, stereo detuning, smooth fade in/out.
    """
    sr  = SAMPLE_RATE
    n   = int(duration_sec * sr)
    t   = np.linspace(0, duration_sec, n, endpoint=False)

    FREQS = [110.0, 164.81, 220.0, 261.63, 329.63, 392.0, 493.88]
    AMPS  = [0.28,  0.22,   0.20,  0.18,   0.18,   0.14,  0.12  ]

    L = np.zeros(n)
    R = np.zeros(n)
    for freq, amp in zip(FREQS, AMPS):
        detune = 0.18
        wl = amp * (0.85 * np.sin(2*np.pi*freq*t)
                  + 0.15 * np.sin(2*np.pi*freq*2*t))
        wr = amp * (0.85 * np.sin(2*np.pi*(freq+detune)*t)
                  + 0.15 * np.sin(2*np.pi*(freq+detune)*2*t))
        L += wl
        R += wr

    # Gentle 0.07 Hz LFO tremolo
    lfo = 0.88 + 0.12 * np.sin(2 * np.pi * 0.07 * t)
    L *= lfo;  R *= lfo

    # Envelope: 4 s fade-in, 6 s fade-out
    env = np.ones(n)
    fi, fo = int(4*sr), int(6*sr)
    env[:fi]  = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    L *= env;  R *= env

    # Normalise to −12 dBFS
    peak = max(np.max(np.abs(L)), np.max(np.abs(R)), 1e-9)
    tgt  = 10 ** (-12 / 20)
    L = (L / peak * tgt * 32767).astype(np.int16)
    R = (R / peak * tgt * 32767).astype(np.int16)

    out = TMP / "ambient_music.wav"
    with wave.open(str(out), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.column_stack([L, R]).tobytes())
    return out


# ── 4. Mix narration + music ──────────────────────────────────────────────────
def mix_audio(narration: Path, music: Path, total_dur: float) -> Path:
    out = TMP / "final_mix.aac"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(narration),
        "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        "[0:a]volume=1.0[narr];"
        "[1:a]volume=0.14,"
        f"atrim=0:{total_dur},"
        "afade=t=in:st=0:d=3,"
        f"afade=t=out:st={total_dur-5}:d=5[music];"
        "[narr][music]amix=inputs=2:normalize=0[mix]",
        "-map", "[mix]",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(total_dur), str(out)
    ], check=True, capture_output=True)
    return out


# ── 5. Mux into video ─────────────────────────────────────────────────────────
def mux(video: Path, audio: Path, output: Path):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-movflags", "+faststart", str(output)
    ], check=True, capture_output=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    total_dur = sum(d for d, _ in NARRATION)
    print(f"Total duration: {total_dur:.1f}s  |  voice rate: {RATE} WPM\n")

    print("Step 1/4 — Generating narration clips…")
    clips = generate_narration_clips()

    print("\nStep 2/4 — Concatenating narration…")
    narration = concat_narration(clips)

    print(f"\nStep 3/4 — Synthesising ambient pad ({total_dur+2:.0f}s)…")
    music = make_ambient_music(total_dur + 2)

    print("\nStep 4/4 — Mixing & muxing…")
    mix = mix_audio(narration, music, total_dur)
    mux(VIDEO_IN, mix, VIDEO_OUT)

    size_mb = VIDEO_OUT.stat().st_size / 1e6
    print(f"\n✓  {VIDEO_OUT.name}")
    print(f"   Duration : {total_dur:.1f}s")
    print(f"   File size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
