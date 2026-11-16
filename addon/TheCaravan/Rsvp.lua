-- RSVPs made in game, and who is coming to each session.
--
-- Clicking In, Late or Out in the Sessions tab records the choice under the
-- character that clicked:
--   db.rsvps["Name-Realm"] = { { id = sessionId, s = "going"|"late"|"out", ts = serverTime }, ... }
-- Addons swap these with the group (the RSVP message, Comm.lua), so a
-- friend's click reaches the player who runs the sync app. That player's
-- next /reload or logout uploads them in the snapshot, and the bot applies
-- each one as the Discord user who linked the character (/character link),
-- when it is newer than that user's RSVP in Discord.
--
-- The schedule says who has linked which characters (`people`) and each
-- session's answers by Discord user (`rsvp`). Clicks made after the schedule
-- was generated are shown on top of it, marked as not in Discord yet.

local _, ns = ...
local Caravan = ns.Caravan

local STATUSES = { going = true, late = true, out = true }
local KEEP_FOR = 14 * 86400
local MAX_CHARS, MAX_ENTRIES = 40, 30
local SEND_DELAY = 2

Caravan.RSVP_ORDER = { "going", "late", "out" }
Caravan.RSVP_LABELS = { going = "In", late = "Late", out = "Out" }

local function short(name)
	return name:match("^[^-]+") or name
end

-- The schedule's key (a Discord user id) for the player who linked `char`.
function Caravan:PersonFor(char)
	local schedule = self:Schedule()
	local people = schedule and schedule.people
	if type(people) ~= "table" or type(char) ~= "string" then
		return nil
	end
	local lower = char:lower()
	for key, p in pairs(people) do
		if type(p) == "table" and type(p.chars) == "table" then
			for _, c in ipairs(p.chars) do
				if type(c) == "string" and c:lower() == lower then
					return key, p
				end
			end
		end
	end
end

function Caravan:IsLinked()
	return self:PersonFor(self.selfName) ~= nil
end

-- A person's name in game: the character of theirs seen most recently here,
-- else their Discord name.
function Caravan:PersonLabel(key, person)
	if type(person) ~= "table" then
		return key
	end
	local best, bestTs
	for _, c in ipairs(type(person.chars) == "table" and person.chars or {}) do
		if type(c) == "string" then
			local m = self.db.members[c]
			local ts = m and m.ts or 0
			if not best or ts > bestTs then
				best, bestTs = c, ts
			end
		end
	end
	if best then
		return short(best)
	end
	return type(person.name) == "string" and person.name or key
end

-- Everyone's answer for session `s`: { [key] = { status, label, pending } }.
function Caravan:SessionAnswers(s)
	local schedule = self:Schedule()
	local stamp = schedule and tonumber(schedule.generated_at) or 0
	local people = schedule and type(schedule.people) == "table" and schedule.people or {}
	local answers = {}
	if type(s.rsvp) == "table" then
		for key, status in pairs(s.rsvp) do
			if STATUSES[status] then
				answers[key] = { status = status, label = self:PersonLabel(key, people[key]) }
			end
		end
	else -- a schedule from a bot before 0.3.0: display names only
		for status in pairs(STATUSES) do
			for _, n in ipairs(type(s[status]) == "table" and s[status] or {}) do
				answers["name:" .. n] = { status = status, label = n }
			end
		end
	end
	local newest = {}
	for char, entries in pairs(self.db.rsvps) do
		for _, e in ipairs(entries) do
			if e.id == s.id and e.ts > stamp then
				local key = self:PersonFor(char) or ("char:" .. char:lower())
				if not newest[key] or e.ts > newest[key] then
					newest[key] = e.ts
					answers[key] = { status = e.s, label = short(char), pending = true }
				end
			end
		end
	end
	return answers
end

-- { going = { answer, ... }, late = ..., out = ... }, each sorted by name.
function Caravan:AnswerLists(s)
	local lists = { going = {}, late = {}, out = {} }
	for _, a in pairs(self:SessionAnswers(s)) do
		local l = lists[a.status]
		l[#l + 1] = a
	end
	for _, l in pairs(lists) do
		table.sort(l, function(x, y) return x.label:lower() < y.label:lower() end)
	end
	return lists
end

-- This player's answer for `s` (and whether it's still on its way to Discord).
function Caravan:MyStatus(s)
	local key = self:PersonFor(self.selfName) or ("char:" .. self.selfName:lower())
	local mine = self:SessionAnswers(s)[key]
	if mine then
		return mine.status, mine.pending == true
	end
end

-- Whether the sync app runs for this account: its copy of the schedule came
-- from the file, or the bot named one of this account's characters.
function Caravan:SyncsHere()
	local schedule = self:Schedule()
	if not schedule then
		return false
	end
	if not schedule.from then
		return true
	end
	local m = type(schedule.sync) == "string" and self.db.members[schedule.sync]
	return type(m) == "table" and not m.receivedAt
end

-- When an in-game RSVP will reach Discord.
function Caravan:RsvpRoute()
	if self:SyncsHere() then
		return "Discord gets it when you /reload or log out."
	end
	local schedule = self:Schedule()
	if schedule and type(schedule.sync) == "string" then
		return string.format("Discord gets it once you've grouped with %s and they /reload or log out.", short(schedule.sync))
	end
	return "Discord gets it once you've grouped with the player who runs the sync app and they /reload or log out."
end

function Caravan:SetRsvp(sessionId, status)
	local s = self:FindSession(sessionId)
	if not s or not STATUSES[status] then
		return false
	end
	local list = self.db.rsvps[self.selfName] or {}
	self.db.rsvps[self.selfName] = list
	local entry
	for _, e in ipairs(list) do
		if e.id == sessionId then
			entry = e
		end
	end
	if not entry then
		entry = { id = sessionId }
		list[#list + 1] = entry
	end
	entry.s, entry.ts = status, GetServerTime()
	self:QueueRsvpSend()
	self:UpdateWindow()
	local text = string.format("You're %s for |c%s%s|r.", self.RSVP_LABELS[status], self.COLOUR, s.title or "Caravan session")
	if self:IsLinked() then
		self:Say(text .. " " .. self:RsvpRoute())
	else
		self:Say(text .. " To make it count in Discord, link this character there: /character link " .. self.selfName)
	end
	return true
end

-- Drop answers for sessions that have ended, and anything over two weeks old.
function Caravan:PruneRsvps()
	local now = GetServerTime()
	for char, list in pairs(self.db.rsvps) do
		local keep = {}
		for _, e in ipairs(type(list) == "table" and list or {}) do
			local s = type(e) == "table" and self:FindSession(e.id)
			local ended = s and s.start + (tonumber(s.duration) or 180) * 60 < now
			if type(e) == "table" and type(e.ts) == "number" and not ended and now - e.ts < KEEP_FOR then
				keep[#keep + 1] = e
			end
		end
		self.db.rsvps[char] = #keep > 0 and keep or nil
	end
end

-- Sharing ---------------------------------------------------------------------

function Caravan:QueueRsvpSend()
	if self.rsvpTimer then
		return
	end
	self.rsvpTimer = self:ScheduleTimer("SendRsvps", SEND_DELAY)
end

function Caravan:SendRsvps()
	self.rsvpTimer = nil
	if not self:GroupChannel() then
		return
	end
	if not self:CanSend() then
		self.rsvpTimer = self:ScheduleTimer("SendRsvps", 5)
		return
	end
	self:PruneRsvps()
	if next(self.db.rsvps) ~= nil then
		self:Send({ t = "RSVP", v = self.SCHEMA, r = self.db.rsvps })
	end
end

-- Merge answers another addon sent; for each character and session the
-- newest click wins. Returns true if anything changed.
function Caravan:MergeRsvps(r)
	if type(r) ~= "table" then
		return false
	end
	local changed, seen = false, 0
	for char, entries in pairs(r) do
		seen = seen + 1
		if seen > MAX_CHARS then
			break
		end
		if type(char) == "string" and #char <= 64 and char:find("-", 1, true) and type(entries) == "table" then
			local list = self.db.rsvps[char] or {}
			for i = 1, math.min(#entries, MAX_ENTRIES) do
				local e = entries[i]
				if type(e) == "table" and type(e.id) == "number" and STATUSES[e.s] and type(e.ts) == "number" then
					local found
					for _, mine in ipairs(list) do
						if mine.id == e.id then
							found = mine
						end
					end
					if not found then
						list[#list + 1] = { id = e.id, s = e.s, ts = e.ts }
						changed = true
					elseif e.ts > found.ts then
						found.s, found.ts = e.s, e.ts
						changed = true
					end
				end
			end
			if #list > 0 then
				self.db.rsvps[char] = list
			end
		end
	end
	if changed then
		self:UpdateWindow()
	end
	return changed
end
