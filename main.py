import discord
from discord.ext import commands
import os

TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

COGS = [
    "cogs.scrim",
    "cogs.inscription",
    "cogs.tournoi",
    "cogs.ticket",
    "cogs.classement",
]

@bot.event
async def on_ready():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅ {cog}")
        except Exception as e:
            print(f"❌ {cog}: {e}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ LigaLabs Bot — {bot.user} | {len(bot.guilds)} serveur(s) | {len(synced)} commandes")
    except Exception as e:
        print(f"❌ Sync: {e}")

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ DISCORD_TOKEN manquant")
