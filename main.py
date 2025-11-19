import discord
from discord.ext import commands
from discord.ext.commands import when_mentioned_or
import json
import os
from config import TOKEN # config.py ফাইল থেকে TOKEN আমদানি করা হচ্ছে
import asyncio 
from discord import app_commands 

# ======================= JSON Prefix Logic =======================
def load_prefixes():
    try:
        with open('prefixes.json', 'r') as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_prefixes():
    with open('prefixes.json', 'w') as f:
        json.dump({str(k): v for k, v in prefixes.items()}, f, indent=4)

prefixes = load_prefixes()

def get_prefix(bot, message):
    if not message.guild:
        return commands.when_mentioned(bot, message)
    return when_mentioned_or(prefixes.get(message.guild.id, "?"))(bot, message)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# ======================= Global Variables =======================
queues = {}
volume_levels = {}
stay_connected = {}
last_embed_message = {}

# ======================= Helpers (needed by cogs) =======================
def is_admin(source):
    # source can be ctx (Context) or interaction (Interaction)
    if isinstance(source, commands.Context):
        return source.author.guild_permissions.administrator or source.guild.owner_id == source.author.id
    elif isinstance(source, discord.Interaction):
        return source.user.guild_permissions.administrator or source.guild.owner_id == source.user.id
    return False

# ======================= Cogs Setup and Events =======================

async def load_cogs():
    await bot.load_extension('music') 
    await bot.load_extension('utility')

@bot.event
async def on_guild_join(guild):
    prefixes[guild.id] = "?"
    save_prefixes()

@bot.event
async def on_ready():
    if not hasattr(bot, 'cogs_loaded'):
        print(f"✅ Bot is online as {bot.user}")
        print("📋 Connected servers:")
        for guild in bot.guilds:
            print(f"- {guild.name} (ID: {guild.id})")
        
        try:
            await load_cogs() 
            print("🧩 Cogs (music.py and utility.py) loaded successfully.")
        except Exception as e:
            print(f"❌ Failed to load Cogs: {e}")
        
        # --- Slash Commands সিঙ্ক করা ---
        try:
            synced = await bot.tree.sync()
            print(f"🌐 Synced {len(synced)} slash commands.")
        except Exception as e:
            print(f"❌ Failed to sync slash commands: {e}")
        # -----------------------------------
        bot.cogs_loaded = True

# ======================= Run Bot (FIXED) =======================

if __name__ == '__main__': # <-- এই কন্ডিশনটিই Error টি ঠিক করবে
    bot.run(TOKEN)
