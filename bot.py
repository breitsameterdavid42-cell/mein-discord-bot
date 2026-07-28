import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import json
import asyncio
import datetime

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

# --- Bot starten ---
bot.run(TOKEN)
