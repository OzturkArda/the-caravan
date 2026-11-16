# Game-data features

How game data gets from WoW into Discord, how sessions get into the game and RSVPs come back, what the addon records, and the two features that post on their own: level-gap alerts and session recaps. The [README](../README.md#game-data-features) has the overview and what each player needs to do; the commands that read this data are in [COMMANDS.md](COMMANDS.md#game-data).

## How game data reaches Discord

```text
Each player's addon ── shares over party chat while grouped ──▶ Arda's addon
                                                                   │ logout, /reload or exit
                                                                   ▼
                                     TheCaravan.lua (SavedVariables on Arda's Mac)
                                                                   │ sync app checks every 5 s,
                                                                   ▼ uploads when it changes
                                       Bot ──▶ commands, level-gap alerts, recaps
```

1. Each player's addon records their own character and shares it with the party, but only with players on their [`/caravan` list](COMMANDS.md#in-game-caravan).
2. Arda's addon therefore holds the whole group. The game writes it to disk on logout, `/reload` and exit, never during play.
3. The sync app on Arda's Mac notices the file change within 5 seconds and uploads it to the bot as a snapshot.
4. The bot keeps the latest snapshot. Commands read it, and each new one can set off a level-gap alert or a recap.

So Discord is as up to date as Arda's last logout or `/reload`, and a friend's progress reaches it only after they've been grouped with Arda.

## Sessions in game, and RSVPs back to Discord

```text
Bot ── sync app writes the schedule while WoW is closed ──▶ Arda's addon
                                                              │ party chat while grouped
                                                              ▼
                                                     Each friend's addon
  In / Late / Out clicked in game ── party chat ──▶ Arda's addon ── next snapshot ──▶ Bot ──▶ session card
```

**The session list.** The sync app asks the bot for the schedule every 5 minutes, and as soon as the game closes, but writes it into the file only while WoW is closed: the game overwrites the file from memory when it exits. At login the addon reads it. When players group up, each addon says when its copy was generated, and anyone holding a newer one sends it. So friends get the list from Arda's addon, or from anyone who already has it, and keep it for their next login. A session scheduled in Discord mid-play reaches the game after Arda restarts it.

The schedule carries the bot's `REMINDER_OFFSETS`, so the addon's [reminders](COMMANDS.md#caravan-reminders) come at the same times as the Discord ones. It also says who has linked which character, so the Sessions tab can show character names and find your own answer.

**RSVPs from the game.** A click on **In**, **Late** or **Out** in the [Sessions tab](COMMANDS.md#the-sessions-tab) is saved with the time of the click, then passed to the group whenever someone joins. For each character and session, the newest click wins. Arda's next logout or `/reload` puts every click Arda's addon knows into the snapshot. The bot then:

- applies each click as the Discord user who [linked](COMMANDS.md#character-link) that character, and skips clicks from unlinked characters;
- uses it only if it's newer than that user's current RSVP, so a later click in Discord wins and uploading the same click again changes nothing;
- skips cancelled and finished sessions, and clicks timed more than 5 minutes after the bot's clock;
- edits the session card in Discord.

The addon forgets clicks once their session has ended, or after 14 days.

## What the addon records

| Data | Recorded | Kept |
|---|---|---|
| Level, XP, zone, class, race, faction, item level (average of worn gear), gear, professions | On login and whenever one changes | The latest values |
| Known recipes | When you open a profession window | The latest list; sent to others only when their copy differs |
| Level-ups | Each level gained | The last 20, up to 14 days |
| Notable loot | Each rare (blue) or better item you loot | The last 20, up to 14 days |
| Dungeon runs | Entering a dungeon and each boss kill. Re-entering within 30 minutes continues the same run. | The last 10, up to 14 days |
| RSVPs | Each **In**, **Late** or **Out** click in the Sessions tab, yours and those passed on by the group | Until the session ends, up to 14 days |

The addon sends nothing in combat or during boss encounters, and catches up afterwards.

## Level-gap alerts

Posts when someone pulls ahead of the rest of the group, so the others know to catch up (or the leader knows to slow down).

**Rule**: a member's level minus the median level of everyone else. When that's more than `LEVEL_GAP`, the bot posts an alert. Only members seen in the last 30 days count, and it needs at least two.

**When**: checked on every new snapshot. One alert each time someone pulls ahead. Once they're back within range, a later gap alerts again.

**Where**: `ALERTS_CHANNEL_ID`, or the sessions channel when that's empty. With neither set, nothing is posted.

**Settings** (in `bot.env`)

| Name | Default | Description |
|---|---|---|
| `LEVEL_GAP` | 3 | How many levels above the median of everyone else counts as pulling ahead. `0` turns alerts off. |
| `ALERTS_CHANNEL_ID` | empty | Channel for alerts. Empty means the sessions channel. |

**Example**: Brynn is 27 and the others are 23, 22 and 22. The median of the others is 22, so the gap is 5, which is more than 3:

```text
📈 Brynn is pulling ahead
Brynn is level 27, 5 levels above the rest of the group (alert above 3).
Corwin 23 · Dara 22 · Ember 22
```

## Session recaps

After each session, posts what the group achieved: who played, levels gained, dungeon runs and notable loot.

**When**: after the session's scheduled end, once a snapshot exported after the session started has arrived. The bot checks every 5 minutes and on every snapshot, for up to 12 hours after the scheduled end. Snapshots that arrive in those 12 hours edit the same post rather than adding a new one.

**What counts**: what the addon timestamped from 30 minutes before the start to 3 hours after the scheduled end. If the next session starts sooner, the window ends there instead, but never before this session's scheduled end. Solo play between sessions isn't counted.

**Contents**

- **Played**: everyone with something recorded in the window.
- **Levels**: each level-up, from → to.
- **Dungeons**: each run with who was there. A run shows "cleared ✅" when the game's Encounter Journal knows the dungeon and either its final boss or every boss it lists has died. Otherwise it shows "3/5 bosses" when the boss count is known, or just the number of bosses, with their names.
- **Loot**: rare or better, with a dot for quality: 🔵 rare, 🟣 epic, 🟠 legendary.

**Where**: the channel the session card is in.

**Skipped**: cancelled sessions, and sessions where nothing was recorded.

**Example**

```text
📜 Recap: Deadmines run
Saturday, 21 November 2026 19:00
Played: Brynn, Corwin, Dara
🎉 Levels
Brynn 18 → 20
Dara 17 → 19
🏰 Dungeons
The Deadmines · cleared ✅ · Brynn, Corwin, Dara
💎 Loot
🔵 Corwin: [Smelting Pants]
🔵 Dara: [Cruel Barb]
Session #12 · from the game snapshot; updates if a later one arrives
```

## Dungeon data

`/dungeons` uses the 35 dungeons in `src/caravan/bot/dungeons.py`, each with a level range, zone, faction territory and source:

- **The nine new Forever dungeons** use the ranges from Blizzard's announcement.
- **The 26 reworked classic dungeons** use community tables (wowforeverguides.com and WCLBox) that haven't been confirmed in game yet, so `/dungeons` marks them "range unconfirmed". Fix a range in that file once you've checked it in game.
