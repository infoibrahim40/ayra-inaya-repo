"""Stage 1: script.yaml -> shots.json + lines.csv (uses the Claude API)."""
import csv
import json
import sys

from common import (check_episode, cfg, ep_dir, load_bible, load_script, ROOT)

SYSTEM = ("You are the animation director and AI-video prompt engineer for the original children's series "
          "'Ayra & Inaya'. You turn a script into a precise shot list. Reply with valid JSON only, no markdown.")


def build_request(script, lines, order, chars, locs, props, style, c):
    dur = c["video"]["duration_seconds"]
    scenes = []
    for sc in script["scenes"]:
        scenes.append({"scene": sc["id"], "location_hint": sc.get("location", ""), "summary": sc.get("summary", ""),
                       "lines": [{"line_id": lid, "char": lines[lid]["char"], "en": lines[lid]["en"]}
                                 for lid in order if lines[lid]["scene"] == sc["id"]]})
    return f"""Episode title: {script.get('title_en','')}

RULES
- Each shot is at most {dur} seconds and shows ONE clear action.
- Use only these character ids: {', '.join(chars)}.
- Use only these location ids (pick the closest): {', '.join(locs)}.
- Optional props, only these ids: {', '.join(props)}.
- Every dialogue line_id must appear in exactly one shot's "lines", in script order. Shots without dialogue are allowed (silent reactions, Miso gags, establishing shots).
- Miso never speaks. Miso acts only through movement, expressions and meows.
- For shots with dialogue, prefer framings where exact lip-sync is not critical (medium-wide, over-the-shoulder, side profile, reaction shots).
- Keep continuity: say in "continuity" what must match the previous and next shot (props held, broken or intact, time of day).
- Never depict any Prophet. Keep worship and sacred places respectful. No unsafe instructions.
- Style: {style['visual_style']}

SCENES
{json.dumps(scenes, ensure_ascii=False, indent=1)}

OUTPUT JSON SCHEMA
{{"shots":[{{"id":"S01_01","scene":"S01","duration":{dur},"location":"<location id>","characters":["CHAR-AYRA"],"props":[],"lines":["S01_L01"],"action":"one clear action","performance":"facial expression and body language","camera":"shot size, angle, movement","lighting":"time of day and light","continuity":"what must stay consistent","sfx":"sound effects"}}]}}"""


def validate(shots, lines, order, chars, locs, props, dur):
    errs, seen = [], []
    ids = set()
    for s in shots:
        sid = s.get("id", "?")
        if sid in ids:
            errs.append(f"duplicate shot id {sid}")
        ids.add(sid)
        for k in ("action", "performance", "camera", "lighting", "continuity"):
            if not s.get(k):
                errs.append(f"{sid}: missing {k}")
        if s.get("location") not in locs:
            errs.append(f"{sid}: unknown location {s.get('location')}")
        for ch in s.get("characters", []):
            if ch not in chars:
                errs.append(f"{sid}: unknown character {ch}")
        for p in s.get("props", []):
            if p not in props:
                errs.append(f"{sid}: unknown prop {p}")
        if not 1 <= float(s.get("duration", 0)) <= dur:
            errs.append(f"{sid}: duration must be 1..{dur}")
        seen += s.get("lines", [])
    if sorted(seen) != sorted(order):
        missing = sorted(set(order) - set(seen))
        extra = sorted(set(seen) - set(order))
        dup = sorted({x for x in seen if seen.count(x) > 1})
        errs.append(f"line coverage wrong: missing={missing} unknown={extra} duplicated={dup}")
    elif seen != order:
        errs.append("dialogue lines are not in script order")
    return errs


def call_claude(prompt, model):
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=16000, system=SYSTEM,
                                 messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    return json.loads(text)


def write_lines_csv(ep, lines, order):
    with open(ep_dir(ep) / "lines.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["line_id", "scene", "char", "en", "bn", "expected_en_audio", "expected_bn_audio"])
        for lid in order:
            ln = lines[lid]
            w.writerow([lid, ln["scene"], ln["char"], ln["en"], ln["bn"],
                        f"episodes/{ep}/audio/en/{lid}.mp3", f"episodes/{ep}/audio/bn/{lid}.mp3"])


def main():
    ep = check_episode(sys.argv[1])
    force = "--force" in sys.argv
    out = ep_dir(ep) / "shots.json"
    script, lines, order = load_script(ep)
    write_lines_csv(ep, lines, order)
    if out.exists() and not force:
        sys.exit(f"{out} already exists. It may contain your manual edits. Re-run with force_plan to overwrite.")
    chars, locs, props, style = load_bible()
    c = cfg()
    data = call_claude(build_request(script, lines, order, chars, locs, props, style, c), c["claude_model"])
    shots = data["shots"]
    errs = validate(shots, lines, order, chars, locs, props, c["video"]["duration_seconds"])
    if errs:
        (ep_dir(ep) / "shots.invalid.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        sys.exit("Plan failed validation:\n- " + "\n- ".join(errs))
    out.write_text(json.dumps({"episode": ep, "shots": shots}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(shots)} shots, about {sum(float(s['duration']) for s in shots):.0f}s of video before dialogue stretching.")


if __name__ == "__main__":
    main()
