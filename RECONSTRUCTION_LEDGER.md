# REA Reconstruction & System Audit Ledger
### Target: Uncover Media Network (`uncover.quantum`, `uncover.ai`, `uncover.robotics`)

This ledger documents the exact reverse-engineered mechanics of the target media network, adhering strictly to REA evidence labeling standards:
- **`[seen]`**: Direct observable facts from the profile screenshot, post metadata, public URLs, and HTTP responses.
- **`[inferred]`**: Algorithmic and architectural deductions verified by our functional reproduction.
- **`[unknown]`**: Hidden infrastructure components operating within private cloud environments.

---

## 1. Network & Business Model Breakdown
- **Account Scale**: 1,752 posts, 763K followers (`@uncover.quantum`) `[seen]`.
- **Multi-Account Matrix**: Sister accounts include `@uncover.ai`, `@uncover.robotics`, and marketing via `@uncovernews.co` `[seen]`.
- **Traffic Monetization**: Bio link `bit.ly/free-ai-newsletter` routes with UTM tracking parameters:
  `https://uncoverai.co/subscribe?utm_source=instagram&utm_medium=bio&utm_campaign=uncover.quantum` `[seen]`.
- **Primary Business Goal**: Converting organic Instagram Reels viewers into a monetizable email newsletter audience on Beehiiv/Substack `[inferred]`.

---

## 2. Content & Creative Architecture
- **Visual Composition**:
  - Vertical canvas: Standard 1080x1920 (9:16) format `[seen]`.
  - Top 35% viewport: Pure black background (`#000000`) housing the channel badge and hook `[seen]`.
  - Channel badge: Circular icon on left with handle `@uncover.quantum` and bold display name `[seen]`.
  - Headline hook: Clean sans-serif sentence case typography, 10–18 words, left-padded to match the avatar `[seen]`.
  - Lower 65% viewport: Centered source video clip scaled to fit width without distortion `[seen]`.
- **Copywriting Blueprint**:
  - Hooks avoid cheap clickbait; they state intriguing physical/technical facts (e.g. "This represents the Casimir effect between two plates caused by Quantum Fluctuations") `[seen]`.
  - Captions consist of 2-3 educational paragraphs, an explicit source credit (`Credit: ...`), a follow CTA, and 10-15 targeted hashtags `[inferred]`.

---

## 3. Technology Pipeline Reproduction
- **Ingestion**: Videos are scraped from science subreddits (r/physicsgifs, r/QuantumComputing) and academic video feeds using `yt-dlp` `[inferred]`.
- **Enrichment**: Speech transcribed via Whisper; hooks and captions synthesized using LLM prompts tuned for viral science retention `[inferred]`.
- **Compositing**: Programmatic FFmpeg filter graph executing against a Pillow-generated transparent card overlay `[inferred]`.
- **Publishing**: Meta Instagram Graph API Content Publishing endpoints (`POST /{ig-user-id}/media` -> `POST /{ig-user-id}/media_publish`) `[inferred]`.
- **Private Cloud Infrastructure**: Whether Uncover runs their scrapers on AWS Lambda, Modal, or VPS workers with cloud storage (Cloudflare R2 or AWS S3) `[unknown]`.
