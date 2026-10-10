"""Stage 2/3: shots.json -> prompts (dry run) or video clips (Veo via the Gemini API)."""
import os
import sys
import time

from common import (ROOT, check_episode, cfg, compose_prompt, load_bible, load_shots, out_dir, pick_refs)


def generate_clip(client, types, model, prompt, refs, vcfg, dest):
    ref_objs = []
    for p in refs:
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        img = types.Image(image_bytes=p.read_bytes(), mime_type=mime)
        ref_objs.append(types.VideoGenerationReferenceImage(image=img, reference_type="asset"))
    config = types.GenerateVideosConfig(
        reference_images=ref_objs or None,
        aspect_ratio=vcfg["aspect_ratio"],
        duration_seconds=vcfg["duration_seconds"],
        resolution=vcfg["resolution"],
        number_of_videos=1,
    )
    op = client.models.generate_videos(model=model, prompt=prompt, config=config)
    while not op.done:
        time.sleep(vcfg["poll_seconds"])
        op = client.operations.get(op)
    if getattr(op, "error", None):
        raise RuntimeError(f"generation error: {op.error}")
    vids = getattr(op.response, "generated_videos", None)
    if not vids:
        raise RuntimeError("no video returned (possibly blocked by safety filters)")
    client.files.download(file=vids[0].video)
    vids[0].video.save(str(dest))


def main():
    ep = check_episode(sys.argv[1])
    dry = "--dry-run" in sys.argv
    redo = ""
    if "--redo" in sys.argv:
        redo = sys.argv[sys.argv.index("--redo") + 1]
    redo_set = {x.strip() for x in redo.split(",") if x.strip()}
    c = cfg()
    vcfg = c["video"]
    chars, locs, props, style = load_bible()
    shots = load_shots(ep)
    o = out_dir(ep)
    (o / "prompts").mkdir(exist_ok=True)
    (o / "clips").mkdir(exist_ok=True)

    for s in shots:
        prompt = compose_prompt(s, chars, locs, props, style)
        refs = pick_refs(s, chars, locs, props, vcfg["max_reference_images"])
        note = "\n\nREFERENCE IMAGES TO ATTACH:\n" + "\n".join(f"- {r.relative_to(ROOT)}" for r in refs)
        (o / "prompts" / f"{s['id']}.txt").write_text(prompt + note + "\n", encoding="utf-8")
    print(f"Wrote {len(shots)} prompts to {o / 'prompts'}")
    if dry:
        return

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    todo = []
    for s in shots:
        dest = o / "clips" / f"{s['id']}.mp4"
        if redo_set and ("all" in redo_set or s["id"] in redo_set) and dest.exists():
            dest.unlink()
        if not dest.exists():
            todo.append((s, dest))
    if len(todo) > vcfg["max_clips_per_run"]:
        print(f"Limiting to {vcfg['max_clips_per_run']} clips this run (config max_clips_per_run). Run again for the rest.")
        todo = todo[: vcfg["max_clips_per_run"]]
    print(f"{len(todo)} clips to generate, {len(shots) - len(todo)} already exist")

    failed = []
    for n, (s, dest) in enumerate(todo, 1):
        prompt = (o / "prompts" / f"{s['id']}.txt").read_text(encoding="utf-8").split("\n\nREFERENCE IMAGES")[0]
        refs = pick_refs(s, chars, locs, props, vcfg["max_reference_images"])
        for attempt in range(vcfg["max_retries"] + 1):
            try:
                print(f"[{n}/{len(todo)}] {s['id']} (attempt {attempt + 1})", flush=True)
                generate_clip(client, types, vcfg["model"], prompt, refs, vcfg, dest)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  failed: {e}", flush=True)
                if dest.exists():
                    dest.unlink()
                if attempt == vcfg["max_retries"]:
                    failed.append(s["id"])
                else:
                    time.sleep(20)
    if failed:
        print("FAILED shots (re-run with redo): " + ",".join(failed))
        sys.exit(1)
    print("All clips ready. Download the artifact, watch every clip, and note shot IDs to redo.")


if __name__ == "__main__":
    main()
