# 🍏 Running Octopus Agent 24/7 on Apple Silicon Mac Mini

This guide provides end-to-end instructions for deploying and running the **Octopus Agent** on an Apple Silicon (M1, M2, M3, M4) Mac Mini as a dedicated 24/7 background appliance.

---

## ⚡ Why Mac Mini is the Ideal Host

1. **Apple Silicon VideoToolbox (`h264_videotoolbox`):**
   - Renders 1080x1920 9:16 Instagram Reels at **300+ frames per second** using dedicated hardware Media Engines.
   - Per-video rendering time drops from ~20s to **1.5 seconds**, keeping the Mac completely cool and silent.
2. **Ultra-Low Power:** Consumes only ~5–8W at idle and ~25W under full 20-niche load.
3. **`launchd` 24/7 Daemon:** Built-in macOS process manager automatically starts the agent on boot and auto-recovers if any unexpected crash occurs.

---

## 🚀 Quick Setup (1-Command Installation)

1. Open **Terminal** on your Mac Mini.
2. Clone this repository:
   ```bash
   git clone https://github.com/harshparmar2004/octopus-agent-.git
   cd octopus-agent-
   ```
3. Run the automated installer:
   ```bash
   chmod +x deployment/mac_mini/setup_mac_mini.sh
   ./deployment/mac_mini/setup_mac_mini.sh
   ```
4. Configure your `.env` credentials (or enter them directly in the Web UI dashboard):
   ```bash
   nano .env
   ```
   Add:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   GEMINI_API_KEY=your_gemini_api_key
   ```

---

## 🛠️ Managing the Background Service (`launchd`)

The installer automatically configures `launchd` so Octopus Agent runs in the background 24/7.

### Start the Service
```bash
launchctl load -w ~/Library/LaunchAgents/com.octopus.agent.plist
```

### Stop the Service
```bash
launchctl unload -w ~/Library/LaunchAgents/com.octopus.agent.plist
```

### View Live Execution Logs
```bash
tail -f logs/launchd_stdout.log
```

---

## 🌐 Exposing the Webhook / Public URL (Zero Port Forwarding)

Instagram Graph API requires a publicly reachable HTTPS URL for video streaming during upload.

### Option A: Cloudflare Tunnel (Recommended, 100% Free & Fast)
```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```
Copy the generated `https://xxxx.trycloudflare.com` URL and put it into `.env`:
```env
PUBLIC_BASE_URL=https://xxxx.trycloudflare.com
```

### Option B: Ngrok
```bash
brew install ngrok
ngrok http 8000
```

---

## 📱 Testing Your Mac Mini from Your Phone

1. Open your Telegram Bot chat on your phone.
2. Send `/start` — the Mac Mini will reply with connected accounts and niche pods.
3. Send any Reel URL (e.g. Instagram reel) ➔ tap your niche ➔ tap **`Publish to ALL Pages`**.
4. The Mac Mini will download, render with VideoToolbox in ~1.5s, generate viral copy with Gemini, and publish across your accounts!
