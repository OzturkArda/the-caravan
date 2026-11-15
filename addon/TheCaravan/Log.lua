-- Remembers what happened to this character, for session recaps in Discord:
-- level-ups, notable loot and dungeon runs, each stamped with server time.
--
-- db.log["Name-Realm"] = {
--   lv   = { { l = new level, ts }, ... },
--   loot = { { id = itemID, n = item name, q = quality, ts }, ... },
--   runs = { { n = instance name, id = instanceID, ts = entered, te = last seen,
--              b = { boss names killed }, nb = bosses in the instance (when the
--              Encounter Journal knows), done = true once the last boss died }, ... },
-- }
-- The lists travel with the character's DATA message, so entries older than
-- two weeks are dropped and each list is capped.

local _, ns = ...
local Caravan = ns.Caravan

local KEEP_SECONDS = 14 * 86400
local CAP = { lv = 20, loot = 20, runs = 10 }
local NOTABLE_QUALITY = 3 -- rare and better
local RUN_GAP = 30 * 60 -- coming back within this time continues the same run
local QUALITY_BY_COLOUR = {
	ff9d9d9d = 0, ffffffff = 1, ff1eff00 = 2, ff0070dd = 3, ffa335ee = 4, ffff8000 = 5, ffe6cc80 = 6, ff00ccff = 7,
}

local function secret(v)
	return issecretvalue ~= nil and issecretvalue(v)
end

local function append(list, entry, cap)
	list[#list + 1] = entry
	while #list > cap do
		table.remove(list, 1)
	end
end

function Caravan:OwnLog()
	local log = self.db.log[self.selfName]
	if type(log) ~= "table" then
		log = {}
		self.db.log[self.selfName] = log
	end
	for key in pairs(CAP) do
		if type(log[key]) ~= "table" then
			log[key] = {}
		end
	end
	return log
end

function Caravan:PruneLog()
	local cutoff = GetServerTime() - KEEP_SECONDS
	local log = self:OwnLog()
	for key in pairs(CAP) do
		local list = log[key]
		for i = #list, 1, -1 do
			local e = list[i]
			if type(e) ~= "table" or (e.te or e.ts or 0) < cutoff then
				table.remove(list, i)
			end
		end
	end
end

-- Levels ------------------------------------------------------------------

function Caravan:OnLevelUp(_, level)
	if type(level) == "number" then
		append(self:OwnLog().lv, { l = level, ts = GetServerTime() }, CAP.lv)
	end
	self:QueueUpdate(2)
end

-- Loot ----------------------------------------------------------------------

-- "You receive loot: %s." -> "^You receive loot: (.+)%.$"
local function toPattern(fmt)
	local p = fmt:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0")
	p = p:gsub("%%%%s", "(.+)"):gsub("%%%%d", "%%d+")
	return "^" .. p .. "$"
end

local LOOT_PATTERNS
local function lootPatterns()
	if not LOOT_PATTERNS then
		LOOT_PATTERNS = {}
		local formats = {
			LOOT_ITEM_SELF_MULTIPLE or "You receive loot: %sx%d.",
			LOOT_ITEM_SELF or "You receive loot: %s.",
			LOOT_ITEM_PUSHED_SELF_MULTIPLE or "You receive item: %sx%d.",
			LOOT_ITEM_PUSHED_SELF or "You receive item: %s.",
		}
		for _, fmt in ipairs(formats) do
			LOOT_PATTERNS[#LOOT_PATTERNS + 1] = toPattern(fmt)
		end
	end
	return LOOT_PATTERNS
end

local function itemQuality(link, id)
	if C_Item and C_Item.GetItemQualityByID then
		local ok, q = pcall(C_Item.GetItemQualityByID, id)
		if ok and type(q) == "number" then
			return q
		end
	end
	local q = link:match("|cnIQ(%d+):")
	if q then
		return tonumber(q)
	end
	local hex = link:match("|c(%x%x%x%x%x%x%x%x)")
	return hex and QUALITY_BY_COLOUR[hex:lower()]
end

-- The item this character received, from a CHAT_MSG_LOOT line, if it's notable.
function Caravan:ParseOwnLoot(text)
	for _, pattern in ipairs(lootPatterns()) do
		local link = text:match(pattern)
		if link then
			local id = tonumber(link:match("|Hitem:(%d+)"))
			local name = link:match("|h%[(.-)%]|h")
			if not id or not name then
				return nil
			end
			local quality = itemQuality(link, id)
			if quality and quality >= NOTABLE_QUALITY then
				return { id = id, n = name:sub(1, 64), q = quality }
			end
			return nil
		end
	end
end

function Caravan:OnLoot(_, text)
	-- In Midnight, chat text can be a secret value that addons may not read.
	if secret(text) or type(text) ~= "string" then
		return
	end
	local ok, item = pcall(self.ParseOwnLoot, self, text)
	if ok and item then
		item.ts = GetServerTime()
		append(self:OwnLog().loot, item, CAP.loot)
		self:QueueUpdate(3)
	end
end

-- Dungeon runs ----------------------------------------------------------------

-- Number of bosses in the current instance and the final boss's encounter ID,
-- from the Encounter Journal. Nil when it can't tell.
function Caravan:InstanceBosses()
	if not (EJ_GetInstanceForMap and EJ_SelectInstance and EJ_GetEncounterInfoByIndex and C_Map and C_Map.GetBestMapForUnit) then
		return nil
	end
	if EncounterJournal and EncounterJournal.IsShown and EncounterJournal:IsShown() then
		return nil -- selecting an instance would change what the open Adventure Guide shows
	end
	local ok, count, finalID = pcall(function()
		local mapID = C_Map.GetBestMapForUnit("player")
		local journalID = mapID and EJ_GetInstanceForMap(mapID)
		if not journalID or journalID == 0 then
			return nil
		end
		EJ_SelectInstance(journalID)
		local n, last = 0, nil
		while n < 40 do
			local name, _, _, _, _, _, encounterID = EJ_GetEncounterInfoByIndex(n + 1, journalID)
			if not name then
				break
			end
			n, last = n + 1, encounterID
		end
		return n, last
	end)
	if ok and count and count > 0 then
		return count, finalID
	end
end

function Caravan:TrackInstance()
	local now = GetServerTime()
	local inInstance, kind = IsInInstance()
	if not inInstance or (kind ~= "party" and kind ~= "raid") then
		if self.currentRun then
			self.currentRun.te = now
			self.currentRun = nil
		end
		return
	end
	local name, _, _, _, _, _, _, instanceID = GetInstanceInfo()
	if secret(name) or type(name) ~= "string" or type(instanceID) ~= "number" then
		return
	end
	local runs = self:OwnLog().runs
	local last = runs[#runs]
	if last and last.id == instanceID and now - (last.te or last.ts or 0) <= RUN_GAP then
		last.te = now
		self.currentRun = last
		return
	end
	local run = { n = name:sub(1, 64), id = instanceID, ts = now, te = now, b = {} }
	run.nb, run.fe = self:InstanceBosses()
	append(runs, run, CAP.runs)
	self.currentRun = run
	self:QueueUpdate(5)
end

function Caravan:RecordBossKill(encounterID, encounterName, success)
	local run = self.currentRun
	if not run or success ~= 1 or secret(encounterName) or type(encounterName) ~= "string" then
		return false
	end
	run.te = GetServerTime()
	for _, boss in ipairs(run.b) do
		if boss == encounterName then
			return false
		end
	end
	if #run.b < 40 then
		run.b[#run.b + 1] = encounterName:sub(1, 64)
	end
	if (run.fe and encounterID == run.fe) or (run.nb and #run.b >= run.nb) then
		run.done = true
	end
	return true
end

function Caravan:OnEncounterEnd(_, encounterID, encounterName, _, _, success)
	local ok, recorded = pcall(self.RecordBossKill, self, encounterID, encounterName, success)
	self:FlushPending()
	if ok and recorded then
		self:QueueUpdate(3)
	end
end

function Caravan:OnLogout()
	if self.currentRun then
		self.currentRun.te = GetServerTime()
	end
end
