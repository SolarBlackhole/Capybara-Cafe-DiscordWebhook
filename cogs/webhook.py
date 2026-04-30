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
        self.punishment_channel_id = os.getenv("PUNISHMENT_CHANNEL_ID")

        self.last_heartbeat = time.time()
        self.server_offline_threshold = 40

        self.web_server.start()
        self.status_monitor.start()

        self.round_active = False

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
        if time.time() - self.last_heartbeat > 45:
            # Send server offline message to both channels
            await self.bot.change_presence(
                status = discord.Status.dnd,
                activity = discord.Game(name = "Cafe Closed")
            )

    async def handler(self, request):
        try:
            data = await request.json()
            event_type = data.get("type")
            content = data.get("content")

            self.last_heartbeat = time.time()

            self.bot.loop.create_task(self.process_event(event_type, content, time.time()))

            if event_type == "Heartbeat":
                await self.update_presence(content)

            return web.Response(text="OK", status=200)
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return web.Response(text="Error processing webhook", status=500)
        
    async def update_presence(self, content):
        # Count is off by one
        count = content.get("PlayerCount", 0)
        count = count - 1

        if count > 25:
            await self.bot.change_presence(
                status = discord.Status.online,
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=f"Serving an OverCapycity Cafe with {count} Customers"
                )
            )
        elif count == 25:
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
                status = discord.Status.idle,
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Watching the empty cafe"
                )
            )

    async def process_event(self, event_type, content, timestamp):
        embed = None
        # Only needed if the event has two variants
        staff_embed = None
        timestamp = await self.handle_timestamp(timestamp)

        match event_type:
            case "PlayerJoined":
                if self.round_active == False:
                    return
                embed = discord.Embed(
                    title="Player Joined",
                    description=f"**{content['PlayerName']}** joined the server.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"ID: {content['PlayerId']} | Count: {content['PlayerCount'] - 1}")
                await self.update_presence(content)
            case "PlayerLeft":
                if self.round_active == False:
                    return
                embed = discord.Embed(
                    title="Player Left",
                    description=f"**{content['PlayerName']}** left the server.",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"ID: {content['PlayerId']} | Count: {content['PlayerCount'] - 1}")
                await self.update_presence(content)
            case "PlayerDied":
                embed = discord.Embed(
                    title="Player Died",
                    description=f"**{content['PlayerName']}** died. Role: {content['Role']}",
                    color=discord.Color.purple(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"ID: {content['PlayerId']}")
            case "PlayerKilled":
                embed = discord.Embed(
                    title="Player Killed",
                    description=f"**{content['AttackerName']}** as a **{content['AttackerRole']}** killed **{content['VictimName']}** who was a **{content['VictimRole']}**.",
                    color=discord.Color.dark_red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"IDs: Attacker {content['AttackerId']}, Victim {content['VictimId']}")
            case "ServerWaveRespawned":
                embed = discord.Embed(
                    title="Wave Respawned",
                    description=f"A {content['Faction']} wave has respawned with {len(content['PlayersRespawned'])} players.",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
            case "PlayerEscaped":
                embed = discord.Embed(
                    title="Player Escaped",
                    description=f"**{content['PlayerName']}** escaped the facility as a **{content['Role']}**.",
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"ID: {content['PlayerId']}")
            case "AdminChatMessage":
                embed = discord.Embed(
                    title="Admin Chat Message",
                    description=f"**{content['SenderName']}**: {content['Message']}",
                    color=discord.Color.purple(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"ID: {content['SenderId']}")
            case "ServerRoundStarted":
                # Normal Embed - No player info or roles
                embed = discord.Embed(
                    title="Round Started",
                    description=f"A new round has started with {content['PlayerCount'] - 1} players.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                # Staff Embed - Include player info and roles from Players array
                staff_embed = discord.Embed(
                    title="Round Started (Staff)",
                    description=f"A new round has started with {content['PlayerCount'] - 1} players.",
                    color=discord.Color.green(),
                )
                for player in content['Players']:
                    if player['PlayerName'] == "Dedicated Server":
                        continue
                    staff_embed.add_field(name=player['PlayerName'], value=f"ID: {player['PlayerId']}", inline=False)
                staff_embed.add_field(name="Timestamp", value=timestamp, inline=False)
                self.round_active = True
            case "ServerRoundEnded":
                self.round_active = False
                embed = discord.Embed(
                    title="Round Ended",
                    description=f"The round has ended.",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Winning Team", value=content['WinningTeam'], inline=False)
                embed.add_field(name="Escaped D-Class", value=content['EscapedDClass'], inline=False)
                embed.add_field(name="Escaped Scientists", value=content['EscapedScientists'], inline=False)
                embed.add_field(name="SCP Kills", value=content['SCPKills'], inline=False)
                embed.add_field(name="Warhead Detonated", value=content['WarheadDetonated'], inline=False)
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
            case "ServerWaitingForPlayers":
                embed = discord.Embed(
                    title="Waiting for Players",
                    description=f"The server is waiting for players to join.",
                    color=discord.Color.yellow(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
            case "PlayerKicked":
                embed = discord.Embed(
                    title="Player Kicked",
                    description=f"**{content['PlayerName']}** was kicked from the server by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']}")
                if content['Reasoning'] != "AFK":
                    await self.create_punishment_log(event_type, content, timestamp)
            case "PlayerBanned":
                embed = discord.Embed(
                    title="Player Banned",
                    description=f"**{content['PlayerName']}** was banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Ban Duration: {content['DurationSeconds']}.",
                    color=discord.Color.dark_red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']}")
                await self.create_punishment_log(event_type, content, timestamp)
            case "PlayerBannedEx":
                embed = discord.Embed(
                    title="Player Banned (Permanent)",
                    description=f"**{content['PlayerName']}** was permanently banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Expires: {content['ExpireDate']}.  ",
                    color=discord.Color.dark_red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
                await self.create_punishment_log(event_type, content, timestamp)
            case "IPBanned":
                embed = discord.Embed(
                    title="IP Banned",
                    description=f"**{content['PlayerName']}** was IP banned from the server by **{content['IssuerName']}** for {content['Reasoning']}. Expires: {content['ExpireDate']}.",
                    color=discord.Color.dark_red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
                await self.create_punishment_log(event_type, content, timestamp)
            case "IPBanUpdated":
                embed = discord.Embed(
                    title="IP Ban Updated",
                    description=f"**{content['PlayerName']}** had their IP ban updated by **{content['IssuerName']}** for {content['Reasoning']}. New Expire Date: {content['ExpireDate']}.",
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
            case "PlayerBanUpdated":
                embed = discord.Embed(
                    title="Player Ban Updated",
                    description=f"**{content['PlayerName']}** had their ban updated by **{content['IssuerName']}** for {content['Reasoning']}. New Expire Date: {content['ExpireDate']}.",
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
            case "IPBanRevoked":
                embed = discord.Embed(
                    title="IP Ban Revoked",
                    description=f"**{content['PlayerName']}** had their IP ban revoked by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
            case "PlayerBanRevoked":
                embed = discord.Embed(
                    title="Player Ban Revoked",
                    description=f"**{content['PlayerName']}** had their ban revoked by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']}")
            case "PlayerMuted":
                embed = discord.Embed(
                    title="Player Muted",
                    description=f"**{content['PlayerName']}** was muted by **{content['IssuerName']}**. Intercom Ban: {content['IsIntercom']}.",
                    color=discord.Color.dark_orange(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']}")
                await self.create_punishment_log(event_type, content, timestamp)
            case "PlayerUnmuted":
                embed = discord.Embed(
                    title="Player Unmuted",
                    description=f"**{content['PlayerName']}** was unmuted by **{content['IssuerName']}** for {content['Reasoning']}.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Player ID: {content['PlayerId']} | Staff ID: {content['IssuerId']}")
            case "PlayerReportedCheater":
                embed = discord.Embed(
                    title="Player Reported for Cheating",
                    description=f"**{content['ReporterName']}** reported **{content['ReportedName']}** for cheating. Reason: {content['Reasoning']}.",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Reporter ID: {content['ReporterId']} | Reported ID: {content['ReportedId']}")
            case "PlayerReportedPlayer":
                embed = discord.Embed(
                    title="Player Reported for Abuse",
                    description=f"**{content['ReporterName']}** reported **{content['ReportedName']}**. Reason: {content['Reasoning']}.",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)
                embed.set_footer(text=f"Reporter ID: {content['ReporterId']} | Reported ID: {content['ReportedId']}")
            case "heartbeat":
                return
            case _:
                embed = discord.Embed(
                    title=f"Unknown Event: {event_type}",
                    description=f"Received an event of type {event_type} with content: {content}",
                    color=discord.Color.light_grey(),
                )
                embed.add_field(name="Timestamp", value=timestamp, inline=False)

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

    async def create_punishment_log(self, event_type, content, timestamp):
        punishment_log_channel = self.bot.get_channel(int(self.punishment_channel_id))
        if punishment_log_channel and punishment_log_channel.type == discord.ChannelType.forum:
            match event_type:
                case "PlayerKicked":
                    title = f"{content['PlayerName']} - {content['PlayerId']} - Kicked"
                    tag = punishment_log_channel.get_tag(1492264419017752709)
                    embed = discord.Embed(
                        title=f"Punishment Log: Kicked",
                        description=f"**Player:** {content['PlayerName']} (ID: {content['PlayerId']})\n**Issuer:** {content['IssuerName']} (ID: {content['IssuerId']})\n**Reason:** {content['Reasoning']}\n**Timestamp:** {timestamp}",
                        color=discord.Color.red(),
                    )
                case "PlayerBanned" | "PlayerBanEx":
                    title = f"{content['PlayerName']} - {content['PlayerId']} - Banned"
                    if content["DurationSeconds"] >= 1576800000:
                        duration_text = "Permanent"
                        tag = punishment_log_channel.get_tag(1492264381558292673) 
                    else:
                        duration_text = f"{content['DurationSeconds']} seconds"
                        tag = punishment_log_channel.get_tag(1492264367767552060)
                    embed = discord.Embed(
                        title=f"Punishment Log: Banned",
                        description=f"**Player:** {content['PlayerName']} (ID: {content['PlayerId']})\n**Issuer:** {content['IssuerName']} (ID: {content['IssuerId']})\n**Reason:** {content['Reasoning']}\n**Duration:** {duration_text}\n**Timestamp:** {timestamp}",
                        color=discord.Color.dark_red(),
                    )
                case "IPBanned":
                    title = f"{content['PlayerName']} - {content['PlayerId']} - IP Banned"
                    if content["DurationSeconds"] >= 1576800000:
                        duration_text = "Permanent"
                        tag = punishment_log_channel.get_tag(1492264353716768948) 
                    else:
                        duration_text = f"{content['DurationSeconds']} seconds"
                        tag = punishment_log_channel.get_tag(1492264353716768948)
                    embed = discord.Embed(
                        title=f"Punishment Log: IP Banned",
                        description=f"**Player:** {content['PlayerName']} (ID: {content['PlayerId']}) (IP: {content['PlayerIP']})\n**Issuer:** {content['IssuerName']} (ID: {content['IssuerId']})\n**Reason:** {content['Reasoning']}\n**Duration:** {duration_text}\n**Timestamp:** {timestamp}",
                        color=discord.Color.dark_red(),
                    )
                case "PlayerMuted":
                    title = f"{content['PlayerName']} - {content['PlayerId']} - Muted"
                    tag = punishment_log_channel.get_tag(1492264353716768948)
                    embed = discord.Embed(
                        title=f"Punishment Log: Muted",
                        description=f"**Player:** {content['PlayerName']} (ID: {content['PlayerId']})\n**Issuer:** {content['IssuerName']} (ID: {content['IssuerId']})\n**Intercom Ban:** {content['IsIntercom']}\n**Timestamp:** {timestamp}",
                        color=discord.Color.dark_orange(),
                    )
                case _:
                    return
                
            tags_to_apply = [tag] if tag else []
            await punishment_log_channel.create_thread(
                name=title,
                embed=embed,
                auto_archive_duration=1440,
                applied_tags=tags_to_apply
            )

    async def handle_timestamp(self, timestamp):
        return f"<t:{int(timestamp)}:F>"

async def setup(bot):
    await bot.add_cog(Webhook(bot))