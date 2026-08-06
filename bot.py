import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import json
import asyncio
import datetime
import re
import aiohttp

# --- Config Files & Storage ---
VERIFY_CONFIG_DATEI = "verify_config.json"
TICKET_SETUP_DATEI = "ticket_setup.json"
TICKET_DATEI = "ticket_tickets.json"
ROLLEN_DATEI = "rollen_config.json"
VOICE_DATEI = "voice_config.json"
EVENT_DATEI = "event_config.json"
DROP_DATEI = "drop_config.json"
GIVEAWAY_DATEI = "giveaway_config.json"
WELCOME_DATEI = "welcome_config.json"
TIMER_DATEI = "timer_config.json"
LEVEL_CONFIG_DATEI = "level_config.json"
LEVEL_DATEI = "level_data.json"
APPLY_SETUP_DATEI = "apply_setup.json"
APPLY_DATEI = "apply_bewerbungen.json"
VIP_CONFIG_DATEI = "vip_config.json"
VIP_LINKS_DATEI = "vip_links.json"
VIP_GESPERRTE_NAMEN_DATEI = "vip_gesperrte_namen.json"
KI_CONFIG_DATEI = "ki_config.json"
KI_USAGE_DATEI = "ki_usage.json"
CHECK_CONFIG_DATEI = "check_config.json"

ERLAUBTE_ROLLE = "⭐ᴄᴏɴᴛᴇɴᴛ ᴄʀᴇᴀᴛᴏʀ"

# =========================================================================
# ============================ VERIFY SYSTEM ==============================
# =========================================================================

def verify_config_laden():
    if os.path.exists(VERIFY_CONFIG_DATEI):
        with open(VERIFY_CONFIG_DATEI, "r") as f:
            return json.load(f)
    return None

def verify_config_speichern(config):
    with open(VERIFY_CONFIG_DATEI, "w") as f:
        json.dump(config, f)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button_main")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = verify_config_laden()
        if not config or not config.get("role_id"):
            await interaction.response.send_message(
                "❌ Verification system has not been properly configured by an administrator.",
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(int(config["role_id"]))
        if role is None:
            await interaction.response.send_message(
                "❌ The verification role could not be found. Please contact support.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message("⚠️ You are already verified!", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ You have been successfully verified! Access granted.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Failed to give you the verified role. Check bot permissions.", ephemeral=True)

# =========================================================================
# ======================== MODERN TICKET SYSTEM ===========================
# =========================================================================

def ticket_setup_laden():
    if os.path.exists(TICKET_SETUP_DATEI):
        with open(TICKET_SETUP_DATEI, "r") as f:
            return json.load(f)
    return None

def ticket_setup_speichern(config):
    with open(TICKET_SETUP_DATEI, "w") as f:
        json.dump(config, f)

def tickets_laden():
    if os.path.exists(TICKET_DATEI):
        with open(TICKET_DATEI, "r") as f:
            return json.load(f)
    return {}

def tickets_speichern(tickets):
    with open(TICKET_DATEI, "w") as f:
        json.dump(tickets, f)

def ticket_zaehler_erhoehen():
    setup = ticket_setup_laden() or {}
    zaehler = setup.get("zaehler", 0) + 1
    setup["zaehler"] = zaehler
    ticket_setup_speichern(setup)
    return zaehler

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        setup = ticket_setup_laden()
        knoepfe = setup.get("knoepfe", ["Support", "Report", "Bug Report", "Other"]) if setup else ["Support", "Report", "Bug Report", "Other"]
        for i, label in enumerate(knoepfe):
            self.add_item(TicketOpenButton(i, label))

class TicketOpenButton(discord.ui.Button):
    def __init__(self, index: int, label: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_open_{index}",
            emoji="🎫"
        )
        self.button_label = label

    async def callback(self, interaction: discord.Interaction):
        await ticket_erstellen(interaction, self.button_label)

async def ticket_erstellen(interaction: discord.Interaction, ticket_typ: str):
    setup = ticket_setup_laden()
    if setup is None:
        await interaction.response.send_message(
            "⚠️ Ticket system has not been set up. An administrator must run `/ticketsystem-setup` first.",
            ephemeral=True
        )
        return

    kategorie = interaction.guild.get_channel(int(setup["kategorie_id"]))
    if kategorie is None:
        await interaction.response.send_message("⚠️ The ticket category no longer exists.", ephemeral=True)
        return

    mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"]))

    alle_tickets = tickets_laden()
    for ch_id, daten in alle_tickets.items():
        if daten["opener_id"] == str(interaction.user.id) and not daten.get("geschlossen"):
            channel_vorhanden = interaction.guild.get_channel(int(ch_id))
            if channel_vorhanden is not None:
                await interaction.response.send_message(
                    f"⚠️ You already have an open ticket: {channel_vorhanden.mention}",
                    ephemeral=True
                )
                return

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if mod_rolle is not None:
        overwrites[mod_rolle] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    nummer = ticket_zaehler_erhoehen()
    channel_name = f"ticket-{nummer:04d}-{interaction.user.name}".lower().replace(" ", "-")[:90]

    try:
        neuer_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=kategorie,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user.id} | Type: {ticket_typ}"
        )
    except discord.HTTPException:
        await interaction.response.send_message("⚠️ Could not create the ticket channel. Missing permissions.", ephemeral=True)
        return

    alle_tickets[str(neuer_channel.id)] = {
        "opener_id": str(interaction.user.id),
        "opener_name": str(interaction.user),
        "guild_id": str(interaction.guild.id),
        "typ": ticket_typ,
        "beansprucht_von": None,
        "geschlossen": False
    }
    tickets_speichern(alle_tickets)

    embed = discord.Embed(
        title=f"🎫 Ticket: {ticket_typ}",
        description=(
            f"Hello {interaction.user.mention}! A staff member will assist you shortly.\n"
            f"Please describe your issue in detail below.\n\n"
            f"🙋 **Claim** – Staff member claims this ticket to handle it privately.\n"
            f"🔁 **Transfer** – Transfer ownership of this ticket to another staff member.\n"
            f"🔒 **Close** – Closes the ticket and sends a full transcript via direct message."
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Opened by {interaction.user}")

    ping_text = mod_rolle.mention if mod_rolle else ""
    await neuer_channel.send(content=f"{interaction.user.mention} {ping_text}", embed=embed, view=TicketActionView())
    await interaction.response.send_message(f"✅ Your ticket has been created: {neuer_channel.mention}", ephemeral=True)

class TicketTransferSelectView(discord.ui.View):
    def __init__(self, mod_rolle_id: int):
        super().__init__(timeout=60)
        self.mod_rolle_id = mod_rolle_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a staff member to transfer to")
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        ziel_user = select.values[0]
        mod_rolle = interaction.guild.get_role(self.mod_rolle_id)

        if mod_rolle is None or mod_rolle not in getattr(ziel_user, "roles", []):
            await interaction.response.send_message("⚠️ Selected member does not have the Support Staff role.", ephemeral=True)
            return

        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))
        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ This ticket no longer exists.", ephemeral=True)
            return

        alter_claimer_id = daten.get("beansprucht_von")
        if alter_claimer_id:
            altes_mitglied = interaction.guild.get_member(int(alter_claimer_id))
            if altes_mitglied is not None:
                await interaction.channel.set_permissions(altes_mitglied, overwrite=None)

        await interaction.channel.set_permissions(
            ziel_user, view_channel=True, send_messages=True, read_message_history=True
        )

        daten["beansprucht_von"] = str(ziel_user.id)
        tickets[str(interaction.channel.id)] = daten
        tickets_speichern(tickets)

        await interaction.response.edit_message(content=f"✅ Ticket transferred to {ziel_user.mention}.", view=None)
        await interaction.channel.send(f"🔁 Ticket has been transferred to {ziel_user.mention}.")

class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ This ticket no longer exists.", ephemeral=True)
            return

        mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"])) if setup else None
        ist_admin = interaction.user.guild_permissions.administrator
        ist_mod = mod_rolle is not None and mod_rolle in interaction.user.roles
        if not (ist_mod or ist_admin):
            await interaction.response.send_message("❌ Only members with the Support Staff role can claim tickets.", ephemeral=True)
            return

        if daten.get("beansprucht_von"):
            beanspruchendes_mitglied = interaction.guild.get_member(int(daten["beansprucht_von"]))
            name = beanspruchendes_mitglied.mention if beanspruchendes_mitglied else "someone else"
            await interaction.response.send_message(f"⚠️ This ticket is already claimed by {name}.", ephemeral=True)
            return

        if mod_rolle is not None:
            await interaction.channel.set_permissions(mod_rolle, view_channel=False)
        await interaction.channel.set_permissions(
            interaction.user, view_channel=True, send_messages=True, read_message_history=True
        )

        daten["beansprucht_von"] = str(interaction.user.id)
        tickets[str(interaction.channel.id)] = daten
        tickets_speichern(tickets)

        embed = discord.Embed(
            description=f"🙋 {interaction.user.mention} has claimed this ticket. Private channel engaged.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="ticket_transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ This ticket no longer exists.", ephemeral=True)
            return

        if not daten.get("beansprucht_von"):
            await interaction.response.send_message("⚠️ Ticket is unclaimed. Claim it first before transferring.", ephemeral=True)
            return

        ist_admin = interaction.user.guild_permissions.administrator
        ist_aktueller_claimer = str(interaction.user.id) == daten["beansprucht_von"]
        if not (ist_aktueller_claimer or ist_admin):
            await interaction.response.send_message("❌ Only the member who claimed this ticket can transfer it.", ephemeral=True)
            return

        view = TicketTransferSelectView(int(setup["mod_rolle_id"]))
        await interaction.response.send_message("Select a staff member to transfer this ticket to:", view=view, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ This ticket no longer exists.", ephemeral=True)
            return

        mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"])) if setup else None
        ist_admin = interaction.user.guild_permissions.administrator
        ist_mod = mod_rolle is not None and mod_rolle in interaction.user.roles
        ist_opener = str(interaction.user.id) == daten["opener_id"]
        ist_claimer = str(interaction.user.id) == (daten.get("beansprucht_von") or "")

        if not (ist_admin or ist_mod or ist_opener or ist_claimer):
            await interaction.response.send_message("❌ You do not have permission to close this ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Closing ticket and saving transcript...")

        zeilen = []
        async for nachricht in interaction.channel.history(limit=None, oldest_first=True):
            zeit = nachricht.created_at.strftime("%Y-%m-%d %H:%M:%S")
            inhalt = nachricht.content or "[Embed or Attachment]"
            zeilen.append(f"[{zeit}] {nachricht.author}: {inhalt}")
        transcript_text = "\n".join(zeilen) if zeilen else "(Empty Chat)"

        dateiname = f"transcript-{interaction.channel.name}.txt"
        with open(dateiname, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        opener = interaction.guild.get_member(int(daten["opener_id"]))
        if opener is not None:
            try:
                dm_embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    description=f"Your ticket **{daten['typ']}** in **{interaction.guild.name}** has been closed.\nA transcript has been attached.",
                    color=discord.Color.dark_grey()
                )
                await opener.send(embed=dm_embed, file=discord.File(dateiname))
            except discord.HTTPException:
                pass

        if os.path.exists(dateiname):
            os.remove(dateiname)

        daten["geschlossen"] = True
        tickets[str(interaction.channel.id)] = daten
        tickets_speichern(tickets)

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.HTTPException:
            pass

# =========================================================================
# ======================== GENERAL BOT SETUP ==============================
# =========================================================================

TOKEN = os.getenv("TOKEN")
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.add_view(VerifyView())
    bot.add_view(TicketPanelView())
    bot.add_view(TicketActionView())

    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} Slash Commands")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

# =========================================================================
# ============================ SLASH COMMANDS =============================
# =========================================================================

@bot.tree.command(name="verify-setup", description="[Admin] Set up the verification panel")
@app_commands.describe(
    channel="The channel where the verify embed will be posted",
    role="The role granted upon successful verification",
    title="Custom panel title",
    description="Custom panel description message"
)
@app_commands.checks.has_permissions(administrator=True)
async def verify_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
    title: str = "Member Verification",
    description: str = "Click the button below to verify yourself and gain full access to the server."
):
    config = {
        "channel_id": str(channel.id),
        "role_id": str(role.id)
    }
    verify_config_speichern(config)

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green()
    )
    embed.set_footer(text=f"{interaction.guild.name} • Verification System")

    await channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message(
        f"✅ Verification system successfully posted in {channel.mention}. Grants role: **{role.name}**",
        ephemeral=True
    )

@bot.tree.command(name="ticketsystem-setup", description="[Admin] Set up the modern ticket system panel")
@app_commands.describe(
    channel="Channel to post the ticket panel",
    category="Category where ticket channels will be created",
    staff_role="Role allowed to view and manage open tickets",
    title="Panel title",
    description="Panel description",
    btn1="Label for Button 1",
    btn2="Label for Button 2",
    btn3="Label for Button 3",
    btn4="Label for Button 4"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticketsystem_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    category: discord.CategoryChannel,
    staff_role: discord.Role,
    title: str = "Support Tickets",
    description: str = "Need assistance? Click a button below to open a private ticket with our team.",
    btn1: str = "Support",
    btn2: str = "Report",
    btn3: str = "Bug Report",
    btn4: str = "Other"
):
    knoepfe = [btn1, btn2, btn3, btn4]
    config = {
        "kategorie_id": str(category.id),
        "mod_rolle_id": str(staff_role.id),
        "panel_channel_id": str(channel.id),
        "knoepfe": knoepfe,
        "zaehler": 0
    }
    ticket_setup_speichern(config)

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{interaction.guild.name} • Ticket System")

    await channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message(
        f"✅ Ticket system setup completed! Panel posted in {channel.mention}.",
        ephemeral=True
    )

bot.run(TOKEN)
