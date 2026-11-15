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

The bot's slash commands work in any channel the bot can see. The addon's `/caravan` commands are typed in the game's chat box.

How to read the entries:

- **Syntax** uses `<name>` for a required option and `[name]` for an optional one. In Discord, type the command, then pick each option from the list that appears. The examples write options as `name:value`, the way Discord shows them.
- **Reply** says who sees the bot's answer: *everyone* in the channel, or *only you* (Discord marks these "Only you can see this").
- **Times you type** are read in your timezone: the one you set with [`/timezone set`](#timezone-set), or the group default `GROUP_TZ` (Australia/Melbourne unless changed in `bot.env`). The bot shows times as Discord timestamps, so each reader sees them in their own local time.
- **Sample replies** show what Discord displays, with placeholder character names.

### Quick reference

| Command | What it does | Reply |
|---|---|---|
| [`/session add`](#session-add) | Schedule a session with RSVP buttons and a Discord event | Everyone |
| [`/session list`](#session-list) | Upcoming sessions | Everyone |
| [`/session cancel`](#session-cancel) | Cancel a session | Everyone |
| [`/session suggest`](#session-suggest) | Best times from everyone's availability | Everyone |
| [`/availability add`](#availability-add) | Add a weekly window when you can play | Only you |
| [`/availability clear`](#availability-clear) | Remove all your windows | Only you |
| [`/availability show`](#availability-show) | See your windows or everyone's | Only you |
| [`/timezone set`](#timezone-set) | Set your timezone | Only you |
| [`/timezone show`](#timezone-show) | See which timezone the bot uses for you | Only you |
| [`/group`](#group) | Everyone's characters | Everyone |
| [`/dungeons`](#dungeons) | Dungeons that suit the group's levels | Everyone |
| [`/craft`](#craft) | Who can craft an item | Everyone |
| [`/order add`](#order-add) | Ask the group to craft something | Everyone |
| [`/order list`](#order-list) | Open crafting orders | Everyone |
| [`/order done`](#order-done) | Mark an order crafted | Everyone |
| [`/order cancel`](#order-cancel) | Withdraw your order | Everyone |
| [`/caravan`](#caravan) | In game: open or close the window | Your chat |
| [`/caravan add`](#caravan-add) | In game: add a player to your list | Your chat |
| [`/caravan addparty`](#caravan-addparty) | In game: add everyone in your group | Your chat |
| [`/caravan remove`](#caravan-remove) | In game: remove a player from your list | Your chat |
| [`/caravan list`](#caravan-list) | In game: show your list | Your chat |
| [`/caravan sync`](#caravan-sync) | In game: share your data with the group now | Your chat |
| [`/caravan minimap`](#caravan-minimap) | In game: show or hide the minimap button | Your chat |

### Sessions

#### `/session add`

Schedules a play session. The bot posts a session card with **In**, **Late** and **Out** buttons, marks you **In**, and creates a Discord event in the server's Events list.

**Syntax**

```text
/session add when:<time> [title:<text>] [duration:<minutes>]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `when` | Time, required | | When the session starts, in your timezone. Either a date and time (`fri 8pm`, `tomorrow 7:30pm`, `21 nov 7pm`, `21/11 19:00`, `2026-11-21 19:00`) or just a time (`8pm`, `19:00`, `noon`). A time on its own means the next time the clock shows it: today if that's still ahead, otherwise tomorrow. Dates are read day first. It must be in the future. |
| `title` | Text | `Caravan session` | What the session is about. The Discord event shows the first 100 characters. |
| `duration` | Minutes, 15–720 | `DEFAULT_DURATION_MIN` (180) | How long the session runs. Sets the event's end time. Also decides how long the session stays in `/session list` and when its recap is posted. |

**Reply**: everyone sees the session card. It goes to the sessions channel (`SESSIONS_CHANNEL_ID`), or to the channel you're in if that isn't set. The confirmation with a link to the card is visible to everyone when the card is in your channel, and only to you when it's posted elsewhere.

**Errors** (only you see them): the time can't be read or is in the past; the command was used in a DM; the bot can't post in the sessions channel.

**Notes**

- The card's footer shows the session number (`Session #12`), which `/session cancel` asks for.
- Anyone can click a button to RSVP or change their answer, and the card's counts update. The buttons keep working after the bot restarts.
- Before the start, the bot posts reminders (`REMINDER_OFFSETS`, default 60 and 15 minutes before) that mention everyone who is **In** or **Late**. If the bot was offline when reminders fell due, it sends only one when it's back.
- The Discord event needs the bot's **Manage Events** permission. Without it, the session is still scheduled, just without an event.

**Examples**

| You type | Result |
|---|---|
| `/session add when:fri 8pm` | Friday 20:00 to 23:00, titled "Caravan session" |
| `/session add when:tomorrow 7:30pm title:Deadmines run duration:120` | Tomorrow 19:30 to 21:30 |
| `/session add when:21/11 19:00 title:Gnomeregan` | 21 November at 19:00 |
| `/session add when:8pm` | Today at 20:00, or tomorrow if 20:00 has passed |

**See also**: [`/session suggest`](#session-suggest) to find a time, [Session recaps](#session-recaps).

#### `/session list`

Lists sessions that haven't ended yet, soonest first, up to 10. A session under way stays on the list until its scheduled end. Cancelled sessions aren't shown.

**Syntax**

```text
/session list
```

**Parameters**: none.

**Reply**: everyone. One line per session: its number, title, start time, and how many people are coming (**In** plus **Late**).

**Example**

```text
/session list
```

```text
#12 Deadmines run · Friday, 20 November 2026 20:00 (in 4 days) · 3 coming
#13 Gnomeregan · Saturday, 21 November 2026 19:00 (in 5 days) · 2 coming
```

#### `/session cancel`

Cancels a session. The card is struck through and loses its buttons, the Discord event is deleted, and no reminders or recap follow. Anyone in the server can cancel any session. There's no undo; schedule it again with `/session add`.

**Syntax**

```text
/session cancel session_id:<number>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `session_id` | Number, required | | The number on the card's footer (`Session #12`) or in `/session list`. |

**Reply**: everyone, e.g. "Cancelled **Deadmines run** (#12)."

**Errors** (only you): "No active session #12" when there's no such session or it's already cancelled.

**Example**

```text
/session cancel session_id:12
```

#### `/session suggest`

Finds the start times when the most people are free, from everyone's weekly windows (see [`/availability add`](#availability-add)). It checks every half hour over the next `days` days and keeps the start times where the whole session fits inside someone's window. It then shows up to three that don't overlap, the most people first, then the earliest.

**Syntax**

```text
/session suggest [duration:<minutes>] [days:<number>]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `duration` | Minutes, 30–720 | `DEFAULT_DURATION_MIN` (180) | The session length to fit. |
| `days` | Number, 1–14 | 7 | How many days ahead to look. |

**Reply**: everyone. "4/4" means four of the four people who have set availability can make it. Each person's windows are read in their own timezone.

**Examples**

| You type | Result |
|---|---|
| `/session suggest` | Best 3-hour times in the next 7 days |
| `/session suggest duration:120 days:14` | Best 2-hour times in the next two weeks |

Sample reply:

```text
Best 3h windows (4 people have set availability):
• Friday, 20 November 2026 19:00 — 4/4: Brynn, Corwin, Dara, Ember
• Saturday, 21 November 2026 14:00 — 3/4: Brynn, Dara, Ember
Book one with /session add.
```

When nobody has set availability, it says so and points to `/availability add`.

### Availability and timezone

#### `/availability add`

Adds a weekly window when you can usually play. [`/session suggest`](#session-suggest) uses these windows. Add one for each day you play; a day can have several.

**Syntax**

```text
/availability add day:<weekday> start:<time> end:<time>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `day` | Choice, Monday–Sunday, required | | The day the window starts. |
| `start` | Time, required | | In your timezone: `19:00`, `7pm`, `7:30pm`, `7.30pm`, `19`, `noon` or `midnight`. |
| `end` | Time, required | | Same formats. `24:00` is the end of the day. An end earlier than the start runs past midnight into the next day. |

**Reply**: only you, e.g. "Added Friday 21:00–01:00 (Europe/London)."

**Errors** (only you): a time that can't be read (`25:00`), or a start equal to the end.

**Notes**: windows repeat every week until you clear them. To change one, run `/availability clear` and add your windows again. Windows store clock times, so after `/timezone set` they mean the same clock times in the new timezone.

**Examples**

| You type | Result |
|---|---|
| `/availability add day:Friday start:7pm end:11pm` | Fridays 19:00 to 23:00 |
| `/availability add day:Friday start:21:00 end:1am` | Friday 21:00 to Saturday 01:00 |
| `/availability add day:Sunday start:noon end:18:00` | Sundays 12:00 to 18:00 |

#### `/availability clear`

Removes all of your weekly windows. Other people's windows aren't touched.

**Syntax**

```text
/availability clear
```

**Parameters**: none.

**Reply**: only you, e.g. "Removed 3 window(s)."

#### `/availability show`

Lists weekly windows by person, with each person's timezone. Times are shown as each person entered them, in their own timezone.

**Syntax**

```text
/availability show [member:<@member>]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `member` | Server member | Everyone | Whose windows to show. |

**Reply**: only you.

**Examples**

| You type | Result |
|---|---|
| `/availability show` | Everyone's windows |
| `/availability show member:@Dara` | Only Dara's windows |

Sample reply:

```text
Dara (Europe/London)
  Friday 19:00–23:00
  Saturday 14:00–18:00
```

#### `/timezone set`

Sets your timezone. It's used to read the times you type in `/session add` and `/availability add`, and for your windows in `/session suggest`. Until you set one, the bot uses the group default (`GROUP_TZ`).

**Syntax**

```text
/timezone set tz:<timezone>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `tz` | Timezone name, required | | An IANA name such as `Europe/London`, `America/New_York` or `Australia/Melbourne`. Start typing a city (`london`, `new york`) and pick from the suggestions. |

**Reply**: only you, e.g. "Your timezone is now Europe/London."

**Errors** (only you): unknown timezone.

**Examples**

```text
/timezone set tz:Europe/London
/timezone set tz:America/New_York
```

#### `/timezone show`

Shows the timezone the bot uses for you.

**Syntax**

```text
/timezone show
```

**Parameters**: none.

**Reply**: only you, e.g. "Your timezone: Europe/London", or the group default with a pointer to `/timezone set`.

### Game data

These commands read the latest game snapshot, so they're as fresh as the last time Arda logged out or used `/reload` (see [How game data reaches Discord](#how-game-data-reaches-discord)).

#### `/group`

Shows everyone in the latest snapshot, highest level first: level, race and class, zone, item level, professions with skill level, and when each was last seen in game.

**Syntax**

```text
/group
```

**Parameters**: none.

**Reply**: everyone. Before the first snapshot arrives, it says there's no game data yet.

Sample reply:

```text
Brynn 27 Dwarf Paladin · Wetlands · iLvl 31 · Mining 140, Blacksmithing 135 · seen 2 hours ago
Corwin 25 Human Mage · Duskwood · iLvl 28 · Tailoring 120, Enchanting 95 · seen 2 hours ago
Dara 24 Night Elf Druid · Ashenvale · iLvl 27 · Herbalism 125, Alchemy 110 · seen 3 days ago
```

#### `/dungeons`

Lists up to 8 dungeons whose level range overlaps the group's levels, best fits first:

1. fewest people out of range;
2. then dungeons in your faction's territory;
3. then the lowest level, then the name.

**Syntax**

```text
/dungeons [level:<1-60>]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `level` | Number, 1–60 | The group's levels | Check a single level instead, e.g. for an alt or someone not in the snapshot. |

**Reply**: everyone. ✅ means everyone is in range; ➖ means someone isn't, and "too low" and "too high" name them. Notes in brackets flag a dungeon in the other faction's territory, a 10-player dungeon, and a range that isn't confirmed yet.

**Notes**

- The group's levels are everyone in the latest snapshot who was seen in the last 30 days.
- The group's faction is the most common one in the snapshot. Dungeons inside the other faction's capital (Ragefire Chasm, the Stockade) are hidden.
- The ranges and their sources are described under [Dungeon data](#dungeon-data).

**Examples**

| You type | Result |
|---|---|
| `/dungeons` | Dungeons for the whole group |
| `/dungeons level:24` | Dungeons for a level-24 character |

Sample reply for an Alliance group of levels 27, 25 and 24:

```text
Brynn 27 · Corwin 25 · Dara 24

✅ Shadowfang Keep 20–30 · Silverpine Forest (range unconfirmed)
✅ Blackfathom Deeps 24–32 · Ashenvale (range unconfirmed)
✅ Excavation Site: Wetlands 24–29 · Wetlands
✅ The Stockade 24–32 · Stormwind City (range unconfirmed)
➖ The Deadmines 17–26 · Westfall (range unconfirmed)
  too high: Brynn
➖ Wailing Caverns 15–24 · The Barrens (range unconfirmed)
  too high: Brynn, Corwin
```

#### `/craft`

Finds who in the group knows a recipe.

**Syntax**

```text
/craft item:<name>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `item` | Text, required | | An item or recipe name. Suggestions list recipes the group knows. An exact name (any capitalisation) finds that recipe. Otherwise every word you type must appear in the name. Up to 10 matches are shown, those starting with what you typed first. |

**Reply**: everyone. Each match lists who can craft it, with their profession and skill level. A footnote names anyone who hasn't shared recipes yet.

**Notes**: the game only lists recipes while a profession window is open, so **each player opens each of their profession windows once**, and again after learning new recipes.

**Examples**

| You type | Result |
|---|---|
| `/craft item:Heavy Linen Bandage` | Who can make Heavy Linen Bandage |
| `/craft item:linen` | Every known recipe with "linen" in its name |
| `/craft item:copper chain` | Recipes with both words, like Copper Chain Belt and Copper Chain Vest |

Sample reply:

```text
Heavy Linen Bandage: Brynn (First Aid 80), Dara (First Aid 115)
No recipes yet from Corwin: open each profession window once in game.
```

#### `/order add`

Posts a crafting request for the group.

**Syntax**

```text
/order add item:<name> [quantity:<1-200>] [note:<text>]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `item` | Text, required | | What you want crafted. Suggestions list recipes the group knows. |
| `quantity` | Number, 1–200 | 1 | How many. |
| `note` | Text, up to 200 characters | | Anything the crafter should know. |

**Reply**: everyone. If `item` exactly matches a recipe someone has shared, the order uses that recipe's name and shows who can craft it. Otherwise it's saved as typed (first 100 characters), with a note that nobody has shared a recipe by that exact name.

**Examples**

| You type | Result |
|---|---|
| `/order add item:Minor Healing Potion quantity:10 note:for the Deadmines run` | Order for 10 potions, with the note |
| `/order add item:Copper Chain Vest` | Order for one vest |

Sample reply:

```text
📦 New order #7 10× Minor Healing Potion for Dara (for the Deadmines run) · can craft: Corwin (Alchemy 85)
```

#### `/order list`

Lists every open order, oldest first, with who can craft each.

**Syntax**

```text
/order list
```

**Parameters**: none.

**Reply**: everyone.

Sample reply:

```text
#7 10× Minor Healing Potion for Dara (for the Deadmines run) · can craft: Corwin (Alchemy 85)
#8 1× Copper Chain Vest for Ember · can craft: Brynn (Blacksmithing 135)
```

#### `/order done`

Marks an order as crafted and handed over, and mentions the person who asked for it. Anyone can mark any order done.

**Syntax**

```text
/order done order_id:<number>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `order_id` | Number, required | | The order number. Suggestions list open orders; type a number or part of the item name. |

**Reply**: everyone, e.g. "✅ Order #7 (10× Minor Healing Potion) is done. @Dara"

**Errors** (only you): "No open order #7" when the order doesn't exist or is already closed.

**Example**

```text
/order done order_id:7
```

#### `/order cancel`

Withdraws an order. Only the person who placed it can cancel it.

**Syntax**

```text
/order cancel order_id:<number>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `order_id` | Number, required | | The order number. Suggestions list open orders. |

**Reply**: everyone, e.g. "🚫 Order #7 (10× Minor Healing Potion) was cancelled."

**Errors** (only you): the order isn't open, or someone else placed it. In that case, use `/order done` once it's crafted.

**Example**

```text
/order cancel order_id:7
```

### In game: `/caravan`

Type these in the game's chat box. Replies appear in your chat window, and only you see them. Your list is the set of players whose data your addon accepts and shares, so each player adds the others once. A name typed without a realm gets your own realm.

Any other word after `/caravan` (e.g. `/caravan help`) prints the list of commands.

#### `/caravan`

Opens or closes The Caravan window: your group's characters (hover a row for gear and professions) and upcoming sessions from Discord. `/caravan show` and the minimap button do the same.

**Syntax**

```text
/caravan
```

#### `/caravan add`

Adds a player to your list, and asks them for their data straight away.

**Syntax**

```text
/caravan add [Name[-Realm]]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `Name-Realm` | Character name | Your target | The player to add. Without a realm, your own realm is used. |

**Reply**: "Dara-YourRealm added." With no name and no player targeted, it prints how to use the command.

**Examples**

| You type | Result |
|---|---|
| `/caravan add Dara` | Adds Dara from your realm |
| `/caravan add Dara-OtherRealm` | Adds Dara from OtherRealm |
| `/caravan add` (with a player targeted) | Adds your target |

#### `/caravan addparty`

Adds everyone in your party or raid who isn't on your list yet. `/caravan addgroup` does the same.

**Syntax**

```text
/caravan addparty
```

**Reply**: "Added Brynn-YourRealm, Corwin-YourRealm." or "Nobody new to add."

#### `/caravan remove`

Removes a player from your list and deletes their character and recipe data from your addon. On Arda's copy, this also drops them from the next snapshot, and so from Discord.

**Syntax**

```text
/caravan remove <Name[-Realm]>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `Name-Realm` | Character name, required | | The player to remove. Without a realm, your own realm is used. |

**Reply**: "Dara-YourRealm removed." or "Not on your list: Dara".

**Example**

```text
/caravan remove Dara
```

#### `/caravan list`

Prints the players on your list.

**Syntax**

```text
/caravan list
```

**Reply**: "Friends: Brynn-YourRealm, Corwin-YourRealm, Dara-YourRealm", or a hint to use `/caravan addparty` when the list is empty.

#### `/caravan sync`

Refreshes your own data, sends it to the group now, and asks everyone for theirs. Sharing normally happens on its own; use this when someone's data in the window looks out of date. It doesn't upload anything to Discord; that happens when Arda logs out or uses `/reload`.

**Syntax**

```text
/caravan sync
```

**Reply**: "Sent your data to the group." or "You're not in a group."

#### `/caravan minimap`

Shows or hides the minimap button. The setting is remembered.

**Syntax**

```text
/caravan minimap
```

## Game-data features

The bot knows what happens in game through the addon. Four commands read that data on request: [`/group`](#group), [`/dungeons`](#dungeons), [`/craft`](#craft) and [`/order`](#order-add). Two features post on their own: [level-gap alerts](#level-gap-alerts) and [session recaps](#session-recaps).

| Feature | What you get | Where | Turned on by |
|---|---|---|---|
| [`/group`](#group) | Everyone's level, class, zone, item level, professions, last seen | Where you type it | Always on |
| [`/dungeons`](#dungeons) | Dungeons that suit the group, with who's too low or too high | Where you type it | Always on |
| [`/craft`](#craft), [`/order`](#order-add) | Who can craft what, and a shared crafting queue | Where you type it | Players opening their profession windows |
| [Level-gap alerts](#level-gap-alerts) | A post when someone pulls ahead of the group | `ALERTS_CHANNEL_ID`, else the sessions channel | `LEVEL_GAP` (default 3; 0 turns it off) |
| [Session recaps](#session-recaps) | Levels, dungeon runs and loot from each session | The session's channel | Always on |

### How game data reaches Discord

```text
Each player's addon ── shares over party chat while grouped ──▶ Arda's addon
                                                                   │ logout, /reload or exit
                                                                   ▼
                                     TheCaravan.lua (SavedVariables on Arda's Mac)
                                                                   │ sync app checks every 5 s,
                                                                   ▼ uploads when it changes
                                       Bot ──▶ commands, level-gap alerts, recaps
```

1. Each player's addon records their own character and shares it with the party, but only with players on their [`/caravan` list](#in-game-caravan).
2. Arda's addon therefore holds the whole group. The game writes it to disk on logout, `/reload` and exit, never during play.
3. The sync app on Arda's Mac notices the file change within 5 seconds and uploads it to the bot as a snapshot.
4. The bot keeps the latest snapshot. Commands read it, and each new one can set off a level-gap alert or a recap.

So Discord is as up to date as Arda's last logout or `/reload`, and a friend's progress reaches it only after they've been grouped with Arda.

### What the addon records

| Data | Recorded | Kept |
|---|---|---|
| Level, XP, zone, class, race, faction, item level, gear, professions | On login and whenever one changes | The latest values |
| Known recipes | When you open a profession window | The latest list; sent to others only when their copy differs |
| Level-ups | Each level gained | The last 20, up to 14 days |
| Notable loot | Each rare (blue) or better item you loot | The last 20, up to 14 days |
| Dungeon runs | Entering a dungeon and each boss kill. Re-entering within 30 minutes continues the same run. | The last 10, up to 14 days |

The addon sends nothing in combat or during boss encounters, and catches up afterwards.

### What each player needs to do

- Install the addon and run `/caravan addparty` once while grouped (see [Setup](#3-addon)).
- **Open each of your profession windows once**, and again after learning new recipes, so `/craft` and `/order` know what you can make.
- Group with Arda during sessions, so your data reaches Arda's addon.
- Arda: log out or `/reload` after a session, so the snapshot, and with it the recap, reaches Discord.

### Level-gap alerts

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

### Session recaps

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

### Dungeon data

`/dungeons` uses the 35 dungeons in `src/caravan/bot/dungeons.py`, each with a level range, zone, faction territory and source:

- **The nine new Forever dungeons** use the ranges from Blizzard's announcement.
- **The 26 reworked classic dungeons** use community tables (wowforeverguides.com and WCLBox) that haven't been confirmed in game yet, so `/dungeons` marks them "range unconfirmed". Fix a range in that file once you've checked it in game.

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
