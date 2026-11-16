"""Slash commands that use game data: /dungeons, /craft, /order and /character."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from . import render
from .gamedata import (
    active_levels,
    character_name,
    find_recipes,
    group_faction,
    members_without_recipes,
    recipe_names,
    suggest_dungeons,
)

if TYPE_CHECKING:
    from .discord_app import CaravanBot


def _now() -> int:
    return int(time.time())


def register_game_commands(bot: CaravanBot) -> None:
    store = bot.store

    def members() -> dict[str, Any]:
        snap = store.latest_snapshot()
        return snap.payload.get("members", {}) if snap else {}

    async def recipe_autocomplete(_: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=n[:100], value=n[:100]) for n in recipe_names(members(), current)]

    async def open_order_autocomplete(_: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        names = store.display_names()
        choices = []
        for o in store.open_orders():
            label = f"#{o.id} {o.quantity}× {o.item} for {names.get(o.requested_by, o.requested_by)}"
            if current.strip().lstrip("#") in label:
                choices.append(app_commands.Choice(name=label[:100], value=o.id))
        return choices[:25]

    @app_commands.command(name="dungeons", description="Dungeons that suit the group's levels")
    @app_commands.describe(level="Check one level instead of the group's")
    async def dungeons(interaction: discord.Interaction, level: app_commands.Range[int, 1, 60] | None = None) -> None:
        group = members()
        if level is not None:
            levels = {"You": level}
            title = f"🗺️ Dungeons for level {level}"
        else:
            snap = store.latest_snapshot()
            now = (snap.payload.get("exported_at") or snap.received_at) if snap else _now()
            levels = active_levels(group, now)
            title = "🗺️ Dungeons for the group"
        faction = group_faction(group)
        fits = suggest_dungeons(levels, faction)
        await interaction.response.send_message(embed=render.dungeons_embed(fits, levels, faction, title))

    @app_commands.command(name="craft", description="Who in the group can craft an item")
    @app_commands.describe(item="Item or recipe name")
    @app_commands.autocomplete(item=recipe_autocomplete)
    async def craft(interaction: discord.Interaction, item: str) -> None:
        group = members()
        text = render.craft_text(item, find_recipes(group, item), members_without_recipes(group))
        await interaction.response.send_message(text[:2000])

    order_group = app_commands.Group(name="order", description="Crafting orders for the group")

    @order_group.command(name="add", description="Ask the group to craft something")
    @app_commands.describe(item="What you want crafted", quantity="How many", note="Anything the crafter should know")
    @app_commands.autocomplete(item=recipe_autocomplete)
    async def order_add(
        interaction: discord.Interaction, item: str, quantity: app_commands.Range[int, 1, 200] = 1,
        note: app_commands.Range[str, 1, 200] | None = None,
    ) -> None:
        store.upsert_user(interaction.user.id, interaction.user.display_name)
        group = members()
        matches = find_recipes(group, item)
        exact = [m for m in matches if m.name.casefold() == item.casefold()]
        name = exact[0].name if exact else item.strip()[:100]
        order = store.create_order(
            channel_id=interaction.channel_id or 0, item=name, quantity=quantity, note=note,
            requested_by=interaction.user.id, now_ts=_now(),
        )
        line = render.order_line(order, store.display_names(), exact)
        if not exact:
            line += "\n-# No one in the group has shared a recipe with exactly that name."
        await interaction.response.send_message(f"📦 New order {line}")

    @order_group.command(name="list", description="Open crafting orders")
    async def order_list(interaction: discord.Interaction) -> None:
        orders = store.open_orders()
        if not orders:
            await interaction.response.send_message("No open orders. Add one with `/order add`.")
            return
        group = members()
        names = store.display_names()
        lines = [render.order_line(o, names, find_recipes(group, o.item)) for o in orders]
        await interaction.response.send_message("\n".join(lines)[:2000])

    async def close(interaction: discord.Interaction, order_id: int, status: str) -> None:
        order = store.get_order(order_id)
        if order is None or order.status != "open":
            await interaction.response.send_message(f"No open order #{order_id}.", ephemeral=True)
            return
        if status == "cancelled" and interaction.user.id != order.requested_by:
            await interaction.response.send_message(
                "Only the person who placed the order can cancel it. Use `/order done` once it's crafted.",
                ephemeral=True,
            )
            return
        store.close_order(order_id, status, interaction.user.id, _now())
        if status == "done":
            text = f"✅ Order #{order.id} ({order.quantity}× {order.item}) is done. <@{order.requested_by}>"
        else:
            text = f"🚫 Order #{order.id} ({order.quantity}× {order.item}) was cancelled."
        await interaction.response.send_message(text, allowed_mentions=discord.AllowedMentions(users=True))

    @order_group.command(name="done", description="Mark an order as crafted and handed over")
    @app_commands.describe(order_id="The order number")
    @app_commands.autocomplete(order_id=open_order_autocomplete)
    async def order_done(interaction: discord.Interaction, order_id: int) -> None:
        await close(interaction, order_id, "done")

    @order_group.command(name="cancel", description="Withdraw an order you placed")
    @app_commands.describe(order_id="The order number")
    @app_commands.autocomplete(order_id=open_order_autocomplete)
    async def order_cancel(interaction: discord.Interaction, order_id: int) -> None:
        await close(interaction, order_id, "cancelled")

    character_group = app_commands.Group(name="character", description="Link your WoW characters to you")

    async def character_autocomplete(_: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        names = sorted({*members(), *(c.name for c in store.characters())}, key=str.lower)
        return [app_commands.Choice(name=n, value=n) for n in names if current.lower() in n.lower()][:25]

    def may_manage(interaction: discord.Interaction) -> bool:
        p = interaction.permissions
        return p.manage_guild or p.administrator

    @character_group.command(name="link", description="Link a WoW character to you, so its in-game RSVPs count as yours")
    @app_commands.describe(name="Character name, e.g. Roland or Roland-Ironvale")
    @app_commands.autocomplete(name=character_autocomplete)
    async def character_link(interaction: discord.Interaction, name: str) -> None:
        full = character_name(name, list(members()))
        if full is None:
            await interaction.response.send_message(
                f"I can't tell which character `{name[:40]}` is. Add the realm, e.g. `Roland-Ironvale`.", ephemeral=True
            )
            return
        owner = store.character_owner(full)
        if owner is not None and owner != interaction.user.id:
            await interaction.response.send_message(
                f"**{full}** is linked to <@{owner}>. They can `/character unlink` it first.",
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        store.upsert_user(interaction.user.id, interaction.user.display_name)
        store.link_character(full, interaction.user.id, _now())
        note = "" if full in members() else "\n-# It isn't in the latest game snapshot yet; check the spelling of the realm."
        await interaction.response.send_message(
            f"Linked **{full}** to you. In, Late and Out in the addon's Sessions tab now count as yours.{note}",
            ephemeral=True,
        )

    @character_group.command(name="unlink", description="Unlink a WoW character")
    @app_commands.describe(name="Character name, e.g. Roland-Ironvale")
    @app_commands.autocomplete(name=character_autocomplete)
    async def character_unlink(interaction: discord.Interaction, name: str) -> None:
        full = character_name(name, [c.name for c in store.characters()])
        owner = store.character_owner(full) if full else None
        if full is None or owner is None:
            await interaction.response.send_message(f"`{name[:40]}` isn't linked to anyone.", ephemeral=True)
            return
        if owner != interaction.user.id and not may_manage(interaction):
            await interaction.response.send_message(
                f"**{full}** is linked to <@{owner}>. Only they or someone with Manage Server can unlink it.",
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        store.unlink_character(full)
        await interaction.response.send_message(f"Unlinked **{full}**.", ephemeral=True)

    @character_group.command(name="list", description="Who has linked which characters")
    async def character_list(interaction: discord.Interaction) -> None:
        links = store.characters()
        if not links:
            await interaction.response.send_message(
                "No characters linked yet. Link yours with `/character link`.", ephemeral=True
            )
            return
        names = store.display_names()
        by_user: dict[int, list[str]] = {}
        for c in links:
            by_user.setdefault(c.user_id, []).append(c.name)
        lines = [f"**{names.get(uid, uid)}**: {', '.join(chars)}" for uid, chars in by_user.items()]
        await interaction.response.send_message("\n".join(lines)[:2000], ephemeral=True)

    bot.tree.add_command(dungeons)
    bot.tree.add_command(craft)
    bot.tree.add_command(order_group)
    bot.tree.add_command(character_group)
