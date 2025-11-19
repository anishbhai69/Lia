import discord
from discord.ext import commands
from discord import app_commands
from main import prefixes, save_prefixes, is_admin, queues, stay_connected

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- PREFIX COMMANDS ---
    
    @commands.command()
    async def setprefix(self, ctx, new_prefix: str):
        if not is_admin(ctx):
            return await ctx.send("⚠️ এই কমান্ডটি শুধু অ্যাডমিনদের জন্য।")
        if len(new_prefix) > 5:
            return await ctx.send("❌ Prefix ৫ অক্ষরের বেশি হতে পারবে না।")
        prefixes[ctx.guild.id] = new_prefix
        save_prefixes()
        await ctx.send(f"✅ Prefix সেট করা হয়েছে: `{new_prefix}`")

    @commands.command()
    async def prefix(self, ctx):
        current_prefix = prefixes.get(ctx.guild.id, "?")
        await ctx.send(f"✅ Current prefix for this server is: `{current_prefix}`")
        
    @commands.command()
    async def help(self, ctx):
        prefix = prefixes.get(ctx.guild.id, "?")
        embed = discord.Embed(
            title="🎵 lia Bot Help",
            description=f"Commands list (Prefix: `{prefix}`):\n\n"
                        f"**Slash Commands (/):**\n"
                        f"`/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/volume`, `/queue`\n"
                        f"`/join`, `/leave`, `/setprefix`, `/prefix`, `/help`\n\n"
                        f"**Prefix Commands (`{prefix}`):**\n"
                        f"`{prefix}play` `{prefix}p`, `{prefix}pause`, `{prefix}resume`, `{prefix}skip`, `{prefix}stop`\n"
                        f"`{prefix}volume`, `{prefix}queue`, `{prefix}join`, `{prefix}leave`, `{prefix}setprefix`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Bot by Anish")
        await ctx.send(embed=embed)
        
    @commands.command()
    async def join(self, ctx):
        if ctx.author.voice:
            voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            if voice and voice.is_connected():
                await voice.move_to(ctx.author.voice.channel)
            else:
                await ctx.author.voice.channel.connect()

            stay_connected[ctx.guild.id] = True
            await ctx.send("✅ Joined your voice channel.")
        else:
            await ctx.send("❌ You must be in a voice channel.")

    @commands.command()
    async def leave(self, ctx):
        if not is_admin(ctx):
            return await ctx.send("⚠️ Only admins can use this command.")
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice:
            voice.stop()
            await voice.disconnect()
            queues[ctx.guild.id] = []
            stay_connected[ctx.guild.id] = False
            await ctx.send("👋 Left the voice channel.")


    # --- SLASH COMMANDS ---
    
    @app_commands.command(name="help", description="Shows the list of all available commands (Slash and Prefix).")
    async def slash_help(self, interaction: discord.Interaction):
        prefix = prefixes.get(interaction.guild_id, "?")
        embed = discord.Embed(
            title="🎵 lia Bot Help (Slash)",
            description=f"Commands list:\n\n"
                        f"**Slash Commands (/):**\n"
                        f"**/play**, **/pause**, **/resume**, **/skip**, **/stop**, **/volume**, **/queue**\n"
                        f"**/join**, **/leave**, **/setprefix**, **/prefix**, **/help**\n\n"
                        f"**Prefix Commands (`{prefix}`):**\n"
                        f"`{prefix}play` / `{prefix}p`, `{prefix}pause`, `{prefix}skip`, etc.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="✔ MY NAME IS LIA 🥰")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="prefix", description="Shows the current command prefix for this server.")
    async def slash_prefix(self, interaction: discord.Interaction):
        current_prefix = prefixes.get(interaction.guild_id, "?")
        await interaction.response.send_message(f"✅ Current prefix for this server is: `{current_prefix}`", ephemeral=True)
    
    @app_commands.command(name="join", description="Makes the bot join your current voice channel.")
    async def slash_join(self, interaction: discord.Interaction):
        if interaction.user.voice:
            voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
            if voice and voice.is_connected():
                await voice.move_to(interaction.user.voice.channel)
            else:
                await interaction.user.voice.channel.connect()

            stay_connected[interaction.guild.id] = True
            await interaction.response.send_message("✅ Joined your voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You must be in a voice channel.", ephemeral=True)

    @app_commands.command(name="leave", description="Makes the bot leave the voice channel (Admin only).")
    async def slash_leave(self, interaction: discord.Interaction):
        if not is_admin(interaction): 
            return await interaction.response.send_message("⚠️ এই কমান্ডটি শুধু অ্যাডমিনদের জন্য।", ephemeral=True)
            
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice:
            voice.stop()
            await voice.disconnect()
            queues[interaction.guild.id] = []
            stay_connected[interaction.guild.id] = False
            await interaction.response.send_message("👋 Left the voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not in a voice channel.", ephemeral=True)

    @app_commands.command(name="setprefix", description="Changes the bot's command prefix (Admin only).")
    @app_commands.describe(new_prefix="The new prefix (max 5 characters)")
    async def slash_setprefix(self, interaction: discord.Interaction, new_prefix: str):
        if not is_admin(interaction):
            return await interaction.response.send_message("⚠️ এই কমান্ডটি শুধু অ্যাডমিনদের জন্য।", ephemeral=True)
            
        if len(new_prefix) > 5:
            return await interaction.response.send_message("❌ Prefix ৫ অক্ষরের বেশি হতে পারবে না।", ephemeral=True)
            
        prefixes[interaction.guild.id] = new_prefix
        save_prefixes()
        await interaction.response.send_message(f"✅ Prefix সেট করা হয়েছে: `{new_prefix}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Utility(bot))
