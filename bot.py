import discord
from discord.ext import commands
import os

# --- Einstellungen ---
TOKEN = os.getenv("TOKEN")  # Token kommt aus Umgebungsvariable (z.B. bei Railway eingetragen)
PREFIX = "!"  # Befehle starten z.B. mit !hallo

# --- Bot erstellen ---
intents = discord.Intents.default()
intents.message_content = True  # wichtig, damit der Bot Nachrichten lesen kann

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# --- Wird ausgeführt, wenn der Bot online geht ---
@bot.event
async def on_ready():
    print(f"✅ Eingeloggt als {bot.user}")

# --- Ein einfacher Befehl: !hallo ---
@bot.command()
async def hallo(ctx):
    await ctx.send(f"Hallo {ctx.author.mention}! 👋")

# --- Noch ein Beispiel: !ping ---
@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

# --- Bot starten ---
bot.run(TOKEN)
