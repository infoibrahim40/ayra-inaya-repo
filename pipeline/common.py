"""Shared helpers for the Ayra & Inaya pipeline."""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cfg():
    return load_yaml(ROOT / "pipeline" / "config.yaml")


def check_episode(ep):
    if not re.fullmatch(r"ep[0-9]{3,4}", ep):
        sys.exit(f"Episode name must look like ep001, got: {ep!r}")
    return ep


def ep_dir(ep):
    return ROOT / "episodes" / ep


def out_dir(ep):
    d = ROOT / "out" / ep
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_script(ep):
    path = ep_dir(ep) / "script.yaml"
    if not path.exists():
        sys.exit(f"Missing {path}")
    data = load_yaml(path)
    lines, order = {}, []
    for sc in data["scenes"]:
        for i, ln in enumerate(sc.get("lines", []), 1):
            lid = f"{sc['id']}_L{i:02d}"
            lines[lid] = {"id": lid, "scene": sc["id"], "char": ln["char"],
                          "en": ln.get("en", ""), "bn": ln.get("bn", "")}
            order.append(lid)
    return data, lines, order


def load_bible():
    b = ROOT / "bible"
    chars = {c["id"]: c for c in load_yaml(b / "characters.yaml")["characters"]}
    locs = {x["id"]: x for x in load_yaml(b / "locations.yaml")["locations"]}
    props = {p["id"]: p for p in load_yaml(b / "props.yaml")["props"]}
    style = load_yaml(b / "style.yaml")
    return chars, locs, props, style


def load_shots(ep):
    path = ep_dir(ep) / "shots.json"
    if not path.exists():
        sys.exit(f"Missing {path}. Run the 'plan' stage first.")
    return json.loads(path.read_text(encoding="utf-8"))["shots"]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"Command failed: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r


def probe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(r.stdout.strip())


def find_audio(ep, lang, line_id):
    d = ep_dir(ep) / "audio" / lang
    for ext in AUDIO_EXT:
        p = d / f"{line_id}{ext}"
        if p.exists():
            return p
    return None


def find_clip(ep, shot_id):
    """Clips you made by hand (episodes/<ep>/clips/) win over API-generated ones (out/<ep>/clips/)."""
    for base in (ep_dir(ep) / "clips", ROOT / "out" / ep / "clips"):
        for ext in (".mp4", ".mov", ".webm", ".mkv"):
            p = base / f"{shot_id}{ext}"
            if p.exists():
                return p
    return None


def compose_prompt(shot, chars, locs, props, style):
    """Deterministic copy-paste prompt. Character/location text always comes from the bible."""
    cs = [chars[c] for c in shot["characters"]]
    char_block = "\n".join(f"- {c['name']}: {c['description']}" for c in cs) or "- (no characters)"
    loc = locs[shot["location"]]["description"]
    prop_block = "; ".join(props[p]["description"] for p in shot.get("props", [])) or "none"
    return f"""PROJECT: Ayra & Inaya
SHOT ID: {shot['id']}
DURATION: about {shot['duration']} seconds

CHARACTERS (must match the attached reference images exactly):
{char_block}

ENVIRONMENT: {loc}
PROPS: {prop_block}

ACTION: {shot['action']}
PERFORMANCE: {shot['performance']}
CAMERA: {shot['camera']}
LIGHTING: {shot['lighting']}
VISUAL STYLE: {style['visual_style']}
CONTINUITY: {shot['continuity']}
AUDIO: only soft ambience and natural sound effects ({shot.get('sfx', 'none')}). No music. No spoken words are needed; mouths move naturally when characters talk.
AVOID: {style['avoid']}"""


def pick_refs(shot, chars, locs, props, max_refs):
    """Reference images in priority order: characters, location, props."""
    cand = [chars[c]["master"] for c in shot["characters"] if c != "CHAR-MISO"]
    if "CHAR-MISO" in shot["characters"]:
        cand.append(chars["CHAR-MISO"]["master"])
    cand.append(locs[shot["location"]]["image"])
    cand += [props[p]["image"] for p in shot.get("props", [])]
    refs = []
    for rel in cand:
        p = ROOT / rel
        if p.exists() and p not in refs:
            refs.append(p)
        if len(refs) >= max_refs:
            break
    return refs
