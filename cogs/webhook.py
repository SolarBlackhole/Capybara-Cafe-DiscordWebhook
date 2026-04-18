from asyncio import tasks
import discord
from discord.ext import commands, tasks
from aiohttp import web
from dotenv import load_dotenv
import os
import datetime
import time
from helpers.eventMappings import event_mappings


class Webhook(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.port = 8081
        load_dotenv()
        self.staff_channel_id = os.getenv("STAFF_CHANNEL_ID")
        self.normal_channel_id = os.getenv("NORMAL_CHANNEL_ID")

        self.last_heartbeat = time.time()
        self.server_offline_threshold = 40

        self.web_server.start()
        self.status_monitor.start()

    def cog_unload(self):
        self.web_server.stop()

    @tasks.loop(count=1)
    async def web_server(self):
        app = web.Application()
        app.router.add_post("/webhook", self.handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

    @tasks.loop(seconds=10)
    async def status_monitor(self):
        if time.time() - self.last_heartbeat > self.server_offline_threshold:
            # Send server offline message to both channels
            await self.bot.change_presence(
                status = discord.Status.dnd,
                activity = discord.Game(name = "Cafe Closed")
            )

    async def handler(self, request):
        try:
            data = await request.json()
            event_type = data.get("type")
            timestamp = data.get("timestamp")
            content = data.get("content")

            self.bot.loop.create_task(self.process_event(event_type, content, timestamp))

            if event_type == "Heartbeat":
                await self.update_presence(content)

            return web.Response(text="OK", status=200)
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return web.Response(text="Error processing webhook", status=500)
        
    async def update_presence(self, content):
        count = content.get("PlayerCount", 0)

        if count == 25:
            await self.bot.change_presence(
                status = discord.Status.online,
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name="Serving a Full Cafe (25/25 Customers)"
                )
            )
        elif count > 0:
            await self.bot.change_presence(
                status = discord.Status.online,
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=f"Serving {count}/25 Customers"
                )
            )
        elif count == 0:
            await self.bot.change_presence(
                status = discord.Status.dnd,
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name="the empty cafe"
                )
            )

    async def process_event(self, event_type, content, timestamp):
        embed = None
        # Only needed if the event has two variants
        staff_embed = None
        timestamp = await self.handle_timestamp(timestamp)

        match event_type:
            case "PlayerJoined":
                embed = discord.Embed(
                    title="Player Joined",
                    description=f"**{content['PlayerName']}** joined the server.",
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"ID: {content['PlayerId']} | Count: {content['PlayerCount']} | Time: {timestamp}")
                self.update_presence(content)
            case "PlayerLeft":
                embed = discord.Embed(
                    title="Player Left",
                    description=f"**{content['PlayerName']}** left the server.",
                    color=discord.Color.red(),
                )
                embed.set_footer(text=f"ID: {content['PlayerId']} | Count: {content['PlayerCount']} | Time: {timestamp}")
                self.update_presence(content)
            case "PlayerDied":
                embed = discord.Embed(
                    title="Player Died",
                    description=f"**{content['PlayerName']}** died. Role: {content['Role']}",
                    color=discord.Color.grey(),
                )
                embed.set_footer(text=f"ID: {content['PlayerId']} | Time: {timestamp}")
            case "PlayerKilled":
                embed = discord.Embed(
                    title="Player Killed",
                    description=f"**{content['AttackerName']}** as a **{content['AttackerRole']}** killed **{content['VictimName']}** who was a **{content['VictimRole']}**.",
                    color=discord.Color.dark_red(),
                )
                embed.set_footer(text=f"IDs: Attacker {content['AttackerId']}, Victim {content['VictimId']} | Time: {timestamp}")
            case "ServerWaveRespawned":
                embed = discord.Embed(
                    title="Wave Respawned",
                    description=f"A {content['Faction']} wave has respawned with {content['PlayersRespawned']} players.",
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"Time: {timestamp}")
            case "PlayerEscaped":
                embed = discord.Embed(
                    title="Player Escaped",
                    description=f"**{content['PlayerName']}** escaped the facility as a **{content['Role']}**.",
                    color=discord.Color.orange(),
                )
                embed.set_footer(text=f"ID: {content['PlayerId']} | Time: {timestamp}")
            case "AdminChatMessage":
                embed = discord.Embed(
                    title="Admin Chat Message",
                    description=f"**{content['SenderName']}**: {content['Message']}",
                    color=discord.Color.purple(),
                )
                embed.set_footer(text=f"ID: {content['SenderId']} | Time: {timestamp}")
            case "ServerRoundStarted":
                # Normal Embed - No player info or roles
                embed = discord.Embed(
                    title="Round Started",
                    description=f"A new round has started with {content['PlayerCount']} players.",
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"Time: {timestamp}")

                # Staff Embed - Include player info and roles from Players array
                staff_embed = discord.Embed(
                    title="Round Started (Staff)",
                    description=f"A new round has started with {content['PlayerCount']} players. \n\n**Player Details:**\n" + "\n".join([f"**{player['PlayerName']}** ({player['PlayerId']}) as a **{player['Role']}**" for player in content['Players']]),
                    color=discord.Color.green(),
                )
                staff_embed.set_footer(text=f"Time: {timestamp}")
            case "ServerRoundEnded":
                embed = discord.Embed(
                    title="Round Ended",
                    description=f"The round has ended. \n\nWinning team: {content['WinningTeam']}. \n\nEscaped D-Class: {content['EscapedDClass']}. \n\nEscaped Scientists: {content['EscapedScientists']}. \n\nSCP Kills: {content['SCPKills']}. \n\nWarhead Detonated: {content['WarheadDetonated']}",
                    color=discord.Color.red(),
                )
                embed.set_footer(text=f"Time: {timestamp}")
            case "ServerWaitingForPlayers":
                embed = discord.Embed(
                    title="Waiting for Players",
                    description=f"The server is waiting for players to join.",
                    color=discord.Color.yellow(),
                )
                embed.set_footer(text=f"Time: {timestamp}")
            case "PlayerKicked":
                embed = discord.Embed(
                    title="Player Kicked",
                    description=f"**{content['PlayerName']}** was kicked from the server by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.red(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']} | Time: {timestamp}")
            case "PlayerBanned":
                embed = discord.Embed(
                    title="Player Banned",
                    description=f"**{content['PlayerName']}** was banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Ban Duration: {content['DurationSeconds']}.",
                    color=discord.Color.dark_red(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']} | Time: {timestamp}")
            case "PlayerBannedEx":
                embed = discord.Embed(
                    title="Player Banned (Permanent)",
                    description=f"**{content['PlayerName']}** was permanently banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Expires: {content['ExpireDate']}.  ",
                    color=discord.Color.dark_red(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "IPBanned":
                embed = discord.Embed(
                    title="IP Banned",
                    description=f"**{content['PlayerName']}** was IP banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Expires: {content['ExpireDate']}.",
                    color=discord.Color.dark_red(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "IPBanUpdated":
                embed = discord.Embed(
                    title="IP Ban Updated",
                    description=f"**{content['PlayerName']}** had their IP ban updated by **{content['IssuerName']}** for {content['Reasoning']}. New Expire Date: {content['ExpireDate']}.",
                    color=discord.Color.orange(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "PlayerBanUpdated":
                embed = discord.Embed(
                    title="Player Ban Updated",
                    description=f"**{content['PlayerName']}** had their ban updated by **{content['IssuerName']}** for {content['Reasoning']}. New Expire Date: {content['ExpireDate']}.",
                    color=discord.Color.orange(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "IPBanRevoked":
                embed = discord.Embed(
                    title="IP Ban Revoked",
                    description=f"**{content['PlayerName']}** had their IP ban revoked by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "PlayerBanRevoked":
                embed = discord.Embed(
                    title="Player Ban Revoked",
                    description=f"**{content['PlayerName']}** had their ban revoked by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Time: {timestamp}")
            case "PlayerMuted":
                embed = discord.Embed(
                    title="Player Muted",
                    description=f"**{content['PlayerName']}** was muted by **{content['IssuerName']}** for {content['Reasoning']}. Intercom Ban: {content['IsIntercom']} Expires: {content['ExpireDate']}.",
                    color=discord.Color.dark_orange(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']} | Time: {timestamp}")
            case "PlayerUnmuted":
                embed = discord.Embed(
                    title="Player Unmuted",
                    description=f"**{content['PlayerName']}** was unmuted by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']} | Time: {timestamp}")
            case "heartbeat":
                return
            case _:
                embed = discord.Embed(
                    title=f"Unknown Event: {event_type}",
                    description=f"Received an event of type {event_type} with content: {content}",
                    color=discord.Color.light_grey(),
                )
                embed.set_footer(text=f"Time: {timestamp}")

        if staff_embed:
            await self.send_to_discord(event_type, embed, has_staff_variant=True, staff_content=staff_embed)
        else:
            await self.send_to_discord(event_type, embed)

    async def send_to_discord(self, event_type, content, has_staff_variant=False, staff_content=None):
        channels = event_mappings.get(event_type, "")
        targets = [channel.strip() for channel in channels.split(",")]
        if "normal" in targets and self.normal_channel_id:
            normal_channel = self.bot.get_channel(int(self.normal_channel_id))
            if normal_channel:
                await normal_channel.send(embed=content)
        if "staff" in targets and self.staff_channel_id:
            channel = self.bot.get_channel(int(self.staff_channel_id))
            if channel:
                if has_staff_variant and staff_content:
                    await channel.send(embed=staff_content)
                else:
                    await channel.send(embed=content)

    async def handle_timestamp(self, timestamp):
        # Convert the timestamp (yyyy-MM-ddTHH:mm:ss.fffffffZ) to a discord timestamp format
        # <t:UNIXTIMESTAMP:F> for full date and time
        dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return f"<t:{int(dt.timestamp())}:F>"

async def setup(bot):
    await bot.add_cog(Webhook(bot))