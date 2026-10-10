# Ayra & Inaya: automated episode builder

You give: **approved images + a script + voice files**. GitHub Actions gives: prompts, video clips, and final **English + Bangla MP4s with subtitles**.

## One-time setup
1. Create a **private** GitHub repo and upload this folder.
2. Repo Settings, Secrets and variables, Actions: add `GEMINI_API_KEY`.
3. Repo Settings, Actions, General, Workflow permissions: choose **Read and write**.
4. Put approved images in `assets/` using the exact filenames from the prompt pack (`assets/characters/CHAR-AYRA_front.png`, `assets/locations/LOC-AYRA-HOME_wide_day.png`, ...). Keep each image under about 2 MB.
5. Optional: licensed or free-license music in `audio/music/`, Bangla font (Kalpurush) in `fonts/` for burned-in subtitles.
6. Track progress with `ASSET_CHECKLIST.md` and run `python tools/check_assets.py` to list missing images. Image prompts: `docs/asset_prompts.csv`.
7. Check `pipeline/config.yaml` against the current docs of your video model (model name, clip length, resolution, number of reference images).

## For every episode
1. Create `episodes/ep001/script.yaml` (copy `episodes/ep000/script.yaml`). Each line has `char`, `en`, `bn`.
2. Actions tab, **build-episode**, Run workflow:
   - `plan`: writes `episodes/ep001/shots.json` and `lines.csv` (commits to the repo). **Read and edit shots.json by hand if needed.**
   - `prompts`: free. Produces one text prompt per shot (download the artifact). You can also paste these into any other video tool manually.
   - `generate`: makes the clips (this costs money). Download the `ep001-clips` artifact, watch every clip. To fix bad ones, run again with `redo` = `S03_02,S05_01`.
   - `assemble`: makes `ep001_en.mp4`, `ep001_bn.mp4`, and `.srt` files (artifact `ep001-final`).
3. Voice files: record each line listed in `lines.csv` and save as `episodes/ep001/audio/en/S01_L01.mp3` and `.../bn/S01_L01.mp3`. Missing voice files = silence with estimated timing, so you can preview first.
4. Watch the full video, then upload to YouTube manually.

## Start small
Run `ep000` (30-second demo) through all four stages first to see real cost and quality.

## Known limits
- Lip movement will not match your voice exactly. The planner prefers framings where this matters less.
- Character consistency depends on the model and reference images. Some clips will need redo.
- Clips are kept in the Actions cache (evicted after about 7 days unused or when the 10 GB repo cache fills) and in a 14-day artifact. Download clips you want to keep.
- Quran, hadith or dua lines: never auto-generate. Add them only with a verified source and have a knowledgeable reviewer check the episode.
- No Prophet is ever depicted (see `bible/style.yaml`).

## FREE mode (no paid API)
The only paid parts are the Claude API (plan stage) and the video API (generate stage). You can skip both:
1. **Plan:** ask Claude in chat for `shots.json` and save it as `episodes/ep001/shots.json` (the `plan` stage is not needed). `ep000` already has one.
2. **Prompts:** run stage `prompts` (free). Download the artifact: one text file per shot, with the reference images to attach.
3. **Clips by hand:** generate each clip in a video tool whose free plan you have (limits change, check them), and save it as `episodes/ep001/clips/S01_01.mp4` (the shot ID is the filename). `.mov`/`.webm` also work.
4. **Voice:** your own files in `episodes/ep001/audio/en|bn/`.
5. **Assemble:** run stage `assemble` (no API key needed, uses only ffmpeg). GitHub Actions minutes: a private repo gets a monthly free allowance, assembly takes a few minutes.
