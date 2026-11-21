-- A small fake of the WoW client, enough to load Ace3 and The Caravan and
-- drive them from tests: events, timers, addon messages and unit data.

local W = {
	now = 100,                  -- GetTime()
	serverEpoch = 1794800000,   -- GetServerTime() at now = 0
	timers = {},
	frames = {},
	outbox = {},
	prints = {},
	errors = {},
	loggedIn = false,
	inCombat = false,
	realm = "Ironvale",
	player = {
		name = "Roland", class = "WARRIOR", className = "Warrior", race = "Human",
		level = 14, xp = 500, xpMax = 8000, zone = "Elwynn Forest",
	},
	profs = { { name = "Mining", rank = 52, max = 75 }, { name = "Blacksmithing", rank = 40, max = 75 } },
	gear = { [1] = { id = 7413, il = 15 }, [16] = { id = 1292, il = 14 } },
	group = {},                 -- { { name = "Friend", realm = nil or "Other" } }
	target = nil,
}
WOW = W

-- Frames ------------------------------------------------------------------

local Frame = {}
Frame.__index = function(self, key)
	local method = rawget(Frame, key)
	if method then
		return method
	end
	-- Any other widget method: accept the call, return a new stub object.
	return function()
		return setmetatable({ events = {}, scripts = {} }, Frame)
	end
end

function Frame:RegisterEvent(event) self.events[event] = true end
function Frame:UnregisterEvent(event) self.events[event] = nil end
function Frame:UnregisterAllEvents() self.events = {} end
function Frame:IsEventRegistered(event) return self.events[event] == true end
function Frame:SetScript(name, fn) self.scripts[name] = fn end
function Frame:GetScript(name) return self.scripts[name] end
function Frame:HookScript(name, fn) self.scripts[name] = fn end
function Frame:IsShown() return self.shown == true end
function Frame:Show() self.shown = true end
function Frame:Hide() self.shown = false end
function Frame:GetCenter() return 0, 0 end
function Frame:GetEffectiveScale() return 1 end

-- Size, anchors and text are remembered so layout code can be checked.
local function sized(self)
	if self.scripts.OnSizeChanged then
		self.scripts.OnSizeChanged(self, self.width, self.height)
	end
end
function Frame:SetWidth(w) self.width = w sized(self) end
function Frame:SetHeight(h) self.height = h sized(self) end
function Frame:SetSize(w, h) self.width, self.height = w, h sized(self) end
function Frame:GetWidth() return rawget(self, "width") or 140 end
function Frame:GetHeight() return rawget(self, "height") or 20 end
function Frame:ClearAllPoints() self.points = {} end
function Frame:SetPoint(point, a, b, c, d)
	self.points = rawget(self, "points") or {}
	local rel, relPoint, x, y = a, b, c, d
	if type(a) == "number" then -- SetPoint(point, x, y)
		rel, relPoint, x, y = nil, point, a, b
	elseif type(a) == "string" then -- SetPoint(point, relPoint, x, y)
		rel, relPoint, x, y = nil, a, b, c
	end
	self.points[#self.points + 1] = { point, rel, relPoint or point, x or 0, y or 0 }
end
function Frame:GetPoint(i)
	local p = rawget(self, "points") and self.points[i or 1]
	if p then
		return p[1], p[2], p[3], p[4], p[5]
	end
end
function Frame:SetText(text) self.text = text end
function Frame:GetText() return rawget(self, "text") end
-- Roughly 6 pixels a character, ignoring colour codes.
function Frame:GetStringWidth()
	local plain = tostring(rawget(self, "text") or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
	return #plain * 6
end
function Frame:GetUnboundedStringWidth() return self:GetStringWidth() end
-- Sizing by mouse: tests set W.dragSize = { w, h } before StopMovingOrSizing.
function Frame:StartSizing() self.sizing = true end
function Frame:StopMovingOrSizing()
	if rawget(self, "sizing") and W.dragSize then
		self:SetSize(W.dragSize[1], W.dragSize[2])
	end
	self.sizing = false
end

function CreateFrame(_, name)
	local f = setmetatable({ events = {}, scripts = {} }, Frame)
	W.frames[#W.frames + 1] = f
	if name then
		_G[name] = f
	end
	return f
end

UIParent = CreateFrame("Frame", "UIParent")
Minimap = CreateFrame("Frame", "Minimap")
GameTooltip = CreateFrame("Frame", "GameTooltip")
UISpecialFrames = {}
DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) W.prints[#W.prints + 1] = msg end }
SlashCmdList = {}
hash_SlashCmdList = {}
RAID_CLASS_COLORS = { WARRIOR = { colorStr = "ffc69b6d" }, MAGE = { colorStr = "ff3fc7eb" } }

-- On-screen warnings and sounds are recorded for tests.
W.notices, W.sounds = {}, {}
RaidWarningFrame = CreateFrame("Frame", "RaidWarningFrame")
ChatTypeInfo = { RAID_WARNING = { r = 1, g = 0.28, b = 0 } }
SOUNDKIT = { RAID_WARNING = 8959 }
function RaidNotice_AddMessage(_, text) W.notices[#W.notices + 1] = text end
function PlaySound(id) W.sounds[#W.sounds + 1] = id end

-- FauxScrollFrame: the offset lives on the scroll frame, as in the game.
function FauxScrollFrame_GetOffset(frame) return rawget(frame, "offset") or 0 end
function FauxScrollFrame_Update(frame, total, visible)
	frame.total, frame.visible = total, visible
end
function FauxScrollFrame_OnVerticalScroll(frame, value, rowHeight, update)
	frame.offset = math.floor(value / rowHeight + 0.5)
	update()
end

function W.fire(event, ...)
	for _, f in ipairs(W.frames) do
		if f.events[event] and f.scripts.OnEvent then
			f.scripts.OnEvent(f, event, ...)
		end
	end
end

-- Time and timers -----------------------------------------------------------

function GetTime() return W.now end
function GetServerTime() return W.serverEpoch + math.floor(W.now) end
function time() return GetServerTime() end
date = os.date
function GetFramerate() return 60 end

C_Timer = {
	After = function(delay, fn)
		W.timers[#W.timers + 1] = { at = W.now + delay, fn = fn }
	end,
}

-- Run timers and OnUpdate scripts for `seconds` of game time.
function W.advance(seconds)
	local target = W.now + seconds
	while W.now < target do
		local step = math.min(0.1, target - W.now)
		W.now = W.now + step
		local i = 1
		while i <= #W.timers do
			local t = W.timers[i]
			if t.at <= W.now then
				table.remove(W.timers, i)
				t.fn()
			else
				i = i + 1
			end
		end
		for _, f in ipairs(W.frames) do
			if f.scripts.OnUpdate then
				f.scripts.OnUpdate(f, step)
			end
		end
	end
end

-- Lua/WoW helpers ---------------------------------------------------------------

tinsert, tremove, wipe = table.insert, table.remove, function(t) for k in pairs(t) do t[k] = nil end return t end
strsub, strfind, strlen, strlower, strupper, strmatch, format = string.sub, string.find, string.len, string.lower, string.upper, string.match, string.format
function strtrim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
function securecallfunction(fn, ...) return fn(...) end
-- WoW's xpcall forwards extra arguments to the function, like Lua 5.2.
local luaXpcall = xpcall
function xpcall(fn, handler, ...)
	local n, args = select("#", ...), { ... }
	return luaXpcall(function() return fn(unpack(args, 1, n)) end, handler)
end
function geterrorhandler() return function(err) W.errors[#W.errors + 1] = tostring(err) end end
function hooksecurefunc(tbl, name, hook)
	if type(tbl) == "string" then
		tbl, name, hook = _G, tbl, name
	end
	local original = tbl[name]
	tbl[name] = function(...)
		local r = { original(...) }
		hook(...)
		return unpack(r)
	end
end
function IsLoggedIn() return W.loggedIn end
function Ambiguate(name) return name end

-- Addon messages --------------------------------------------------------------

Enum = { SendAddonMessageResult = { Success = 0, AddonMessageThrottle = 3, NotInGroup = 5, ChannelThrottle = 8, GeneralError = 9 } }
C_ChatInfo = {
	RegisterAddonMessagePrefix = function() return true end,
	IsAddonMessagePrefixRegistered = function() return true end,
	SendAddonMessage = function(prefix, text, channel, target)
		W.outbox[#W.outbox + 1] = { prefix = prefix, text = text, channel = channel, target = target }
		return 0
	end,
	SendAddonMessageLogged = function() return 0 end,
	SendChatMessage = function() end,
}
C_BattleNet = {}
function BNSendGameData() end

-- Units -----------------------------------------------------------------------

LE_PARTY_CATEGORY_HOME, LE_PARTY_CATEGORY_INSTANCE = 1, 2

local function unitInfo(unit)
	if unit == "player" then
		return { name = W.player.name }
	end
	local i = unit:match("^party(%d+)$")
	if i then
		return W.group[tonumber(i)]
	end
	if unit == "target" then
		return W.target
	end
end

function UnitIsPlayer(unit) return unitInfo(unit) ~= nil end
function UnitFullName(unit)
	local u = unitInfo(unit)
	if not u then
		return nil
	end
	if unit == "player" then
		return W.player.name, W.player.surname or W.realm -- WoW Forever: the surname
	end
	return u.name, u.realm
end
function UnitName(unit) return (UnitFullName(unit)) end
function UnitClass() return W.player.className, W.player.class end
function UnitRace() return W.player.race end
function UnitLevel() return W.player.level end
function UnitXP() return W.player.xp end
function UnitXPMax() return W.player.xpMax end
function GetRealZoneText() return W.player.zone end
function GetNormalizedRealmName() return W.realm end
function GetRealmName() return W.realm end
function InCombatLockdown() return W.inCombat end
function IsEncounterInProgress() return false end
function IsInGroup() return #W.group > 0 end
function IsInRaid() return false end
function GetNumGroupMembers() return #W.group > 0 and #W.group + 1 or 0 end

function GetProfessions()
	local function at(i) return W.profs[i] and i or nil end
	return at(1), at(2), at(3), at(4), at(5)
end
function GetProfessionInfo(i)
	local p = W.profs[i]
	return p.name, 0, p.rank, p.max
end
function GetInventoryItemID(_, slot) return W.gear[slot] and W.gear[slot].id end
function GetInventoryItemLink(_, slot) return W.gear[slot] and ("item:" .. W.gear[slot].id .. ":" .. slot) end
function GetDetailedItemLevelInfo(link)
	local slot = tonumber(link:match(":(%d+)$"))
	return W.gear[slot] and W.gear[slot].il
end
function GetAverageItemLevel() return nil, nil end
function UnitFactionGroup() return W.player.faction or "Alliance", W.player.faction or "Alliance" end

-- Secret values: tests mark one value as secret through W.secret.
function issecretvalue(v) return W.secret ~= nil and v == W.secret end

-- Loot ----------------------------------------------------------------------------

LOOT_ITEM_SELF = "You receive loot: %s."
LOOT_ITEM_SELF_MULTIPLE = "You receive loot: %sx%d."
LOOT_ITEM_PUSHED_SELF = "You receive item: %s."
LOOT_ITEM_PUSHED_SELF_MULTIPLE = "You receive item: %sx%d."
W.itemQuality = {}          -- [itemID] = quality; missing = not cached yet
C_Item = { GetItemQualityByID = function(id) return W.itemQuality[id] end }

-- Instances and the Encounter Journal ---------------------------------------------

W.instance = nil            -- { name, kind = "party", id = instanceID, mapID }
W.ej = {}                   -- [mapID] = { journalID, bosses = { { name, encounterID } } }
W.ejSelected = nil

function IsInInstance()
	if W.instance then
		return true, W.instance.kind or "party"
	end
	return false, "none"
end
function GetInstanceInfo()
	local i = W.instance
	if not i then
		return "Elwynn Forest", "none", 0, "", 0, 0, false, 0
	end
	return i.name, i.kind or "party", 1, "Normal", 5, 0, false, i.id
end
C_Map = { GetBestMapForUnit = function() return W.instance and W.instance.mapID end }
function EJ_GetInstanceForMap(mapID)
	local e = W.ej[mapID]
	return e and e.journalID or 0
end
function EJ_SelectInstance(journalID) W.ejSelected = journalID end
function EJ_GetEncounterInfoByIndex(index, journalID)
	if W.ejSelected ~= journalID then
		return nil -- the real API needs EJ_SelectInstance first
	end
	for _, e in pairs(W.ej) do
		if e.journalID == journalID and e.bosses[index] then
			local b = e.bosses[index]
			return b.name, "", index, 0, "", journalID, b.encounterID, 0
		end
	end
end

-- Professions window ----------------------------------------------------------------

W.tradeskill = nil          -- { name, linked = false, recipes = { { id, name, learned } } }
C_TradeSkillUI = {
	GetAllRecipeIDs = function()
		local ids = {}
		for _, r in ipairs(W.tradeskill and W.tradeskill.recipes or {}) do
			ids[#ids + 1] = r.id
		end
		return ids
	end,
	GetRecipeInfo = function(id)
		for _, r in ipairs(W.tradeskill and W.tradeskill.recipes or {}) do
			if r.id == id then
				return { recipeID = id, name = r.name, learned = r.learned ~= false, isRecraft = r.isRecraft }
			end
		end
	end,
	GetBaseProfessionInfo = function()
		return { professionName = W.tradeskill and W.tradeskill.name or "", professionID = 164 }
	end,
	IsTradeSkillLinked = function() return W.tradeskill ~= nil and W.tradeskill.linked == true end,
	IsTradeSkillGuild = function() return false end,
	IsNPCCrafting = function() return false end,
	IsDataSourceChanging = function() return false end,
}

-- Loading -------------------------------------------------------------------------

function W.loadFile(path, addonName, ns)
	local chunk, err = loadfile(path)
	if not chunk then
		error(err)
	end
	chunk(addonName, ns)
end
