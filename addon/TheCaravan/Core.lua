-- The Caravan: shares each member's character with the group and shows
-- upcoming sessions that the sync app copies in from Discord.

local ADDON_NAME, ns = ...

local Caravan = LibStub("AceAddon-3.0"):NewAddon(
	ADDON_NAME, "AceConsole-3.0", "AceEvent-3.0", "AceTimer-3.0", "AceComm-3.0", "AceSerializer-3.0"
)
ns.Caravan = Caravan
_G.TheCaravan = Caravan

Caravan.SCHEMA = 1
Caravan.PREFIX = "TheCaravan"
Caravan.COLOUR = "ffc99140"

local function trim(s)
	return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

function Caravan:OnInitialize()
	if type(TheCaravanDB) ~= "table" then
		TheCaravanDB = {}
	end
	local db = TheCaravanDB
	db.roster = db.roster or {}   -- [lowercase "name-realm"] = "Name-Realm"
	db.members = db.members or {} -- ["Name-Realm"] = member data (see Collect.lua)
	db.recipes = db.recipes or {} -- ["Name-Realm"] = known recipes (see Recipes.lua)
	db.log = db.log or {}         -- ["Name-Realm"] = this account's characters' history (see Log.lua)
	db.minimap = db.minimap or { angle = 200, hide = false }
	db.window = db.window or {}   -- saved size and position of the window (UI.lua)
	db.rsvps = db.rsvps or {}     -- ["Name-Realm"] = in-game RSVPs (see Rsvp.lua)
	if db.reminders == nil then
		db.reminders = true       -- in-game session reminders (Schedule.lua)
	end
	self.db = db
	self.unlisted = {}
	self.recipeAsked = {}
	self:RegisterChatCommand("caravan", "OnSlashCommand")
end

function Caravan:OnEnable()
	self.selfName = self:PlayerFullName()
	self.db.lastCharacter = self.selfName
	self:RegisterComm(self.PREFIX, "OnCommReceived")
	self:RegisterEvent("PLAYER_ENTERING_WORLD", "OnEnteringWorld")
	self:RegisterEvent("PLAYER_LEVEL_UP", "OnLevelUp")
	self:RegisterEvent("PLAYER_EQUIPMENT_CHANGED", "QueueUpdate", 5)
	self:RegisterEvent("SKILL_LINES_CHANGED", "QueueUpdate", 5)
	self:RegisterEvent("ZONE_CHANGED_NEW_AREA", "OnZoneChanged")
	self:RegisterEvent("PLAYER_XP_UPDATE", "OnXPUpdate")
	self:RegisterEvent("GROUP_ROSTER_UPDATE", "OnGroupChanged")
	self:RegisterEvent("PLAYER_REGEN_ENABLED", "FlushPending")
	self:RegisterEvent("ENCOUNTER_END", "OnEncounterEnd")
	self:RegisterEvent("CHAT_MSG_LOOT", "OnLoot")
	self:RegisterEvent("TRADE_SKILL_SHOW", "QueueRecipeScan")
	self:RegisterEvent("TRADE_SKILL_LIST_UPDATE", "QueueRecipeScan")
	self:RegisterEvent("TRADE_SKILL_DATA_SOURCE_CHANGED", "QueueRecipeScan")
	self:RegisterEvent("PLAYER_LOGOUT", "OnLogout")
	self:CreateMinimapButton()
end

function Caravan:OnEnteringWorld(_, isLogin, isReload)
	if isLogin or isReload then
		self:PruneLog()
		self:PruneRsvps()
	end
	self:TrackInstance()
	self:QueueUpdate(5)
	self:OnGroupChanged()
	if isLogin or isReload then
		self:ScheduleTimer("AnnounceNextSession", 10)
		self:ScheduleReminders()
	end
end

-- Names -----------------------------------------------------------------
--
-- Players are keyed "Name-Realm". WoW Forever has no realms: names are unique
-- across the region and carry a surname. UnitFullName returns the surname
-- where other clients return the realm, and addon messages arrive from
-- "Name Surname". Both become "Name-Surname", so every path gives one key.

local function capitalise(s)
	return s:sub(1, 1):upper() .. s:sub(2):lower()
end

local function join(name, second)
	if second and second ~= "" then
		return name .. "-" .. second
	end
	return name
end

-- "" on WoW Forever.
function Caravan:RealmName()
	local realm = GetNormalizedRealmName and GetNormalizedRealmName()
	if not realm or realm == "" then
		realm = (GetRealmName() or ""):gsub("[%s%-]", "")
	end
	return realm
end

function Caravan:PlayerFullName()
	local name, realm = UnitFullName("player")
	if not realm or realm == "" then
		realm = self:RealmName()
	end
	return join(name, realm)
end

-- "Name", "Name-Realm" or "Name Surname" as the client reports it
-- -> "Name-Realm" or "Name-Surname".
function Caravan:Normalize(name)
	if type(name) ~= "string" then
		return nil
	end
	name = trim(name)
	if name == "" then
		return nil
	end
	if not name:find("-", 1, true) then
		local first, rest = name:match("^(%S+)%s+(.+)$")
		if first then
			name = first .. "-" .. (rest:gsub("%s+", ""))
		else
			name = join(name, self:RealmName())
		end
	end
	return name
end

-- A name typed by the player: capitalise it like the game does (the surname
-- too, where there are no realms).
function Caravan:NormalizeInput(text)
	local full = self:Normalize(text)
	if not full then
		return nil
	end
	local char, second = full:match("^([^-]+)-(.+)$")
	if not char then
		return capitalise(full)
	end
	if self:RealmName() == "" then
		second = capitalise(second)
	end
	return capitalise(char) .. "-" .. second
end

function Caravan:UnitFullNameNormalized(unit)
	if not UnitIsPlayer(unit) then
		return nil
	end
	local name, realm = UnitFullName(unit)
	if not name then
		return nil
	end
	if not realm or realm == "" then
		realm = self:RealmName()
	end
	return join(name, realm)
end

function Caravan:GroupUnits()
	local units = {}
	if IsInRaid() then
		for i = 1, GetNumGroupMembers() do
			units[#units + 1] = "raid" .. i
		end
	elseif IsInGroup() then
		for i = 1, GetNumGroupMembers() - 1 do
			units[#units + 1] = "party" .. i
		end
	end
	return units
end

-- Roster ----------------------------------------------------------------

function Caravan:IsOnRoster(fullName)
	return fullName ~= nil and self.db.roster[fullName:lower()] ~= nil
end

function Caravan:AddToRoster(fullName)
	if not fullName or fullName == self.selfName then
		return false
	end
	self.db.roster[fullName:lower()] = fullName
	self.unlisted[fullName] = nil
	return true
end

function Caravan:RemoveFromRoster(fullName)
	local key = fullName and fullName:lower()
	local stored = key and self.db.roster[key]
	if not stored then
		return false
	end
	self.db.roster[key] = nil
	self.db.members[stored] = nil
	self.db.recipes[stored] = nil
	return true
end

function Caravan:RosterNames()
	local names = {}
	for _, name in pairs(self.db.roster) do
		names[#names + 1] = name
	end
	table.sort(names)
	return names
end

-- Slash commands --------------------------------------------------------

local HELP = {
	"/caravan - open or close the window",
	"/caravan add Name Surname - add a friend (no name: your target)",
	"/caravan addparty - add everyone in your group",
	"/caravan remove Name Surname - remove a friend",
	"/caravan list - show your friends list",
	"/caravan sync - send your data and ask the group for theirs",
	"/caravan minimap - show or hide the minimap button",
	"/caravan reminders - turn session reminders on or off",
}

function Caravan:Say(text)
	self:Print(text)
end

function Caravan:OnSlashCommand(input)
	local cmd, rest = (input or ""):match("^%s*(%S*)%s*(.-)%s*$")
	cmd = (cmd or ""):lower()
	if cmd == "" or cmd == "show" then
		self:ToggleWindow()
	elseif cmd == "add" then
		local name
		if rest ~= "" then
			name = self:NormalizeInput(rest)
		else
			name = self:UnitFullNameNormalized("target")
		end
		if not name then
			self:Say("Usage: /caravan add Name Surname, or target a player first.")
		elseif self:AddToRoster(name) then
			self:Say(name .. " added.")
			self:RequestData()
			self:UpdateWindow()
		end
	elseif cmd == "addparty" or cmd == "addgroup" then
		local added = {}
		for _, unit in ipairs(self:GroupUnits()) do
			local name = self:UnitFullNameNormalized(unit)
			if name and not self:IsOnRoster(name) and self:AddToRoster(name) then
				added[#added + 1] = name
			end
		end
		self:Say(#added > 0 and ("Added " .. table.concat(added, ", ") .. ".") or "Nobody new to add.")
		if #added > 0 then
			self:RequestData()
			self:UpdateWindow()
		end
	elseif cmd == "remove" then
		local name = self:NormalizeInput(rest)
		if name and self:RemoveFromRoster(name) then
			self:Say(name .. " removed.")
			self:UpdateWindow()
		else
			self:Say("Not on your list: " .. rest)
		end
	elseif cmd == "list" then
		local names = self:RosterNames()
		self:Say(#names > 0 and ("Friends: " .. table.concat(names, ", ")) or "Your list is empty. /caravan addparty adds your group.")
	elseif cmd == "sync" then
		self:RefreshSelf()
		self:Broadcast(true)
		self:RequestData()
		self:Say(self:GroupChannel() and "Sent your data to the group." or "You're not in a group.")
	elseif cmd == "minimap" then
		self.db.minimap.hide = not self.db.minimap.hide
		self:UpdateMinimapButton()
	elseif cmd == "reminders" then
		self.db.reminders = self.db.reminders == false
		self:ScheduleReminders()
		self:Say(self.db.reminders and "Session reminders on." or "Session reminders off.")
	else
		for _, line in ipairs(HELP) do
			self:Say(line)
		end
	end
end

function Caravan:OnZoneChanged()
	self:TrackInstance()
	self:QueueUpdate(5)
end

function TheCaravan_OnAddonCompartmentClick()
	Caravan:ToggleWindow()
end
