#!/usr/bin/env python3
"""
Build Sigil demo video for VP/Director audience.
Uses Pillow to render title cards, ffmpeg to assemble.
Output: sigil-demo.mp4  (~75 seconds)
"""

import subprocess
import os
import tempfile
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FRAMES_DIR = Path(__file__).parent
OUT = FRAMES_DIR.parent / "sigil-demo.mp4"
TMP = FRAMES_DIR / "_tmp_cards"
TMP.mkdir(exist_ok=True)

W, H = 1280, 800
FPS  = 30

# ── Brand colours ────────────────────────────────────────────────────────────
BG       = (11,  12,  20)
BG2      = (15,  17,  23)
ACCENT   = (99, 102, 241)
ACCENT2  = (139, 92, 246)
WHITE    = (248, 250, 252)
MUTED    = (139, 139, 168)
DIM      = (74,  74, 106)

# ── Font helpers ─────────────────────────────────────────────────────────────
FONT_PATHS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

def _load(size, bold=False):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size, index=1 if bold else 0)
        except Exception:
            pass
    return ImageFont.load_default()

FONT_HUGE   = _load(72, bold=True)
FONT_BIG    = _load(52, bold=True)
FONT_MED    = _load(28)
FONT_SMALL  = _load(20)
FONT_LABEL  = _load(18)
FONT_CODE   = _load(20)

def _text_width(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2] - bb[0]

def _center_x(draw, text, font):
    return (W - _text_width(draw, text, font)) // 2

def _hex_accent_bar(draw, y=H-8, width=120, color=ACCENT):
    x0 = (W - width) // 2
    draw.rounded_rectangle([x0, y-3, x0+width, y+3], radius=3, fill=color)

def _bg_gradient(img):
    """Subtle radial glow in centre."""
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = W//2, H//2
    for r in range(300, 0, -10):
        alpha = max(0, int((300-r)/300 * 18))
        draw.ellipse([cx-r, cy-r, cx+r, cy+r],
                     fill=(*ACCENT, alpha))
    return img

# ── Title card generator ─────────────────────────────────────────────────────
def make_title_card(path, title, subtitle="", tagline=""):
    img = Image.new("RGB", (W, H), BG)
    img = _bg_gradient(img)
    draw = ImageDraw.Draw(img)

    # Top rule
    draw.line([(80, 52), (W-80, 52)], fill=(*ACCENT, 60), width=1)

    # Title
    lines = title.split("\n")
    font = FONT_BIG if len(title) > 30 else FONT_HUGE
    total_h = len(lines) * (font.size + 10)
    y0 = H//2 - total_h//2 - (50 if subtitle else 0)
    for line in lines:
        x = _center_x(draw, line, font)
        draw.text((x+2, y0+2), line, font=font, fill=(0,0,0,120))
        draw.text((x, y0), line, font=font, fill=WHITE)
        y0 += font.size + 12

    # Subtitle block
    if subtitle:
        sy = y0 + 24
        for line in subtitle.split("\n"):
            # detect code lines
            f = FONT_CODE if line.startswith(" ") or line.startswith("cd ") or line.startswith("git ") or "uvicorn" in line else FONT_MED
            col = (180, 190, 210) if f is FONT_CODE else MUTED
            x = _center_x(draw, line, f)
            draw.text((x, sy), line, font=f, fill=col)
            sy += f.size + 10

    # Tagline at bottom
    if tagline:
        x = _center_x(draw, tagline, FONT_LABEL)
        draw.text((x, H-52), tagline, font=FONT_LABEL, fill=ACCENT)

    # Accent bar
    _hex_accent_bar(draw)

    # Bottom rule
    draw.line([(80, H-18), (W-80, H-18)], fill=(*ACCENT, 40), width=1)

    img.save(path, "PNG")

# ── Screenshot compositor ────────────────────────────────────────────────────
def make_screen_card(path, src_path, label=""):
    src = Image.open(src_path).convert("RGB")
    # Scale to fill 1280×800
    src = src.resize((W, H), Image.LANCZOS)
    draw = ImageDraw.Draw(src)

    if label:
        # Bottom label bar
        bar_h = 48
        draw.rectangle([(0, H-bar_h), (W, H)], fill=(11,12,20,220))
        x = _center_x(draw, label, FONT_LABEL)
        draw.text((x, H-bar_h+15), label, font=FONT_LABEL, fill=WHITE)
        # Accent line above bar
        draw.line([(0, H-bar_h), (W, H-bar_h)], fill=ACCENT, width=1)

    src.save(path, "PNG")

# ── Segment list ─────────────────────────────────────────────────────────────
# (type, src_filename_or_None, duration_sec, title, subtitle, label/tagline)
SEGMENTS = [
    ("title",  None,                     3.5,
     "SIGIL",
     "Developer Intelligence Platform",
     "github.com/RajuRoopani/sigil-ai"),

    ("title",  None,                     4.0,
     "The Problem",
     "Your best engineers carry years of invisible expertise.\n"
     "It lives in commits, diffs, PR threads — and evaporates\n"
     "when they leave, burn out, or go on vacation.",
     ""),

    ("title",  None,                     3.5,
     "The Solution",
     "Point Sigil at any repo + developer.\n"
     "In under a minute: a complete AI replica\n"
     "of their expertise — deployable anywhere.",
     ""),

    ("screen", "demo-01-home.png",       3.5,
     "", "", "Step 1 — Enter any GitHub or Azure DevOps repo + developer username"),

    ("screen", "demo-02-home-filled.png",3.0,
     "", "", "Works with public repos, private repos, and enterprise Azure DevOps"),

    ("screen", "demo-03-profile-hero.png",4.5,
     "", "", "Claude reads every commit, diff, PR, review thread, and work item"),

    ("screen", "demo-04-mindmap.png",    4.0,
     "", "", "Skill Sigil — zoomable radial map of every competency cluster"),

    ("screen", "demo-05-skills.png",     4.0,
     "", "", "Every skill scored with commit evidence — not self-reported, not guessed"),

    ("screen", "demo-06-commits.png",    3.5,
     "", "", "Every analyzed commit links back to the original — fully auditable"),

    ("screen", "demo-07-agent-btn.png",  3.5,
     "", "", "Step 2 — Turn any profile into a live AI agent with one click"),

    ("screen", "demo-08-chat-open.png",  3.0,
     "", "", "The agent loads identity.md + soul.md as its system prompt"),

    ("screen", "demo-09-chat-question.png", 2.5,
     "", "", "Ask it anything — architecture decisions, code review, debugging instincts"),

    ("screen", "demo-10-chat-response.png", 5.5,
     "", "", "Responds in their voice — their vocabulary, opinions, and domain depth"),

    ("screen", "demo-11-agent-files.png",4.0,
     "", "", "Output: identity.md + soul.md — drop into any Claude-based agent system"),

    ("screen", "demo-12-past-sigils.png",4.0,
     "", "", "Your entire team's expertise — cached, searchable, queryable on demand"),

    ("title",  None,                     4.5,
     "7 Signals → 3 Artifacts → ∞ Agents",
     "Commits  ·  Diffs  ·  PRs  ·  Review Threads\n"
     "Work Items  ·  Repo Tree  ·  Key Files\n\n"
     "GitHub & Azure DevOps  ·  No Database  ·  Zero Infrastructure",
     ""),

    ("title",  None,                     5.0,
     "Try It Today",
     " git clone github.com/RajuRoopani/sigil-ai\n"
     " cd sigil-ai/backend\n"
     " pip install -r requirements.txt\n"
     " uvicorn main:app --port 8003",
     "The best engineers leave traces everywhere. Sigil reads them."),
]

# ── Generate all frame images ────────────────────────────────────────────────
def generate_frames():
    frame_specs = []  # (path, duration)
    for i, seg in enumerate(SEGMENTS):
        stype, src, dur, title, subtitle, label = seg
        out_path = TMP / f"frame_{i:03d}.png"

        if stype == "title":
            make_title_card(out_path, title, subtitle, label)
        else:
            make_screen_card(out_path, FRAMES_DIR / src, label)

        frame_specs.append((out_path, dur))
        print(f"  [{i+1:2d}/{len(SEGMENTS)}] {out_path.name}")

    return frame_specs

# ── Build video with crossfades ──────────────────────────────────────────────
def build_video(frame_specs):
    # Generate per-frame video clips, then concatenate with xfade
    FADE = 0.4  # seconds of crossfade
    clips = []

    for idx, (path, dur) in enumerate(frame_specs):
        clip = TMP / f"clip_{idx:03d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(path),
            "-t", str(dur),
            "-vf", f"scale={W}:{H},fps={FPS}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(clip)
        ], capture_output=True, check=True)
        clips.append(clip)
        print(f"  clip {idx+1}/{len(frame_specs)}")

    # Concatenate with xfade transitions
    print("  Concatenating with crossfades…")
    if len(clips) == 1:
        import shutil
        shutil.copy(clips[0], OUT)
        return

    # Build xfade filter chain
    n = len(clips)
    # Calculate offset for each xfade (cumulative duration minus fade overlaps)
    durations = [s[1] for s in frame_specs]
    offsets = []
    t = 0.0
    for i in range(n - 1):
        t += durations[i] - FADE
        offsets.append(round(t, 3))

    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    # Build filter: chain xfades
    filt_parts = []
    for i in range(n - 1):
        inp_a = f"[xf{i}]" if i > 0 else f"[0:v]"
        inp_b = f"[{i+1}:v]"
        out_l = f"[xf{i+1}]" if i < n-2 else "[outv]"
        filt_parts.append(
            f"{inp_a}{inp_b}xfade=transition=fade:duration={FADE}:offset={offsets[i]}{out_l}"
        )

    filtergraph = ";".join(filt_parts)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filtergraph,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(OUT),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-2000:])
        raise RuntimeError("ffmpeg concat failed")

def main():
    print("Generating frame images…")
    frame_specs = generate_frames()
    print(f"\nBuilding video ({len(frame_specs)} segments)…")
    build_video(frame_specs)
    size_mb = OUT.stat().st_size / 1e6
    total_dur = sum(s[1] for s in frame_specs)
    print(f"\n✓ Done → {OUT}")
    print(f"  Duration : {total_dur:.1f}s")
    print(f"  File size: {size_mb:.1f} MB")

if __name__ == "__main__":
    main()
