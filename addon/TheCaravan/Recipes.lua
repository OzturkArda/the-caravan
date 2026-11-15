-- Known recipes, for /craft in Discord. The game only lists recipes while a
-- profession window is open, so each one is read when its window opens.
--
-- A recipe list can run to a few kilobytes, so it isn't part of the DATA
-- message. DATA carries a short signature (rh); group members who hold a
-- different version ask for the list with RREQ and the owner answers with RCP:
--   { t = "RREQ", v = SCHEMA, who = "Name-Realm" }
--   { t = "RCP",  v = SCHEMA, h = signature, p = { [profession] = { recipe names } } }
--
-- db.recipes["Name-Realm"] = { h = signature, ts = time, p = { [profession] = { names } } }

local _, ns = ...
local Caravan = ns.Caravan

local MAX_PROFS, MAX_RECIPES = 8, 800
local ASK_AGAIN_AFTER = 120 -- seconds before asking the same member again
local SEND_GAP = 30 -- seconds between our own RCP messages

local function ownTradeSkill(T)
	for _, fn in ipairs({ "IsTradeSkillLinked", "IsTradeSkillGuild", "IsNPCCrafting", "IsRuneforging" }) do
		if T[fn] then
			local ok, yes = pcall(T[fn])
			if ok and yes then
				return false
			end
		end
	end
	return true
end

-- The open profession's name and its learned recipe names, or nil.
function Caravan:ReadOpenProfession()
	local T = C_TradeSkillUI
	local names, seen = {}, {}
	local function add(name)
		if type(name) == "string" and name ~= "" and not seen[name] and #names < MAX_RECIPES then
			seen[name] = true
			names[#names + 1] = name:sub(1, 64)
		end
	end
	local prof
	if T and T.GetAllRecipeIDs and T.GetRecipeInfo and T.GetBaseProfessionInfo then
		if (T.IsDataSourceChanging and T.IsDataSourceChanging()) or not ownTradeSkill(T) then
			return nil
		end
		local info = T.GetBaseProfessionInfo()
		prof = info and info.professionName
		for _, id in ipairs(T.GetAllRecipeIDs() or {}) do
			local r = T.GetRecipeInfo(id)
			if r and r.learned and not (r.isRecraft or r.isDummyRecipe or r.isGatheringRecipe or r.isSalvageRecipe) then
				add(r.name)
			end
		end
	elseif GetTradeSkillLine and GetNumTradeSkills and GetTradeSkillInfo then
		prof = GetTradeSkillLine()
		for i = 1, GetNumTradeSkills() or 0 do
			local name, kind = GetTradeSkillInfo(i)
			if kind ~= "header" and kind ~= "subheader" then
				add(name)
			end
		end
	end
	if type(prof) ~= "string" or prof == "" or prof == "UNKNOWN" or #names == 0 then
		return nil -- an empty list usually means the data hasn't loaded yet
	end
	table.sort(names)
	return prof:sub(1, 64), names
end

function Caravan:RecipeSignature(p)
	local profs = {}
	for prof in pairs(p) do
		profs[#profs + 1] = prof
	end
	table.sort(profs)
	local h, n = 0, 0
	local function mix(s)
		for i = 1, #s do
			h = (h * 31 + s:byte(i)) % 4294967291
		end
		h = (h * 31 + 10) % 4294967291
	end
	for _, prof in ipairs(profs) do
		mix(prof)
		for _, name in ipairs(p[prof]) do
			mix(name)
			n = n + 1
		end
	end
	return string.format("%d:%x", n, h)
end

function Caravan:OwnRecipes()
	return self.db.recipes[self.selfName]
end

function Caravan:QueueRecipeScan()
	if self.recipeScanTimer then
		return
	end
	self.recipeScanTimer = self:ScheduleTimer(function()
		self.recipeScanTimer = nil
		self:ScanRecipes()
	end, 1)
end

function Caravan:ScanRecipes()
	if InCombatLockdown() then
		return false
	end
	local ok, prof, names = pcall(self.ReadOpenProfession, self)
	if not ok or not prof then
		return false
	end
	local mine = self:OwnRecipes() or { p = {} }
	if not mine.p[prof] then
		local count = 0
		for _ in pairs(mine.p) do
			count = count + 1
		end
		if count >= MAX_PROFS then
			return false
		end
	end
	mine.p[prof] = names
	local sig = self:RecipeSignature(mine.p)
	if sig == mine.h then
		return false
	end
	mine.h, mine.ts = sig, GetServerTime()
	self.db.recipes[self.selfName] = mine
	self:QueueUpdate(2) -- DATA carries the new signature, and the group asks for the list
	return true
end

-- Someone's DATA carried recipe signature `sig`: ask for the list if ours differs.
function Caravan:CheckRecipes(name, sig)
	if type(sig) ~= "string" then
		return
	end
	local have = self.db.recipes[name]
	if have and have.h == sig then
		return
	end
	local now = GetTime()
	if self.recipeAsked[name] and now - self.recipeAsked[name] < ASK_AGAIN_AFTER then
		return
	end
	if self:Send({ t = "RREQ", v = self.SCHEMA, who = name }) then
		self.recipeAsked[name] = now
	end
end

function Caravan:QueueRecipeSend()
	if self.recipeSendTimer or not self:OwnRecipes() then
		return
	end
	local wait = 2
	if self.lastRecipeSend then
		wait = math.max(wait, SEND_GAP - (GetTime() - self.lastRecipeSend))
	end
	self.recipeSendTimer = self:ScheduleTimer(function()
		self.recipeSendTimer = nil
		self:SendRecipes()
	end, wait)
end

function Caravan:SendRecipes()
	local mine = self:OwnRecipes()
	if not mine or not self:GroupChannel() then
		return false
	end
	if not self:CanSend() then
		self.pendingRecipes = true
		return false
	end
	self.pendingRecipes = false
	self.lastRecipeSend = GetTime()
	return self:Send({ t = "RCP", v = self.SCHEMA, h = mine.h, p = mine.p })
end

function Caravan:SanitizeRecipes(msg)
	if type(msg.h) ~= "string" or type(msg.p) ~= "table" then
		return nil
	end
	local p, profs = {}, 0
	for prof, list in pairs(msg.p) do
		if type(prof) == "string" and type(list) == "table" and profs < MAX_PROFS then
			local names = {}
			for i = 1, math.min(#list, MAX_RECIPES) do
				if type(list[i]) == "string" then
					names[#names + 1] = list[i]:sub(1, 64)
				end
			end
			p[prof:sub(1, 64)] = names
			profs = profs + 1
		end
	end
	return { h = msg.h:sub(1, 32), ts = GetServerTime(), p = p }
end
