-- Group sync over addon messages (AceComm handles splitting and throttling).
--
-- Messages are AceSerializer tables:
--   { t = "DATA", v = SCHEMA, d = memberData }  -- someone's latest data
--   { t = "REQ",  v = SCHEMA }                  -- "please send yours"
--   RREQ and RCP carry recipe lists (see Recipes.lua).
-- Only data from players on your roster is kept.

local _, ns = ...
local Caravan = ns.Caravan

local MIN_XP_BROADCAST_GAP = 60

local function str(v, limit)
	if type(v) == "string" then
		return v:sub(1, limit or 64)
	end
end

local function num(v)
	if type(v) == "number" and v == v and v > -1e10 and v < 1e10 then
		return v
	end
end

-- Copy up to `cap` table entries through `clean`, dropping the ones it rejects.
local function list(v, cap, clean)
	local out = {}
	if type(v) == "table" then
		for i = 1, math.min(#v, cap) do
			local item = type(v[i]) == "table" and clean(v[i])
			if item then
				out[#out + 1] = item
			end
		end
	end
	return out
end

local function levelEntry(e)
	return num(e.l) and num(e.ts) and { l = e.l, ts = e.ts }
end

local function lootEntry(e)
	return num(e.id) and str(e.n) and { id = e.id, n = str(e.n), q = num(e.q), ts = num(e.ts) }
end

local function runEntry(e)
	if not (str(e.n) and num(e.ts)) then
		return nil
	end
	local bosses = {}
	if type(e.b) == "table" then
		for i = 1, math.min(#e.b, 40) do
			bosses[#bosses + 1] = str(e.b[i])
		end
	end
	return { n = str(e.n), id = num(e.id), ts = e.ts, te = num(e.te), b = bosses, nb = num(e.nb), done = e.done == true or nil }
end

function Caravan:SanitizeMember(d)
	if type(d) ~= "table" or not num(d.level) then
		return nil
	end
	local out = {
		name = str(d.name), realm = str(d.realm), class = str(d.class, 16), race = str(d.race),
		faction = str(d.faction, 16), level = num(d.level), xp = num(d.xp), xpMax = num(d.xpMax),
		zone = str(d.zone, 128), ilvl = num(d.ilvl), ts = num(d.ts), rh = str(d.rh, 32), profs = {}, gear = {},
		lv = list(d.lv, 20, levelEntry), loot = list(d.loot, 20, lootEntry), runs = list(d.runs, 10, runEntry),
	}
	if type(d.profs) == "table" then
		for i = 1, math.min(#d.profs, 8) do
			local p = d.profs[i]
			if type(p) == "table" and str(p.name) then
				out.profs[#out.profs + 1] = { name = str(p.name), rank = num(p.rank), max = num(p.max) }
			end
		end
	end
	if type(d.gear) == "table" then
		for i = 1, math.min(#d.gear, 19) do
			local g = d.gear[i]
			if type(g) == "table" and num(g.id) then
				out.gear[#out.gear + 1] = { s = num(g.s), id = num(g.id), il = num(g.il) }
			end
		end
	end
	return out
end

function Caravan:GroupChannel()
	local home = LE_PARTY_CATEGORY_HOME or 1
	local instance = LE_PARTY_CATEGORY_INSTANCE or 2
	if IsInGroup(home) then
		return IsInRaid(home) and "RAID" or "PARTY"
	elseif IsInGroup(instance) then
		return "INSTANCE_CHAT"
	end
end

-- Addon messages can be blocked in combat and during boss encounters, so
-- sends wait for FlushPending.
function Caravan:CanSend()
	if InCombatLockdown() then
		return false
	end
	if IsEncounterInProgress and IsEncounterInProgress() then
		return false
	end
	return true
end

function Caravan:Send(msg)
	local channel = self:GroupChannel()
	if not channel then
		return false
	end
	if not self:CanSend() then
		self.pendingSend = true
		return false
	end
	local ok, err = pcall(self.SendCommMessage, self, self.PREFIX, self:Serialize(msg), channel, nil, "BULK")
	if not ok then
		self.lastSendError = err
	end
	return ok
end

function Caravan:Broadcast()
	local data = self.db.members[self.selfName]
	if not data then
		return false
	end
	self.lastBroadcast = GetTime()
	return self:Send({ t = "DATA", v = self.SCHEMA, d = data })
end

function Caravan:RequestData()
	if self.requestTimer then
		return
	end
	self.requestTimer = self:ScheduleTimer(function()
		self.requestTimer = nil
		self:Send({ t = "REQ", v = self.SCHEMA })
	end, 1)
end

-- Collect and broadcast once things settle (several events often fire together).
function Caravan:QueueUpdate(delay)
	if self.updateTimer then
		return
	end
	self.updateTimer = self:ScheduleTimer(function()
		self.updateTimer = nil
		if self:RefreshSelf() then
			self:Broadcast()
		end
	end, type(delay) == "number" and delay or 3)
end

function Caravan:OnXPUpdate()
	self:RefreshSelf()
	if not self.lastBroadcast or GetTime() - self.lastBroadcast >= MIN_XP_BROADCAST_GAP then
		self:QueueUpdate(3)
	end
end

function Caravan:FlushPending()
	if self.pendingRefresh then
		self:QueueUpdate(2)
	elseif self.pendingSend then
		self.pendingSend = false
		self:Broadcast()
	end
	if self.pendingRecipes then
		self:QueueRecipeSend()
	end
end

-- When someone joins the group, swap data with them.
function Caravan:OnGroupChanged()
	local current, newcomer = {}, false
	for _, unit in ipairs(self:GroupUnits()) do
		local name = self:UnitFullNameNormalized(unit)
		if name then
			current[name] = true
			if not (self.lastGroup and self.lastGroup[name]) then
				newcomer = true
			end
		end
	end
	self.lastGroup = current
	if newcomer then
		self:QueueUpdate(2)
		self:RequestData()
	end
end

function Caravan:OnCommReceived(prefix, message, _, sender)
	if prefix ~= self.PREFIX then
		return
	end
	local from = self:Normalize(sender)
	if not from or from == self.selfName then
		return
	end
	local ok, msg = self:Deserialize(message)
	if not ok or type(msg) ~= "table" or type(msg.v) ~= "number" then
		return
	end
	if msg.v > self.SCHEMA then
		if not self.warnedVersion then
			self.warnedVersion = true
			self:Say("Someone in your group has a newer version of The Caravan. Update yours to see their data.")
		end
		return
	end
	if not self:IsOnRoster(from) then
		if msg.t == "DATA" then
			self.unlisted[from] = true
			self:UpdateWindow()
		end
		return
	end
	local key = self.db.roster[from:lower()]
	if msg.t == "DATA" then
		local data = self:SanitizeMember(msg.d)
		if data then
			data.receivedAt = GetServerTime()
			self.db.members[key] = data
			self:UpdateWindow()
			self:CheckRecipes(key, data.rh)
		end
	elseif msg.t == "REQ" then
		self:QueueUpdate(1 + math.random() * 2)
	elseif msg.t == "RREQ" then
		if type(msg.who) == "string" and msg.who:lower() == self.selfName:lower() then
			self:QueueRecipeSend()
		end
	elseif msg.t == "RCP" then
		local recipes = self:SanitizeRecipes(msg)
		if recipes then
			self.db.recipes[key] = recipes
		end
	end
end
