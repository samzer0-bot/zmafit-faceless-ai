# zmafit-faceless-ai

Free renderer for the Make scenario **faceless ai**.

Flow: Make (Gemini script + Gemini voice + Drive) → `repository_dispatch` → this workflow
(Pexels clips + FFmpeg + word-by-word subtitles) → GitHub release asset → Make webhook
→ YouTube (private).

## Setup

1. Create a **public** repository named `zmafit-faceless-ai` (public: free unlimited Actions minutes,
   and Make can download the release video without a login).
2. Upload `render.py`, `requirements.txt`, `used_clips.json`, `README.md` and
   `.github/workflows/render.yml` (keep that path exactly).
3. Settings → Secrets and variables → Actions → New repository secret:
   - `PEXELS_API_KEY`: your Pexels API key
   - `MAKE_WEBHOOK_URL`: `https://hook.eu2.make.com/odv3ie6pd1wlvm6bik39hrpzosic8fxn`
4. Create a fine-grained token (GitHub → Settings → Developer settings → Fine-grained tokens) for
   this repository only, with **Contents: Read and write**. In Make, open **faceless ai** → the
   last HTTP module → replace `PASTE_GITHUB_TOKEN_HERE` with the token.

## Variety (anti-repetition)

- Every Pexels clip id is stored in `used_clips.json` and never reused.
- Random Pexels page, random cut lengths (2.6–4.4 s), random start offsets, 30% mirrored clips.
- 4 visual templates (font, colours, subtitle position, colour grade).
- Make rotates 8 voices, 5 video formats and 30 topics.
