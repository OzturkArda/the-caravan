-- Upcoming sessions from Discord, and the in-game reminders for them.
--
-- TheCaravanSchedule comes from one of two places:
--   * the sync app writes it into the SavedVariables file while the game is
--     closed (only on the Mac that runs the sync app);
--   * another player's addon sends it over the group channel (Comm.lua),
--     and it is kept when it was generated later than the one held here.
-- Either way it looks like the bot's /schedule export:
--   { version, generated_at, reminders = { 60, 15 },
--     sessions = { { id, title, start, duration, going, late, out }, ... } }
-- plus `from` = "Name-Realm" when another player's addon sent it.

local _, ns = ...
local Caravan = ns.Caravan

local DEFAULT_REMINDERS = { 60, 15 }

function Caravan:Schedule()
	local s = TheCaravanSchedule
	if type(s) == "table" and type(s.sessions) == "table" then
		return s
	end
end

-- When the schedule held here was generated, or 0 without one.
function Caravan:ScheduleStamp()
	local s = self:Schedule()
	return s and tonumber(s.generated_at) or 0
end

function Caravan:UpcomingSessions()
	local out = {}
	local schedule = self:Schedule()
	if not schedule then
		return out
	end
	local now = time()
	for _, s in ipairs(schedule.sessions) do
		if type(s) == "table" and type(s.start) == "number" then
			local finish = s.start + (tonumber(s.duration) or 180) * 60
			if finish > now then
				out[#out + 1] = s
			end
		end
	end
	table.sort(out, function(a, b) return a.start < b.start end)
	return out
end

function Caravan:FindSession(id)
	local schedule = self:Schedule()
	for _, s in ipairs(schedule and schedule.sessions or {}) do
		if type(s) == "table" and s.id == id then
			return s
		end
	end
end

function Caravan:FormatCountdown(seconds)
	if seconds <= 0 then
		return "now"
	end
	local h = math.floor(seconds / 3600)
	local m = math.floor((seconds % 3600) / 60)
	if h >= 24 then
		return string.format("in %dd %dh", math.floor(h / 24), h % 24)
	elseif h > 0 then
		return string.format("in %dh %dm", h, m)
	end
	return string.format("in %dm", m)
end

function Caravan:AnnounceNextSession()
	local nextSession = self:UpcomingSessions()[1]
	if not nextSession then
		return
	end
	local untilStart = nextSession.start - time()
	if untilStart > 24 * 3600 then
		return
	end
	self:Say(string.format(
		"Next session: |c%s%s|r %s (%s).",
		self.COLOUR, nextSession.title or "Caravan session",
		date("%a %H:%M", nextSession.start), self:FormatCountdown(untilStart)
	))
end

-- Keep `schedule` if it is newer than the one held here. Returns true if kept.
function Caravan:AcceptSchedule(schedule, from)
	if type(schedule) ~= "table" or type(schedule.generated_at) ~= "number" then
		return false
	end
	if schedule.generated_at <= self:ScheduleStamp() then
		return false
	end
	schedule.from = from
	TheCaravanSchedule = schedule
	self:OnScheduleChanged()
	if from then
		local short = from:match("^[^-]+") or from
		local nextSession = self:UpcomingSessions()[1]
		if nextSession then
			self:Say(string.format("Got the session list from %s. Next: |c%s%s|r %s.", short, self.COLOUR,
				nextSession.title or "Caravan session", date("%a %d %b %H:%M", nextSession.start)))
		else
			self:Say(string.format("Got the session list from %s: no upcoming sessions.", short))
		end
	end
	return true
end

function Caravan:OnScheduleChanged()
	self:ScheduleReminders()
	self:UpdateWindow()
end

-- Reminders ----------------------------------------------------------------

-- Minutes before the start, from the bot's REMINDER_OFFSETS when the
-- schedule carries them.
function Caravan:ReminderOffsets()
	local schedule = self:Schedule()
	local out = {}
	for _, m in ipairs(schedule and type(schedule.reminders) == "table" and schedule.reminders or {}) do
		if type(m) == "number" and m > 0 and m <= 24 * 60 then
			out[#out + 1] = m
		end
	end
	return #out > 0 and out or DEFAULT_REMINDERS
end

function Caravan:ScheduleReminders()
	for _, timer in ipairs(self.reminderTimers or {}) do
		self:CancelTimer(timer)
	end
	self.reminderTimers = {}
	if self.db.reminders == false then
		return
	end
	local now = time()
	for _, s in ipairs(self:UpcomingSessions()) do
		for _, minutes in ipairs(self:ReminderOffsets()) do
			local at = s.start - minutes * 60
			if at > now and s.id then
				self.reminderTimers[#self.reminderTimers + 1] = self:ScheduleTimer("Remind", at - now, s.id, minutes)
			end
		end
	end
end

local function minutesText(minutes)
	if minutes % 60 == 0 then
		local h = minutes / 60
		return h == 1 and "1 hour" or string.format("%d hours", h)
	elseif minutes > 60 then
		return string.format("%dh %dm", math.floor(minutes / 60), minutes % 60)
	end
	return minutes == 1 and "1 minute" or string.format("%d minutes", minutes)
end

function Caravan:Remind(sessionId, minutes)
	local s = self:FindSession(sessionId)
	if not s or self.db.reminders == false then
		return
	end
	if self.MyStatus and self:MyStatus(s) == "out" then
		return
	end
	local title = s.title or "Caravan session"
	local text = string.format("%s starts in %s (%s).", title, minutesText(minutes), date("%H:%M", s.start))
	self:Say(string.format("|c%s%s|r starts in %s (%s).", self.COLOUR, title, minutesText(minutes), date("%H:%M", s.start)))
	if RaidNotice_AddMessage and RaidWarningFrame then
		local colour = ChatTypeInfo and ChatTypeInfo["RAID_WARNING"] or { r = 1, g = 0.82, b = 0 }
		RaidNotice_AddMessage(RaidWarningFrame, "The Caravan: " .. text, colour)
	end
	if PlaySound and SOUNDKIT and SOUNDKIT.RAID_WARNING then
		PlaySound(SOUNDKIT.RAID_WARNING, "Master")
	end
end
