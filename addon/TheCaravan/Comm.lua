-- Group sync over addon messages (AceComm handles splitting and throttling).
--
-- Messages are AceSerializer tables:
--   { t = "DATA", v = SCHEMA, d = memberData, sg = scheduleStamp }  -- someone's latest data
--   { t = "REQ",  v = SCHEMA }                  -- "please send yours"
--   { t = "SCHED", v = SCHEMA, s = schedule }   -- the session list (see Schedule.lua)
--   { t = "RSVP", v = SCHEMA, r = db.rsvps }    -- in-game RSVPs known here (see Rsvp.lua)
--   RREQ and RCP carry recipe lists (see Recipes.lua).
-- Only data from players on your roster is kept.
--
-- The session list reaches friends without the sync app like this: DATA
-- carries `sg`, when the sender's schedule was generated (0 for none).
-- Anyone holding a newer one answers with SCHED, and the receiver keeps it
-- if it is still newer than its own. Addons older than 0.3.0 send no `sg`,
-- so they are never sent a schedule they would ignore.

local _, ns = ...
local Caravan = ns.Caravan

local MIN_XP_BROADCAST_GAP = 60
local SCHEDULE_SEND_GAP = 15 -- seconds between our own SCHED messages
local MAX_SESSIONS, MAX_NAMES = 30, 40

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

-- A list of up to MAX_NAMES strings.
local function nameList(v)
	local out = {}
	if type(v) == "table" then
		for i = 1, math.min(#v, MAX_NAMES) do
			local n = str(v[i])
			if n then
				out[#out + 1] = n
			end
		end
	end
	return out
end

local RSVP_STATUS = { going = true, late = true, out = true }

-- { [Discord user id] = status }, as in a schedule session's `rsvp`.
local function statusMap(v)
	if type(v) ~= "table" then
		return nil
	end
	local out, n = {}, 0
	for key, status in pairs(v) do
		n = n + 1
		if n > MAX_NAMES then
			break
		end
		if type(key) == "string" and #key <= 24 and RSVP_STATUS[status] then
			out[key] = status
		end
	end
	return out
end

-- { [Discord user id] = { name, chars } }, as in a schedule's `people`.
local function peopleMap(v)
	if type(v) ~= "table" then
		return nil
	end
	local out, n = {}, 0
	for key, p in pairs(v) do
		n = n + 1
		if n > MAX_NAMES then
			break
		end
		if type(key) == "string" and #key <= 24 and type(p) == "table" then
			out[key] = { name = str(p.name), chars = nameList(p.chars) }
		end
	end
	return out
end

-- A schedule received from another player, cut down to the fields the
-- addon uses and to sane sizes.
function Caravan:SanitizeSchedule(s)
	if type(s) ~= "table" or not num(s.generated_at) or type(s.sessions) ~= "table" then
		return nil
	end
	local out = {
		version = num(s.version) or 1, generated_at = s.generated_at, sessions = {}, reminders = {},
		people = peopleMap(s.people), sync = str(s.sync),
	}
	for i = 1, math.min(#s.sessions, MAX_SESSIONS) do
		local x = s.sessions[i]
		if type(x) == "table" and num(x.id) and num(x.start) then
			out.sessions[#out.sessions + 1] = {
				id = x.id, title = str(x.title, 100), start = x.start, duration = num(x.duration),
				going = nameList(x.going), late = nameList(x.late), out = nameList(x.out), rsvp = statusMap(x.rsvp),
			}
		end
	end
	if type(s.reminders) == "table" then
		for i = 1, math.min(#s.reminders, 5) do
			local m = num(s.reminders[i])
			if m then
				out.reminders[#out.reminders + 1] = m
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
	return self:Send({ t = "DATA", v = self.SCHEMA, d = data, sg = self:ScheduleStamp() })
end

-- Send our schedule after a short random wait, unless someone else sends the
-- same or a newer one first (several friends may hold it).
function Caravan:QueueScheduleSend()
	if self.scheduleTimer or not self:Schedule() then
		return
	end
	if self.lastScheduleSend and GetTime() - self.lastScheduleSend < SCHEDULE_SEND_GAP then
		return
	end
	self.scheduleTimer = self:ScheduleTimer("SendSchedule", 1 + math.random() * 2)
end

function Caravan:SendSchedule()
	self.scheduleTimer = nil
	local schedule = self:Schedule()
	if not schedule then
		return
	end
	if not self:CanSend() then
		self.scheduleTimer = self:ScheduleTimer("SendSchedule", 5)
		return
	end
	self.lastScheduleSend = GetTime()
	local copy = {}
	for k, v in pairs(schedule) do
		if k ~= "from" then
			copy[k] = v
		end
	end
	self:Send({ t = "SCHED", v = self.SCHEMA, s = copy })
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
		self:QueueRsvpSend()
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
		if type(msg.sg) == "number" and msg.sg < self:ScheduleStamp() then
			self:QueueScheduleSend()
		end
	elseif msg.t == "SCHED" then
		local schedule = self:SanitizeSchedule(msg.s)
		if schedule then
			if self.scheduleTimer and schedule.generated_at >= self:ScheduleStamp() then
				self:CancelTimer(self.scheduleTimer) -- someone else sent it already
				self.scheduleTimer = nil
			end
			self:AcceptSchedule(schedule, key)
		end
	elseif msg.t == "RSVP" then
		self:MergeRsvps(msg.r)
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
