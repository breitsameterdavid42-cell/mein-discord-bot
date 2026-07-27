import discord
from discord.ext import commands
from discord import app_commands
import os
import random

# --- Rollenname, der /newvideo nutzen darf (muss EXAKT so heißen wie deine Rolle) ---
ERLAUBTE_ROLLE = "⭐ᴄᴏɴᴛᴇɴᴛ ᴄʀᴇᴀᴛᴏʀ"

# --- Self-Role Buttons: hier deine 6 Rollen eintragen (Emoji, Anzeigename, EXAKTER Rollenname auf dem Server) ---
SELF_ROLLEN = [
    {"emoji": "📢", "label": "Announcement", "rollenname": "Announcement"},
    {"emoji": "🔔", "label": "Sub Announcement", "rollenname": "Sub Announcement"},
    {"emoji": "🎉", "label": "Events", "rollenname": "Events"},
    {"emoji": "📱", "label": "Social Media", "rollenname": "Social Media"},
    {"emoji": "📊", "label": "Polls", "rollenname": "Polls"},
    {"emoji": "⭐", "label": "Content Creator", "rollenname": "Content Creator"},
]

# --- Einstellungen ---
TOKEN = os.getenv("TOKEN")  # Token kommt aus Umgebungsvariable (z.B. bei Railway eingetragen)
PREFIX = "!"  # Befehle starten z.B. mit !hallo

# --- Bot erstellen ---
intents = discord.Intents.default()
intents.message_content = True  # wichtig, damit der Bot Nachrichten lesen kann

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# --- Self-Role Button-Logik ---
class RollenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None = Buttons funktionieren dauerhaft, auch nach Neustart
        for rolle_info in SELF_ROLLEN:
            self.add_item(RollenButton(rolle_info))

class RollenButton(discord.ui.Button):
    def __init__(self, rolle_info):
        super().__init__(
            label=rolle_info["label"],
            emoji=rolle_info["emoji"],
            style=discord.ButtonStyle.secondary,
            custom_id=f"rolle_{rolle_info['rollenname']}"  # wichtig: muss eindeutig + dauerhaft sein
        )
        self.rollenname = rolle_info["rollenname"]

    async def callback(self, interaction: discord.Interaction):
        rolle = discord.utils.get(interaction.guild.roles, name=self.rollenname)

        if rolle is None:
            await interaction.response.send_message(
                f"⚠️ Die Rolle '{self.rollenname}' wurde auf dem Server nicht gefunden.",
                ephemeral=True
            )
            return

        if rolle in interaction.user.roles:
            # Hatte die Rolle schon -> entfernen
            await interaction.user.remove_roles(rolle)
            await interaction.response.send_message(f"❌ Rolle **{self.rollenname}** entfernt.", ephemeral=True)
        else:
            # Hatte die Rolle noch nicht -> hinzufügen
            await interaction.user.add_roles(rolle)
            await interaction.response.send_message(f"✅ Rolle **{self.rollenname}** hinzugefügt!", ephemeral=True)

# --- Wird ausgeführt, wenn der Bot online geht ---
@bot.event
async def on_ready():
    print(f"✅ Eingeloggt als {bot.user}")
    bot.add_view(RollenView())  # sorgt dafür, dass die Buttons auch nach Neustart klickbar bleiben
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

# --- /rollen: Postet die Nachricht mit den Self-Role Buttons ---
@bot.tree.command(name="rollen", description="Postet die Benachrichtigungs-Rollen zum Anklicken")
async def rollen(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎭 Benachrichtigungs-Rollen",
        description="Wähle hier aus, bei welchen Ereignissen du gepingt werden möchtest.\nKlicke einfach auf die Buttons, um Rollen zu verwalten.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=RollenView())

# --- Bot starten ---
bot.run(TOKEN)
