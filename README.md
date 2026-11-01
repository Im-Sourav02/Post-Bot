# Infinix Syndicate Post Bot

A private Telegram bot for publishing posts to your channels in one fixed format:

```
[ media + caption + channel signature ]
[ 💎 Premium ] [ 📁 Backup ]     ← links from the channel's settings (skipped if unset)
[ 🔴 Download              ]     ← link asked for every post
```

It supports immediate and scheduled sending, scheduled deletion, live editing of published posts (media, caption, buttons), resending to other channels, and per-channel settings (signature, Premium/Backup links, forwarding protection).

**Stack:** Python 3.11, [Kurigram](https://pypi.org/project/kurigram/) (maintained Pyrogram fork, imported as `pyrogram`), TgCrypto, MongoDB via Motor, Docker.

---

## 1. Create the bot (BotFather)

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Choose a name (e.g. *Infinix Syndicate Post Bot*) and a username ending in `bot`.
3. Copy the **token** it gives you → `BOT_TOKEN`.
4. Optional but recommended:
   - `/setcommands`, then paste:
     ```
     start - Main menu
     newpost - Create a new post
     myposts - Edit or delete posts
     settings - Channel settings
     cancel - Stop the current step
     help - Show help
     ```
   - `/setjoingroups` → **Disable** (the bot is meant for private chats and channels only).
   - `/setdescription`, `/setuserpic` as you like.

## 2. Get API_ID and API_HASH

Kurigram talks to Telegram over MTProto, which needs app credentials in addition to the bot token:

1. Log in at <https://my.telegram.org> with your phone number.
2. Open **API development tools** and create an app (any title / short name).
3. Copy **App api_id** → `API_ID` and **App api_hash** → `API_HASH`.

Keep `API_HASH` and `BOT_TOKEN` secret. The bot never writes them to the logs.

## 3. Find your OWNER_ID

Send any message to [@userinfobot](https://t.me/userinfobot) and copy your numeric ID → `OWNER_ID`.

## 4. Channel permissions

For every channel you want to post to:

1. Open the channel → **Administrators** → **Add Admin** → search for your bot.
2. Enable at least:
   - ✅ **Post messages**
   - ✅ **Edit messages of others**
   - ✅ **Delete messages of others**
3. Save, then in a private chat with the bot (as the owner) send `/addchannel` and either
   **forward any message from the channel**, or send its `@username` / ID (e.g. `-1001234567890`).
   The bot checks it has all three permissions before saving the channel.

If the bot is later removed from a channel or loses a permission, posting/editing shows a clear error instead of failing silently.

## 5. Configure

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `API_ID`, `API_HASH` | From my.telegram.org |
| `BOT_TOKEN` | From BotFather |
| `OWNER_ID` | Your numeric Telegram user ID |
| `MONGO_URI` | `mongodb://mongo:27017` for the bundled MongoDB, or an Atlas `mongodb+srv://...` URI |
| `DB_NAME` | Database name (default `postbot`) |
| `TIMEZONE` | IANA name used for scheduling input and display, e.g. `UTC`, `Asia/Kolkata` |
| `SCHEDULER_INTERVAL` | Optional, seconds between scheduler checks (default `15`) |
| `LOG_LEVEL` | Optional, default `INFO` |
| `COMPOSE_PROFILES` | `local-mongo` starts the bundled MongoDB; remove it when using Atlas |

Sessions are in-memory (`in_memory=True`), so no `.session` files are created or need to be persisted.

**Welcome banner (optional):** put an image at `assets/welcome.jpg` and `/start` shows it above the welcome text.

## 6. Run with Docker

Requires Docker with Compose v2.20 or newer.

**With the bundled MongoDB** (default `.env`):

```bash
docker compose up -d --build
docker compose logs -f bot
```

**With MongoDB Atlas:** set `MONGO_URI` to your Atlas URI, delete the `COMPOSE_PROFILES=local-mongo` line from `.env`, then run the same command. Only the bot container starts. In Atlas → *Network Access*, allow your server's IP.

Data lives in MongoDB (the `mongo-data` volume for the bundled database), so restarting or rebuilding the bot container loses nothing.

### Run without Docker (development)

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m bot
```

Set `MONGO_URI` to a reachable MongoDB, e.g. `mongodb://localhost:27017`.

### Hosting notes

- Any always-on Linux host with Docker works (a small VPS is plenty). The bot uses long polling, so no public URL, domain or open port is needed.
- `restart: unless-stopped` brings the bot back after crashes and reboots.
- Scheduled sends and deletions are stored in MongoDB and checked every ~15 s, so anything that came due while the bot was down fires right after it starts again.
- Run exactly **one** bot instance per token.

---

## Usage

### Roles

- **Owner** (`OWNER_ID`): everything, plus
  - `/addadmin <user_id>`: add an admin (or reply with `/addadmin` to a message from, or forwarded from, that person)
  - `/dltadmin <user_id>`: remove an admin (same reply option; the owner can't be removed)
  - `/admins`: list admins
  - `/addchannel`: add a channel (forward a message from it, or send `@username` / ID)
  - `/removechannel`: remove a channel (its scheduled posts are cancelled)
- **Admins:** create posts, edit posts, change channel settings.
- **Everyone else** gets a single "not authorized" reply.

### New Post (`✈️ New Post` or `/newpost`)

1. Pick the channel.
2. Send the media: photo, video, GIF, file, audio or voice. If it already has a caption, step 3 is skipped.
3. Send the caption. **🖼 Attach media** shows the media with the prompt, and **❌ NO** cancels.
4. Send the Download link (it is validated).
5. Check the preview, then **✅ Send Now** or **🕒 Schedule Sending** (`DD/MM/YYYY HH:MM` in `TIMEZONE`).
6. After sending you get **Share**, **Resend post**, **Resend identical post**, **New post in channel** and **Edit post**, plus a share link `t.me/<bot>?start=resend<token>` that only admins can use.

Caption formatting (bold, italic, links, spoilers…) is preserved and stored as HTML. Caption plus signature must fit Telegram's 1024-character limit; the bot tells you exactly how many characters to cut.

**Not supported by Telegram for this format:** albums can't have inline buttons, and stickers and round videos can't have captions. The bot explains this when you send one.

### My Posts (`📂 My Posts` or `/myposts`)

Pick a channel to see its posts, 8 per page, filterable by **🗓 Scheduled** or **📤 Sent**. Tap a number to open the edit panel; 🗑 cancels a scheduled post or deletes a sent one from the channel (after confirmation).

The edit panel changes the **live** channel post: replace media, edit caption (signature re-applied), edit the Download link and refresh Premium/Backup, schedule deletion, resend, and share the message link. Each item has a 👀 preview.

### Settings (`⚙️ Settings` or `/settings`)

Per channel: **✍️ Signature**, **🗂 Backup** link, **⭐ Premium** link (set / edit / remove) and **↪️ Forwarding** (when restricted, posts are sent with `protect_content`).

---

## Project structure

```
bot/
  __main__.py          entry point: logging (with secret redaction), MongoDB, client, scheduler
  config.py            .env loading and validation
  db/                  MongoDB (Motor) access: admins, channels, posts, states + indexes
  handlers/            guard (authorization), router (callback/step dispatch), start, newpost,
                       myposts (list + edit panel), resend, settings, owner
  keyboards/           inline keyboards (callback_data kept under 64 bytes)
  services/            poster (send/edit/delete live posts), scheduler, media, formatting,
                       errors (friendly messages), ui (edit-in-place rendering), screens, links
assets/welcome.jpg     optional /start banner
```

### MongoDB collections

- `admins`: `user_id` (unique), `added_by`, `added_at`
- `channels`: `tg_chat_id` (unique), `title`, `username`, `signature`, `backup_url`, `premium_url`, `protect_content`, `added_at`
- `posts`: `token` (unique), `channel_id`, `media_type`, `file_id`, `caption_html`, `download_url`, `status` (`draft|scheduled|sent|deleted|cancelled`; `sending`/`deleting` are brief internal claims), `message_id`, `send_at`, `sent_at`, `delete_at`, `delete_delay`, `created_by`, `created_at`
- `states`: `user_id` (unique), `step`, `data`. Conversation state is persisted, so a flow survives restarts.

Indexes: `posts(status, send_at)`, `posts(status, delete_at)`, `posts.token` (unique), `admins.user_id` (unique), plus helpers for channels, states and post lists.
