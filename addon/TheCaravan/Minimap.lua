-- Minimap button: click to open the window, drag to move it around the edge.

local _, ns = ...
local Caravan = ns.Caravan

local ICON = "Interface\\Icons\\INV_Misc_Map_01"

local function place(button, angle)
	local radius = (Minimap:GetWidth() / 2) + 10
	local rad = math.rad(angle)
	button:ClearAllPoints()
	button:SetPoint("CENTER", Minimap, "CENTER", math.cos(rad) * radius, math.sin(rad) * radius)
end

local function dragUpdate(button)
	local mx, my = Minimap:GetCenter()
	local px, py = GetCursorPosition()
	local scale = Minimap:GetEffectiveScale()
	local angle = math.deg(math.atan2(py / scale - my, px / scale - mx))
	Caravan.db.minimap.angle = angle
	place(button, angle)
end

function Caravan:CreateMinimapButton()
	if self.minimapButton then
		return
	end
	local b = CreateFrame("Button", "TheCaravanMinimapButton", Minimap)
	b:SetSize(31, 31)
	b:SetFrameStrata("MEDIUM")
	b:SetFrameLevel(8)
	b:RegisterForClicks("AnyUp")
	b:RegisterForDrag("LeftButton")
	b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")

	local background = b:CreateTexture(nil, "BACKGROUND")
	background:SetSize(20, 20)
	background:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
	background:SetPoint("TOPLEFT", 7, -5)

	local icon = b:CreateTexture(nil, "ARTWORK")
	icon:SetSize(17, 17)
	icon:SetTexture(ICON)
	icon:SetPoint("TOPLEFT", 7, -6)

	local border = b:CreateTexture(nil, "OVERLAY")
	border:SetSize(53, 53)
	border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
	border:SetPoint("TOPLEFT")

	b:SetScript("OnClick", function() Caravan:ToggleWindow() end)
	b:SetScript("OnDragStart", function(button) button:SetScript("OnUpdate", dragUpdate) end)
	b:SetScript("OnDragStop", function(button) button:SetScript("OnUpdate", nil) end)
	b:SetScript("OnEnter", function(button)
		GameTooltip:SetOwner(button, "ANCHOR_LEFT")
		GameTooltip:AddLine("The Caravan")
		local nextSession = Caravan:UpcomingSessions()[1]
		if nextSession then
			GameTooltip:AddLine(string.format("Next: %s, %s", nextSession.title or "session", date("%a %H:%M", nextSession.start)), 1, 1, 1)
		end
		GameTooltip:AddLine("Click to open. Drag to move.", 0.7, 0.7, 0.7)
		GameTooltip:Show()
	end)
	b:SetScript("OnLeave", function() GameTooltip:Hide() end)

	self.minimapButton = b
	self:UpdateMinimapButton()
end

function Caravan:UpdateMinimapButton()
	local b = self.minimapButton
	if not b then
		return
	end
	if self.db.minimap.hide then
		b:Hide()
	else
		place(b, self.db.minimap.angle or 200)
		b:Show()
	end
end
