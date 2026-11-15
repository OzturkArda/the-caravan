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
2. In Discord, turn on Developer Mode (Settings > Advanced) so you can right-click the server and the sessions channel and **Copy ID**.
3. On the Mac, put the bot machine's SSH destination in `~/.config/caravan/deploy.env` (template: `deploy/deploy.env.example`).
4. From this repo on the Mac: `deploy/configure-bot.sh`. It asks for the token (hidden), server ID and sessions channel ID, writes them into `~/.config/caravan/bot.env` on the bot machine, prints the invite link (permissions: View Channels, Send Messages, Embed Links, Read Message History, Manage Events), waits while you add the bot, then deploys and starts it. Press Enter at a prompt to keep the current value.
5. Rerun `deploy/deploy-bot.sh` after any bot change. Other settings are in `~/.config/caravan/bot.env` on the bot machine (template: `deploy/bot.env.example`); rerunning `configure-bot.sh` adds any the template has gained.

### 2. Sync app (Arda's Mac)

`deploy/install-sync.sh` creates `~/.config/caravan/sync.env` (set `CARAVAN_API_URL` to the bot machine's address and `CARAVAN_API_TOKEN` to the bot's value), then installs a LaunchAgent. Log: `~/Library/Logs/caravan-sync.log`.

### 3. Addon

- Arda: `deploy/link-addon.sh` links the addon into `/Applications/World of Warcraft/_forever_/Interface/AddOns`.
- Friends: `deploy/package-addon.sh` builds `dist/TheCaravan-<version>.zip`; unzip it into `World of Warcraft/_forever_/Interface/AddOns`.
- In game, group up and run `/caravan addparty` once. Only players on your list are accepted.

## Commands

The bot's slash commands work in any channel the bot can see. The addon's `/caravan` commands are typed in the game's chat box. **[docs/COMMANDS.md](docs/COMMANDS.md)** has the full reference: syntax, options, who sees the reply, errors and examples for every command.

| Command | What it does | Reply |
|---|---|---|
| [`/session add`](docs/COMMANDS.md#session-add) | Schedule a session with RSVP buttons and a Discord event | Everyone |
| [`/session list`](docs/COMMANDS.md#session-list) | Upcoming sessions | Everyone |
| [`/session cancel`](docs/COMMANDS.md#session-cancel) | Cancel a session you scheduled | Everyone |
| [`/session suggest`](docs/COMMANDS.md#session-suggest) | Best times from everyone's availability | Everyone |
| [`/availability add`](docs/COMMANDS.md#availability-add) | Add a weekly window when you can play | Only you |
| [`/availability clear`](docs/COMMANDS.md#availability-clear) | Remove all your windows | Only you |
| [`/availability show`](docs/COMMANDS.md#availability-show) | See your windows or everyone's | Only you |
| [`/timezone set`](docs/COMMANDS.md#timezone-set) | Set your timezone | Only you |
| [`/timezone show`](docs/COMMANDS.md#timezone-show) | See which timezone the bot uses for you | Only you |
| [`/group`](docs/COMMANDS.md#group) | Everyone's characters | Everyone |
| [`/dungeons`](docs/COMMANDS.md#dungeons) | Dungeons that suit the group's levels | Everyone |
| [`/craft`](docs/COMMANDS.md#craft) | Who can craft an item | Everyone |
| [`/order add`](docs/COMMANDS.md#order-add) | Ask the group to craft something | Everyone |
| [`/order list`](docs/COMMANDS.md#order-list) | Open crafting orders | Everyone |
| [`/order done`](docs/COMMANDS.md#order-done) | Mark an order crafted | Everyone |
| [`/order cancel`](docs/COMMANDS.md#order-cancel) | Withdraw your order | Everyone |
| [`/caravan`](docs/COMMANDS.md#caravan) | In game: open or close the window | Your chat |
| [`/caravan add`](docs/COMMANDS.md#caravan-add) | In game: add a player to your list | Your chat |
| [`/caravan addparty`](docs/COMMANDS.md#caravan-addparty) | In game: add everyone in your group | Your chat |
| [`/caravan remove`](docs/COMMANDS.md#caravan-remove) | In game: remove a player from your list | Your chat |
| [`/caravan list`](docs/COMMANDS.md#caravan-list) | In game: show your list | Your chat |
| [`/caravan sync`](docs/COMMANDS.md#caravan-sync) | In game: share your data with the group now | Your chat |
| [`/caravan minimap`](docs/COMMANDS.md#caravan-minimap) | In game: show or hide the minimap button | Your chat |

## Game-data features

The bot knows what happens in game through the addon. Four commands read that data on request: [`/group`](docs/COMMANDS.md#group), [`/dungeons`](docs/COMMANDS.md#dungeons), [`/craft`](docs/COMMANDS.md#craft) and [`/order`](docs/COMMANDS.md#order-add). Two features post on their own: [level-gap alerts](docs/GAME-DATA.md#level-gap-alerts) and [session recaps](docs/GAME-DATA.md#session-recaps).

| Feature | What you get | Where | Turned on by |
|---|---|---|---|
| [`/group`](docs/COMMANDS.md#group) | Everyone's level, class, zone, item level, professions, last seen | Where you type it | Always on |
| [`/dungeons`](docs/COMMANDS.md#dungeons) | Dungeons that suit the group, with who's too low or too high | Where you type it | Always on |
| [`/craft`](docs/COMMANDS.md#craft), [`/order`](docs/COMMANDS.md#order-add) | Who can craft what, and a shared crafting queue | Where you type it | Players opening their profession windows |
| [Level-gap alerts](docs/GAME-DATA.md#level-gap-alerts) | A post when someone pulls ahead of the group | `ALERTS_CHANNEL_ID`, else the sessions channel | `LEVEL_GAP` (default 3; 0 turns it off) |
| [Session recaps](docs/GAME-DATA.md#session-recaps) | Levels, dungeon runs and loot from each session | The session's channel | Always on |

How the data travels, what the addon records, and the rules behind alerts and recaps are in **[docs/GAME-DATA.md](docs/GAME-DATA.md)**.

### What each player needs to do

- Install the addon and run `/caravan addparty` once while grouped (see [Setup](#3-addon)).
- **Open each of your profession windows once**, and again after learning new recipes, so `/craft` and `/order` know what you can make.
- Group with Arda during sessions, so your data reaches Arda's addon.
- Arda: log out or `/reload` after a session, so the snapshot, and with it the recap, reaches Discord.

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
