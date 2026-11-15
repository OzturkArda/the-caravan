"""WoW Forever dungeons and their level ranges, for /dungeons.

Forever reworked the classic dungeons' level ranges and added nine new ones,
so these are not the 2004 numbers. Sources (checked 2026-11-16):

- BLIZZARD: "Explore the New Dungeons of World of Warcraft: Forever",
  https://news.blizzard.com/en-us/article/24301455 - the nine new dungeons.
- REPORTED: the "Dungeons by Level" tables at https://wowforeverguides.com/dungeons/by-level
  (updated 2026-11-09) and https://wowforever.wclbox.com/en/fuben, which agree
  on every classic dungeon. wowforeverguides marks them "reported" (press or
  datamine, not confirmed by Blizzard) and WCLBox covers the beta, so check
  them against the live game and correct them here.

Both community tables list wider ranges for some new dungeons than Blizzard
does (e.g. Hall of Thanes 13-20); Blizzard's numbers are used.
"""

from __future__ import annotations

from dataclasses import dataclass

BLIZZARD = "blizzard"
REPORTED = "reported"


@dataclass(frozen=True)
class Dungeon:
    name: str
    low: int
    high: int
    zone: str
    source: str
    territory: str | None = None  # "Alliance" or "Horde" when the entrance is in that faction's land
    in_city: bool = False  # entrance inside that faction's capital: the other faction can't use it
    players: int = 5


DUNGEONS: tuple[Dungeon, ...] = (
    Dungeon("Ragefire Chasm", 13, 18, "Orgrimmar", REPORTED, "Horde", in_city=True),
    Dungeon("Hall of Thanes", 13, 18, "Dun Morogh, beneath Ironforge", BLIZZARD, "Alliance"),
    Dungeon("Ruins of Lordaeron", 15, 20, "Tirisfal Glades, above the Undercity", BLIZZARD, "Horde"),
    Dungeon("Wailing Caverns", 15, 24, "The Barrens", REPORTED),
    Dungeon("The Deadmines", 17, 26, "Westfall", REPORTED),
    Dungeon("Shadowfang Keep", 20, 30, "Silverpine Forest", REPORTED),
    Dungeon("Blackfathom Deeps", 24, 32, "Ashenvale", REPORTED),
    Dungeon("The Stockade", 24, 32, "Stormwind City", REPORTED, "Alliance", in_city=True),
    Dungeon("Excavation Site: Wetlands", 24, 29, "Wetlands", BLIZZARD),
    Dungeon("City of Dalaran", 28, 33, "Alterac Mountains", BLIZZARD),
    Dungeon("Gnomeregan", 29, 38, "Dun Morogh", REPORTED),
    Dungeon("Razorfen Kraul", 29, 38, "The Barrens", REPORTED),
    Dungeon("Scarlet Monastery: Graveyard", 30, 38, "Tirisfal Glades", REPORTED),
    Dungeon("Scarlet Monastery: Library", 33, 41, "Tirisfal Glades", REPORTED),
    Dungeon("The Drowned City", 35, 40, "off the coast of Stranglethorn Vale", BLIZZARD),
    Dungeon("Scarlet Monastery: Armory", 36, 44, "Tirisfal Glades", REPORTED),
    Dungeon("Razorfen Downs", 37, 46, "The Barrens", REPORTED),
    Dungeon("Scarlet Monastery: Cathedral", 38, 46, "Tirisfal Glades", REPORTED),
    Dungeon("Krol'dok Stronghold", 40, 45, "Riverglades", BLIZZARD),
    Dungeon("Uldaman", 41, 51, "Badlands", REPORTED),
    Dungeon("Zul'Farrak", 44, 54, "Tanaris", REPORTED),
    Dungeon("Maraudon", 46, 55, "Desolace", REPORTED),
    Dungeon("Alcaz Prison", 48, 53, "Dustwallow Marsh", BLIZZARD),
    Dungeon("Sunken Temple", 50, 60, "Swamp of Sorrows", REPORTED),
    Dungeon("Blackrock Depths", 52, 60, "Blackrock Mountain", REPORTED),
    Dungeon("Dire Maul East", 54, 60, "Feralas", REPORTED),
    Dungeon("Lower Blackrock Spire", 55, 60, "Blackrock Mountain", REPORTED),
    Dungeon("Blackmaw Hold", 55, 60, "Azshara", BLIZZARD),
    Dungeon("Dire Maul West", 56, 60, "Feralas", REPORTED),
    Dungeon("Dire Maul North", 56, 60, "Feralas", REPORTED),
    Dungeon("Scholomance", 58, 60, "Western Plaguelands", REPORTED),
    Dungeon("Shaper's Terrace", 58, 60, "Un'Goro Crater", BLIZZARD),
    Dungeon("Stratholme: Main Gate", 58, 60, "Eastern Plaguelands", REPORTED),
    Dungeon("Stratholme: Service Gate", 58, 60, "Eastern Plaguelands", REPORTED),
    Dungeon("Upper Blackrock Spire", 59, 60, "Blackrock Mountain", REPORTED, players=10),
)
