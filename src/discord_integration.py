import asyncio
import threading
import logging
import io
import os
import time
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import discord
    from discord.ext import commands, tasks
    _DISCORD_AVAILABLE = True
except Exception:
    _DISCORD_AVAILABLE = False
    logger.warning("discord.py not available; Discord integration disabled")


def read_recent_logs(log_path, minutes=5):
    if not os.path.exists(log_path):
        return "No log file found."

    cutoff = datetime.now() - timedelta(minutes=minutes)
    lines = []
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                m = re.match(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', line)
                if m:
                    try:
                        ts = datetime.strptime(m.group(1), '%d/%m/%Y %H:%M:%S')
                        if ts >= cutoff:
                            lines.append(line.rstrip())
                    except ValueError:
                        pass
                elif lines:
                    lines.append(line.rstrip())
    except Exception as e:
        return f"Failed to read logs: {e}"

    if not lines:
        return "(no log entries in the last few minutes)"

    text = '\n'.join(lines[-200:])
    if len(text) > 1900:
        text = '...(truncated)...\n' + text[-1900:]
    return text


class DiscordBot:
    """Discord bot that sends periodic status updates with control buttons."""

    def __init__(self, token, channel_id, update_interval_minutes,
                 callbacks,
                 get_stats_callback, get_screenshot_callback,
                 log_path):
        self.token = (token or '').strip()
        try:
            self.channel_id = int(str(channel_id).strip())
        except (ValueError, TypeError):
            self.channel_id = 0
        self.update_interval = max(1, int(update_interval_minutes)) * 60

        self.callbacks = callbacks or {}
        self.get_stats = get_stats_callback
        self.get_screenshot = get_screenshot_callback
        self.log_path = log_path

        self._thread = None
        self._loop = None
        self._bot = None
        self._update_task = None
        self._ready = threading.Event()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not _DISCORD_AVAILABLE:
            logger.error("Cannot start Discord bot: discord.py not installed")
            return False
        if not self.token or not self.channel_id:
            logger.error("Cannot start Discord bot: missing token or channel_id")
            return False
        if self.is_running():
            return True

        self._thread = threading.Thread(target=self._run, daemon=True, name='DiscordBot')
        self._thread.start()
        return True

    def stop(self):
        if not self._loop or not self._bot:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._bot.close(), self._loop)
        except Exception as e:
            logger.error(f"Error stopping Discord bot: {e}")

    def notify_stuck(self, reason):
        if not self._ready.is_set() or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(self._send_stuck(reason), self._loop)

    def notify_event(self, title, description, color=0x3498db):
        if not self._ready.is_set() or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(
            self._send_event(title, description, color), self._loop
        )

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            intents = discord.Intents.default()
            self._bot = commands.Bot(command_prefix='!', intents=intents)

            bot = self._bot
            outer = self

            async def _run_callback(interaction, cb_name):
                await interaction.response.defer(ephemeral=True, thinking=True)
                cb = outer.callbacks.get(cb_name)
                if cb is None:
                    await interaction.followup.send(f'❌ Callback "{cb_name}" not registered', ephemeral=True)
                    return
                try:
                    result = cb()
                    ok, msg = result if isinstance(result, tuple) else (True, 'Done')
                    icon = '✅' if ok else '⚠️'
                    await interaction.followup.send(f'{icon} {msg}', ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f'❌ Failed: {e}', ephemeral=True)

            class ControlView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(label='Mirror Dungeon', style=discord.ButtonStyle.success,
                                   custom_id='workerbee_start_mirror', row=0)
                async def start_mirror_btn(self, interaction, button):
                    await _run_callback(interaction, 'start_mirror')

                @discord.ui.button(label='Exp', style=discord.ButtonStyle.success,
                                   custom_id='workerbee_start_exp', row=0)
                async def start_exp_btn(self, interaction, button):
                    await _run_callback(interaction, 'start_exp')

                @discord.ui.button(label='Threads', style=discord.ButtonStyle.success,
                                   custom_id='workerbee_start_threads', row=0)
                async def start_threads_btn(self, interaction, button):
                    await _run_callback(interaction, 'start_threads')

                @discord.ui.button(label='Chain', style=discord.ButtonStyle.primary,
                                   custom_id='workerbee_start_chain', row=0)
                async def start_chain_btn(self, interaction, button):
                    await _run_callback(interaction, 'start_chain')

                @discord.ui.button(label='Stop', style=discord.ButtonStyle.danger,
                                   custom_id='workerbee_stop', row=1)
                async def stop_btn(self, interaction, button):
                    await _run_callback(interaction, 'stop_all')

            @bot.event
            async def on_ready():
                logger.info(f"Discord bot ready as {bot.user}")
                bot.add_view(ControlView())
                self._ready.set()
                if self._update_task is None or not self._update_task.is_running():
                    self._update_task = _update_loop
                    _update_loop.start()
                await outer._send_event(
                    'WorkerBee online',
                    'Bot connected. Status updates will post on interval.',
                    color=0x2ecc71,
                )

            @tasks.loop(seconds=self.update_interval)
            async def _update_loop():
                try:
                    await outer._send_update(ControlView())
                except Exception as e:
                    logger.error(f"Discord update failed: {e}")

            self._loop.run_until_complete(bot.start(self.token))
        except Exception as e:
            logger.error(f"Discord bot thread crashed: {e}")
        finally:
            self._ready.clear()

    async def _get_channel(self):
        channel = self._bot.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error(f"Cannot fetch Discord channel {self.channel_id}: {e}")
                return None
        return channel

    async def _send_update(self, view):
        channel = await self._get_channel()
        if not channel:
            return

        stats = self.get_stats() or {}

        embed = discord.Embed(
            title='WorkerBee Status',
            color=0x3498db,
            timestamp=datetime.utcnow(),
        )
        for key, value in stats.items():
            embed.add_field(name=str(key), value=str(value), inline=True)

        file = None
        screenshot = self.get_screenshot()
        if screenshot:
            file = discord.File(io.BytesIO(screenshot), filename='screen.png')
            embed.set_image(url='attachment://screen.png')

        if file:
            await channel.send(embed=embed, file=file, view=view)
        else:
            await channel.send(embed=embed, view=view)

    async def _send_event(self, title, description, color):
        channel = await self._get_channel()
        if not channel:
            return
        embed = discord.Embed(
            title=title, description=description, color=color,
            timestamp=datetime.utcnow(),
        )
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Discord send_event failed: {e}")

    async def _send_stuck(self, reason):
        channel = await self._get_channel()
        if not channel:
            return

        log_text = read_recent_logs(self.log_path, minutes=5)

        embed = discord.Embed(
            title='WorkerBee Stuck',
            description=f"**Reason:** {reason}",
            color=0xe74c3c,
            timestamp=datetime.utcnow(),
        )

        file = None
        screenshot = self.get_screenshot()
        if screenshot:
            file = discord.File(io.BytesIO(screenshot), filename='stuck.png')
            embed.set_image(url='attachment://stuck.png')

        try:
            if file:
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
            for chunk_start in range(0, len(log_text), 1900):
                chunk = log_text[chunk_start:chunk_start + 1900]
                await channel.send(f"```\n{chunk}\n```")
        except Exception as e:
            logger.error(f"Discord send_stuck failed: {e}")
