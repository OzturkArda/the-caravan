# The Caravan

A companion for our WoW Forever group: plan sessions in Discord, see each other's characters in game, and see game data in Discord.

| Part | Runs on | Does |
|---|---|---|
| Discord bot (`src/caravan/bot`) | A Linux machine on the home network (systemd user service) | Sessions with RSVP buttons, native Discord events, reminders, availability and time suggestions; game data: `/group`, `/dungeons`, `/craft`, `/order`, level-gap alerts, session recaps; HTTP API for the sync app |
| Addon (`addon/TheCaravan`) | Everyone's WoW | Shares level, XP, zone, professions, known recipes, gear, and recent level-ups, notable loot and dungeon runs with the group; shows upcoming sessions |
| Sync app (`src/caravan/sync`) | Arda's Mac | Uploads the addon's saved data to the bot; writes the schedule into it while WoW is closed |

Addons can't reach the internet, so game data travels through the addon's SavedVariables file (`TheCaravan.lua`). The game writes that file on logout, `/reload` and exit, so Discord gets snapshots, not live data. Everyone's addon shares its data in the party, so Arda's file holds the whole group and only Arda runs the sync app.

## Setup

Machine names, addresses and tokens live in `~/.config/caravan/` on each machine, never in the repo. Each file has a template in `deploy/*.env.example`.

### 1. Discord bot (once)

1. At https://discord.com/developers/applications create an application, open **Bot**, and copy the token (Reset Token).
2. Invite it, replacing `APP_ID` with the application ID from **General Information**:
   `https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot+applications.commands&permissions=8590019584`
   (View Channels, Send Messages, Embed Links, Read Message History, Manage Events.)
3. On the Mac, put the bot machine's SSH destination in `~/.config/caravan/deploy.env` (template: `deploy/deploy.env.example`).
4. On the bot machine, fill in `~/.config/caravan/bot.env` (template: `deploy/bot.env.example`): the token, server ID and sessions channel ID.
5. From this repo on the Mac: `deploy/deploy-bot.sh`. Rerun it after any bot change.

### 2. Sync app (Arda's Mac)

`deploy/install-sync.sh` creates `~/.config/caravan/sync.env` (set `CARAVAN_API_URL` to the bot machine's address and `CARAVAN_API_TOKEN` to the bot's value), then installs a LaunchAgent. Log: `~/Library/Logs/caravan-sync.log`.

### 3. Addon

- Arda: `deploy/link-addon.sh` links the addon into `/Applications/World of Warcraft/_forever_/Interface/AddOns`.
- Friends: `deploy/package-addon.sh` builds `dist/TheCaravan-<version>.zip`; unzip it into `World of Warcraft/_forever_/Interface/AddOns`.
- In game, group up and run `/caravan addparty` once. Only players on your list are accepted.

## Commands

Discord: `/session add when [title] [duration]`, `/session list`, `/session cancel`, `/session suggest`, `/availability add|clear|show`, `/timezone set|show`, `/group`, `/dungeons [level]`, `/craft item`, `/order add item [quantity] [note]`, `/order list`, `/order done id`, `/order cancel id`.
Times like `fri 8pm`, `tomorrow 7:30pm` or `2026-11-21 19:00` are read in your timezone (`/timezone set`, default `GROUP_TZ`).

Game: `/caravan` (window), `/caravan add Name`, `/caravan addparty`, `/caravan remove Name`, `/caravan list`, `/caravan sync`, `/caravan minimap`.

## Game-data features

All of these read the latest snapshot, so they reflect the last time Arda logged out or typed `/reload`.

- **`/group`**: everyone's level, class, zone, item level, professions, and when each was last seen.
- **`/dungeons`**: dungeons whose level range overlaps the group's, best fits first, with who's under or over. Dungeons inside the other faction's capital are hidden. Pass `level` to check a single level. Ranges are in `src/caravan/bot/dungeons.py`: the nine new dungeons use Blizzard's numbers, and the reworked classics use community tables that aren't confirmed yet (shown as "range unconfirmed"). Fix them there once checked in game.
- **`/craft item`**: who knows a matching recipe. The game lists recipes only while a profession window is open, so **each player opens each of their profession windows once** (and again after learning new recipes). Autocomplete suggests known recipe names.
- **`/order`**: a simple crafting queue. Anyone can mark an order done; only the requester can cancel it.
- **Level-gap alerts**: a post when someone gets more than `LEVEL_GAP` levels (default 3) above the median of everyone else. One alert per time they pull ahead. Members not seen for 30 days are left out. Posts go to `ALERTS_CHANNEL_ID`, or the sessions channel.
- **Session recaps**: after a session's scheduled end, once a snapshot from after its start has arrived, the bot posts levels gained, dungeon runs (bosses killed, and "cleared" when the game's Encounter Journal knows the boss count) and rare-or-better loot. It counts what the addon timestamped between 30 minutes before the start and 3 hours after the scheduled end, so solo play between sessions isn't included. Later snapshots within 12 hours edit the post. Sessions where nothing happened get no recap.

## Development

```
uv sync
uv run pytest
```

`tests/test_addon.py` runs the real addon and Ace3 libraries in Lua 5.1 against a fake WoW client (`tests/wow_stub.lua`), including two clients exchanging data. Behaviour in the live client still needs an in-game check.

## Forever platform notes

- Forever uses the Mainline 12.1.5 addon API with Midnight's restrictions; the TOC `## Interface:` is 16001 (patch 1.60.1). Check with `/dump select(4, GetBuildInfo())` after patches.
- Trial accounts can't send addon messages, so their data won't reach the group.
- The addon sends nothing in combat or during boss encounters and catches up afterwards.
- Loot is read from loot chat lines. Midnight can hide chat text from addons (secret values); those lines are skipped.
- Recipe lists are sent only when a group member is missing that version (about 1 KB per 40 recipes).
