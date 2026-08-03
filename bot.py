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

# --- Rollenname, der /newvideo nutzen darf (muss EXAKT so heißen wie deine Rolle) ---
ERLAUBTE_ROLLE = "⭐ᴄᴏɴᴛᴇɴᴛ ᴄʀᴇᴀᴛᴏʀ"

# --- Speicherort für die per /rollen-setup ausgewählten Rollen ---
ROLLEN_DATEI = "rollen_config.json"

def rollen_laden():
    if os.path.exists(ROLLEN_DATEI):
        with open(ROLLEN_DATEI, "r") as f:
            return json.load(f)
    return []  # noch keine Rollen konfiguriert

def rollen_speichern(rollen_liste):
    with open(ROLLEN_DATEI, "w") as f:
        json.dump(rollen_liste, f)

# --- Speicherort für die per /voice-setup ausgewählte Kategorie ---
VOICE_DATEI = "voice_config.json"

def voice_kategorie_laden():
    if os.path.exists(VOICE_DATEI):
        with open(VOICE_DATEI, "r") as f:
            return json.load(f).get("kategorie_id")
    return None

def voice_kategorie_speichern(kategorie_id):
    with open(VOICE_DATEI, "w") as f:
        json.dump({"kategorie_id": kategorie_id}, f)

# --- Speicherort für die per /event-setup eingerichtete Config ---
EVENT_DATEI = "event_config.json"

def event_config_laden():
    if os.path.exists(EVENT_DATEI):
        with open(EVENT_DATEI, "r") as f:
            return json.load(f)
    return None

def event_config_speichern(link, channel_id):
    with open(EVENT_DATEI, "w") as f:
        json.dump({"link": link, "channel_id": channel_id}, f)

# --- Speicherort für die per /drop-setup eingerichtete Config ---
DROP_DATEI = "drop_config.json"

# --- Standard-Reaction-Emojis pro Tier (können teilweise überschrieben werden) ---
STANDARD_EMOJIS = {
    "honig": "🍯",
    "episch": "⚡",
    "mythic": "🔮",
    "secret": "👑"
}

# --- Feste Werte pro Drop-Tier: Anzeigename, Wins, Intervall in Sekunden ---
DROP_TIERS = {
    "honig": {"name": "Honey Drop", "wins": 50, "intervall": 15 * 60, "farbe": 0xF5A623},
    "episch": {"name": "Episch", "wins": 300, "intervall": 30 * 60, "farbe": 0x9B59B6},
    "mythic": {"name": "Mythic", "wins": 500, "intervall": 60 * 60, "farbe": 0xE91E63},
    "secret": {"name": "Secret", "wins": 800, "intervall": None, "farbe": 0x2C2F33},  # Intervall = zufällig 4-5h
}

def drop_config_laden():
    if os.path.exists(DROP_DATEI):
        with open(DROP_DATEI, "r") as f:
            return json.load(f)
    return None

def drop_config_speichern(config):
    with open(DROP_DATEI, "w") as f:
        json.dump(config, f)

def drop_code_generieren() -> str:
    """Erstellt einen zufälligen 4-stelligen Code, z.B. '0472'."""
    return f"{random.randint(0, 9999):04d}"

# --- Speicherort für alle Giveaways (laufend + beendet) ---
GIVEAWAY_DATEI = "giveaway_config.json"

def giveaways_laden():
    if os.path.exists(GIVEAWAY_DATEI):
        with open(GIVEAWAY_DATEI, "r") as f:
            return json.load(f)
    return {}

def giveaways_speichern(giveaways):
    with open(GIVEAWAY_DATEI, "w") as f:
        json.dump(giveaways, f)

# --- Speicherort für alle laufenden Timer ---
TIMER_DATEI = "timer_config.json"

def timer_laden():
    if os.path.exists(TIMER_DATEI):
        with open(TIMER_DATEI, "r") as f:
            return json.load(f)
    return {}

def timer_speichern(timers):
    with open(TIMER_DATEI, "w") as f:
        json.dump(timers, f)

def zeit_aufteilen(sekunden: int):
    """Wandelt eine Sekundenzahl in (Tage, Stunden, Minuten, Sekunden) um."""
    sekunden = max(int(sekunden), 0)
    tage, rest = divmod(sekunden, 86400)
    stunden, rest = divmod(rest, 3600)
    minuten, sek = divmod(rest, 60)
    return tage, stunden, minuten, sek

def timer_embed_bauen(daten: dict, rest_sekunden: int, abgelaufen: bool = False) -> discord.Embed:
    """Baut das Countdown-Embed für einen Timer."""
    tage, stunden, minuten, sek = zeit_aufteilen(rest_sekunden)

    if abgelaufen:
        embed = discord.Embed(
            title="⏰ Timer abgelaufen!",
            description=f"**{daten['grund']}**",
            color=discord.Color.red()
        )
        embed.add_field(name="Status", value="✅ Die Zeit ist um!", inline=False)
    else:
        embed = discord.Embed(
            title="⏳ Timer läuft",
            description=f"**{daten['grund']}**",
            color=discord.Color.orange()
        )
        embed.add_field(name="📅 Tage", value=f"```{tage}```", inline=True)
        embed.add_field(name="🕐 Stunden", value=f"```{stunden}```", inline=True)
        embed.add_field(name="⏱️ Minuten", value=f"```{minuten}```", inline=True)
        embed.add_field(name="⏲️ Sekunden", value=f"```{sek}```", inline=True)
        embed.add_field(
            name="🔔 Endet",
            value=f"<t:{daten['ende_timestamp']}:f> (<t:{daten['ende_timestamp']}:R>)",
            inline=False
        )

    embed.set_footer(text=f"Gestartet von {daten.get('ersteller_name', 'Unbekannt')}")
    return embed

# --- Merkt sich laufende Timer-Tasks, damit sie z.B. per /timerstop abgebrochen werden können ---
timer_tasks: dict[str, asyncio.Task] = {}

async def timer_loop(timer_id: str):
    """Läuft im Hintergrund, aktualisiert alle 5 Sekunden das Countdown-Embed bis der Timer abläuft."""
    try:
        while True:
            timers = timer_laden()
            daten = timers.get(timer_id)
            if daten is None or daten.get("beendet"):
                return

            guild = bot.get_guild(int(daten["guild_id"]))
            channel = guild.get_channel(int(daten["channel_id"])) if guild else None

            jetzt = datetime.datetime.now(datetime.timezone.utc).timestamp()
            rest_sekunden = daten["ende_timestamp"] - jetzt

            if channel is not None:
                try:
                    nachricht = await channel.fetch_message(int(daten["message_id"]))
                    if rest_sekunden <= 0:
                        await nachricht.edit(embed=timer_embed_bauen(daten, 0, abgelaufen=True))
                    else:
                        await nachricht.edit(embed=timer_embed_bauen(daten, rest_sekunden))
                except (discord.NotFound, discord.HTTPException):
                    pass

            if rest_sekunden <= 0:
                if channel is not None:
                    try:
                        await channel.send(
                            f"⏰ <@{daten['ersteller_id']}> Dein Timer ist abgelaufen: **{daten['grund']}**"
                        )
                    except discord.HTTPException:
                        pass

                daten["beendet"] = True
                timers[timer_id] = daten
                timer_speichern(timers)
                return

            await asyncio.sleep(5)
    finally:
        timer_tasks.pop(timer_id, None)

def timer_starten(timer_id: str):
    """Startet den Hintergrund-Task für einen Timer (bricht einen evtl. bereits laufenden Task nicht doppelt)."""
    if timer_id in timer_tasks:
        return
    task = bot.loop.create_task(timer_loop(timer_id))
    timer_tasks[timer_id] = task

def dauer_parsen(dauer_text: str) -> int:
    """Wandelt z.B. '30m', '2h', '1d' in Sekunden um."""
    einheiten = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    dauer_text = dauer_text.strip().lower()
    if len(dauer_text) < 2 or dauer_text[-1] not in einheiten:
        raise ValueError("Ungültiges Zeitformat")
    zahl = int(dauer_text[:-1])
    if zahl <= 0:
        raise ValueError("Zahl muss größer als 0 sein")
    return zahl * einheiten[dauer_text[-1]]

# =========================================================================
# ================================ TICKETS ================================
# =========================================================================

# --- Speicherort für die per /newticketsystem eingerichtete Konfiguration ---
TICKET_SETUP_DATEI = "ticket_setup.json"

def ticket_setup_laden():
    if os.path.exists(TICKET_SETUP_DATEI):
        with open(TICKET_SETUP_DATEI, "r") as f:
            return json.load(f)
    return None

def ticket_setup_speichern(config):
    with open(TICKET_SETUP_DATEI, "w") as f:
        json.dump(config, f)

# --- Speicherort für alle offenen/geschlossenen Ticket-Channels ---
TICKET_DATEI = "ticket_tickets.json"

def tickets_laden():
    if os.path.exists(TICKET_DATEI):
        with open(TICKET_DATEI, "r") as f:
            return json.load(f)
    return {}

def tickets_speichern(tickets):
    with open(TICKET_DATEI, "w") as f:
        json.dump(tickets, f)

def ticket_zaehler_erhoehen():
    """Fortlaufende Nummer für Ticket-Channel-Namen, z.B. ticket-0007."""
    setup = ticket_setup_laden() or {}
    zaehler = setup.get("zaehler", 0) + 1
    setup["zaehler"] = zaehler
    ticket_setup_speichern(setup)
    return zaehler

# --- Panel mit den 4 auswählbaren Knöpfen ("Support" / "Report" / usw.) ---
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Buttons funktionieren dauerhaft, auch nach Neustart
        setup = ticket_setup_laden()
        knoepfe = setup.get("knoepfe", []) if setup else []
        for i, label in enumerate(knoepfe):
            self.add_item(TicketOpenButton(i, label))

class TicketOpenButton(discord.ui.Button):
    def __init__(self, index: int, label: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_open_{index}",  # muss eindeutig + dauerhaft sein
            emoji="🎫"
        )
        self.index = index
        self.button_label = label

    async def callback(self, interaction: discord.Interaction):
        await ticket_erstellen(interaction, self.button_label)

async def ticket_erstellen(interaction: discord.Interaction, ticket_typ: str):
    """Erstellt einen neuen privaten Ticket-Channel für den User, der den Knopf gedrückt hat."""
    setup = ticket_setup_laden()
    if setup is None:
        await interaction.response.send_message(
            "⚠️ Es wurde noch kein Ticket-System eingerichtet. Ein Admin muss zuerst `/newticketsystem` ausführen.",
            ephemeral=True
        )
        return

    kategorie = interaction.guild.get_channel(int(setup["kategorie_id"]))
    if kategorie is None:
        await interaction.response.send_message(
            "⚠️ Die eingerichtete Kategorie existiert nicht mehr.",
            ephemeral=True
        )
        return

    mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"]))

    # --- Verhindern, dass ein User mehrere offene Tickets gleichzeitig hat ---
    alle_tickets = tickets_laden()
    for ch_id, daten in alle_tickets.items():
        if daten["opener_id"] == str(interaction.user.id) and not daten.get("geschlossen"):
            channel_vorhanden = interaction.guild.get_channel(int(ch_id))
            if channel_vorhanden is not None:
                await interaction.response.send_message(
                    f"⚠️ Du hast bereits ein offenes Ticket: {channel_vorhanden.mention}",
                    ephemeral=True
                )
                return

    # --- Berechtigungen für den neuen Ticket-Channel ---
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
            topic=f"Ticket von {interaction.user.id} | Typ: {ticket_typ}"
        )
    except discord.HTTPException:
        await interaction.response.send_message(
            "⚠️ Der Ticket-Channel konnte nicht erstellt werden. Habe ich die nötigen Rechte?",
            ephemeral=True
        )
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
            f"Hallo {interaction.user.mention}! Ein Team-Mitglied kümmert sich gleich um dich.\n"
            f"Beschreib dein Anliegen einfach hier im Chat.\n\n"
            f"🙋 **Übernehmen** – ein Team-Mitglied holt sich das Ticket in den privaten Bereich.\n"
            f"🔒 **Schließen** – schließt das Ticket, du bekommst den ganzen Chat per DM."
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Geöffnet von {interaction.user}")

    ping_text = mod_rolle.mention if mod_rolle else ""
    await neuer_channel.send(content=f"{interaction.user.mention} {ping_text}", embed=embed, view=TicketActionView())

    await interaction.response.send_message(
        f"✅ Dein Ticket wurde erstellt: {neuer_channel.mention}",
        ephemeral=True
    )

# --- Auswahlmenü, das erscheint, wenn 'Übergeben' gedrückt wird ---
class TicketTransferSelectView(discord.ui.View):
    """Nur Leute mit der Ticket-Mod-Rolle sind gültige Ziele für die Übergabe."""
    def __init__(self, mod_rolle_id: int):
        super().__init__(timeout=60)
        self.mod_rolle_id = mod_rolle_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Wähle ein Team-Mitglied aus")
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        ziel_user = select.values[0]
        mod_rolle = interaction.guild.get_role(self.mod_rolle_id)

        if mod_rolle is None or mod_rolle not in getattr(ziel_user, "roles", []):
            await interaction.response.send_message(
                "⚠️ Diese Person hat nicht die Ticket-Mod-Rolle.",
                ephemeral=True
            )
            return

        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))
        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ Dieses Ticket existiert nicht mehr.", ephemeral=True)
            return

        alter_claimer_id = daten.get("beansprucht_von")

        # --- alten Übernehmer die Sicht entziehen, neuen freischalten ---
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

        await interaction.response.edit_message(content=f"✅ Ticket an {ziel_user.mention} übergeben.", view=None)
        await interaction.channel.send(f"🔁 Ticket wurde an {ziel_user.mention} übergeben.")

# --- Buttons, die in jedem einzelnen Ticket-Channel angezeigt werden ---
class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Buttons funktionieren dauerhaft, auch nach Neustart

    @discord.ui.button(label="Übernehmen", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ Dieses Ticket existiert nicht mehr.", ephemeral=True)
            return

        mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"])) if setup else None
        ist_admin = interaction.user.guild_permissions.administrator
        ist_mod = mod_rolle is not None and mod_rolle in interaction.user.roles
        if not (ist_mod or ist_admin):
            await interaction.response.send_message(
                "❌ Nur Personen mit der Ticket-Mod-Rolle können Tickets übernehmen.",
                ephemeral=True
            )
            return

        if daten.get("beansprucht_von"):
            beanspruchendes_mitglied = interaction.guild.get_member(int(daten["beansprucht_von"]))
            name = beanspruchendes_mitglied.mention if beanspruchendes_mitglied else "jemand anderem"
            await interaction.response.send_message(f"⚠️ Dieses Ticket wird bereits von {name} bearbeitet.", ephemeral=True)
            return

        # --- Ticket in den privaten Bereich des Übernehmers ziehen ---
        if mod_rolle is not None:
            await interaction.channel.set_permissions(mod_rolle, view_channel=False)
        await interaction.channel.set_permissions(
            interaction.user, view_channel=True, send_messages=True, read_message_history=True
        )

        daten["beansprucht_von"] = str(interaction.user.id)
        tickets[str(interaction.channel.id)] = daten
        tickets_speichern(tickets)

        embed = discord.Embed(
            description=f"🙋 {interaction.user.mention} hat dieses Ticket übernommen. Nur du und {interaction.user.mention} sehen den Chat jetzt noch.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Übergeben", style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="ticket_transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ Dieses Ticket existiert nicht mehr.", ephemeral=True)
            return

        if not daten.get("beansprucht_von"):
            await interaction.response.send_message(
                "⚠️ Das Ticket wurde noch von niemandem übernommen. Drück zuerst auf 'Übernehmen'.",
                ephemeral=True
            )
            return

        ist_admin = interaction.user.guild_permissions.administrator
        ist_aktueller_claimer = str(interaction.user.id) == daten["beansprucht_von"]
        if not (ist_aktueller_claimer or ist_admin):
            await interaction.response.send_message(
                "❌ Nur die Person, die das Ticket übernommen hat, kann es übergeben.",
                ephemeral=True
            )
            return

        if setup is None:
            await interaction.response.send_message("⚠️ Ticket-System ist nicht eingerichtet.", ephemeral=True)
            return

        view = TicketTransferSelectView(int(setup["mod_rolle_id"]))
        await interaction.response.send_message(
            "Wähle die Person aus, an die das Ticket übergeben werden soll:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = ticket_setup_laden()
        tickets = tickets_laden()
        daten = tickets.get(str(interaction.channel.id))

        if daten is None or daten.get("geschlossen"):
            await interaction.response.send_message("⚠️ Dieses Ticket existiert nicht mehr.", ephemeral=True)
            return

        mod_rolle = interaction.guild.get_role(int(setup["mod_rolle_id"])) if setup else None
        ist_admin = interaction.user.guild_permissions.administrator
        ist_mod = mod_rolle is not None and mod_rolle in interaction.user.roles
        ist_opener = str(interaction.user.id) == daten["opener_id"]
        ist_claimer = str(interaction.user.id) == (daten.get("beansprucht_von") or "")

        if not (ist_admin or ist_mod or ist_opener or ist_claimer):
            await interaction.response.send_message("❌ Du darfst dieses Ticket nicht schließen.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Ticket wird geschlossen und der Chat wird verschickt...")

        # --- Ganzen Chatverlauf als Textdatei sammeln ---
        zeilen = []
        async for nachricht in interaction.channel.history(limit=None, oldest_first=True):
            zeit = nachricht.created_at.strftime("%d.%m.%Y %H:%M")
            inhalt = nachricht.content or "[kein Text / Anhang oder Embed]"
            zeilen.append(f"[{zeit}] {nachricht.author}: {inhalt}")
        transcript_text = "\n".join(zeilen) if zeilen else "(Keine Nachrichten)"

        dateiname = f"transcript-{interaction.channel.name}.txt"
        with open(dateiname, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        # --- Transcript per DM an den Ersteller des Tickets schicken ---
        guild = interaction.guild
        opener = guild.get_member(int(daten["opener_id"]))
        if opener is not None:
            try:
                dm_embed = discord.Embed(
                    title="🔒 Dein Ticket wurde geschlossen",
                    description=f"Anbei der komplette Chatverlauf deines Tickets **{daten['typ']}**.",
                    color=discord.Color.dark_grey()
                )
                await opener.send(embed=dm_embed, file=discord.File(dateiname))
            except discord.HTTPException:
                pass  # z.B. wenn der User DMs deaktiviert hat

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
# =========================== ENDE TICKET-SYSTEM ==========================
# =========================================================================

# =========================================================================
# ================================ APPLY ===================================
# =========================================================================

# --- Speicherort für die per /apply-setup eingerichtete Konfiguration ---
APPLY_SETUP_DATEI = "apply_setup.json"

def apply_setup_laden():
    if os.path.exists(APPLY_SETUP_DATEI):
        with open(APPLY_SETUP_DATEI, "r") as f:
            return json.load(f)
    return None

def apply_setup_speichern(config):
    with open(APPLY_SETUP_DATEI, "w") as f:
        json.dump(config, f)

# --- Speicherort für alle eingereichten Bewerbungen ---
APPLY_DATEI = "apply_bewerbungen.json"

def bewerbungen_laden():
    if os.path.exists(APPLY_DATEI):
        with open(APPLY_DATEI, "r") as f:
            return json.load(f)
    return {}

def bewerbungen_speichern(bewerbungen):
    with open(APPLY_DATEI, "w") as f:
        json.dump(bewerbungen, f)

def apply_zaehler_erhoehen():
    """Fortlaufende ID für jede neue Bewerbung."""
    setup = apply_setup_laden() or {}
    zaehler = setup.get("zaehler", 0) + 1
    setup["zaehler"] = zaehler
    apply_setup_speichern(setup)
    return zaehler

MAX_APPLY_FRAGEN = 20

# --- Panel mit dem "Apply starten"-Knopf ---
class ApplyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Button funktioniert dauerhaft, auch nach Neustart

    @discord.ui.button(label="Apply starten", style=discord.ButtonStyle.success, emoji="📋", custom_id="apply_start")
    async def apply_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup = apply_setup_laden()
        if setup is None or not setup.get("fragen"):
            await interaction.response.send_message(
                "⚠️ Es sind noch keine Fragen eingerichtet. Ein Admin muss zuerst `/apply-frage-hinzufuegen` nutzen.",
                ephemeral=True
            )
            return

        # --- Verhindern, dass jemand mehrere offene Bewerbungen gleichzeitig hat ---
        alle_bewerbungen = bewerbungen_laden()
        for b_id, daten in alle_bewerbungen.items():
            if daten["opener_id"] == str(interaction.user.id) and daten.get("status") == "offen":
                await interaction.response.send_message(
                    "⚠️ Du hast bereits eine laufende Bewerbung. Beantworte zuerst die Fragen in deinen DMs.",
                    ephemeral=True
                )
                return

        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(embed=discord.Embed(
                title="📋 Bewerbung gestartet",
                description=(
                    f"Du beantwortest jetzt **{len(setup['fragen'])} Fragen**.\n"
                    f"Schreib deine Antwort einfach hier in den Chat. Du hast pro Frage **10 Minuten** Zeit."
                ),
                color=discord.Color.blurple()
            ))
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ Ich konnte dir keine DM schicken. Bitte aktiviere private Nachrichten von Servermitgliedern und versuch es erneut.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "✅ Ich hab dir eine DM geschickt! Beantworte dort die Fragen.",
            ephemeral=True
        )

        bot.loop.create_task(apply_ablauf_durchfuehren(interaction.user, interaction.guild.id, dm_channel, setup["fragen"]))

async def apply_ablauf_durchfuehren(user: discord.User, guild_id: int, dm_channel: discord.DMChannel, fragen: list[str]):
    """Stellt dem User nacheinander alle Fragen per DM und wartet jeweils auf seine Antwort."""
    def check(nachricht: discord.Message) -> bool:
        return nachricht.author.id == user.id and isinstance(nachricht.channel, discord.DMChannel)

    antworten = []
    for i, frage in enumerate(fragen, start=1):
        await dm_channel.send(embed=discord.Embed(
            title=f"Frage {i}/{len(fragen)}",
            description=frage,
            color=discord.Color.blue()
        ))
        try:
            antwort_nachricht = await bot.wait_for("message", check=check, timeout=600)
        except asyncio.TimeoutError:
            await dm_channel.send(
                "⏰ Zeit abgelaufen. Deine Bewerbung wurde abgebrochen. Du kannst jederzeit über den Button erneut starten."
            )
            return
        antworten.append(antwort_nachricht.content or "[kein Text / nur Anhang]")

    setup = apply_setup_laden()
    if setup is None:
        await dm_channel.send("⚠️ Die Bewerbung konnte nicht gespeichert werden, da das System nicht mehr eingerichtet ist.")
        return

    guild = bot.get_guild(guild_id)
    review_channel = guild.get_channel(int(setup["review_channel_id"])) if guild else None

    bewerbung_id = str(apply_zaehler_erhoehen())
    bewerbungen = bewerbungen_laden()
    bewerbungen[bewerbung_id] = {
        "opener_id": str(user.id),
        "opener_name": str(user),
        "guild_id": str(guild_id),
        "fragen": fragen,
        "antworten": antworten,
        "status": "offen",
        "message_id": None,
        "review_channel_id": setup["review_channel_id"]
    }

    embed = discord.Embed(
        title=f"📋 Neue Bewerbung von {user}",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    for i, (frage, antwort) in enumerate(zip(fragen, antworten), start=1):
        embed.add_field(name=f"{i}. {frage}", value=antwort[:1024], inline=False)
    embed.set_footer(text=f"User-ID: {user.id} | Bewerbung #{bewerbung_id}")

    if review_channel is not None:
        try:
            gesendete_nachricht = await review_channel.send(embed=embed, view=ApplyReviewView(bewerbung_id))
            bewerbungen[bewerbung_id]["message_id"] = str(gesendete_nachricht.id)
        except discord.HTTPException:
            pass

    bewerbungen_speichern(bewerbungen)

    await dm_channel.send(embed=discord.Embed(
        title="✅ Bewerbung eingereicht!",
        description="Danke für deine Antworten. Dein Team wird sich bald bei dir melden.",
        color=discord.Color.green()
    ))

# --- Angenommen/Abgelehnt-Buttons unter jeder Bewerbung im Review-Channel ---
class ApplyReviewView(discord.ui.View):
    def __init__(self, bewerbung_id: str):
        super().__init__(timeout=None)  # timeout=None = Buttons funktionieren dauerhaft, auch nach Neustart
        self.bewerbung_id = bewerbung_id
        self.annehmen.custom_id = f"apply_accept_{bewerbung_id}"
        self.ablehnen.custom_id = f"apply_decline_{bewerbung_id}"

    async def _bewerbung_pruefen(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Nur Admins können Bewerbungen annehmen oder ablehnen.",
                ephemeral=True
            )
            return None

        bewerbungen = bewerbungen_laden()
        daten = bewerbungen.get(self.bewerbung_id)
        if daten is None:
            await interaction.response.send_message("⚠️ Diese Bewerbung wurde nicht gefunden.", ephemeral=True)
            return None
        if daten.get("status") != "offen":
            await interaction.response.send_message("⚠️ Über diese Bewerbung wurde bereits entschieden.", ephemeral=True)
            return None
        return daten

    @discord.ui.button(label="Angenommen", style=discord.ButtonStyle.success, emoji="✅", custom_id="apply_accept_placeholder")
    async def annehmen(self, interaction: discord.Interaction, button: discord.ui.Button):
        daten = await self._bewerbung_pruefen(interaction)
        if daten is None:
            return

        setup = apply_setup_laden()
        rolle = interaction.guild.get_role(int(setup["accept_rolle_id"])) if setup else None
        mitglied = interaction.guild.get_member(int(daten["opener_id"]))

        if rolle is not None and mitglied is not None:
            try:
                await mitglied.add_roles(rolle)
            except discord.HTTPException:
                pass

        bewerbungen = bewerbungen_laden()
        daten["status"] = "angenommen"
        bewerbungen[self.bewerbung_id] = daten
        bewerbungen_speichern(bewerbungen)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value=f"✅ Angenommen von {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

        if mitglied is not None:
            try:
                await mitglied.send(embed=discord.Embed(
                    title="✅ Deine Bewerbung wurde angenommen!",
                    description=f"Herzlichen Glückwunsch! Du hast jetzt die Rolle **{rolle.name if rolle else ''}** erhalten.",
                    color=discord.Color.green()
                ))
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Abgelehnt", style=discord.ButtonStyle.danger, emoji="❌", custom_id="apply_decline_placeholder")
    async def ablehnen(self, interaction: discord.Interaction, button: discord.ui.Button):
        daten = await self._bewerbung_pruefen(interaction)
        if daten is None:
            return

        bewerbungen = bewerbungen_laden()
        daten["status"] = "abgelehnt"
        bewerbungen[self.bewerbung_id] = daten
        bewerbungen_speichern(bewerbungen)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"❌ Abgelehnt von {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

        mitglied = interaction.guild.get_member(int(daten["opener_id"]))
        if mitglied is not None:
            try:
                await mitglied.send(embed=discord.Embed(
                    title="❌ Deine Bewerbung wurde abgelehnt",
                    description="Schade, diesmal hat es nicht geklappt. Du kannst dich in Zukunft gerne erneut bewerben.",
                    color=discord.Color.red()
                ))
            except discord.HTTPException:
                pass

# =========================================================================
# ============================= ENDE APPLY =================================
# =========================================================================

# =========================================================================
# ============================== VIP AUTO ==================================
# =========================================================================

# --- Speicherort für die per /vipauto eingerichtete Konfiguration ---
VIP_CONFIG_DATEI = "vip_config.json"

def vip_config_laden():
    if os.path.exists(VIP_CONFIG_DATEI):
        with open(VIP_CONFIG_DATEI, "r") as f:
            return json.load(f)
    return None

def vip_config_speichern(config):
    with open(VIP_CONFIG_DATEI, "w") as f:
        json.dump(config, f)

# --- Speicherort für alle verknüpften Discord <-> Roblox Accounts ---
VIP_LINKS_DATEI = "vip_links.json"

def vip_links_laden():
    if os.path.exists(VIP_LINKS_DATEI):
        with open(VIP_LINKS_DATEI, "r") as f:
            return json.load(f)
    return {}  # { "discord_id": {"roblox_id": ..., "roblox_name": ...} }

def vip_links_speichern(links):
    with open(VIP_LINKS_DATEI, "w") as f:
        json.dump(links, f)

# --- Speicherort für alle JEMALS verifizierten Roblox-Namen (wird NIE wieder freigegeben) ---
VIP_GESPERRTE_NAMEN_DATEI = "vip_gesperrte_namen.json"

def vip_gesperrte_namen_laden():
    if os.path.exists(VIP_GESPERRTE_NAMEN_DATEI):
        with open(VIP_GESPERRTE_NAMEN_DATEI, "r") as f:
            return json.load(f)
    return {}  # { "roblox_name_lowercase": "discord_id" }

def vip_gesperrte_namen_speichern(namen):
    with open(VIP_GESPERRTE_NAMEN_DATEI, "w") as f:
        json.dump(namen, f)

async def roblox_userid_von_name(username: str):
    """Fragt bei Roblox die User-ID zu einem Benutzernamen ab. Gibt (id, echter_name) oder None zurück."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": True},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                daten = await resp.json()
                ergebnisse = daten.get("data", [])
                if not ergebnisse:
                    return None
                return ergebnisse[0]["id"], ergebnisse[0]["name"]
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None

async def roblox_besitzt_gamepass(user_id: int, gamepass_id: str) -> bool:
    """Prüft, ob ein Roblox-User einen bestimmten Game Pass besitzt."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://inventory.roblox.com/v1/users/{user_id}/items/GamePass/{gamepass_id}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return False
                daten = await resp.json()
                return len(daten.get("data", [])) > 0
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False

async def vip_verfyroblox_ablauf(message: discord.Message):
    """Ablauf für '?VerfyRoblox': User verknüpft seinen Roblox-Namen dauerhaft mit seinem Discord-Account."""
    links = vip_links_laden()
    if str(message.author.id) in links:
        bereits = links[str(message.author.id)]["roblox_name"]
        await message.channel.send(
            f"⚠️ {message.author.mention} Du bist bereits verifiziert als **{bereits}**.",
            delete_after=15
        )
        return

    frage_nachricht = await message.channel.send(
        f"{message.author.mention} Schreib jetzt deinen **Roblox-Benutzernamen** hier in den Chat. Du hast 2 Minuten Zeit."
    )

    def check(m: discord.Message) -> bool:
        return m.author.id == message.author.id and m.channel.id == message.channel.id

    try:
        antwort = await bot.wait_for("message", check=check, timeout=120)
    except asyncio.TimeoutError:
        await message.channel.send(f"⏰ {message.author.mention} Zeit abgelaufen. Schreib erneut `?VerfyRoblox`, um es nochmal zu versuchen.", delete_after=15)
        return

    roblox_name_eingabe = antwort.content.strip()
    ergebnis = await roblox_userid_von_name(roblox_name_eingabe)
    if ergebnis is None:
        await message.channel.send(
            f"❌ {message.author.mention} Dieser Roblox-Name wurde nicht gefunden. Schreib erneut `?VerfyRoblox`, um es nochmal zu versuchen.",
            delete_after=20
        )
        return

    roblox_id, roblox_name_echt = ergebnis
    name_key = roblox_name_echt.lower()

    gesperrte_namen = vip_gesperrte_namen_laden()
    if name_key in gesperrte_namen:
        await message.channel.send(
            f"❌ {message.author.mention} Der Roblox-Name **{roblox_name_echt}** wurde bereits verwendet und kann nicht erneut verknüpft werden.",
            delete_after=20
        )
        return

    # --- Verknüpfung dauerhaft speichern, Name wird für immer gesperrt ---
    links[str(message.author.id)] = {"roblox_id": roblox_id, "roblox_name": roblox_name_echt}
    vip_links_speichern(links)

    gesperrte_namen[name_key] = str(message.author.id)
    vip_gesperrte_namen_speichern(gesperrte_namen)

    await message.channel.send(
        f"✅ {message.author.mention} Erfolgreich verknüpft mit Roblox-Account **{roblox_name_echt}**! "
        f"Dieser Name ist jetzt für immer an deinen Discord-Account gebunden."
    )

async def vip_verfy_ablauf(message: discord.Message):
    """Ablauf für '?Verfy': prüft, ob der verknüpfte Roblox-Account den Game Pass besitzt, und vergibt ggf. die Rolle."""
    config = vip_config_laden()
    if config is None or not config.get("gamepass_id"):
        await message.channel.send("⚠️ Das VIP-System wurde noch nicht eingerichtet. Ein Admin muss zuerst `/vipauto` nutzen.", delete_after=15)
        return

    links = vip_links_laden()
    link = links.get(str(message.author.id))
    if link is None:
        await message.channel.send(
            f"⚠️ {message.author.mention} Du musst dich zuerst mit `?VerfyRoblox` im Verify-Channel verknüpfen.",
            delete_after=15
        )
        return

    warte_nachricht = await message.channel.send(f"⏳ Prüfe, ob **{link['roblox_name']}** den Game Pass besitzt...")

    besitzt = await roblox_besitzt_gamepass(link["roblox_id"], config["gamepass_id"])

    if not besitzt:
        await warte_nachricht.edit(
            content=f"❌ {message.author.mention} **{link['roblox_name']}** besitzt den Game Pass noch nicht. Kauf ihn und versuch es erneut mit `?Verfy`."
        )
        return

    rolle = message.guild.get_role(int(config["rolle_id"]))
    if rolle is None:
        await warte_nachricht.edit(content="⚠️ Die eingerichtete Rolle existiert nicht mehr. Bitte einen Admin kontaktieren.")
        return

    try:
        await message.author.add_roles(rolle)
    except discord.HTTPException:
        await warte_nachricht.edit(content="⚠️ Ich konnte dir die Rolle nicht geben. Habe ich genug Rechte?")
        return

    await warte_nachricht.edit(
        content=f"✅ {message.author.mention} Bestätigt! **{link['roblox_name']}** besitzt den Game Pass. Du hast jetzt die Rolle **{rolle.name}**!"
    )

# =========================================================================
# ============================ ENDE VIP AUTO ================================
# =========================================================================

# =========================================================================
# ========================= KI SCRIPT GENERATOR ============================
# =========================================================================

# --- Speicherort für den per /creatki eingerichteten KI-Channel ---
KI_CONFIG_DATEI = "ki_config.json"

def ki_config_laden():
    if os.path.exists(KI_CONFIG_DATEI):
        with open(KI_CONFIG_DATEI, "r") as f:
            return json.load(f)
    return None

def ki_config_speichern(config):
    with open(KI_CONFIG_DATEI, "w") as f:
        json.dump(config, f)

# --- Speicherort für die Nutzung pro Spieler (Anzahl Scripts + Cooldown) ---
KI_USAGE_DATEI = "ki_usage.json"

def ki_usage_laden():
    if os.path.exists(KI_USAGE_DATEI):
        with open(KI_USAGE_DATEI, "r") as f:
            return json.load(f)
    return {}

def ki_usage_speichern(usage):
    with open(KI_USAGE_DATEI, "w") as f:
        json.dump(usage, f)

KI_FREI_LIMIT = 10                   # so viele Scripts darf ein Nicht-VIP machen...
KI_COOLDOWN_SEKUNDEN = 2 * 60 * 60    # ...bevor er 2 Stunden warten muss

# --- Pollinations.ai: kostenloser Text-KI-Anbieter, funktioniert OHNE bezahlten API-Key.
#     Optional kann man sich auf https://enter.pollinations.ai einen KOSTENLOSEN Key holen (kein Guthaben,
#     keine Kreditkarte nötig) - macht die Antworten nur zuverlässiger/schneller. Ohne Key läuft es trotzdem.
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")  # optional, darf leer bleiben
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "openai")  # z.B. "openai", "qwen-coder", "mistral"

def ki_ist_vip(member: discord.Member) -> bool:
    """Prüft, ob ein Mitglied die VIP-Rolle aus /vipauto besitzt (dann unbegrenzte KI-Nutzung)."""
    vip_config = vip_config_laden()
    if vip_config is None or not vip_config.get("rolle_id"):
        return False
    rolle = member.guild.get_role(int(vip_config["rolle_id"]))
    return rolle is not None and rolle in member.roles

async def ki_script_generieren(beschreibung: str) -> str:
    """Nutzt die kostenlose Pollinations-Text-API, um einen Roblox-Studio-Lua-Script zu erstellen."""
    system_prompt = (
        "You are an expert Roblox Studio scripting assistant. The user will describe what they want "
        "a Roblox Studio Lua script to do. Respond with ONLY a single, complete, working Lua script "
        "wrapped in a ```lua code block, using correct Roblox APIs (game:GetService, Instance.new, "
        "CollectionService, RemoteEvents where sensible, etc). Add short inline comments explaining key "
        "steps. Mention briefly at the very end (outside the code block, one line) whether it's a "
        "Script/LocalScript and where it should be placed. Do not add any other explanation."
    )
    payload = {
        "model": POLLINATIONS_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": beschreibung}
        ]
    }
    headers = {"content-type": "application/json"}
    if POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://text.pollinations.ai/openai",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                fehler_text = await resp.text()
                raise RuntimeError(f"KI-Anbieter Fehler {resp.status}: {fehler_text[:200]}")
            daten = await resp.json()
            try:
                return daten["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError):
                raise RuntimeError("Unerwartetes Antwortformat vom KI-Anbieter.")

async def ki_ablauf(message: discord.Message, beschreibung: str):
    """Ablauf für '?ki <Beschreibung>': generiert per KI einen Roblox-Studio-Script und postet ihn."""
    if not beschreibung:
        await message.channel.send(
            f"⚠️ {message.author.mention} Bitte beschreibe, was der Script machen soll. "
            f"Beispiel: `?ki mach ein part unsichtbar wenn man es anklickt`",
            delete_after=15
        )
        return

    user_id = str(message.author.id)
    ist_vip = ki_ist_vip(message.author)

    usage = ki_usage_laden()
    eintrag = usage.get(user_id, {"anzahl": 0, "cooldown_bis": None})

    jetzt = datetime.datetime.now(datetime.timezone.utc).timestamp()

    if not ist_vip:
        # --- Cooldown abgelaufen? Dann zurücksetzen, Spieler bekommt wieder 10 freie Scripts ---
        if eintrag.get("cooldown_bis") and jetzt >= eintrag["cooldown_bis"]:
            eintrag = {"anzahl": 0, "cooldown_bis": None}

        # --- Noch im Cooldown? -> Englische Nachricht, wie gewünscht ---
        if eintrag.get("cooldown_bis") and jetzt < eintrag["cooldown_bis"]:
            rest = int(eintrag["cooldown_bis"] - jetzt)
            stunden, rest_sek = divmod(rest, 3600)
            minuten, _ = divmod(rest_sek, 60)
            await message.channel.send(
                f"⏰ {message.author.mention} You have a timer of **{stunden}h {minuten}m** before you can "
                f"use the KI again, or get **VIP** for unlimited access!"
            )
            return

        # --- Limit erreicht -> Cooldown starten ---
        if eintrag["anzahl"] >= KI_FREI_LIMIT:
            eintrag["cooldown_bis"] = jetzt + KI_COOLDOWN_SEKUNDEN
            usage[user_id] = eintrag
            ki_usage_speichern(usage)
            await message.channel.send(
                f"⏰ {message.author.mention} You have used all **{KI_FREI_LIMIT}** free scripts. "
                f"You now have a timer of **2 hours** before you can use the KI again, or get **VIP** "
                f"for unlimited access!"
            )
            return

    warte_nachricht = await message.channel.send(
        f"🤖 {message.author.mention} Generiere deinen Script, bitte kurz warten..."
    )

    try:
        script_text = await ki_script_generieren(beschreibung)
    except Exception as e:
        await warte_nachricht.edit(
            content=f"❌ {message.author.mention} Bei der KI-Generierung ist ein Fehler aufgetreten: `{e}`"
        )
        return

    if not script_text:
        await warte_nachricht.edit(
            content=f"❌ {message.author.mention} Die KI hat keinen Script zurückgegeben. Versuch es erneut."
        )
        return

    # --- Nutzung hochzählen (nur für Nicht-VIP) ---
    if not ist_vip:
        eintrag["anzahl"] = eintrag.get("anzahl", 0) + 1
        usage[user_id] = eintrag
        ki_usage_speichern(usage)
        rest_scripts = KI_FREI_LIMIT - eintrag["anzahl"]
        status_text = (
            f"✅ Noch **{rest_scripts}/{KI_FREI_LIMIT}** kostenlose Scripts übrig."
            if rest_scripts > 0 else
            "⚠️ Das war dein letzter kostenloser Script für die nächsten 2 Stunden."
        )
    else:
        status_text = "👑 VIP – unbegrenzte Nutzung."

    header = f"🤖 {message.author.mention} Hier ist dein Roblox Studio Script:\n{status_text}\n"
    await warte_nachricht.delete()

    # --- Discord-Nachrichten sind auf 2000 Zeichen begrenzt -> ggf. aufteilen ---
    if len(script_text) <= 1900:
        await message.channel.send(f"{header}{script_text}")
    else:
        await message.channel.send(header)
        for i in range(0, len(script_text), 1900):
            chunk = script_text[i:i + 1900]
            await message.channel.send(chunk)

# =========================================================================
# ====================== ENDE KI SCRIPT GENERATOR ==========================
# =========================================================================

# =========================================================================
# ============================== AUTOMOD ====================================
# =========================================================================

# --- Erkennt Discord-Einladungslinks (discord.gg/..., discord.com/invite/..., usw.) ---
DISCORD_INVITE_REGEX = re.compile(r"(discord\.gg/|discord(?:app)?\.com/invite/)\S+", re.IGNORECASE)

# --- Merkt sich die letzten Nachrichten-Zeitpunkte pro User, um Spam zu erkennen ---
spam_tracker: dict[int, list[float]] = {}
SPAM_NACHRICHTEN_ANZAHL = 5   # ab wie vielen Nachrichten...
SPAM_ZEITFENSTER = 5          # ...innerhalb von wie vielen Sekunden gilt es als Spam

async def automod_timeout(message: discord.Message, dauer: datetime.timedelta, grund: str):
    """Verhängt ein Timeout und informiert den User im Channel."""
    try:
        await message.author.timeout(dauer, reason=grund)
        await message.channel.send(
            f"🔇 {message.author.mention} wurde für **{grund}** getimeoutet.",
            delete_after=10
        )
    except discord.HTTPException:
        pass

async def automod_pruefen(message: discord.Message) -> bool:
    """Prüft eine Nachricht auf Automod-Verstöße. Gibt True zurück, wenn eine Aktion ausgeführt wurde."""
    if message.author.bot or message.guild is None:
        return False

    # --- Admins/Owner werden von der Automod nicht erfasst ---
    if message.author.guild_permissions.administrator:
        return False

    # --- 1) Discord-Invite-Link erkannt -> 2 Stunden Timeout ---
    if DISCORD_INVITE_REGEX.search(message.content):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await automod_timeout(message, datetime.timedelta(hours=2), "Posten eines Discord-Invite-Links")
        return True

    # --- 2) Spam-Erkennung -> 5 Minuten Timeout ---
    jetzt = datetime.datetime.now(datetime.timezone.utc).timestamp()
    zeitstempel = spam_tracker.get(message.author.id, [])
    zeitstempel = [t for t in zeitstempel if jetzt - t < SPAM_ZEITFENSTER]  # alte Einträge rauswerfen
    zeitstempel.append(jetzt)
    spam_tracker[message.author.id] = zeitstempel

    if len(zeitstempel) >= SPAM_NACHRICHTEN_ANZAHL:
        spam_tracker[message.author.id] = []  # zurücksetzen, damit nicht sofort nochmal ausgelöst wird
        await automod_timeout(message, datetime.timedelta(minutes=5), "Spammen")
        return True

    return False

# =========================================================================
# ============================= ENDE AUTOMOD =================================
# =========================================================================

# --- Einstellungen ---
TOKEN = os.getenv("TOKEN")  # Token kommt aus Umgebungsvariable (z.B. bei Railway eingetragen)
PREFIX = "!"  # Befehle starten z.B. mit !hallo

# --- Bot erstellen ---
intents = discord.Intents.default()
intents.message_content = True  # wichtig, damit der Bot Nachrichten lesen kann
intents.voice_states = True  # wichtig, damit der Bot Nutzer in Voice-Channels verschieben kann
intents.members = True  # wichtig für Rollen-Verwaltung

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# --- Self-Role Button-Logik ---
class RollenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Buttons funktionieren dauerhaft, auch nach Neustart
        for rolle_info in rollen_laden():
            self.add_item(RollenButton(rolle_info))

class RollenButton(discord.ui.Button):
    def __init__(self, rolle_info):
        super().__init__(
            label=rolle_info["name"],
            emoji=rolle_info.get("emoji") or None,
            style=discord.ButtonStyle.secondary,
            custom_id=f"rolle_{rolle_info['id']}"  # wichtig: muss eindeutig + dauerhaft sein
        )
        self.rollen_id = int(rolle_info["id"])

    async def callback(self, interaction: discord.Interaction):
        rolle = interaction.guild.get_role(self.rollen_id)

        if rolle is None:
            await interaction.response.send_message(
                "⚠️ Diese Rolle existiert nicht mehr auf dem Server.",
                ephemeral=True
            )
            return

        if rolle in interaction.user.roles:
            await interaction.user.remove_roles(rolle)
            await interaction.response.send_message(f"❌ Rolle **{rolle.name}** entfernt.", ephemeral=True)
        else:
            await interaction.user.add_roles(rolle)
            await interaction.response.send_message(f"✅ Rolle **{rolle.name}** hinzugefügt!", ephemeral=True)

# --- Auswahlmenü für /rollen-setup ---
class RollenSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Wähle bis zu 6 Rollen aus",
        min_values=1,
        max_values=6
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        rollen_liste = [{"id": str(r.id), "name": r.name, "emoji": None} for r in select.values]
        rollen_speichern(rollen_liste)
        namen = ", ".join(r.name for r in select.values)
        await interaction.response.send_message(
            f"✅ Gespeichert! Diese Rollen werden jetzt bei `/rollen` angezeigt: **{namen}**\n"
            f"Nutze jetzt `/rollen`, um die Buttons zu posten.",
            ephemeral=True
        )

# --- "Create a Voice" Button-Logik ---
class VoiceCreatorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Button funktioniert dauerhaft, auch nach Neustart

    @discord.ui.button(label="Create", style=discord.ButtonStyle.primary, emoji="🎙️", custom_id="create_voice_channel")
    async def create_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        kategorie_id = voice_kategorie_laden()
        if kategorie_id is None:
            await interaction.response.send_message(
                "⚠️ Es wurde noch keine Kategorie eingerichtet. Ein Admin muss zuerst `/voice-setup` ausführen.",
                ephemeral=True
            )
            return

        kategorie = interaction.guild.get_channel(int(kategorie_id))
        if kategorie is None:
            await interaction.response.send_message(
                "⚠️ Die eingerichtete Kategorie existiert nicht mehr.",
                ephemeral=True
            )
            return

        # --- Neuen Voice-Channel erstellen, benannt nach dem User ---
        neuer_channel = await interaction.guild.create_voice_channel(
            name=f"{interaction.user.display_name}'s Channel",
            category=kategorie
        )

        # --- Falls der User schon in einem Voice-Channel ist, direkt reinschieben ---
        if interaction.user.voice:
            await interaction.user.move_to(neuer_channel)
            await interaction.response.send_message(
                f"✅ Dein Voice-Channel {neuer_channel.mention} wurde erstellt, du wurdest direkt reinverschoben!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Dein Voice-Channel {neuer_channel.mention} wurde erstellt! Tritt ihm manuell bei.",
                ephemeral=True
            )

# --- Giveaway Button-Logik ("Teilnehmen") ---
class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: str, teilnehmer_anzahl: int = 0):
        super().__init__(timeout=None)  # timeout=None = Button funktioniert dauerhaft, auch nach Neustart
        self.giveaway_id = giveaway_id
        # eindeutige custom_id pro Giveaway, damit mehrere gleichzeitig laufen können
        self.teilnehmen.custom_id = f"giveaway_join_{giveaway_id}"
        self.teilnehmen.label = f"Teilnehmen ({teilnehmer_anzahl})"

    @discord.ui.button(label="Teilnehmen (0)", style=discord.ButtonStyle.success, emoji="🎉")
    async def teilnehmen(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaways = giveaways_laden()
        daten = giveaways.get(self.giveaway_id)

        if daten is None or daten.get("beendet"):
            await interaction.response.send_message("⚠️ Dieses Giveaway ist bereits beendet.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if user_id in daten["teilnehmer"]:
            daten["teilnehmer"].remove(user_id)
            nachricht_text = "❌ Du hast das Giveaway verlassen."
        else:
            daten["teilnehmer"].append(user_id)
            nachricht_text = "✅ Du nimmst jetzt am Giveaway teil! Viel Glück! 🍀"

        giveaways[self.giveaway_id] = daten
        giveaways_speichern(giveaways)

        button.label = f"Teilnehmen ({len(daten['teilnehmer'])})"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(nachricht_text, ephemeral=True)

async def giveaway_beenden(giveaway_id: str, warte_sekunden: float):
    """Wartet bis zum Ende des Giveaways und lost dann automatisch einen Gewinner aus."""
    if warte_sekunden > 0:
        await asyncio.sleep(warte_sekunden)

    giveaways = giveaways_laden()
    daten = giveaways.get(giveaway_id)
    if daten is None or daten.get("beendet"):
        return

    guild = bot.get_guild(int(daten["guild_id"]))
    channel = guild.get_channel(int(daten["channel_id"])) if guild else None

    nachricht = None
    if channel is not None:
        try:
            nachricht = await channel.fetch_message(int(daten["message_id"]))
        except (discord.NotFound, discord.HTTPException):
            nachricht = None

    teilnehmer_ids = daten["teilnehmer"]
    if teilnehmer_ids:
        gewinner_id = random.choice(teilnehmer_ids)
        gewinner_text = f"<@{gewinner_id}>"
    else:
        gewinner_text = "Niemand hat teilgenommen 😢"

    embed = discord.Embed(
        title="🌊🎉 GIVEAWAY BEENDET 🎉🌊",
        description=f"Das Giveaway ist vorbei! Danke an alle, die mitgemacht haben.",
        color=discord.Color.from_rgb(0, 102, 204)
    )
    embed.add_field(name="🏆 Gewinn", value=f"```{daten['preis']}```", inline=False)
    embed.add_field(name="🎊 Gewinner", value=gewinner_text, inline=False)
    embed.add_field(name="👑 Host", value=f"<@{daten['host_id']}>", inline=False)
    embed.set_footer(text=f"Teilnehmer insgesamt: {len(teilnehmer_ids)}")
    if daten.get("bild"):
        embed.set_thumbnail(url=daten["bild"])

    if nachricht is not None:
        try:
            await nachricht.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

    if channel is not None:
        await channel.send(
            f"🎉 Herzlichen Glückwunsch {gewinner_text}! Du hast **{daten['preis']}** gewonnen! 🎉"
        )

    daten["beendet"] = True
    giveaways[giveaway_id] = daten
    giveaways_speichern(giveaways)

# --- Drop-System: postet automatisch & dauerhaft Drops im eingestellten Intervall ---
drop_tasks_gestartet = False  # verhindert, dass die Loops mehrfach gestartet werden

async def drop_loop(tier_key: str):
    """Läuft dauerhaft im Hintergrund: postet sofort einen Drop und danach im festen Intervall."""
    tier = DROP_TIERS[tier_key]

    while True:
        config = drop_config_laden()

        if config is None:
            # Noch kein /drop-setup gemacht -> kurz warten und nochmal prüfen
            await asyncio.sleep(30)
            continue

        channel_id = config.get("channel_id")
        channel = bot.get_channel(int(channel_id)) if channel_id else None

        if channel is not None:
            rolle_id = config.get(f"{tier_key}_rolle_id")
            rolle = channel.guild.get_role(int(rolle_id)) if rolle_id else None
            ping_text = rolle.mention if rolle else ""

            emoji = config.get(f"{tier_key}_emoji") or STANDARD_EMOJIS[tier_key]
            code = drop_code_generieren()

            embed = discord.Embed(
                description=f"**{tier['name']}** is dropping now: **{tier['wins']} wins**!\nCode: `{code}`",
                color=tier["farbe"]
            )
            embed.set_author(name="Drop Announcement")
            embed.add_field(name=emoji, value=f"**{tier['wins']}**", inline=True)

            try:
                gesendete_nachricht = await channel.send(content=ping_text, embed=embed)
                try:
                    await gesendete_nachricht.add_reaction(emoji)
                except discord.HTTPException:
                    pass  # falls das Emoji ungültig ist, wird die Reaction einfach übersprungen
            except discord.HTTPException:
                pass

        # --- Wartezeit bis zum nächsten Drop bestimmen ---
        if tier_key == "secret":
            wartezeit = random.uniform(4 * 3600, 5 * 3600)  # zufällig zwischen 4 und 5 Stunden
        else:
            wartezeit = tier["intervall"]

        await asyncio.sleep(wartezeit)

def drops_starten():
    """Startet die 4 Hintergrund-Loops (Honey, Episch, Mythic, Secret) genau einmal."""
    global drop_tasks_gestartet
    if drop_tasks_gestartet:
        return
    drop_tasks_gestartet = True
    for tier_key in DROP_TIERS:
        bot.loop.create_task(drop_loop(tier_key))

# --- Wird ausgeführt, wenn der Bot online geht ---
@bot.event
async def on_ready():
    print(f"✅ Eingeloggt als {bot.user}")
    bot.add_view(RollenView())  # sorgt dafür, dass die Buttons auch nach Neustart klickbar bleiben
    bot.add_view(VoiceCreatorView())
    bot.add_view(TicketPanelView())  # Ticket-Panel-Knöpfe bleiben nach Neustart klickbar
    bot.add_view(TicketActionView())  # Übernehmen/Übergeben/Schließen bleiben nach Neustart klickbar
    bot.add_view(ApplyPanelView())  # "Apply starten"-Knopf bleibt nach Neustart klickbar

    # --- Offene Bewerbungen nach einem Neustart wiederherstellen, damit die Buttons noch reagieren ---
    bewerbungen = bewerbungen_laden()
    for b_id, daten in bewerbungen.items():
        if daten.get("status") == "offen":
            bot.add_view(ApplyReviewView(b_id))

    # --- Laufende Giveaways nach einem Neustart wiederherstellen ---
    giveaways = giveaways_laden()
    jetzt = datetime.datetime.now(datetime.timezone.utc).timestamp()
    for g_id, daten in giveaways.items():
        if daten.get("beendet"):
            continue
        bot.add_view(GiveawayView(g_id, len(daten["teilnehmer"])))
        rest_sekunden = daten["ende_timestamp"] - jetzt
        bot.loop.create_task(giveaway_beenden(g_id, max(rest_sekunden, 0)))

    # --- Drop-System nach einem Neustart automatisch fortsetzen, falls schon eingerichtet ---
    if drop_config_laden() is not None:
        drops_starten()

    # --- Laufende Timer nach einem Neustart wiederherstellen ---
    timers = timer_laden()
    for t_id, daten in timers.items():
        if daten.get("beendet"):
            continue
        timer_starten(t_id)

    try:
        synced = await bot.tree.sync()
        print(f"🔄 {len(synced)} Slash-Commands synchronisiert")
    except Exception as e:
        print(f"Fehler beim Sync: {e}")

# --- Ein einfacher Befehl: !hallo ---
# --- Zentrale Nachrichtenprüfung: Automod (Invite-Links/Spam) + VIP-Befehle (?VerfyRoblox / ?Verfy) ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # --- Automod zuerst prüfen (löscht ggf. die Nachricht und timeoutet den User) ---
    verstoss = await automod_pruefen(message)
    if verstoss:
        return  # bei einem Verstoß werden keine weiteren Befehle mehr aus dieser Nachricht ausgeführt

    if message.guild is not None:
        config = vip_config_laden()
        inhalt = message.content.strip().lower()

        if config is not None:
            if inhalt == "?verfyroblox" and str(message.channel.id) == config.get("verify_channel_id"):
                await vip_verfyroblox_ablauf(message)
                return

            if inhalt == "?verfy" and str(message.channel.id) == config.get("check_channel_id"):
                await vip_verfy_ablauf(message)
                return

        # --- KI-Script-Generator: nur im per /creatki eingerichteten Channel ---
        ki_config = ki_config_laden()
        if ki_config is not None and str(message.channel.id) == ki_config.get("channel_id"):
            original_inhalt = message.content.strip()

            if original_inhalt.lower().startswith("?ki"):
                beschreibung = original_inhalt[3:].strip()
                await ki_ablauf(message, beschreibung)
                return

            # --- ?Vip: prüft (wie ?Verfy) den Game-Pass-Kauf und vergibt bei Erfolg die VIP-Rolle ---
            if inhalt == "?vip":
                await vip_verfy_ablauf(message)
                return

    # --- Wichtig: sorgt dafür, dass die normalen !Befehle (z.B. !hallo) weiter funktionieren ---
    await bot.process_commands(message)

@bot.command()
async def hallo(ctx):
    await ctx.send(f"Hallo {ctx.author.mention}! 👋")

# --- Noch ein Beispiel: !ping ---
@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

# --- Würfeln: !würfel ---
@bot.command()
async def würfel(ctx):
    zahl = random.randint(1, 6)
    await ctx.send(f"🎲 Du hast eine {zahl} gewürfelt!")

# --- Münze werfen: !münze ---
@bot.command()
async def münze(ctx):
    ergebnis = random.choice(["Kopf", "Zahl"])
    await ctx.send(f"🪙 Es ist **{ergebnis}**!")

# --- Avatar anzeigen: !avatar ---
@bot.command()
async def avatar(ctx):
    await ctx.send(ctx.author.display_avatar.url)

# --- Server-Info: !serverinfo ---
@bot.command()
async def serverinfo(ctx):
    server = ctx.guild
    await ctx.send(f"📊 **{server.name}** hat {server.member_count} Mitglieder.")

# --- Neue Mitglieder automatisch begrüßen ---
@bot.event
async def on_member_join(member):
    kanal = discord.utils.get(member.guild.text_channels, name="willkommen")  # Kanalname anpassen!
    if kanal:
        await kanal.send(f"Willkommen auf dem Server, {member.mention}! 🎉")

# --- /newvideo: Neuer Content-Post (nur für die erlaubte Rolle) ---
@bot.tree.command(name="newvideo", description="Poste einen neuen Video-Link")
@app_commands.describe(link="Der Link zu deinem Video", plattform="Auf welcher Plattform?")
@app_commands.choices(plattform=[
    app_commands.Choice(name="TikTok", value="TikTok"),
    app_commands.Choice(name="YouTube", value="YouTube"),
    app_commands.Choice(name="Instagram", value="Instagram"),
    app_commands.Choice(name="Twitch", value="Twitch"),
])
async def newvideo(interaction: discord.Interaction, link: str, plattform: app_commands.Choice[str]):
    # --- Rollen-Check ---
    rolle = discord.utils.get(interaction.user.roles, name=ERLAUBTE_ROLLE)
    if rolle is None:
        await interaction.response.send_message(
            "❌ Du hast nicht die passende Rolle, um diesen Befehl zu nutzen.",
            ephemeral=True  # nur der User selbst sieht diese Fehlermeldung
        )
        return

    # --- Embed bauen (die "Kachel" mit Bild, Titel usw.) ---
    embed = discord.Embed(
        title=f"🎬 Neuer Content von {interaction.user.display_name}!",
        color=discord.Color.blue()
    )
    embed.add_field(name="Plattform", value=plattform.value, inline=False)
    embed.add_field(name="🔗", value=f"[HIER KLICKEN UM DEN LINK ZU ÖFFNEN]({link})", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)  # Profilbild rechts/oben im Embed
    embed.set_footer(text=f"{plattform.value} Alert")

    # --- Rolle pingen + Embed senden ---
    ping_rolle = discord.utils.get(interaction.guild.roles, name="Ping Content Creator")  # Name ggf. anpassen!
    ping_text = ping_rolle.mention if ping_rolle else ""

    await interaction.response.send_message(content=ping_text, embed=embed)

# --- /rollen-setup: Admin wählt hier die 6 Rollen per Menü aus ---
@bot.tree.command(name="rollen-setup", description="[Admin] Wähle die Rollen für das Self-Role Menü aus")
@app_commands.checks.has_permissions(administrator=True)
async def rollen_setup(interaction: discord.Interaction):
    view = RollenSetupView()
    await interaction.response.send_message(
        "Wähle unten bis zu 6 Rollen aus, die im `/rollen`-Menü erscheinen sollen:",
        view=view,
        ephemeral=True
    )

# --- /rollen: Postet die Nachricht mit den Self-Role Buttons ---
@bot.tree.command(name="rollen", description="Postet die Benachrichtigungs-Rollen zum Anklicken")
async def rollen(interaction: discord.Interaction):
    if not rollen_laden():
        await interaction.response.send_message(
            "⚠️ Es sind noch keine Rollen eingerichtet. Ein Admin muss zuerst `/rollen-setup` ausführen.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🎭 Benachrichtigungs-Rollen",
        description="Wähle hier aus, bei welchen Ereignissen du gepingt werden möchtest.\nKlicke einfach auf die Buttons, um Rollen zu verwalten.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=RollenView())

# --- /voice-setup: Admin wählt Channel + Kategorie für den Voice-Creator aus ---
@bot.tree.command(name="voice-setup", description="[Admin] Richtet den 'Create a Voice' Button ein")
@app_commands.describe(channel="In welchem Channel soll der Button gepostet werden?", kategorie="In welcher Kategorie sollen die Voice-Channels erstellt werden?")
@app_commands.checks.has_permissions(administrator=True)
async def voice_setup(interaction: discord.Interaction, channel: discord.TextChannel, kategorie: discord.CategoryChannel):
    voice_kategorie_speichern(str(kategorie.id))

    embed = discord.Embed(
        title="🎙️ Create a Voice",
        description="Klicke auf den Button, um deinen eigenen Voice-Channel zu erstellen.",
        color=discord.Color.blue()
    )
    await channel.send(embed=embed, view=VoiceCreatorView())

    await interaction.response.send_message(
        f"✅ Eingerichtet! Der Button wurde in {channel.mention} gepostet, neue Channels landen in **{kategorie.name}**.",
        ephemeral=True
    )

# --- /event-setup: Admin trägt einmalig den Roblox-Link + Ziel-Channel ein ---
@bot.tree.command(name="event-setup", description="[Admin] Richtet den Roblox-Spiel-Link für Events ein")
@app_commands.describe(link="Der Link zu deinem Roblox-Spiel", channel="In welchem Channel sollen Events gepostet werden?")
@app_commands.checks.has_permissions(administrator=True)
async def event_setup(interaction: discord.Interaction, link: str, channel: discord.TextChannel):
    event_config_speichern(link, str(channel.id))
    await interaction.response.send_message(
        f"✅ Eingerichtet! Events werden ab jetzt in {channel.mention} gepostet, mit Link zu: {link}",
        ephemeral=True
    )

# --- /event: Postet eine Event-Ankündigung (z.B. "x1 Speed") ---
@bot.tree.command(name="event", description="Kündige ein laufendes Event an (z.B. x1 Speed)")
@app_commands.describe(text="Was ist das Event? (z.B. 'x1 Speed')")
async def event(interaction: discord.Interaction, text: str):
    config = event_config_laden()
    if config is None:
        await interaction.response.send_message(
            "⚠️ Es wurde noch kein Roblox-Link eingerichtet. Ein Admin muss zuerst `/event-setup` ausführen.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(config["channel_id"]))
    if channel is None:
        await interaction.response.send_message("⚠️ Der eingerichtete Channel existiert nicht mehr.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎮 Event läuft gerade!",
        description=f"**{text}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="🔗 Spiel beitreten", value=f"[HIER KLICKEN]({config['link']})", inline=False)
    embed.set_footer(text=f"Gestartet von {interaction.user.display_name}")
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    # --- Falls es eine Rolle "Events" gibt, wird sie automatisch gepingt ---
    events_rolle = discord.utils.get(interaction.guild.roles, name="Events")
    ping_text = events_rolle.mention if events_rolle else ""

    await channel.send(content=ping_text, embed=embed)
    await interaction.response.send_message(f"✅ Event in {channel.mention} gepostet!", ephemeral=True)

# --- /giveaway: Startet ein neues Giveaway im Water-Style ---
@bot.tree.command(name="giveaway", description="[Admin] Starte ein neues Giveaway")
@app_commands.describe(
    preis="Was gibt es zu gewinnen?",
    dauer="Wie lange soll das Giveaway laufen? (z.B. 30m, 2h, 1d)",
    ping_rolle="Rolle, die beim Start gepingt werden soll (optional)",
    bild="Bild-URL, die im Giveaway angezeigt wird (optional)"
)
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(
    interaction: discord.Interaction,
    preis: str,
    dauer: str,
    ping_rolle: discord.Role = None,
    bild: str = None
):
    try:
        sekunden = dauer_parsen(dauer)
    except ValueError:
        await interaction.response.send_message(
            "⚠️ Ungültiges Zeitformat! Nutze z.B. `30m`, `2h` oder `1d`.",
            ephemeral=True
        )
        return

    ende_zeit = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sekunden)
    ende_unix = int(ende_zeit.timestamp())
    giveaway_id = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000))  # eindeutige ID

    # --- Embed im Water/Beach-Style ---
    embed = discord.Embed(
        title="🌊🎁 EPISCHES GIVEAWAY 🎁🌊",
        description="Ein brandneues Event wurde gestartet! Mach mit und sichere dir die Chance auf einen fantastischen Gewinn.",
        color=discord.Color.from_rgb(0, 153, 255)  # Water-Blau
    )
    embed.add_field(name="🏆 Gewinn", value=f"```{preis}```", inline=False)
    embed.add_field(name="👑 Host", value=interaction.user.mention, inline=False)
    embed.add_field(name="⏳ Ende", value=f"<t:{ende_unix}:R> (<t:{ende_unix}:f>)", inline=False)
    embed.add_field(name="👇", value="*Klicke unten auf den Button, um in den Lostopf zu springen!*", inline=False)
    embed.set_footer(text="Viel Glück an alle Teilnehmer!")
    if bild:
        embed.set_thumbnail(url=bild)

    view = GiveawayView(giveaway_id, 0)
    ping_text = ping_rolle.mention if ping_rolle else ""

    await interaction.response.send_message(content=ping_text, embed=embed, view=view)
    gesendete_nachricht = await interaction.original_response()

    # --- Giveaway speichern, damit es auch nach einem Neustart weiterläuft ---
    giveaways = giveaways_laden()
    giveaways[giveaway_id] = {
        "preis": preis,
        "host_id": str(interaction.user.id),
        "guild_id": str(interaction.guild.id),
        "channel_id": str(interaction.channel.id),
        "message_id": str(gesendete_nachricht.id),
        "ende_timestamp": ende_unix,
        "teilnehmer": [],
        "beendet": False,
        "bild": bild
    }
    giveaways_speichern(giveaways)

    bot.loop.create_task(giveaway_beenden(giveaway_id, sekunden))

# --- /giveaway-reroll: Lost bei einem beendeten Giveaway einen neuen Gewinner aus ---
@bot.tree.command(name="giveaway-reroll", description="[Admin] Lost bei einem beendeten Giveaway einen neuen Gewinner aus")
@app_commands.describe(nachricht_id="Die Nachrichten-ID des Giveaway-Embeds")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway_reroll(interaction: discord.Interaction, nachricht_id: str):
    giveaways = giveaways_laden()
    treffer = None
    for g_id, daten in giveaways.items():
        if daten.get("message_id") == nachricht_id:
            treffer = (g_id, daten)
            break

    if treffer is None:
        await interaction.response.send_message("⚠️ Kein Giveaway mit dieser Nachrichten-ID gefunden.", ephemeral=True)
        return

    g_id, daten = treffer
    if not daten["teilnehmer"]:
        await interaction.response.send_message("⚠️ Es gab keine Teilnehmer bei diesem Giveaway.", ephemeral=True)
        return

    gewinner_id = random.choice(daten["teilnehmer"])
    await interaction.response.send_message(
        f"🎉 Neuer Gewinner für **{daten['preis']}**: <@{gewinner_id}>! Herzlichen Glückwunsch! 🎉"
    )

# --- /drop-setup: Admin richtet Channel + Ping-Rollen für das automatische Drop-System ein ---
@bot.tree.command(name="drop-setup", description="[Admin] Richte die automatischen Drops ein (Honey/Episch/Mythic/Secret)")
@app_commands.describe(
    channel="In welchem Channel sollen die Drops gepostet werden?",
    honig_rolle="Rolle, die bei Honey Drop (alle 15 Min) gepingt wird (optional)",
    episch_rolle="Rolle, die bei Episch (alle 30 Min) gepingt wird (optional)",
    mythic_rolle="Rolle, die bei Mythic (jede Stunde) gepingt wird (optional)",
    secret_rolle="Rolle, die bei Secret (alle 4-5 Std.) gepingt wird (optional)",
    secret_emoji="Reaction-Emoji für Secret Drops (optional, Standard: 👑)"
)
@app_commands.checks.has_permissions(administrator=True)
async def drop_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    honig_rolle: discord.Role = None,
    episch_rolle: discord.Role = None,
    mythic_rolle: discord.Role = None,
    secret_rolle: discord.Role = None,
    secret_emoji: str = None
):
    war_bereits_eingerichtet = drop_config_laden() is not None

    config = {
        "channel_id": str(channel.id),
        "honig_rolle_id": str(honig_rolle.id) if honig_rolle else None,
        "episch_rolle_id": str(episch_rolle.id) if episch_rolle else None,
        "mythic_rolle_id": str(mythic_rolle.id) if mythic_rolle else None,
        "secret_rolle_id": str(secret_rolle.id) if secret_rolle else None,
        "secret_emoji": secret_emoji  # None = Standard-Emoji (👑) wird verwendet
    }
    drop_config_speichern(config)

    await interaction.response.send_message(
        f"✅ Drop-System eingerichtet! Drops werden ab jetzt in {channel.mention} gepostet:\n"
        f"🍯 Honey Drop – alle 15 Min. (50 Wins)\n"
        f"⚡ Episch – alle 30 Min. (300 Wins)\n"
        f"🔮 Mythic – jede Stunde (500 Wins)\n"
        f"👑 Secret – alle 4-5 Std. (800 Wins)\n\n"
        f"Der erste Drop von jedem Typ kommt jetzt sofort!",
        ephemeral=True
    )

    # --- Beim allerersten Setup starten die Loops sofort -> erster Drop kommt direkt ---
    if not war_bereits_eingerichtet:
        drops_starten()

# --- /timerglobal: Startet einen live runterzählenden Countdown-Timer in einem Channel ---
@bot.tree.command(name="timerglobal", description="Startet einen Countdown-Timer in einem Channel")
@app_commands.describe(
    channel="In welchem Channel soll der Timer gepostet werden?",
    grund="Warum läuft dieser Timer? (wird im Embed angezeigt)",
    tage="Anzahl Tage (optional, Standard: 0)",
    stunden="Anzahl Stunden (optional, Standard: 0)",
    minuten="Anzahl Minuten (optional, Standard: 0)",
    sekunden="Anzahl Sekunden (optional, Standard: 0)"
)
async def timerglobal(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    grund: str,
    tage: int = 0,
    stunden: int = 0,
    minuten: int = 0,
    sekunden: int = 0
):
    gesamt_sekunden = tage * 86400 + stunden * 3600 + minuten * 60 + sekunden

    if gesamt_sekunden <= 0:
        await interaction.response.send_message(
            "⚠️ Bitte gib eine Dauer größer als 0 an (Tage/Stunden/Minuten/Sekunden).",
            ephemeral=True
        )
        return

    ende_zeit = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=gesamt_sekunden)
    ende_unix = int(ende_zeit.timestamp())
    timer_id = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000))  # eindeutige ID

    daten = {
        "grund": grund,
        "guild_id": str(interaction.guild.id),
        "channel_id": str(channel.id),
        "ersteller_id": str(interaction.user.id),
        "ersteller_name": interaction.user.display_name,
        "ende_timestamp": ende_unix,
        "beendet": False,
        "message_id": None
    }

    embed = timer_embed_bauen(daten, gesamt_sekunden)

    try:
        gesendete_nachricht = await channel.send(embed=embed)
    except discord.HTTPException:
        await interaction.response.send_message(
            "⚠️ Ich konnte in diesem Channel keine Nachricht senden. Habe ich dort die nötigen Rechte?",
            ephemeral=True
        )
        return

    daten["message_id"] = str(gesendete_nachricht.id)

    timers = timer_laden()
    timers[timer_id] = daten
    timer_speichern(timers)

    timer_starten(timer_id)

    await interaction.response.send_message(
        f"✅ Timer gestartet in {channel.mention}! Endet <t:{ende_unix}:R>.",
        ephemeral=True
    )

# --- /timerstop: Bricht einen laufenden Timer vorzeitig ab ---
@bot.tree.command(name="timerstop", description="Bricht einen laufenden Timer über seine Nachrichten-ID ab")
@app_commands.describe(nachricht_id="Die Nachrichten-ID des Timer-Embeds")
async def timerstop(interaction: discord.Interaction, nachricht_id: str):
    timers = timer_laden()
    treffer = None
    for t_id, daten in timers.items():
        if daten.get("message_id") == nachricht_id:
            treffer = (t_id, daten)
            break

    if treffer is None:
        await interaction.response.send_message("⚠️ Kein Timer mit dieser Nachrichten-ID gefunden.", ephemeral=True)
        return

    t_id, daten = treffer

    if daten.get("beendet"):
        await interaction.response.send_message("⚠️ Dieser Timer ist bereits beendet.", ephemeral=True)
        return

    # --- Nur der Ersteller oder ein Admin darf den Timer abbrechen ---
    ist_ersteller = str(interaction.user.id) == daten["ersteller_id"]
    ist_admin = interaction.user.guild_permissions.administrator
    if not (ist_ersteller or ist_admin):
        await interaction.response.send_message(
            "❌ Nur der Ersteller des Timers oder ein Admin kann ihn abbrechen.",
            ephemeral=True
        )
        return

    daten["beendet"] = True
    timers[t_id] = daten
    timer_speichern(timers)

    task = timer_tasks.pop(t_id, None)
    if task is not None:
        task.cancel()

    guild = bot.get_guild(int(daten["guild_id"]))
    channel = guild.get_channel(int(daten["channel_id"])) if guild else None
    if channel is not None:
        try:
            nachricht = await channel.fetch_message(int(daten["message_id"]))
            abgebrochen_embed = discord.Embed(
                title="🛑 Timer abgebrochen",
                description=f"**{daten['grund']}**",
                color=discord.Color.dark_grey()
            )
            abgebrochen_embed.set_footer(text=f"Abgebrochen von {interaction.user.display_name}")
            await nachricht.edit(embed=abgebrochen_embed)
        except (discord.NotFound, discord.HTTPException):
            pass

    await interaction.response.send_message("✅ Timer wurde abgebrochen.", ephemeral=True)

# --- /newticketsystem: Admin richtet das komplette Ticket-System ein und postet das Panel ---
@bot.tree.command(name="newticketsystem", description="[Admin] Richtet das Ticket-System ein und postet das Panel mit 4 Knöpfen")
@app_commands.describe(
    channel="In welchem Channel soll das Ticket-Panel gepostet werden?",
    titel="Titel des Panel-Embeds",
    beschreibung="Beschreibungstext des Panel-Embeds",
    kategorie="In welcher Kategorie sollen die Ticket-Channels erstellt werden?",
    mod_rolle="Welche Rolle soll die Tickets sehen und bearbeiten können?",
    bild="Bild-URL, die im Panel angezeigt wird (optional)",
    knopf1="Beschriftung für Knopf 1 (Standard: Support)",
    knopf2="Beschriftung für Knopf 2 (Standard: Report)",
    knopf3="Beschriftung für Knopf 3 (Standard: Bug melden)",
    knopf4="Beschriftung für Knopf 4 (Standard: Sonstiges)"
)
@app_commands.checks.has_permissions(administrator=True)
async def newticketsystem(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    titel: str,
    beschreibung: str,
    kategorie: discord.CategoryChannel,
    mod_rolle: discord.Role,
    bild: str = None,
    knopf1: str = "Support",
    knopf2: str = "Report",
    knopf3: str = "Bug melden",
    knopf4: str = "Sonstiges"
):
    knoepfe = [knopf1, knopf2, knopf3, knopf4]

    bestehende_config = ticket_setup_laden() or {}
    config = {
        "kategorie_id": str(kategorie.id),
        "mod_rolle_id": str(mod_rolle.id),
        "panel_channel_id": str(channel.id),
        "knoepfe": knoepfe,
        "zaehler": bestehende_config.get("zaehler", 0)
    }
    ticket_setup_speichern(config)

    embed = discord.Embed(
        title=titel,
        description=beschreibung,
        color=discord.Color.blurple()
    )
    if bild:
        embed.set_image(url=bild)

    await channel.send(embed=embed, view=TicketPanelView())

    await interaction.response.send_message(
        f"✅ Ticket-System eingerichtet! Panel gepostet in {channel.mention}.\n"
        f"Neue Tickets landen in **{kategorie.name}**, sichtbar für **{mod_rolle.name}**.\n"
        f"Knöpfe: {', '.join(knoepfe)}",
        ephemeral=True
    )

# =========================================================================
# =========================== APPLY-COMMANDS ===============================
# =========================================================================

# --- /apply-setup: Admin richtet Titel, Beschreibung, Channels und die Annahme-Rolle ein ---
@bot.tree.command(name="apply-setup", description="[Admin] Richtet das Apply-System ein und postet das Panel")
@app_commands.describe(
    channel="In welchem Channel soll der 'Apply starten'-Knopf gepostet werden?",
    titel="Titel des Panel-Embeds",
    beschreibung="Beschreibungstext des Panel-Embeds",
    review_channel="In welchem Channel sollen fertige Bewerbungen erscheinen?",
    rolle="Welche Rolle wird bei Annahme vergeben?",
    bild="Bild-URL, die im Panel angezeigt wird (optional)",
    knopf_text="Beschriftung des Buttons (Standard: Apply starten)"
)
@app_commands.checks.has_permissions(administrator=True)
async def apply_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    titel: str,
    beschreibung: str,
    review_channel: discord.TextChannel,
    rolle: discord.Role,
    bild: str = None,
    knopf_text: str = "Apply starten"
):
    bestehende_config = apply_setup_laden() or {}
    config = {
        "panel_channel_id": str(channel.id),
        "review_channel_id": str(review_channel.id),
        "accept_rolle_id": str(rolle.id),
        "titel": titel,
        "beschreibung": beschreibung,
        "bild": bild,
        "knopf_text": knopf_text,
        "fragen": bestehende_config.get("fragen", []),
        "zaehler": bestehende_config.get("zaehler", 0)
    }
    apply_setup_speichern(config)

    embed = discord.Embed(title=titel, description=beschreibung, color=discord.Color.blurple())
    if bild:
        embed.set_image(url=bild)

    view = ApplyPanelView()
    view.apply_start.label = knopf_text
    await channel.send(embed=embed, view=view)

    anzahl_fragen = len(config["fragen"])
    hinweis = "" if anzahl_fragen > 0 else "\n⚠️ Es sind noch keine Fragen eingerichtet! Nutze `/apply-frage-hinzufuegen`."
    await interaction.response.send_message(
        f"✅ Apply-System eingerichtet! Panel gepostet in {channel.mention}.\n"
        f"Fertige Bewerbungen landen in {review_channel.mention}.\n"
        f"Bei Annahme wird die Rolle **{rolle.name}** vergeben.\n"
        f"Aktuell eingerichtete Fragen: **{anzahl_fragen}**{hinweis}",
        ephemeral=True
    )

# --- /apply-frage-hinzufuegen: Admin fügt eine einzelne Frage hinzu (bis zu 20) ---
@bot.tree.command(name="apply-frage-hinzufuegen", description="[Admin] Fügt eine Frage zur Bewerbung hinzu (max. 20)")
@app_commands.describe(frage="Der Text der Frage")
@app_commands.checks.has_permissions(administrator=True)
async def apply_frage_hinzufuegen(interaction: discord.Interaction, frage: str):
    setup = apply_setup_laden()
    if setup is None:
        await interaction.response.send_message(
            "⚠️ Richte zuerst `/apply-setup` ein, bevor du Fragen hinzufügst.",
            ephemeral=True
        )
        return

    fragen = setup.get("fragen", [])
    if len(fragen) >= MAX_APPLY_FRAGEN:
        await interaction.response.send_message(
            f"⚠️ Es sind bereits {MAX_APPLY_FRAGEN} Fragen eingerichtet (Maximum erreicht).",
            ephemeral=True
        )
        return

    fragen.append(frage)
    setup["fragen"] = fragen
    apply_setup_speichern(setup)

    await interaction.response.send_message(
        f"✅ Frage **{len(fragen)}/{MAX_APPLY_FRAGEN}** hinzugefügt:\n> {frage}",
        ephemeral=True
    )

# --- /apply-fragen-anzeigen: Zeigt alle aktuell eingerichteten Fragen ---
@bot.tree.command(name="apply-fragen-anzeigen", description="[Admin] Zeigt alle eingerichteten Bewerbungsfragen")
@app_commands.checks.has_permissions(administrator=True)
async def apply_fragen_anzeigen(interaction: discord.Interaction):
    setup = apply_setup_laden()
    fragen = setup.get("fragen", []) if setup else []

    if not fragen:
        await interaction.response.send_message("⚠️ Es sind noch keine Fragen eingerichtet.", ephemeral=True)
        return

    text = "\n".join(f"**{i}.** {f}" for i, f in enumerate(fragen, start=1))
    embed = discord.Embed(title=f"📋 Bewerbungsfragen ({len(fragen)}/{MAX_APPLY_FRAGEN})", description=text, color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- /apply-frage-entfernen: Entfernt eine Frage anhand ihrer Nummer ---
@bot.tree.command(name="apply-frage-entfernen", description="[Admin] Entfernt eine Bewerbungsfrage anhand ihrer Nummer")
@app_commands.describe(nummer="Die Nummer der Frage (siehe /apply-fragen-anzeigen)")
@app_commands.checks.has_permissions(administrator=True)
async def apply_frage_entfernen(interaction: discord.Interaction, nummer: int):
    setup = apply_setup_laden()
    fragen = setup.get("fragen", []) if setup else []

    if not fragen or nummer < 1 or nummer > len(fragen):
        await interaction.response.send_message("⚠️ Ungültige Nummer. Nutze `/apply-fragen-anzeigen`, um die Nummern zu sehen.", ephemeral=True)
        return

    entfernt = fragen.pop(nummer - 1)
    setup["fragen"] = fragen
    apply_setup_speichern(setup)

    await interaction.response.send_message(f"✅ Frage entfernt: \n> {entfernt}", ephemeral=True)

# --- /apply-panel-posten: Postet das Panel erneut (z.B. nach Änderungen an den Fragen) ---
@bot.tree.command(name="apply-panel-posten", description="[Admin] Postet das Apply-Panel erneut im eingerichteten Channel")
@app_commands.checks.has_permissions(administrator=True)
async def apply_panel_posten(interaction: discord.Interaction):
    setup = apply_setup_laden()
    if setup is None:
        await interaction.response.send_message("⚠️ Richte zuerst `/apply-setup` ein.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(int(setup["panel_channel_id"]))
    if channel is None:
        await interaction.response.send_message("⚠️ Der eingerichtete Panel-Channel existiert nicht mehr.", ephemeral=True)
        return

    embed = discord.Embed(title=setup["titel"], description=setup["beschreibung"], color=discord.Color.blurple())
    if setup.get("bild"):
        embed.set_image(url=setup["bild"])

    view = ApplyPanelView()
    view.apply_start.label = setup.get("knopf_text", "Apply starten")
    await channel.send(embed=embed, view=view)

    await interaction.response.send_message(f"✅ Panel erneut gepostet in {channel.mention}.", ephemeral=True)

# =========================================================================
# ========================= ENDE APPLY-COMMANDS ============================
# =========================================================================

# =========================================================================
# ============================ VIP-COMMANDS =================================
# =========================================================================

# --- /vipauto: Admin richtet Game Pass, Verify-Channel, Check-Channel und die VIP-Rolle ein ---
@bot.tree.command(name="vipauto", description="[Admin] Richtet das automatische VIP-Game-Pass-System ein")
@app_commands.describe(
    gamepass_id="Die ID deines Roblox Game Pass (Zahl aus dem Game-Pass-Link)",
    verify_channel="Channel, in dem User mit '?VerfyRoblox' ihren Roblox-Namen verknüpfen",
    check_channel="Channel, in dem User mit '?Verfy' den Game-Pass-Kauf prüfen lassen",
    rolle="Welche Rolle wird vergeben, wenn der Game Pass gekauft wurde?"
)
@app_commands.checks.has_permissions(administrator=True)
async def vipauto(
    interaction: discord.Interaction,
    gamepass_id: str,
    verify_channel: discord.TextChannel,
    check_channel: discord.TextChannel,
    rolle: discord.Role
):
    config = {
        "gamepass_id": gamepass_id,
        "verify_channel_id": str(verify_channel.id),
        "check_channel_id": str(check_channel.id),
        "rolle_id": str(rolle.id)
    }
    vip_config_speichern(config)

    await interaction.response.send_message(
        f"✅ VIP-Auto-System eingerichtet!\n"
        f"🆔 Game Pass ID: `{gamepass_id}`\n"
        f"📝 Verifizieren mit `?VerfyRoblox` in {verify_channel.mention}\n"
        f"🔍 Kauf prüfen mit `?Verfy` in {check_channel.mention}\n"
        f"🎭 Belohnungsrolle: **{rolle.name}**",
        ephemeral=True
    )

# =========================================================================
# ========================= ENDE VIP-COMMANDS ================================
# =========================================================================

# =========================================================================
# ============================ KI-COMMANDS ==================================
# =========================================================================

# --- /creatki: Admin richtet den Channel für den KI-Script-Generator ein ---
@bot.tree.command(name="creatki", description="[Admin] Richtet den Channel für den KI-Script-Generator (?ki) ein")
@app_commands.describe(channel="In welchem Channel dürfen Spieler '?ki <Beschreibung>' benutzen?")
@app_commands.checks.has_permissions(administrator=True)
async def creatki(interaction: discord.Interaction, channel: discord.TextChannel):
    ki_config_speichern({"channel_id": str(channel.id)})

    await interaction.response.send_message(
        f"✅ KI-Script-Generator eingerichtet in {channel.mention}!\n"
        f"🤖 Jeder Spieler kann dort `?ki <Beschreibung>` schreiben, z.B.:\n"
        f"> `?ki mach ein part unsichtbar wenn man es anklickt`\n"
        f"📊 Kostenlos: **{KI_FREI_LIMIT} Scripts** pro Spieler, danach **2 Stunden** Cooldown.\n"
        f"👑 VIP (unbegrenzt) erhält man über `?Vip` im selben Channel – geprüft wird der Game Pass "
        f"aus `/vipauto` (Roblox-Account vorher mit `?VerfyRoblox` verknüpfen).\n"
        f"🆓 Die KI läuft über einen kostenlosen Anbieter, es wird **kein bezahlter API-Key** benötigt.",
        ephemeral=True
    )

# =========================================================================
# ========================= ENDE KI-COMMANDS =================================
# =========================================================================

# --- Bot starten ---
bot.run(TOKEN)
