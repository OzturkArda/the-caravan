# Commands

Every command The Caravan understands. The bot's slash commands work in any channel the bot can see; the addon's `/caravan` commands are typed in the game's chat box. For a one-line summary of each, see the [quick reference](../README.md#commands) in the README.

How to read the entries:

- **Syntax** uses `<name>` for a required option and `[name]` for an optional one. In Discord, type the command, then pick each option from the list that appears. The examples write options as `name:value`, the way Discord shows them.
- **Reply** says who sees the bot's answer: *everyone* in the channel, or *only you* (Discord marks these "Only you can see this").
- **Times you type** are read in your timezone: the one you set with [`/timezone set`](#timezone-set), or the group default `GROUP_TZ` (Australia/Melbourne unless changed in `bot.env`). The bot shows times as Discord timestamps, so each reader sees them in their own local time.
- **Sample replies** show what Discord displays, with placeholder character names.

**Contents**

- [Sessions](#sessions): [`/session add`](#session-add), [`/session list`](#session-list), [`/session cancel`](#session-cancel), [`/session suggest`](#session-suggest)
- [Availability and timezone](#availability-and-timezone): [`/availability add`](#availability-add), [`/availability clear`](#availability-clear), [`/availability show`](#availability-show), [`/timezone set`](#timezone-set), [`/timezone show`](#timezone-show)
- [Game data](#game-data): [`/group`](#group), [`/dungeons`](#dungeons), [`/craft`](#craft), [`/order add`](#order-add), [`/order list`](#order-list), [`/order done`](#order-done), [`/order cancel`](#order-cancel)
- [Characters](#characters): [`/character link`](#character-link), [`/character unlink`](#character-unlink), [`/character list`](#character-list)
- [In game: `/caravan`](#in-game-caravan): [`/caravan`](#caravan), [`add`](#caravan-add), [`addparty`](#caravan-addparty), [`remove`](#caravan-remove), [`list`](#caravan-list), [`sync`](#caravan-sync), [`minimap`](#caravan-minimap), [`reminders`](#caravan-reminders)

## Sessions

### `/session add`

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
- Before the start, the bot posts reminders (`REMINDER_OFFSETS`, default 60 and 15 minutes before) that mention everyone who is **In** or **Late**, e.g. "⏰ **Deadmines run** starts at 19:30 (in 15 minutes)" with a link to the card. Discord shows both times in each reader's local time. If the bot was offline when reminders fell due, it sends only one when it's back.
- The Discord event needs the bot's **Manage Events** permission. Without it, the session is still scheduled, just without an event.

**Examples**

| You type | Result |
|---|---|
| `/session add when:fri 8pm` | Friday 20:00 to 23:00, titled "Caravan session" |
| `/session add when:tomorrow 7:30pm title:Deadmines run duration:120` | Tomorrow 19:30 to 21:30 |
| `/session add when:21/11 19:00 title:Gnomeregan` | 21 November at 19:00 |
| `/session add when:8pm` | Today at 20:00, or tomorrow if 20:00 has passed |

**See also**: [`/session suggest`](#session-suggest) to find a time, [Session recaps](GAME-DATA.md#session-recaps).

### `/session list`

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

### `/session cancel`

Cancels a session. The card is struck through and loses its buttons, the Discord event is deleted, and no reminders or recap follow. Only the person who scheduled the session can cancel it, or a member with the **Manage Server** or **Administrator** permission. There's no undo; schedule it again with `/session add`.

**Syntax**

```text
/session cancel session_id:<number>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `session_id` | Number, required | | The number on the card's footer (`Session #12`) or in `/session list`. |

**Reply**: everyone, e.g. "Cancelled **Deadmines run** (#12)."

**Errors** (only you):

- "No active session #12" when there's no such session or it's already cancelled.
- "Only @Brynn, who scheduled session #12, or someone with Manage Server can cancel it." when it isn't yours to cancel.

**Example**

```text
/session cancel session_id:12
```

### `/session suggest`

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

## Availability and timezone

### `/availability add`

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

### `/availability clear`

Removes all of your weekly windows. Other people's windows aren't touched.

**Syntax**

```text
/availability clear
```

**Parameters**: none.

**Reply**: only you, e.g. "Removed 3 window(s)."

### `/availability show`

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

### `/timezone set`

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

### `/timezone show`

Shows the timezone the bot uses for you.

**Syntax**

```text
/timezone show
```

**Parameters**: none.

**Reply**: only you, e.g. "Your timezone: Europe/London", or the group default with a pointer to `/timezone set`.

## Game data

These commands read the latest game snapshot, so they're as fresh as the last time Arda logged out or used `/reload` (see [How game data reaches Discord](GAME-DATA.md#how-game-data-reaches-discord)).

### `/group`

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

### `/dungeons`

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
- The ranges and their sources are described under [Dungeon data](GAME-DATA.md#dungeon-data).

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

### `/craft`

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

### `/order add`

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

### `/order list`

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

### `/order done`

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

### `/order cancel`

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

## Characters

Linking tells the bot which WoW characters are yours, so the **In**, **Late** and **Out** buttons in the addon's [Sessions tab](#the-sessions-tab) count as your RSVP in Discord. Link each character you play, alts included. A character belongs to one Discord account at a time.

### `/character link`

Links a WoW character to you.

**Syntax**

```text
/character link name:<character>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `name` | Text, required | | `Name` or `Name Surname`, as the game shows it (`Name-Surname` works too). Suggestions list the characters in the latest game snapshot. Without a surname, the name must match exactly one character there. |

**Reply**: only you, e.g. "Linked **Dara-Brightwood** to you. In, Late and Out in the addon's Sessions tab now count as yours." When the character isn't in the latest snapshot yet, a note asks you to check the surname's spelling.

**Errors** (only you): the name matches no character, or several, without a surname ("Add the surname, e.g. `Roland Ironvale`"); the character is linked to someone else ("They can `/character unlink` it first").

**Examples**

| You type | Result |
|---|---|
| `/character link name:Dara` | Links Dara, if only one Dara is in the snapshot |
| `/character link name:Dara Brightwood` | Links Dara Brightwood, snapshot or not |

### `/character unlink`

Unlinks a character. Only the player it's linked to, or someone with **Manage Server**, can unlink it.

**Syntax**

```text
/character unlink name:<character>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `name` | Text, required | | `Name` or `Name Surname` of a linked character. |

**Reply**: only you, e.g. "Unlinked **Dara-Brightwood**."

**Errors** (only you): the character isn't linked; it's linked to someone else and you don't have Manage Server.

### `/character list`

Shows who has linked which characters.

**Syntax**

```text
/character list
```

**Reply**: only you, one line per player, e.g. "**Dara**: Dara-Brightwood, Dalt-Brightwood".

## In game: `/caravan`

Type these in the game's chat box. Replies appear in your chat window, and only you see them. Your list is the set of players whose data your addon accepts and shares, so each player adds the others once. WoW Forever has no realms, so type a player's full name, first name and surname, as the game shows it above their head.

Any other word after `/caravan` (e.g. `/caravan help`) prints the list of commands.

### `/caravan`

Opens or closes The Caravan window. `/caravan show` and the minimap button do the same. Drag the title to move it and the bottom-right corner to resize it; the size and position are remembered. Columns share out the width, and the list scrolls when it's longer than the window.

**Syntax**

```text
/caravan
```

#### The Group tab

Your group's characters: level with XP progress, zone, professions, item level (the average of worn gear) and when their data was last updated. Professions switch to short names when the column is too narrow for the full list. Hover a row for XP, every profession with its skill and every piece of gear.

#### The Sessions tab

Upcoming sessions from Discord, with who's coming and who's out. People who have [linked a character](#characters) show under that character's name. Hover a row for the full details.

The **You** column has **In**, **Late** and **Out** buttons; your current answer is highlighted. A click is saved straight away and marked with `*` until Discord has it:

- On the Mac that runs the sync app, Discord gets it at your next `/reload` or logout.
- Everyone else's addon passes it on while grouped, so it reaches Discord once you've grouped with the player who runs the sync app and they `/reload` or log out.

It counts only for a [linked](#character-link) character; the footer says so when yours isn't. A later click in Discord replaces it.

The session list itself comes from the sync app, or from any friend's addon when you group up, whichever is newer. Changes made in Discord while you play arrive after the sync app's player restarts the game. The footer says when the list was synced and who passed it on.

### `/caravan add`

Adds a player to your list, and asks them for their data straight away.

**Syntax**

```text
/caravan add [Name Surname]
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `Name Surname` | Character name | Your target | The player to add. `Name-Surname` works too. |

**Reply**: "Dara-Brightwood added." With no name and no player targeted, it prints how to use the command.

**Examples**

| You type | Result |
|---|---|
| `/caravan add Dara Brightwood` | Adds Dara Brightwood |
| `/caravan add` (with a player targeted) | Adds your target |

### `/caravan addparty`

Adds everyone in your party or raid who isn't on your list yet. `/caravan addgroup` does the same.

**Syntax**

```text
/caravan addparty
```

**Reply**: "Added Brynn-Ashford, Corwin-Vale." or "Nobody new to add."

### `/caravan remove`

Removes a player from your list and deletes their character and recipe data from your addon. On Arda's copy, this also drops them from the next snapshot, and so from Discord.

**Syntax**

```text
/caravan remove <Name Surname>
```

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `Name Surname` | Character name, required | | The player to remove. `Name-Surname` works too. |

**Reply**: "Dara-Brightwood removed." or "Not on your list: Dara Brightwood".

**Example**

```text
/caravan remove Dara
```

### `/caravan list`

Prints the players on your list.

**Syntax**

```text
/caravan list
```

**Reply**: "Friends: Brynn-Ashford, Corwin-Vale, Dara-Brightwood", or a hint to use `/caravan addparty` when the list is empty.

### `/caravan sync`

Refreshes your own data, sends it to the group now, and asks everyone for theirs. Sharing normally happens on its own; use this when someone's data in the window looks out of date. It doesn't upload anything to Discord; that happens when Arda logs out or uses `/reload`.

**Syntax**

```text
/caravan sync
```

**Reply**: "Sent your data to the group." or "You're not in a group."

### `/caravan minimap`

Shows or hides the minimap button. The setting is remembered.

**Syntax**

```text
/caravan minimap
```

### `/caravan reminders`

Turns in-game session reminders off or on. They're on by default and the setting is remembered.

A reminder comes at the same times as the bot's Discord reminders (`REMINDER_OFFSETS`, 60 and 15 minutes before by default): a line in chat, a raid-warning banner in the middle of the screen and the raid-warning sound. There's none for a session you've said you're **Out** of, and none for times that passed before you logged in; the login message ("Next session: …") covers those.

**Syntax**

```text
/caravan reminders
```

**Reply**: "Session reminders off." or "Session reminders on."

**Sample reminder**

```text
Deadmines run starts in 15 minutes (19:30).
```
