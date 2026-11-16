-- Reads the local player's character data.
--
-- Member data shape (shared over addon messages and saved for the sync app):
--   name, realm, class (class file, e.g. "WARRIOR"), race, faction, level, xp,
--   xpMax, zone, ilvl, ts (server time of collection),
--   profs = { { name, rank, max }, ... }, gear = { { s = slot, id, il }, ... },
--   rh = known-recipes signature (Recipes.lua),
--   lv, loot, runs = recent level-ups, notable loot and dungeon runs (Log.lua)

local _, ns = ...
local Caravan = ns.Caravan

local GEAR_SLOTS = { 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 }

local function itemLevel(link)
	local getter = (C_Item and C_Item.GetDetailedItemLevelInfo) or GetDetailedItemLevelInfo
	if not getter or not link then
		return nil
	end
	local ok, ilvl = pcall(getter, link)
	return ok and ilvl or nil
end

function Caravan:CollectProfessions()
	local out = {}
	if GetProfessions and GetProfessionInfo then
		local indices = { GetProfessions() }
		for i = 1, 5 do
			local index = indices[i]
			if index then
				local name, _, rank, maxRank = GetProfessionInfo(index)
				if name then
					out[#out + 1] = { name = name, rank = rank, max = maxRank }
				end
			end
		end
	elseif GetNumSkillLines and GetSkillLineInfo then
		for i = 1, GetNumSkillLines() do
			local name, isHeader, _, rank, _, _, maxRank, isAbandonable = GetSkillLineInfo(i)
			if name and not isHeader and isAbandonable then
				out[#out + 1] = { name = name, rank = rank, max = maxRank }
			end
		end
	end
	return out
end

function Caravan:CollectGear()
	local gear = {}
	for _, slot in ipairs(GEAR_SLOTS) do
		local id = GetInventoryItemID("player", slot)
		if id then
			gear[#gear + 1] = { s = slot, id = id, il = itemLevel(GetInventoryItemLink("player", slot)) }
		end
	end
	return gear
end

-- Average item level of what's worn. The game's own average
-- (GetAverageItemLevel) counts empty slots as zero, which reads oddly low
-- while levelling.
function Caravan:AverageItemLevel(gear)
	local total, count = 0, 0
	for _, item in ipairs(gear) do
		if item.il and item.il > 0 then
			total, count = total + item.il, count + 1
		end
	end
	return count > 0 and math.floor(total / count * 10 + 0.5) / 10 or nil
end

function Caravan:CollectSelf()
	local name, realm = UnitFullName("player")
	local _, classFile = UnitClass("player")
	local gear = self:CollectGear()
	local okProfs, profs = pcall(self.CollectProfessions, self)
	local log = self:OwnLog()
	local recipes = self:OwnRecipes()
	return {
		name = name,
		realm = (realm and realm ~= "") and realm or self:RealmName(),
		class = classFile,
		race = UnitRace("player"),
		faction = UnitFactionGroup and UnitFactionGroup("player") or nil,
		level = UnitLevel("player"),
		xp = UnitXP("player"),
		xpMax = UnitXPMax("player"),
		zone = GetRealZoneText(),
		profs = okProfs and profs or {},
		ilvl = self:AverageItemLevel(gear),
		gear = gear,
		rh = recipes and recipes.h or nil,
		lv = log.lv,
		loot = log.loot,
		runs = log.runs,
		ts = GetServerTime(),
	}
end

-- Store fresh data for this character. In combat some unit data may be
-- restricted, so collection waits until combat ends.
function Caravan:RefreshSelf()
	if InCombatLockdown() then
		self.pendingRefresh = true
		return false
	end
	self.pendingRefresh = false
	local ok, data = pcall(self.CollectSelf, self)
	if not ok or type(data) ~= "table" or not data.level then
		return false
	end
	self.db.members[self.selfName] = data
	self:UpdateWindow()
	return true
end
