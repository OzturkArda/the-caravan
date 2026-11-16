-- The Caravan window: a Group tab (everyone's characters) and a Sessions
-- tab (upcoming sessions from Discord).
--
-- The window can be moved and resized; its size and position are saved for
-- the account. Columns have a minimum width and share out any extra width by
-- weight, the list shows as many rows as fit, and scrolls when there are more.

local _, ns = ...
local Caravan = ns.Caravan

local ROW_HEIGHT = 18
local PAD = 10            -- frame edge to list
local HEADER_TOP = 58     -- frame top to the column headers
local LIST_TOP = 74       -- frame top to the first row
local FOOTER_HEIGHT = 38  -- room for two lines of footer text
local SCROLLBAR = 24
local CELLS = 6
local MIN_W, MIN_H, MAX_W, MAX_H = 600, 220, 1600, 1000
local DEFAULT_W, DEFAULT_H = 760, 330

local SLOT_NAMES = {
	[1] = "Head", [2] = "Neck", [3] = "Shoulder", [5] = "Chest", [6] = "Waist", [7] = "Legs",
	[8] = "Feet", [9] = "Wrist", [10] = "Hands", [11] = "Ring", [12] = "Ring", [13] = "Trinket",
	[14] = "Trinket", [15] = "Back", [16] = "Main hand", [17] = "Off hand", [18] = "Ranged",
}

-- min: width in pixels; flex: share of the width left over once every
-- column has its minimum.
local LAYOUTS = {
	group = {
		{ label = "Name", min = 90, flex = 0.5 },
		{ label = "Level", min = 56 },
		{ label = "Zone", min = 110, flex = 0.8 },
		{ label = "Professions", min = 160, flex = 3 },
		{ label = "iLvl", min = 40 },
		{ label = "Updated", min = 64 },
	},
	sessions = {
		{ label = "When", min = 112 },
		{ label = "Session", min = 110, flex = 1.5 },
		{ label = "Coming", min = 130, flex = 3 },
		{ label = "Out", min = 70, flex = 1 },
	},
}
Caravan.LAYOUTS = LAYOUTS

-- Shorter profession names, used when the full list doesn't fit its column.
local SHORT_PROF = {
	Alchemy = "Alch", Blacksmithing = "Smith", Enchanting = "Ench", Engineering = "Eng",
	Herbalism = "Herb", Inscription = "Insc", Jewelcrafting = "JC", Leatherworking = "LW",
	Mining = "Mine", Skinning = "Skin", Tailoring = "Tailor", ["First Aid"] = "Aid",
	Fishing = "Fish", Cooking = "Cook",
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

function Caravan:ProfessionSummary(profs, short)
	local parts = {}
	for _, p in ipairs(profs or {}) do
		local name = short and SHORT_PROF[p.name] or p.name
		parts[#parts + 1] = string.format("%s %s", name, p.rank or "?")
	end
	return #parts > 0 and table.concat(parts, ", ") or "-"
end

local function levelText(m)
	if not m.level then
		return ""
	end
	if m.xp and m.xpMax and m.xpMax > 0 then
		return string.format("%d |cff9d9d9d%d%%|r", m.level, m.xp / m.xpMax * 100)
	end
	return tostring(m.level)
end

local function textWidth(fs)
	if fs.GetUnboundedStringWidth then
		return fs:GetUnboundedStringWidth()
	end
	return fs:GetStringWidth()
end

-- Show `full`, or `short` when `full` doesn't fit the cell.
local function fitText(fs, full, short)
	fs:SetText(full)
	if short and short ~= full and textWidth(fs) > fs:GetWidth() then
		fs:SetText(short)
	end
end

-- Pixel widths for a layout's columns across `total` pixels.
function Caravan:ColumnWidths(layout, total)
	local fixed, flex = 0, 0
	for _, col in ipairs(layout) do
		fixed = fixed + col.min
		flex = flex + (col.flex or 0)
	end
	local widths = {}
	if total < fixed then
		for i, col in ipairs(layout) do
			widths[i] = math.floor(col.min * total / fixed)
		end
		return widths
	end
	local spare = total - fixed
	for i, col in ipairs(layout) do
		local extra = (flex > 0 and col.flex) and spare * col.flex / flex or 0
		widths[i] = math.floor(col.min + extra)
	end
	return widths
end

local function memberTooltip(row)
	local m = row.member
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip:AddLine(classColoured(row.fullName, m and m.class))
	if not m then
		GameTooltip:AddLine("No data yet: group up once to swap data.", 0.8, 0.8, 0.8)
		GameTooltip:Show()
		return
	end
	GameTooltip:AddLine(string.format("Level %s %s", m.level or "?", m.race or ""), 1, 1, 1)
	if m.xp and m.xpMax and m.xpMax > 0 then
		GameTooltip:AddLine(string.format("XP %d / %d (%d%%)", m.xp, m.xpMax, m.xp / m.xpMax * 100), 0.8, 0.8, 0.8)
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

local function clamp(v, lo, hi)
	return math.max(lo, math.min(hi, v))
end

local function scrollBar(f)
	local bar = f.list.ScrollBar
	if type(bar) ~= "table" then
		bar = _G["TheCaravanFrameListScrollBar"]
	end
	return type(bar) == "table" and bar or nil
end

function Caravan:SaveWindowGeometry()
	local f, saved = self.frame, self.db.window
	saved.w = math.floor(f:GetWidth() + 0.5)
	saved.h = math.floor(f:GetHeight() + 0.5)
	local point, _, relPoint, x, y = f:GetPoint(1)
	if type(point) == "string" and type(x) == "number" and type(y) == "number" then
		saved.point, saved.relPoint = point, relPoint
		saved.x, saved.y = math.floor(x + 0.5), math.floor(y + 0.5)
	end
end

function Caravan:CreateWindow()
	if self.frame then
		return self.frame
	end
	local saved = self.db.window
	local f = CreateFrame("Frame", "TheCaravanFrame", UIParent, "BasicFrameTemplateWithInset")
	f:SetSize(clamp(saved.w or DEFAULT_W, MIN_W, MAX_W), clamp(saved.h or DEFAULT_H, MIN_H, MAX_H))
	if saved.point then
		f:SetPoint(saved.point, UIParent, saved.relPoint or saved.point, saved.x or 0, saved.y or 0)
	else
		f:SetPoint("CENTER")
	end
	f:SetMovable(true)
	f:SetResizable(true)
	if f.SetResizeBounds then
		f:SetResizeBounds(MIN_W, MIN_H, MAX_W, MAX_H)
	elseif f.SetMinResize then
		f:SetMinResize(MIN_W, MIN_H)
		f:SetMaxResize(MAX_W, MAX_H)
	end
	f:EnableMouse(true)
	f:RegisterForDrag("LeftButton")
	f:SetScript("OnDragStart", f.StartMoving)
	f:SetScript("OnDragStop", function(frame)
		frame:StopMovingOrSizing()
		self:SaveWindowGeometry()
	end)
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
		fs:SetWordWrap(false)
		f.header[c] = fs
	end

	-- The scroll frame only drives the scroll bar; the rows sit on the window.
	f.list = CreateFrame("ScrollFrame", "TheCaravanFrameList", f, "FauxScrollFrameTemplate")
	f.list:SetScript("OnVerticalScroll", function(list, offset)
		if FauxScrollFrame_OnVerticalScroll then
			FauxScrollFrame_OnVerticalScroll(list, offset, ROW_HEIGHT, function() self:UpdateWindow() end)
		end
	end)
	f:EnableMouseWheel(true)
	f:SetScript("OnMouseWheel", function(_, delta)
		local bar = scrollBar(f)
		if bar then
			bar:SetValue(bar:GetValue() - delta * ROW_HEIGHT * 3)
		end
	end)
	f.rows = {}

	f.empty = f:CreateFontString(nil, "OVERLAY", "GameFontDisable")
	f.empty:SetPoint("CENTER", f, "CENTER", 0, -10)

	f.footer = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	f.footer:SetPoint("BOTTOMLEFT", PAD + 4, 10)
	f.footer:SetJustifyH("LEFT")
	f.footer:SetJustifyV("BOTTOM")

	local grip = CreateFrame("Button", nil, f)
	grip:SetSize(16, 16)
	grip:SetPoint("BOTTOMRIGHT", -5, 5)
	grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
	grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
	grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
	grip:SetScript("OnMouseDown", function() f:StartSizing("BOTTOMRIGHT") end)
	grip:SetScript("OnMouseUp", function()
		f:StopMovingOrSizing()
		self:SaveWindowGeometry()
		self:LayoutWindow()
		self:UpdateWindow()
	end)
	f.grip = grip
	f:SetScript("OnSizeChanged", function()
		self:LayoutWindow()
		self:UpdateWindow()
	end)

	self.frame = f
	self.tab = self.tab or "group"
	self:LayoutWindow()
	return f
end

local function onRowEnter(row)
	if row.session then
		sessionTooltip(row)
	elseif row.fullName then
		memberTooltip(row)
	end
end

function Caravan:CreateRow(f, i)
	local row = CreateFrame("Button", nil, f)
	row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
	row.bg = row:CreateTexture(nil, "BACKGROUND")
	row.bg:SetAllPoints()
	row.bg:SetColorTexture(1, 1, 1, i % 2 == 0 and 0.04 or 0)
	row.cells = {}
	for c = 1, CELLS do
		local fs = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
		fs:SetJustifyH("LEFT")
		fs:SetWordWrap(false)
		row.cells[c] = fs
	end
	row:SetScript("OnEnter", onRowEnter)
	row:SetScript("OnLeave", function() GameTooltip:Hide() end)
	return row
end

-- Fit rows and columns to the window's current size.
function Caravan:LayoutWindow()
	local f = self.frame
	if not f then
		return
	end
	local w, h = f:GetWidth(), f:GetHeight()
	local listWidth = w - 2 * PAD - SCROLLBAR
	local visible = math.max(1, math.floor((h - LIST_TOP - FOOTER_HEIGHT) / ROW_HEIGHT))
	for i = #f.rows + 1, visible do
		f.rows[i] = self:CreateRow(f, i)
	end
	for i, row in ipairs(f.rows) do
		row:ClearAllPoints()
		row:SetPoint("TOPLEFT", f, "TOPLEFT", PAD, -LIST_TOP - (i - 1) * ROW_HEIGHT)
		row:SetSize(listWidth, ROW_HEIGHT)
		if i > visible then
			row:Hide()
		end
	end
	f.visibleRows = visible
	f.listWidth = listWidth
	f.list:ClearAllPoints()
	f.list:SetPoint("TOPLEFT", f, "TOPLEFT", PAD, -LIST_TOP)
	f.list:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -PAD - SCROLLBAR, FOOTER_HEIGHT)
	f.empty:SetWidth(listWidth - 40)
	f.footer:SetWidth(w - 2 * PAD - 24)
	self:ApplyColumns()
end

function Caravan:ApplyColumns()
	local f = self.frame
	local layout = LAYOUTS[self.tab] or LAYOUTS.group
	local widths = self:ColumnWidths(layout, f.listWidth)
	f.columnWidths = widths
	local x = 0
	for c = 1, CELLS do
		local col, width = layout[c], widths[c]
		local header = f.header[c]
		header:ClearAllPoints()
		if col then
			header:SetPoint("TOPLEFT", f, "TOPLEFT", PAD + 4 + x, -HEADER_TOP)
			header:SetWidth(width - 6)
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
				cell:SetWidth(width - 6)
				cell:Show()
			else
				cell:SetText("")
				cell:Hide()
			end
		end
		x = x + (width or 0)
	end
end

function Caravan:ShowTab(tab)
	self:CreateWindow()
	self.tab = tab
	local f = self.frame
	f.list.offset = 0
	local bar = scrollBar(f)
	if bar then
		bar:SetValue(0)
	end
	for name, button in pairs({ group = f.tabGroup, sessions = f.tabSessions }) do
		if name == tab then
			button:LockHighlight()
		else
			button:UnlockHighlight()
		end
	end
	self:ApplyColumns()
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

-- Fill the visible rows from `items`, starting at the scroll position.
function Caravan:FillRows(items, fill)
	local f = self.frame
	local visible = f.visibleRows
	local offset = FauxScrollFrame_GetOffset and FauxScrollFrame_GetOffset(f.list) or 0
	offset = clamp(offset, 0, math.max(0, #items - visible))
	if FauxScrollFrame_Update then
		FauxScrollFrame_Update(f.list, #items, visible, ROW_HEIGHT)
	end
	for i, row in ipairs(f.rows) do
		local item = i <= visible and items[offset + i]
		row.member, row.session, row.fullName = nil, nil, nil
		if item then
			fill(row, item)
			row:Show()
		else
			row:Hide()
		end
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
	self:FillRows(list, function(row, entry)
		local m = entry.data
		local short = entry.name:match("^[^-]+") or entry.name
		row.fullName = entry.name
		row.member = m
		row.cells[1]:SetText(classColoured(short, m and m.class))
		row.cells[2]:SetText(m and levelText(m) or "")
		row.cells[3]:SetText(m and m.zone or "")
		if m then
			fitText(row.cells[4], self:ProfessionSummary(m.profs), self:ProfessionSummary(m.profs, true))
		else
			row.cells[4]:SetText("|cff888888no data yet|r")
		end
		row.cells[5]:SetText(m and m.ilvl or "")
		row.cells[6]:SetText(m and ago(m.ts) or "")
	end)
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
	self:FillRows(sessions, function(row, s)
		row.session = s
		local coming = {}
		for _, n in ipairs(type(s.going) == "table" and s.going or {}) do
			coming[#coming + 1] = n
		end
		for _, n in ipairs(type(s.late) == "table" and s.late or {}) do
			coming[#coming + 1] = n .. " (late)"
		end
		local out = type(s.out) == "table" and s.out or {}
		row.cells[1]:SetText(date("%a %d %b %H:%M", s.start))
		row.cells[2]:SetText(s.title or "Caravan session")
		row.cells[3]:SetText(#coming > 0 and table.concat(coming, ", ") or "-")
		fitText(row.cells[4], #out > 0 and table.concat(out, ", ") or "-", tostring(#out))
	end)
	f.empty:SetText(#sessions == 0 and "No upcoming sessions.\nSessions from Discord come in through the sync app,\nor from a friend's addon when you group up." or "")
	local schedule = self:Schedule()
	if schedule and schedule.generated_at then
		local via = type(schedule.from) == "string" and (" via " .. (schedule.from:match("^[^-]+") or schedule.from)) or ""
		f.footer:SetText(string.format("From Discord%s, synced %s. Schedule with /session add in Discord.",
			via, date("%a %d %b %H:%M", schedule.generated_at)))
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
