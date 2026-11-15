-- The Caravan window: a Group tab (everyone's characters) and a Sessions
-- tab (upcoming sessions from Discord).

local _, ns = ...
local Caravan = ns.Caravan

local ROWS = 12
local ROW_HEIGHT = 20
local CELLS = 6

local SLOT_NAMES = {
	[1] = "Head", [2] = "Neck", [3] = "Shoulder", [5] = "Chest", [6] = "Waist", [7] = "Legs",
	[8] = "Feet", [9] = "Wrist", [10] = "Hands", [11] = "Ring", [12] = "Ring", [13] = "Trinket",
	[14] = "Trinket", [15] = "Back", [16] = "Main hand", [17] = "Off hand", [18] = "Ranged",
}

local LAYOUTS = {
	group = {
		{ label = "Name", width = 118 }, { label = "Lvl", width = 34 }, { label = "Zone", width = 128 },
		{ label = "Professions", width = 168 }, { label = "iLvl", width = 40 }, { label = "Updated", width = 70 },
	},
	sessions = {
		{ label = "When", width = 120 }, { label = "Session", width = 160 },
		{ label = "Coming", width = 220 }, { label = "Out", width = 58 },
	},
}

local function ago(ts)
	if not ts then
		return "-"
	end
	local diff = GetServerTime() - ts
	if diff < 60 then
		return "just now"
	elseif diff < 3600 then
		return string.format("%dm ago", diff / 60)
	elseif diff < 86400 then
		return string.format("%dh ago", diff / 3600)
	end
	return string.format("%dd ago", diff / 86400)
end

local function classColoured(text, classFile)
	local colour = classFile and RAID_CLASS_COLORS and RAID_CLASS_COLORS[classFile]
	if colour and colour.colorStr then
		return "|c" .. colour.colorStr .. text .. "|r"
	end
	return text
end

local function itemName(id)
	local name
	if C_Item and C_Item.GetItemNameByID then
		name = C_Item.GetItemNameByID(id)
	elseif GetItemInfo then
		name = GetItemInfo(id)
	end
	return name or ("item " .. id)
end

local function profSummary(profs)
	local parts = {}
	for _, p in ipairs(profs or {}) do
		parts[#parts + 1] = string.format("%s %s", p.name, p.rank or "?")
	end
	return #parts > 0 and table.concat(parts, ", ") or "-"
end

local function memberTooltip(row)
	local m = row.member
	if not m then
		return
	end
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip:AddLine(classColoured(row.fullName, m.class))
	GameTooltip:AddLine(string.format("Level %s %s", m.level or "?", m.race or ""), 1, 1, 1)
	if m.xp and m.xpMax and m.xpMax > 0 then
		GameTooltip:AddLine(string.format("XP %d%%", m.xp / m.xpMax * 100), 0.8, 0.8, 0.8)
	end
	if m.zone then
		GameTooltip:AddLine(m.zone, 0.8, 0.8, 0.8)
	end
	if m.profs and #m.profs > 0 then
		GameTooltip:AddLine(" ")
		for _, p in ipairs(m.profs) do
			GameTooltip:AddDoubleLine(p.name, string.format("%s/%s", p.rank or "?", p.max or "?"), 1, 0.82, 0, 1, 1, 1)
		end
	end
	if m.gear and #m.gear > 0 then
		GameTooltip:AddLine(" ")
		for _, g in ipairs(m.gear) do
			GameTooltip:AddDoubleLine(SLOT_NAMES[g.s] or "?", string.format("%s (%s)", itemName(g.id), g.il or "?"), 0.7, 0.7, 0.7, 1, 1, 1)
		end
	end
	GameTooltip:Show()
end

local function sessionTooltip(row)
	local s = row.session
	if not s then
		return
	end
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip:AddLine(s.title or "Caravan session", 0.79, 0.57, 0.25)
	GameTooltip:AddLine(date("%A %d %B, %H:%M", s.start), 1, 1, 1)
	GameTooltip:AddLine(string.format("%d minutes", s.duration or 0), 0.8, 0.8, 0.8)
	for _, group in ipairs({ { "In", s.going }, { "Late", s.late }, { "Out", s.out } }) do
		if type(group[2]) == "table" and #group[2] > 0 then
			GameTooltip:AddDoubleLine(group[1], table.concat(group[2], ", "), 1, 0.82, 0, 1, 1, 1)
		end
	end
	GameTooltip:Show()
end

local function makeTab(parent, text, x, onClick)
	local tab = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	tab:SetSize(90, 22)
	tab:SetPoint("TOPLEFT", x, -28)
	tab:SetText(text)
	tab:SetScript("OnClick", onClick)
	return tab
end

function Caravan:CreateWindow()
	if self.frame then
		return self.frame
	end
	local f = CreateFrame("Frame", "TheCaravanFrame", UIParent, "BasicFrameTemplateWithInset")
	f:SetSize(600, 380)
	f:SetPoint("CENTER")
	f:SetMovable(true)
	f:EnableMouse(true)
	f:RegisterForDrag("LeftButton")
	f:SetScript("OnDragStart", f.StartMoving)
	f:SetScript("OnDragStop", f.StopMovingOrSizing)
	f:SetClampedToScreen(true)
	f:Hide()
	tinsert(UISpecialFrames, "TheCaravanFrame")

	f.title = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
	f.title:SetPoint("TOP", 0, -6)
	f.title:SetText("The Caravan")

	f.tabGroup = makeTab(f, "Group", 12, function() self:ShowTab("group") end)
	f.tabSessions = makeTab(f, "Sessions", 106, function() self:ShowTab("sessions") end)

	f.header = {}
	for c = 1, CELLS do
		local fs = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
		fs:SetJustifyH("LEFT")
		f.header[c] = fs
	end

	f.rows = {}
	for i = 1, ROWS do
		local row = CreateFrame("Button", nil, f)
		row:SetSize(576, ROW_HEIGHT)
		row:SetPoint("TOPLEFT", 12, -58 - i * (ROW_HEIGHT + 1))
		row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
		row.cells = {}
		for c = 1, CELLS do
			local fs = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
			fs:SetJustifyH("LEFT")
			fs:SetWordWrap(false)
			row.cells[c] = fs
		end
		row:SetScript("OnEnter", function(r)
			if r.member then
				memberTooltip(r)
			elseif r.session then
				sessionTooltip(r)
			end
		end)
		row:SetScript("OnLeave", function() GameTooltip:Hide() end)
		f.rows[i] = row
	end

	f.empty = f:CreateFontString(nil, "OVERLAY", "GameFontDisable")
	f.empty:SetPoint("CENTER", 0, 0)
	f.empty:SetWidth(520)

	f.footer = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	f.footer:SetPoint("BOTTOMLEFT", 14, 12)
	f.footer:SetWidth(570)
	f.footer:SetJustifyH("LEFT")

	self.frame = f
	self.tab = "group"
	return f
end

function Caravan:ApplyLayout(layout)
	local f = self.frame
	local x = 0
	for c = 1, CELLS do
		local col = layout[c]
		local header = f.header[c]
		header:ClearAllPoints()
		if col then
			header:SetPoint("TOPLEFT", f, "TOPLEFT", 16 + x, -62)
			header:SetWidth(col.width - 6)
			header:SetText(col.label)
			header:Show()
		else
			header:Hide()
		end
		for _, row in ipairs(f.rows) do
			local cell = row.cells[c]
			cell:ClearAllPoints()
			if col then
				cell:SetPoint("LEFT", row, "LEFT", 4 + x, 0)
				cell:SetWidth(col.width - 6)
				cell:Show()
			else
				cell:Hide()
			end
		end
		x = x + (col and col.width or 0)
	end
end

function Caravan:ShowTab(tab)
	self:CreateWindow()
	self.tab = tab
	self:ApplyLayout(LAYOUTS[tab])
	self:UpdateWindow()
end

function Caravan:ToggleWindow()
	local f = self:CreateWindow()
	if f:IsShown() then
		f:Hide()
	else
		f:Show()
		self:ShowTab(self.tab or "group")
	end
end

-- Members to show: roster friends plus every character of this account
-- (data collected locally has no receivedAt).
function Caravan:SortedMembers()
	local list = {}
	for name, data in pairs(self.db.members) do
		if name == self.selfName or self:IsOnRoster(name) or not data.receivedAt then
			list[#list + 1] = { name = name, data = data }
		end
	end
	for _, name in ipairs(self:RosterNames()) do
		if not self.db.members[name] then
			list[#list + 1] = { name = name }
		end
	end
	table.sort(list, function(a, b)
		local la = a.data and a.data.level or 0
		local lb = b.data and b.data.level or 0
		if la ~= lb then
			return la > lb
		end
		return a.name < b.name
	end)
	return list
end

function Caravan:FillGroup()
	local f = self.frame
	local list = self:SortedMembers()
	for i, row in ipairs(f.rows) do
		local entry = list[i]
		row.member, row.session, row.fullName = nil, nil, nil
		if entry then
			local m = entry.data
			local short = entry.name:match("^[^-]+") or entry.name
			row.fullName = entry.name
			row.member = m
			row.cells[1]:SetText(classColoured(short, m and m.class))
			row.cells[2]:SetText(m and m.level or "")
			row.cells[3]:SetText(m and m.zone or "")
			row.cells[4]:SetText(m and profSummary(m.profs) or "|cff888888no data yet|r")
			row.cells[5]:SetText(m and m.ilvl or "")
			row.cells[6]:SetText(m and ago(m.ts) or "")
			row:Show()
		else
			row:Hide()
		end
	end
	f.empty:SetText(#list <= 1 and "Add your friends with /caravan addparty while grouped,\nor /caravan add Name." or "")
	local unlisted = {}
	for name in pairs(self.unlisted) do
		unlisted[#unlisted + 1] = name
	end
	table.sort(unlisted)
	if #unlisted > 0 then
		f.footer:SetText("Not on your list: " .. table.concat(unlisted, ", ") .. " - /caravan add Name")
	else
		f.footer:SetText("Data is shared while you're grouped. Hover a row for gear and professions.")
	end
end

function Caravan:FillSessions()
	local f = self.frame
	local sessions = self:UpcomingSessions()
	for i, row in ipairs(f.rows) do
		local s = sessions[i]
		row.member, row.session = nil, nil
		if s then
			row.session = s
			local coming = {}
			for _, n in ipairs(type(s.going) == "table" and s.going or {}) do
				coming[#coming + 1] = n
			end
			for _, n in ipairs(type(s.late) == "table" and s.late or {}) do
				coming[#coming + 1] = n .. " (late)"
			end
			row.cells[1]:SetText(date("%a %d %b %H:%M", s.start))
			row.cells[2]:SetText(s.title or "Caravan session")
			row.cells[3]:SetText(#coming > 0 and table.concat(coming, ", ") or "-")
			row.cells[4]:SetText(type(s.out) == "table" and #s.out or 0)
			row:Show()
		else
			row:Hide()
		end
	end
	f.empty:SetText(#sessions == 0 and "No upcoming sessions.\nSessions from Discord appear here after the sync app updates\nyour saved data while the game is closed." or "")
	local schedule = TheCaravanSchedule
	if type(schedule) == "table" and schedule.generated_at then
		f.footer:SetText("From Discord, synced " .. date("%a %d %b %H:%M", schedule.generated_at) .. ". Schedule /session add in Discord.")
	else
		f.footer:SetText("Schedule sessions in Discord with /session add.")
	end
end

function Caravan:UpdateWindow()
	local f = self.frame
	if not f or not f:IsShown() then
		return
	end
	if self.tab == "sessions" then
		self:FillSessions()
	else
		self:FillGroup()
	end
end
