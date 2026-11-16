"""The addon window: resizing, column widths and scrolling."""

from .addon_harness import Client, run, to_py

FIVE_PROFS = [
    {"name": "Blacksmithing", "rank": 26, "max": 75}, {"name": "Mining", "rank": 53, "max": 75},
    {"name": "First Aid", "rank": 58, "max": 75}, {"name": "Fishing", "rank": 20, "max": 75},
    {"name": "Cooking", "rank": 35, "max": 75},
]


def open_window(a: Client):
    a.slash("")
    return a.g.TheCaravanFrame


def resize(a: Client, w: int, h: int) -> None:
    f = a.g.TheCaravanFrame
    a.W.dragSize = a.lua.table(w, h)
    f.grip.scripts.OnMouseDown(f.grip)
    f.grip.scripts.OnMouseUp(f.grip)


def test_column_widths_share_the_spare_width_by_weight():
    a = Client("Roland")
    layout = a.addon.LAYOUTS.group
    mins = [col["min"] for col in to_py(layout)]
    widths = to_py(a.call("ColumnWidths", layout, sum(mins) + 430))
    assert all(w >= m for w, m in zip(widths, mins))
    assert sum(widths) <= sum(mins) + 430
    extra = [w - m for w, m in zip(widths, mins)]
    assert extra[3] == max(extra)                  # Professions gets the biggest share
    assert extra[1] == extra[4] == extra[5] == 0   # Level, iLvl and Updated stay at their minimum
    squeezed = to_py(a.call("ColumnWidths", layout, sum(mins) // 2))
    assert sum(squeezed) <= sum(mins) // 2


def test_window_opens_at_the_default_size_and_remembers_a_new_one():
    a = Client("Roland")
    run([a], 6)
    f = open_window(a)
    assert (f.width, f.height) == (760, 330)
    rows = f.visibleRows
    resize(a, 1000, 520)
    saved = to_py(a.g.TheCaravanDB.window)
    assert saved["w"] == 1000 and saved["h"] == 520
    assert f.visibleRows > rows
    assert sum(to_py(f.columnWidths)) <= f.listWidth
    assert a.errors == []

    b = Client("Roland", db=to_py(a.g.TheCaravanDB))  # next login, same saved data
    g = open_window(b)
    assert (g.width, g.height) == (1000, 520)


def test_saved_size_is_kept_within_bounds():
    a = Client("Roland")
    a.g.TheCaravanDB.window = a.lua.table_from({"w": 50, "h": 5000})
    f = open_window(a)
    assert (f.width, f.height) == (600, 1000)


def test_professions_are_shortened_only_when_they_dont_fit():
    a = Client("Roland")
    a.W.profs = a.lua.table_from(FIVE_PROFS, recursive=True)
    run([a], 6)
    f = open_window(a)
    resize(a, 1300, 330)
    assert f.rows[1].cells[4].text == "Blacksmithing 26, Mining 53, First Aid 58, Fishing 20, Cooking 35"
    resize(a, 600, 330)
    assert f.rows[1].cells[4].text == "Smith 26, Mine 53, Aid 58, Fish 20, Cook 35"


def test_level_column_shows_xp_progress():
    a = Client("Roland")
    run([a], 6)
    f = open_window(a)
    assert f.rows[1].cells[2].text == "14 |cff9d9d9d6%|r"


def test_long_lists_scroll():
    a = Client("Roland")
    for i in range(30):
        a.slash(f"add Friend{chr(97 + i)}" if i < 26 else f"add Pal{chr(97 + i - 26)}")
    run([a], 6)
    f = open_window(a)
    visible = f.visibleRows
    assert f.list.total == 31 and f.list.visible == visible
    first = f.rows[1].fullName
    f.list.scripts.OnVerticalScroll(f.list, 18 * 5)
    assert f.rows[1].fullName != first
    a.call("ShowTab", "sessions")
    a.call("ShowTab", "group")
    assert f.rows[1].fullName == first  # switching tabs scrolls back to the top
    assert a.errors == []


def test_sessions_tab_lists_names_out():
    now = 1794800000 + 100
    schedule = {"generated_at": now, "sessions": {1: {"title": "Raid night", "start": now + 600, "duration": 120,
                                                      "going": {1: "Arda"}, "late": {1: "Bo"}, "out": {1: "Cy"}}}}
    a = Client("Roland", schedule=schedule)
    f = open_window(a)
    a.call("ShowTab", "sessions")
    cells = [f.rows[1].cells[i].text for i in range(2, 5)]
    assert cells == ["Raid night", "Arda, Bo (late)", "Cy"]
    assert "Schedule with /session add" in f.footer.text
