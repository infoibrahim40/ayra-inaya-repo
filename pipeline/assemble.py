"""Stage 4: clips + your voice files -> final MP4 and SRT for each language (ffmpeg)."""
import os
import sys

from common import (ROOT, check_episode, cfg, find_audio, find_clip, load_script, load_shots, out_dir, probe_duration, run)

LANGS = {"en": "eng", "bn": "ben"}


def estimate(text, lang):
    """Fallback duration when a voice file is missing (preview builds)."""
    n = len(text.split())
    return max(1.0, n * 0.42 + 0.4) if lang == "en" else max(1.0, n * 0.5 + 0.4)


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def build(ep, lang):
    c = cfg()["output"]
    o = out_dir(ep)
    script, lines, order = load_script(ep)
    shots = load_shots(ep)
    norm = o / f"norm_{lang}"
    norm.mkdir(exist_ok=True)
    (o / "final").mkdir(exist_ok=True)

    t = 0.0
    concat, events, subs, missing_clips, missing_audio = [], [], [], [], []
    for s in shots:
        clip = find_clip(ep, s["id"])
        if clip is None:
            missing_clips.append(s["id"])
            continue
        clip_len = probe_duration(clip)
        cur, ev = 0.3, []
        for lid in s.get("lines", []):
            a = find_audio(ep, lang, lid)
            if a:
                d = probe_duration(a)
            else:
                missing_audio.append(lid)
                d = estimate(lines[lid][lang], lang)
            ev.append((lid, a, cur, d))
            cur += d + 0.25
        dialog_end = (cur - 0.25) if ev else 0.0
        length = max(clip_len, dialog_end + 0.4)
        pad = max(0.0, length - clip_len) + 0.1
        dest = norm / f"{s['id']}.mp4"
        vf = (f"scale={c['width']}:{c['height']}:force_original_aspect_ratio=decrease,"
              f"pad={c['width']}:{c['height']}:(ow-iw)/2:(oh-ih)/2,fps={c['fps']},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={length:.3f},setpts=PTS-STARTPTS")
        run(["ffmpeg", "-y", "-i", str(clip), "-an", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
             "-crf", "18", "-pix_fmt", "yuv420p", str(dest)])
        concat.append(dest)
        for lid, a, off, d in ev:
            start = t + off
            if a:
                events.append((a, start))
            subs.append((start, start + max(d, 1.2), lines[lid][lang]))
        t += length

    if missing_clips:
        sys.exit("Missing clips (generate or redo these shots first): " + ", ".join(missing_clips))
    if missing_audio:
        print(f"WARNING [{lang}]: no voice file for {len(missing_audio)} lines, using silence: {', '.join(missing_audio)}")

    total = t
    lst = o / f"concat_{lang}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in concat), encoding="utf-8")
    video = o / f"video_{lang}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])

    # audio mix: dialogue placed at exact times (+ optional music)
    audio = o / f"audio_{lang}.wav"
    music = script.get("music")
    cmd = ["ffmpeg", "-y"]
    labels, filt = [], []
    for i, (a, start) in enumerate(events):
        cmd += ["-i", str(a)]
        ms = int(start * 1000)
        filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    idx = len(events)
    if music:
        mp = ROOT / music
        if mp.exists():
            cmd += ["-stream_loop", "-1", "-i", str(mp)]
            filt.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={c['music_volume']},atrim=0:{total:.3f}[mus]")
            labels.append("[mus]")
            idx += 1
        else:
            print(f"WARNING: music file not found: {music}")
    if not labels:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        filt.append("[0:a]anull[sil]")
        labels.append("[sil]")
    mix = "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,apad=whole_dur={total:.3f},loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    filt.append(mix)
    cmd += ["-filter_complex", ";".join(filt), "-map", "[out]", "-t", f"{total:.3f}", str(audio)]
    run(cmd)

    srt = o / "final" / f"{ep}_{lang}.srt"
    with open(srt, "w", encoding="utf-8") as f:
        for n, (a, b, txt) in enumerate(subs, 1):
            f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n\n")

    final = o / "final" / f"{ep}_{lang}.mp4"
    if os.environ.get("BURN_SUBS") == "1":
        font = "Kalpurush" if lang == "bn" else "Arial"
        style = f"FontName={font},FontSize=22,Outline=2,MarginV=40"
        run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-vf",
             f"subtitles={srt}:fontsdir=fonts:force_style='{style}'", "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(final)])
    else:
        run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-i", str(srt), "-map", "0:v", "-map", "1:a",
             "-map", "2", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
             f"-metadata:s:s:0", f"language={LANGS[lang]}", str(final)])
    print(f"Built {final} ({total:.1f}s)")


def main():
    ep = check_episode(sys.argv[1])
    langs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["en", "bn"]
    for lang in langs:
        if lang not in LANGS:
            sys.exit(f"Unknown language {lang}")
        build(ep, lang)


if __name__ == "__main__":
    main()
