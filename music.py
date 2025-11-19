import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
from yt_dlp import YoutubeDL
from main import queues, volume_levels, stay_connected, last_embed_message, is_admin
from discord import app_commands

# ======================= Constants =======================
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': 'True',
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ======================= Helpers =======================

# Helper function to get context/interaction metadata for playback
async def _get_playback_meta(context_like):
    if isinstance(context_like, commands.Context):
        return context_like.guild, context_like.author, context_like.author.voice
    elif isinstance(context_like, discord.Interaction):
        return context_like.guild, context_like.user, context_like.user.voice

async def update_embed_to_song_ended(ctx):
    try:
        msg = last_embed_message.get(ctx.guild.id)
        if msg and msg.embeds:
            embed = msg.embeds[0]
            embed.color = discord.Color.from_rgb(114, 114, 117)
            embed.set_author(name="✅ Song Ended", icon_url=ctx.bot.user.display_avatar.url)
            embed.description = "🎵 Playback finished."
            await msg.edit(embed=embed, view=None)
    except Exception as e:
        print(f"Failed to update embed after song ended: {e}")

async def play_next(ctx):
    if ctx.guild.id not in queues or not queues[ctx.guild.id]:
        await update_embed_to_song_ended(ctx)

        if not stay_connected.get(ctx.guild.id, False):
            voice = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
            if voice and voice.is_connected():
                await voice.disconnect()
        return

    url, requester = queues[ctx.guild.id].pop(0)
    await _play_song(ctx, url, requester)

async def _play_song(context_like, url, requester):
    guild, user, user_voice = await _get_playback_meta(context_like)

    bot_client = context_like.client if isinstance(context_like, discord.Interaction) else context_like.bot
    voice = discord.utils.get(bot_client.voice_clients, guild=guild)
    
    # 1. Handle Voice Channel Join & Movement 
    if user_voice:
        if voice:
            if voice.channel != user_voice.channel:
                await voice.move_to(user_voice.channel)
                voice = discord.utils.get(bot_client.voice_clients, guild=guild)
        else:
            try:
                voice = await user_voice.channel.connect()
            except discord.errors.ClientException:
                voice = discord.utils.get(bot_client.voice_clients, guild=guild)
            
            if not voice:
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="❌ ভয়েস চ্যানেলে সংযোগ স্থাপন করা যায়নি। (অনুমতি বা অন্য সমস্যা)",
                    color=discord.Color.red()
                )
                if isinstance(context_like, commands.Context):
                    await context_like.send(embed=error_embed)
                elif isinstance(context_like, discord.Interaction):
                    await context_like.edit_original_response(embed=error_embed, content=None)
                return

    else:
        error_embed = discord.Embed(
             title="❌ Error",
             description="❌ গান চালানোর জন্য আপনাকে একটি ভয়েস চ্যানেলে থাকতে হবে।",
             color=discord.Color.red()
         )
        
        if isinstance(context_like, commands.Context):
            await context_like.send(embed=error_embed)
        elif isinstance(context_like, discord.Interaction):
            await context_like.edit_original_response(embed=error_embed, content=None)
        return
        
    if not voice: return 

    try:
        # 2. Extract Info
        def extract_info_blocking():
             with YoutubeDL(YDL_OPTIONS) as ydl:
                 return ydl.extract_info(url, download=False)

        info = await bot_client.loop.run_in_executor(None, extract_info_blocking)
        
        stream_url = info['url']
        title = info.get('title', 'Unknown')
        thumbnail = info.get('thumbnail')
        duration = info.get('duration', 0)
            
        source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)

        if guild.id in volume_levels:
            source.volume = volume_levels[guild.id]
        
        # 3. Play song and set after_song
        ctx = await bot_client.get_context(context_like) if isinstance(context_like, discord.Interaction) else context_like
        
        def after_song(error):
            if error:
                 print(f"Player error in {ctx.guild.name}: {error}")
            
            coro = play_next(ctx)
            ctx.bot.loop.call_soon_threadsafe(ctx.bot.loop.create_task, coro) 
            
        voice.play(source, after=after_song)

        # 4. Send Embed
        duration_str = f"`{duration // 60}:{duration % 60:02}`" if duration else "Unknown"
        embed = discord.Embed(
            title=f"🎵 {title}",
            description=f"**Duration:** {duration_str}\n🎧 Requested by {requester.mention}",
            color=discord.Color.from_rgb(114, 114, 117)
        )
        embed.set_author(name="Now Playing", icon_url=ctx.bot.user.display_avatar.url) 
        embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text="✔ MY NAME IS LIA 🥰")

        view = MusicControlView(ctx)

        if isinstance(context_like, commands.Context):
            msg = await context_like.send(embed=embed, view=view)
        elif isinstance(context_like, discord.Interaction):
            await context_like.edit_original_response(embed=embed, view=view, content=None)
            msg = await context_like.original_response()
            
        last_embed_message[guild.id] = msg

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Error",
            description=f"❌ Error playing song: {str(e)}",
            color=discord.Color.red()
        )
        if isinstance(context_like, commands.Context):
            await context_like.send(embed=error_embed)
        elif isinstance(context_like, discord.Interaction):
            await context_like.edit_original_response(embed=error_embed, content=None)


# ======================= Button Controls (MusicControlView) =======================
class MusicControlView(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = ctx.bot # Access bot from context

    async def _ephemeral_reply(self, interaction: discord.Interaction, title: str, description: str):
        embed = discord.Embed(
            title=title,
            description=f"{description}\nAction by {interaction.user.mention}",
            color=discord.Color.from_rgb(114, 114, 117)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="⏸ Pause", style=discord.ButtonStyle.blurple)
    async def pause(self, interaction: discord.Interaction, button: Button):
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)
        
        if not voice:
             return await self._ephemeral_reply(interaction, "❌ Error", "বট ভয়েস চ্যানেলে নেই।")

        if voice.is_playing():
            voice.pause()
            await self._ephemeral_reply(interaction, "✅ Successfully Paused", "")
        else:
            await self._ephemeral_reply(interaction, "❌ Error", "কোন গান বাজছে না।")

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.green)
    async def resume(self, interaction: discord.Interaction, button: Button):
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)
        
        if not voice:
             return await self._ephemeral_reply(interaction, "❌ Error", "বট ভয়েস চ্যানেলে নেই।")

        if voice.is_paused():
            voice.resume()
            await self._ephemeral_reply(interaction, "✅ Successfully Resumed", "")
        else:
            await self._ephemeral_reply(interaction, "❌ Error", "কোন গান Pause করা নেই।")

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)

        if not voice:
             return await self._ephemeral_reply(interaction, "❌ Error", "বট ভয়েস চ্যানেলে নেই।")

        if voice.is_playing() or voice.is_paused():
            voice.stop()
            await self._ephemeral_reply(interaction, "✅ Successfully Skipped", "")
        else:
            await self._ephemeral_reply(interaction, "❌ Error", "Skip করার মতো কিছু নেই।")

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: Button):
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)
        
        if not voice:
             return await self._ephemeral_reply(interaction, "❌ Error", "বট ভয়েস চ্যানেলে নেই।")

        voice.stop()
        queues[self.ctx.guild.id] = []
        await self._ephemeral_reply(interaction, "✅ Successfully Stopped", "")

    @discord.ui.button(label="🔊 Vol +", style=discord.ButtonStyle.grey)
    async def volume_up(self, interaction: discord.Interaction, button: Button):
        guild_id = self.ctx.guild.id
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)
        
        volume_levels[guild_id] = min(volume_levels.get(guild_id, 1.0) + 0.1, 2.0)
        
        if voice and voice.source:
             voice.source.volume = volume_levels[guild_id] 
        
        await self._ephemeral_reply(interaction, "✅ Successfully Volume Increased", f"New Volume: `{volume_levels[guild_id]*100:.0f}%`")

    @discord.ui.button(label="🔉 Vol -", style=discord.ButtonStyle.grey)
    async def volume_down(self, interaction: discord.Interaction, button: Button):
        guild_id = self.ctx.guild.id
        voice = discord.utils.get(self.bot.voice_clients, guild=self.ctx.guild)
        
        volume_levels[guild_id] = max(volume_levels.get(guild_id, 1.0) - 0.1, 0.0)
        
        if voice and voice.source:
            voice.source.volume = volume_levels[guild_id] 

        await self._ephemeral_reply(interaction, "✅ Successfully Volume Decreased", f"New Volume: `{volume_levels[guild_id]*100:.0f}%`")

# ======================= Cog Class =======================
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- PREFIX COMMANDS ---
    @commands.command(aliases=['p'])
    async def play(self, ctx, *, search: str):
        processing_msg = await ctx.send(embed=discord.Embed(
            description="🔄 Processing your song... Please wait.",
            color=discord.Color.from_rgb(114, 114, 117)
        ))
        
        def extract_info_blocking():
            with YoutubeDL(YDL_OPTIONS) as ydl:
                if search.startswith("http://") or search.startswith("https://"):
                    return ydl.extract_info(search, download=False)
                else:
                    return ydl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]

        try:
            info = await self.bot.loop.run_in_executor(None, extract_info_blocking)
            
            url = info['webpage_url']
            title = info.get('title', 'Unknown')
                
        except Exception as e:
            await processing_msg.edit(embed=discord.Embed(
                title="❌ Error",
                description=f"❌ Error playing song: {str(e)}",
                color=discord.Color.red()
            ))
            return

        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []

        queues[ctx.guild.id].append((url, ctx.author))
        await processing_msg.delete() 
        
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        
        if not voice or not voice.is_playing():
            await _play_song(ctx, url, ctx.author)
            return

        await ctx.send(f"✅ Added to queue: **{title}**")


    @commands.command()
    async def pause(self, ctx):
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice and voice.is_playing():
            voice.pause()
            await ctx.send("⏸ Music paused!")

    @commands.command()
    async def resume(self, ctx):
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice and voice.is_paused():
            voice.resume()
            await ctx.send("▶️ Music resumed!")

    @commands.command()
    async def skip(self, ctx):
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice and voice.is_playing():
            voice.stop()
            await ctx.send("⏭ Skipped!")

    @commands.command()
    async def stop(self, ctx):
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice:
            voice.stop()
            queues[ctx.guild.id] = []
            await ctx.send("⏹ Music stopped!")

    @commands.command()
    async def volume(self, ctx, level: int):
        if level < 0 or level > 200:
            return await ctx.send("⚠️ Volume must be between 0 and 200.")
        volume_levels[ctx.guild.id] = level / 100
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice and voice.source:
             voice.source.volume = volume_levels[ctx.guild.id] 
        await ctx.send(f"🔊 Volume set to {level}%")

    @commands.command()
    async def queue(self, ctx):
        q = queues.get(ctx.guild.id, [])
        
        currently_playing = "Nothing"
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice and voice.is_playing() and ctx.guild.id in last_embed_message:
            embed_msg = last_embed_message[ctx.guild.id]
            if embed_msg.embeds and embed_msg.embeds[0].title:
                 currently_playing = embed_msg.embeds[0].title.replace("🎵 ", "")

        if not q:
            return await ctx.send(f"🎶 Now Playing: **{currently_playing}**\n🚫 Queue is empty.")
        
        msg = "\n".join([f"{i+1}. {yt[0]} (Queued by {yt[1].name})" for i, yt in enumerate(q)])
        
        embed = discord.Embed(
            title="📜 Music Queue",
            description=f"**🎶 Now Playing:** **{currently_playing}**\n\n**Upcoming Songs:**\n{msg}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    # --- SLASH COMMANDS (App Commands) ---
    
    @app_commands.command(name="play", description="Plays a song from YouTube or searches for it.")
    @app_commands.describe(search="The song name or YouTube link to play")
    async def slash_play(self, interaction: discord.Interaction, search: str):
        await interaction.response.defer() 
        
        def extract_info_blocking():
            with YoutubeDL(YDL_OPTIONS) as ydl:
                if search.startswith("http://") or search.startswith("https://"):
                    return ydl.extract_info(search, download=False)
                else:
                    return ydl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]

        try:
            info = await self.bot.loop.run_in_executor(None, extract_info_blocking)

            url = info['webpage_url']
            title = info.get('title', 'Unknown')
                
        except Exception as e:
            await interaction.edit_original_response(embed=discord.Embed(
                title="❌ Error",
                description=f"❌ Error finding song: {str(e)}",
                color=discord.Color.red()
            ), content=None)
            return

        if interaction.guild_id not in queues:
            queues[interaction.guild_id] = []

        queues[interaction.guild_id].append((url, interaction.user))
        
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not voice or not voice.is_playing():
            await _play_song(interaction, url, interaction.user)
            return

        await interaction.edit_original_response(embed=discord.Embed(
            title="✅ Added to queue",
            description=f"**{title}** added by {interaction.user.mention}",
            color=discord.Color.green()
        ), content=None)
        
    @app_commands.command(name="pause", description="Pauses the current song.")
    async def slash_pause(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice and voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸ Music paused!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No song is currently playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resumes the paused song.")
    async def slash_resume(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice and voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ Music resumed!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No song is paused.", ephemeral=True)

    @app_commands.command(name="skip", description="Skips the current song and plays the next one in the queue.")
    async def slash_skip(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice and voice.is_playing():
            voice.stop()
            await interaction.response.send_message("⏭ Skipped!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)

    @app_commands.command(name="stop", description="Stops playback and clears the queue.")
    async def slash_stop(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice:
            voice.stop()
            queues[interaction.guild.id] = []
            await interaction.response.send_message("⏹ Music stopped and queue cleared!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not in a voice channel.", ephemeral=True)

    @app_commands.command(name="volume", description="Sets the music volume (0-200).")
    @app_commands.describe(level="Volume level (0 to 200)")
    async def slash_volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 200]):
        volume_levels[interaction.guild.id] = level / 100
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice and voice.source:
            voice.source.volume = volume_levels[interaction.guild.id]
        
        await interaction.response.send_message(f"🔊 Volume set to {level}%", ephemeral=True)

    @app_commands.command(name="queue", description="Shows the list of songs in the queue.")
    async def slash_queue(self, interaction: discord.Interaction):
        q = queues.get(interaction.guild_id, [])
        
        currently_playing = "Nothing"
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if voice and voice.is_playing() and interaction.guild_id in last_embed_message:
            msg = last_embed_message[interaction.guild_id]
            if msg and msg.embeds and msg.embeds[0].title:
                 currently_playing = msg.embeds[0].title.replace("🎵 ", "")

        if not q:
            embed = discord.Embed(title="📜 Music Queue", description=f"🎶 Now Playing: **{currently_playing}**\n\n🚫 Queue is empty.", color=discord.Color.blue())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        msg = "\n".join([f"{i+1}. {yt[0]} (Queued by {yt[1].name})" for i, yt in enumerate(q)])
        
        embed = discord.Embed(
            title="📜 Music Queue",
            description=f"**🎶 Now Playing:** **{currently_playing}**\n\n**Upcoming Songs:**\n{msg}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Music(bot))
