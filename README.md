# YT Autopilot — two faceless channels, one bot

Channel A (market data recaps) and Channel B (business documentaries) run on one Telegram-controlled
pipeline: **ideas → you pick + add an angle → script → voice → visuals → render → you approve → scheduled upload**.

## How it flows

1. On schedule (A: Sun + Wed 8 PM IST, B: Thu 8 PM IST) the bot sends 5 ranked topic ideas. `/ideas a` does it on demand.
2. Tap a number, then reply with your one-line angle. No angle, no video (keeps every video original).
3. ~5–15 min later you get: long-video preview, thumbnail, 3 Shorts previews, title and description.
4. Tap **Approve** (uploads + schedules everything), **Changes** (type a note, it re-renders), or **Reject**.
5. Long video goes to the next channel slot (A: Mon/Thu 5:30 PM ET, B: Sat 10 AM ET); Shorts go daily after it.

## Files

| File | Job |
| --- | --- |
| `bot.py` | Telegram bot, buttons, scheduler (entry point) |
| `pipeline.py` | Job lifecycle, publish slots, descriptions, cleanup |
| `ideas.py` | Topic finder (Binance data + Reddit top posts → Claude) |
| `scriptgen.py` | Scene-by-scene script + Shorts as JSON, policy rules, hook/structure rotation |
| `market.py` | Binance futures data: price, funding, open interest, long/short |
| `visuals.py` | Charts from live data, stat/title/timeline cards, Pexels stock footage |
| `tts.py` | ElevenLabs voice per scene |
| `render.py` | FFmpeg: scenes → video, captions, loudness, chapters, previews |
| `thumbnail.py` | 1280×720 thumbnail |
| `youtube.py` | Upload, schedule, AI-content disclosure, thumbnail |
| `channels.py` | Everything that differs between Channel A and B |
| `selftest.py` | Offline render test, no keys needed |
| `get_youtube_token.py` | One-time refresh token per channel (run on your laptop) |

## Setup (about 1–2 hours, once)

### 1. YouTube channels
- Create two **Brand Account** channels on one Google account. Verify both by phone (needed for custom thumbnails).

### 2. Google Cloud (one project serves both channels)
1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. OAuth consent screen → External → add your Gmail as test user → then **Publish app** (status "In production").
   Apps left in "Testing" get refresh tokens that expire after 7 days.
3. Credentials → Create OAuth client ID → **Desktop app** → download `client_secret.json`.
4. On your laptop: `pip install google-auth-oauthlib` → `python get_youtube_token.py client_secret.json`.
   Pick **Channel A** in the browser → copy the token to `YT_REFRESH_TOKEN_A`. Repeat for Channel B.
5. Uploads from a new API project are forced to **private** until Google audits it. Submit the
   "YouTube API Services audit" form early (setup week). Until approved, approve in Telegram, then make
   videos public manually in YouTube Studio.
6. Default quota is 10,000 units/day; one upload costs ~1,600, so about 6 uploads/day per project.

### 3. Other keys
- **Anthropic**: console.anthropic.com → API key.
- **ElevenLabs**: API key + two voice IDs (distinct voices per channel).
- **Pexels**: free key at pexels.com/api.
- **Telegram**: @BotFather → new bot token. Get your chat ID from @userinfobot.

### 4. Test locally (optional)
```
pip install -r requirements.txt     # plus ffmpeg installed on your machine
python selftest.py                  # renders sample videos into ./work/selftest
```

### 5. Deploy on Railway
1. Push this folder to a new private GitHub repo → Railway → New project → Deploy from repo (uses the Dockerfile).
2. Settings → **Region: EU or Asia** (Binance blocks US IPs; US regions return HTTP 451).
3. Add a **Volume** mounted at `/data`.
4. Variables: copy from `.env.example`. Keep `DRY_RUN_UPLOAD=1` and `ENABLED_CHANNELS=A` for the first runs.
5. In Telegram send `/ideas a`, run one full video, check the preview. When happy, set `DRY_RUN_UPLOAD=0`.
6. Week 5: set `ENABLED_CHANNELS=A,B`.

## Tuning
- Voice, colours, schedule, formats, rules: `channels.py`.
- Hook styles and structures that rotate between videos: `scriptgen.py`.
- Caption size/position: `render.py` (`style`). Chart layout: `visuals.py`.
- Rendering is CPU-heavy. If Railway is slow or costly, upgrade the plan or run the bot on a small VPS.

## Guardrails built in
- Script generation refuses to run without your angle.
- Channel A prompts forbid buy/sell calls, price targets and named-analyst personas; description adds a not-financial-advice line.
- Every upload sets `containsSyntheticMedia: true` (YouTube's altered/synthetic content disclosure).
- Hook style and structure rotate, and the same stock clip is never reused inside one video.
- Stock footage only from Pexels; charts from your own data.
