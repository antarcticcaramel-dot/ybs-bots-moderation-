"""
╔══════════════════════════════════════════════════════════════════╗
║           ULTRA MODERATION BOT - Full Feature Discord Bot        ║
║  Features: Auto-Mod, Staff System, AI, Timers, Dashboards & More ║
╚══════════════════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
import random
import string
import datetime
import re
import aiohttp
import hashlib
import time
from typing import Optional
from collections import defaultdict

# ─── CONFIG ──────────────────────────────────────────────────────────────────

CONFIG_FILE       = "config.json"
WARNINGS_FILE     = "warnings.json"
STAFF_CODES_FILE  = "staff_codes.json"
TIMERS_FILE       = "timers.json"
REPORTS_FILE      = "reports.json"
PREMIUM_USERS_FILE= "premium.json"
COUNTING_FILE     = "counting.json"
NOTES_FILE        = "notes.json"
DASHBOARD_FILE    = "dashboard.html"   # served at /dashboard

DEFAULT_CONFIG = {
    "prefix": "/",
    "guild_id": None,
    "owner_id": None,
    "staff_roles": [],
    "admin_roles": [],
    "mod_roles": [],
    "log_channel": None,
    "mod_log_channel": None,
    "welcome_channel": None,
    "counting_channel": None,
    "bot_commands_channel": None,
    "premium_channels": [],
    "report_channel": None,
    "staff_channel": None,
    "automod": {
        "enabled": True,
        "ban_bad_links": True,
        "ban_invite_links": True,
        "anti_nuke": True,
        "anti_spam": True,
        "anti_caps": True,
        "anti_mass_mention": True,
        "bad_words": [],
        "whitelist_links": [],
        "max_mentions": 5,
        "spam_threshold": 5,
        "caps_threshold": 0.7,
        "anti_raid": True,
        "anti_ghost_ping": True,
        "max_warnings": 3,
        "warn_action": "mute",
        "mute_duration": 10,
    },
    "ai": {
        "enabled": True,
        "channel": None,
        "roblox_only": True,
    },
    "website": "https://yourwebsite.com",
    "dashboard": "https://yourdashboard.com",
    "roblox_portfolio": "https://www.roblox.com/users/",
    "staff_code": None,
    "daily_codes": {},
    "nickname_logs": True,
}

# ─── LOAD / SAVE ─────────────────────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default.copy() if isinstance(default, dict) else default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

config      = load_json(CONFIG_FILE,       DEFAULT_CONFIG)
warnings    = load_json(WARNINGS_FILE,     {})
staff_codes = load_json(STAFF_CODES_FILE,  {})
reports     = load_json(REPORTS_FILE,      {"bugs": [], "users": []})
premium     = load_json(PREMIUM_USERS_FILE,{})
counting    = load_json(COUNTING_FILE,     {"count": 0, "last_user": None})
notes       = load_json(NOTES_FILE,        {})

# ─── BOT SETUP ───────────────────────────────────────────────────────────────

intents = discord.Intents.all()
bot  = commands.Bot(command_prefix=config.get("prefix", "/"), intents=intents)
tree = bot.tree

spam_tracker = defaultdict(list)
nuke_tracker = defaultdict(list)
raid_tracker = []

# ─── IN-MEMORY CACHES (for dashboard) ────────────────────────────────────────

mod_log_cache   = []   # last 100 mod actions
automod_counts  = defaultdict(int)

def push_mod_log(action, moderator, target, reason):
    mod_log_cache.append({
        "action":    action,
        "moderator": str(moderator),
        "target":    str(target),
        "reason":    reason,
        "time":      datetime.datetime.utcnow().isoformat()
    })
    if len(mod_log_cache) > 100:
        mod_log_cache.pop(0)

def inc_automod(category: str):
    automod_counts[category] += 1

# ─── ROBLOX OBFUSCATOR ───────────────────────────────────────────────────────

def obfuscate_roblox_link(user_id: str) -> str:
    mapping = {'0':'O','1':'l','2':'Z','3':'E','4':'A','5':'S','6':'G','7':'T','8':'B','9':'q'}
    result = ""
    for i, ch in enumerate(str(user_id)):
        if i % 2 == 0 and ch in mapping:
            result += mapping[ch]
        else:
            result += ch
    return result

# ─── PERMISSION HELPERS ──────────────────────────────────────────────────────

def is_staff(member: discord.Member) -> bool:
    all_ids = set(config.get("staff_roles",[]) + config.get("admin_roles",[]) + config.get("mod_roles",[]))
    return any(r.id in all_ids for r in member.roles) or member.guild_permissions.administrator

def is_admin(member: discord.Member) -> bool:
    admin_ids = set(config.get("admin_roles",[]))
    return any(r.id in admin_ids for r in member.roles) or member.guild_permissions.administrator

def get_today_str():
    return datetime.date.today().isoformat()

def check_daily_code(user_id: int, code: str) -> bool:
    today = get_today_str()
    return config.get("daily_codes", {}).get(today) == code

# ─── EMBED HELPERS ───────────────────────────────────────────────────────────

def success_embed(title, desc):
    e = discord.Embed(title=f"✅ {title}", description=desc, color=0x2ecc71)
    e.timestamp = datetime.datetime.utcnow()
    _add_nav(e)
    return e

def error_embed(title, desc):
    e = discord.Embed(title=f"❌ {title}", description=desc, color=0xe74c3c)
    e.timestamp = datetime.datetime.utcnow()
    return e

def info_embed(title, desc, color=0x3498db):
    e = discord.Embed(title=f"ℹ️ {title}", description=desc, color=color)
    e.timestamp = datetime.datetime.utcnow()
    _add_nav(e)
    return e

def _add_nav(e: discord.Embed):
    website = config.get("website","https://yourwebsite.com")
    dash    = config.get("dashboard","https://yourdashboard.com")
    e.add_field(name="🔗 Quick Links", value=f"[🌐 Website]({website}) • [📊 Dashboard]({dash})", inline=False)

class NavView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        website = config.get("website","https://yourwebsite.com")
        dash    = config.get("dashboard","https://yourdashboard.com")
        self.add_item(discord.ui.Button(label="🌐 Website",   url=website, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="📊 Dashboard", url=dash,    style=discord.ButtonStyle.link))

    @discord.ui.button(label="📢 Report Issue", style=discord.ButtonStyle.secondary, emoji="🚨")
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BugReportModal())

class BugReportModal(discord.ui.Modal, title="🐛 Bug / Issue Report"):
    description = discord.ui.TextInput(label="Describe the bug", style=discord.TextStyle.paragraph, placeholder="What went wrong?", max_length=1000)
    steps       = discord.ui.TextInput(label="Steps to reproduce", style=discord.TextStyle.paragraph, required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        report = {
            "type": "bug", "user": str(interaction.user), "user_id": interaction.user.id,
            "description": self.description.value, "steps": self.steps.value,
            "time": datetime.datetime.utcnow().isoformat()
        }
        reports["bugs"].append(report)
        save_json(REPORTS_FILE, reports)
        ch_id = config.get("report_channel")
        if ch_id:
            ch = interaction.guild.get_channel(ch_id)
            if ch:
                e = discord.Embed(title="🐛 New Bug Report", color=0xe67e22)
                e.add_field(name="Reporter",     value=interaction.user.mention)
                e.add_field(name="Description",  value=self.description.value, inline=False)
                if self.steps.value:
                    e.add_field(name="Steps", value=self.steps.value, inline=False)
                await ch.send(embed=e)
        await interaction.response.send_message(embed=success_embed("Bug Reported","Thank you! Staff will look into it."), ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  SELECT MENU UI COMPONENTS FOR STAFF COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Ban Modal ──
class BanModal(discord.ui.Modal, title="🔨 Ban User"):
    reason      = discord.ui.TextInput(label="Reason", placeholder="Reason for ban", max_length=512)
    delete_days = discord.ui.TextInput(label="Delete message history (days, 0-7)", default="0", max_length=1)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = max(0, min(7, int(self.delete_days.value)))
        except:
            days = 0
        try:
            await interaction.guild.ban(self.user, reason=self.reason.value, delete_message_days=days)
            await interaction.response.send_message(embed=success_embed("User Banned", f"{self.user.mention} banned.\n**Reason:** {self.reason.value}"), view=NavView())
            await _mod_log(interaction.guild, "BAN", interaction.user, self.user, self.reason.value)
            try: await self.user.send(embed=error_embed("You've Been Banned", f"You were banned from **{interaction.guild.name}**\n**Reason:** {self.reason.value}"))
            except: pass
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Kick Modal ──
class KickModal(discord.ui.Modal, title="👢 Kick User"):
    reason = discord.ui.TextInput(label="Reason", placeholder="Reason for kick", max_length=512)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.guild.kick(self.user, reason=self.reason.value)
            await interaction.response.send_message(embed=success_embed("User Kicked", f"{self.user.mention} kicked.\n**Reason:** {self.reason.value}"), view=NavView())
            await _mod_log(interaction.guild, "KICK", interaction.user, self.user, self.reason.value)
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Mute Modal ──
class MuteModal(discord.ui.Modal, title="🔇 Mute (Timeout) User"):
    minutes = discord.ui.TextInput(label="Duration (minutes)", default="10", max_length=5)
    reason  = discord.ui.TextInput(label="Reason", placeholder="Reason for mute", max_length=512)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mins = max(1, int(self.minutes.value))
            until = datetime.datetime.utcnow() + datetime.timedelta(minutes=mins)
            await self.user.timeout(until, reason=self.reason.value)
            await interaction.response.send_message(embed=success_embed("User Muted", f"{self.user.mention} muted for **{mins}m**.\n**Reason:** {self.reason.value}"), view=NavView())
            await _mod_log(interaction.guild, "MUTE", interaction.user, self.user, self.reason.value)
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Warn Modal ──
class WarnModal(discord.ui.Modal, title="⚠️ Warn User"):
    reason = discord.ui.TextInput(label="Reason", placeholder="Reason for warning", max_length=512)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        count = await add_warning(interaction.guild, self.user, self.reason.value, interaction.user)
        await interaction.response.send_message(embed=success_embed("Warning Issued", f"{self.user.mention} warned (#{count}).\n**Reason:** {self.reason.value}"), view=NavView())
        await _mod_log(interaction.guild, "WARN", interaction.user, self.user, self.reason.value)
        try: await self.user.send(embed=error_embed("Warning Received", f"You received a warning in **{interaction.guild.name}**\n**Reason:** {self.reason.value}\n**Total:** {count}"))
        except: pass

# ── Purge Modal ──
class PurgeModal(discord.ui.Modal, title="🗑️ Purge Messages"):
    amount = discord.ui.TextInput(label="Number of messages (1–500)", default="10", max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = max(1, min(500, int(self.amount.value)))
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=n)
            await interaction.followup.send(embed=success_embed("Purge Complete", f"Deleted **{len(deleted)}** messages."), ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Tempban Modal ──
class TempbanModal(discord.ui.Modal, title="⏳ Temporary Ban"):
    hours  = discord.ui.TextInput(label="Duration (hours)", default="24", max_length=4)
    reason = discord.ui.TextInput(label="Reason", max_length=512)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            h = max(1, int(self.hours.value))
            await interaction.guild.ban(self.user, reason=f"Tempban ({h}h): {self.reason.value}")
            await interaction.response.send_message(embed=success_embed("Tempban", f"{self.user.mention} banned for **{h}h**.\n**Reason:** {self.reason.value}"), view=NavView())
            await asyncio.sleep(h * 3600)
            try: await interaction.guild.unban(self.user)
            except: pass
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Announce Modal ──
class AnnounceModal(discord.ui.Modal, title="📢 Send Announcement"):
    message = discord.ui.TextInput(label="Announcement", style=discord.TextStyle.paragraph, max_length=2000)
    ping    = discord.ui.TextInput(label="Role to ping (name, optional)", required=False, max_length=100)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        e = discord.Embed(title="📢 Announcement", description=self.message.value, color=0xe67e22)
        e.set_footer(text=f"By {interaction.user}", icon_url=interaction.user.display_avatar.url)
        content = None
        if self.ping.value:
            role = discord.utils.get(interaction.guild.roles, name=self.ping.value)
            if role: content = role.mention
        await self.channel.send(content=content, embed=e)
        await interaction.response.send_message(embed=success_embed("Announced", f"Sent to {self.channel.mention}."), ephemeral=True)

# ── Embed Modal ──
class EmbedModal(discord.ui.Modal, title="💬 Send Custom Embed"):
    title_field = discord.ui.TextInput(label="Title", max_length=256)
    desc        = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=2000)
    color       = discord.ui.TextInput(label="Color (hex, e.g. 3498db)", default="3498db", max_length=6)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try: col = int(self.color.value.strip("#"), 16)
        except: col = 0x3498db
        e = discord.Embed(title=self.title_field.value, description=self.desc.value, color=col)
        await self.channel.send(embed=e)
        await interaction.response.send_message(embed=success_embed("Embed Sent", f"Sent to {self.channel.mention}."), ephemeral=True)

# ── Nick Modal ──
class NickModal(discord.ui.Modal, title="✏️ Change Nickname"):
    nickname = discord.ui.TextInput(label="New nickname (blank to remove)", required=False, max_length=32)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        old = self.user.nick
        new = self.nickname.value.strip() or None
        await self.user.edit(nick=new)
        await interaction.response.send_message(embed=success_embed("Nickname Changed", f"{self.user.mention}: `{old}` → `{new or 'None'}`"), view=NavView())

# ── DM Modal ──
class DMModal(discord.ui.Modal, title="📩 DM User"):
    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            e = discord.Embed(title=f"📩 Message from {interaction.guild.name}", description=self.message.value, color=0x3498db)
            e.set_footer(text="You can reply and staff will see it.")
            await self.user.send(embed=e)
            await interaction.response.send_message(embed=success_embed("DM Sent", f"Sent to {self.user.mention}."), ephemeral=True)
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Failed", str(ex)), ephemeral=True)

# ── Slowmode Modal ──
class SlowmodeModal(discord.ui.Modal, title="⏱️ Set Slowmode"):
    seconds = discord.ui.TextInput(label="Seconds (0 to disable)", default="5", max_length=5)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            s = max(0, min(21600, int(self.seconds.value)))
            await self.channel.edit(slowmode_delay=s)
            status = f"{s}s" if s else "Disabled"
            await interaction.response.send_message(embed=success_embed("Slowmode", f"{self.channel.mention}: **{status}**"), view=NavView())
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

# ── Lock Modal ──
class LockModal(discord.ui.Modal, title="🔒 Lock Channel"):
    reason = discord.ui.TextInput(label="Reason", default="Rule violation", max_length=256)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        ow = self.channel.overwrites_for(interaction.guild.default_role)
        ow.send_messages = False
        await self.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
        await interaction.response.send_message(embed=success_embed("Locked", f"{self.channel.mention} locked.\n**Reason:** {self.reason.value}"), view=NavView())
        await self.channel.send(embed=discord.Embed(description=f"🔒 Locked by {interaction.user.mention}. **Reason:** {self.reason.value}", color=0xe74c3c))

# ══════════════════════════════════════════════════════════════════════════════
#  COMPOUND SELECT MENU VIEWS
# ══════════════════════════════════════════════════════════════════════════════

class MemberSelect(discord.ui.UserSelect):
    """Base user-select used by action views."""
    pass

# ── ModAction view — pick user then pick action ──
class ModActionSelect(discord.ui.View):
    """Shown by /mod — pick a user, then pick what to do."""

    def __init__(self):
        super().__init__(timeout=120)
        self.target: Optional[discord.Member] = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="1️⃣  Select a user…", min_values=1, max_values=1)
    async def pick_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.target = select.values[0]
        # enable action dropdown now
        self.action_menu.placeholder = f"2️⃣  Action for {self.target.display_name}…"
        self.action_menu.disabled = False
        await interaction.response.edit_message(
            content=f"**Selected:** {self.target.mention} — now choose an action.",
            view=self
        )

    @discord.ui.select(
        placeholder="2️⃣  Choose action… (select user first)",
        disabled=True,
        options=[
            discord.SelectOption(label="⚠️ Warn",       value="warn",    description="Issue a warning"),
            discord.SelectOption(label="🔇 Mute",       value="mute",    description="Timeout the user"),
            discord.SelectOption(label="🔊 Unmute",     value="unmute",  description="Remove timeout"),
            discord.SelectOption(label="👢 Kick",       value="kick",    description="Kick from server"),
            discord.SelectOption(label="🔨 Ban",        value="ban",     description="Permanently ban"),
            discord.SelectOption(label="⏳ Temp Ban",   value="tempban", description="Ban for X hours"),
            discord.SelectOption(label="🧹 Softban",    value="softban", description="Ban+unban to clear msgs"),
            discord.SelectOption(label="📝 View Warns", value="warns",   description="See user's warnings"),
            discord.SelectOption(label="🗑️ Clear Warns",value="clrwarn", description="Wipe warnings (admin)"),
            discord.SelectOption(label="✏️ Nick",       value="nick",    description="Change nickname"),
            discord.SelectOption(label="👤 User Info",  value="info",    description="View user info"),
            discord.SelectOption(label="📩 DM User",    value="dm",      description="Send a DM as bot"),
        ]
    )
    async def action_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not self.target:
            await interaction.response.send_message("Pick a user first.", ephemeral=True)
            return
        action = select.values[0]
        member = interaction.guild.get_member(self.target.id)
        if not member:
            await interaction.response.send_message(embed=error_embed("Not Found","User not in server."), ephemeral=True)
            return

        if action == "warn":
            await interaction.response.send_modal(WarnModal(member))
        elif action == "mute":
            await interaction.response.send_modal(MuteModal(member))
        elif action == "unmute":
            await member.timeout(None)
            await interaction.response.send_message(embed=success_embed("Unmuted", f"{member.mention} unmuted."), view=NavView())
        elif action == "kick":
            await interaction.response.send_modal(KickModal(member))
        elif action == "ban":
            await interaction.response.send_modal(BanModal(member))
        elif action == "tempban":
            await interaction.response.send_modal(TempbanModal(member))
        elif action == "softban":
            await interaction.guild.ban(member, reason="Softban", delete_message_days=7)
            await interaction.guild.unban(member)
            await interaction.response.send_message(embed=success_embed("Softbanned", f"{member.mention} softbanned."), view=NavView())
        elif action == "warns":
            uid = str(member.id)
            user_warns = warnings.get(uid, [])
            if not user_warns:
                await interaction.response.send_message(embed=info_embed("No Warnings", f"{member.mention} has no warnings."), ephemeral=True)
                return
            e = discord.Embed(title=f"⚠️ Warnings for {member}", color=0xe67e22)
            for i, w in enumerate(user_warns, 1):
                e.add_field(name=f"#{i}", value=f"**Reason:** {w['reason']}\n**By:** {w['moderator']}\n**Time:** {w['time'][:10]}", inline=False)
            await interaction.response.send_message(embed=e, view=NavView())
        elif action == "clrwarn":
            if not is_admin(interaction.user):
                await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True)
                return
            warnings.pop(str(member.id), None)
            save_json(WARNINGS_FILE, warnings)
            await interaction.response.send_message(embed=success_embed("Cleared", f"Warnings cleared for {member.mention}."), view=NavView())
        elif action == "nick":
            await interaction.response.send_modal(NickModal(member))
        elif action == "info":
            e = discord.Embed(title=f"👤 {member}", color=member.color)
            e.set_thumbnail(url=member.display_avatar.url)
            e.add_field(name="ID",        value=member.id)
            e.add_field(name="Nickname",  value=member.nick or "None")
            e.add_field(name="Joined",    value=discord.utils.format_dt(member.joined_at,"R") if member.joined_at else "?")
            e.add_field(name="Created",   value=discord.utils.format_dt(member.created_at,"R"))
            e.add_field(name="Roles",     value=" ".join(r.mention for r in member.roles[1:]) or "None", inline=False)
            e.add_field(name="Warnings",  value=len(warnings.get(str(member.id),[])))
            e.add_field(name="Is Staff",  value="✅" if is_staff(member) else "❌")
            await interaction.response.send_message(embed=e, view=NavView())
        elif action == "dm":
            await interaction.response.send_modal(DMModal(member))

# ── Channel action view ──
class ChannelActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.channel: Optional[discord.TextChannel] = None

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="1️⃣  Select a channel…",
                       channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
    async def pick_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.channel = select.values[0]
        self.ch_action.disabled = False
        self.ch_action.placeholder = f"2️⃣  Action for #{self.channel.name}…"
        await interaction.response.edit_message(
            content=f"**Selected:** {self.channel.mention} — now choose an action.",
            view=self
        )

    @discord.ui.select(
        placeholder="2️⃣  Choose action…",
        disabled=True,
        options=[
            discord.SelectOption(label="🔒 Lock",         value="lock",      description="Prevent @everyone from sending"),
            discord.SelectOption(label="🔓 Unlock",       value="unlock",    description="Restore send permissions"),
            discord.SelectOption(label="⏱️ Set Slowmode", value="slowmode",  description="Add message cooldown"),
            discord.SelectOption(label="🗑️ Purge",        value="purge",     description="Delete messages in bulk"),
            discord.SelectOption(label="📢 Announce",     value="announce",  description="Send an announcement here"),
            discord.SelectOption(label="💬 Send Embed",   value="embed",     description="Send a custom embed here"),
        ]
    )
    async def ch_action(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not self.channel:
            await interaction.response.send_message("Pick a channel first.", ephemeral=True)
            return
        action = select.values[0]
        ch = interaction.guild.get_channel(self.channel.id)
        if not ch:
            await interaction.response.send_message(embed=error_embed("Not Found","Channel not found."), ephemeral=True)
            return

        if action == "lock":
            await interaction.response.send_modal(LockModal(ch))
        elif action == "unlock":
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = True
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            await interaction.response.send_message(embed=success_embed("Unlocked", f"{ch.mention} unlocked."), view=NavView())
            await ch.send(embed=discord.Embed(description=f"🔓 Unlocked by {interaction.user.mention}.", color=0x2ecc71))
        elif action == "slowmode":
            await interaction.response.send_modal(SlowmodeModal(ch))
        elif action == "purge":
            await interaction.response.send_modal(PurgeModal())
        elif action == "announce":
            await interaction.response.send_modal(AnnounceModal(ch))
        elif action == "embed":
            await interaction.response.send_modal(EmbedModal(ch))

# ── Role action view ──
class RoleActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.target_user: Optional[discord.Member] = None
        self.target_role: Optional[discord.Role]   = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="1️⃣  Select user…", min_values=1, max_values=1)
    async def pick_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.target_user = select.values[0]
        self.role_sel.disabled = False
        await interaction.response.edit_message(content=f"**User:** {self.target_user.mention} — now pick a role.", view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="2️⃣  Select role…", disabled=True, min_values=1, max_values=1)
    async def role_sel(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.target_role = select.values[0]
        self.action_sel.disabled = False
        await interaction.response.edit_message(content=f"**User:** {self.target_user.mention} | **Role:** {self.target_role.mention} — add or remove?", view=self)

    @discord.ui.select(
        placeholder="3️⃣  Add or Remove?",
        disabled=True,
        options=[
            discord.SelectOption(label="➕ Add Role",    value="add",    emoji="➕"),
            discord.SelectOption(label="➖ Remove Role", value="remove", emoji="➖"),
        ]
    )
    async def action_sel(self, interaction: discord.Interaction, select: discord.ui.Select):
        member = interaction.guild.get_member(self.target_user.id)
        role   = self.target_role
        if select.values[0] == "add":
            await member.add_roles(role)
            await interaction.response.send_message(embed=success_embed("Role Added", f"{role.mention} → {member.mention}"), view=NavView())
        else:
            await member.remove_roles(role)
            await interaction.response.send_message(embed=success_embed("Role Removed", f"{role.mention} removed from {member.mention}"), view=NavView())

# ── AutoMod toggle view ──
class AutomodToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        placeholder="Select automod setting…",
        options=[
            discord.SelectOption(label="✅ Enable AutoMod",        value="enabled:true"),
            discord.SelectOption(label="❌ Disable AutoMod",       value="enabled:false"),
            discord.SelectOption(label="🔗 Block Bad Links: ON",   value="ban_bad_links:true"),
            discord.SelectOption(label="🔗 Block Bad Links: OFF",  value="ban_bad_links:false"),
            discord.SelectOption(label="📨 Block Invites: ON",     value="ban_invite_links:true"),
            discord.SelectOption(label="📨 Block Invites: OFF",    value="ban_invite_links:false"),
            discord.SelectOption(label="💥 Anti-Nuke: ON",        value="anti_nuke:true"),
            discord.SelectOption(label="💥 Anti-Nuke: OFF",       value="anti_nuke:false"),
            discord.SelectOption(label="📨 Anti-Spam: ON",        value="anti_spam:true"),
            discord.SelectOption(label="📨 Anti-Spam: OFF",       value="anti_spam:false"),
            discord.SelectOption(label="🔡 Anti-Caps: ON",        value="anti_caps:true"),
            discord.SelectOption(label="🔡 Anti-Caps: OFF",       value="anti_caps:false"),
            discord.SelectOption(label="👥 Anti-Mass Mention: ON", value="anti_mass_mention:true"),
            discord.SelectOption(label="👥 Anti-Mass Mention: OFF",value="anti_mass_mention:false"),
            discord.SelectOption(label="🚨 Anti-Raid: ON",        value="anti_raid:true"),
            discord.SelectOption(label="🚨 Anti-Raid: OFF",       value="anti_raid:false"),
            discord.SelectOption(label="🚫 Warn Action → Mute",   value="warn_action:mute"),
            discord.SelectOption(label="🚫 Warn Action → Kick",   value="warn_action:kick"),
            discord.SelectOption(label="🚫 Warn Action → Ban",    value="warn_action:ban"),
        ]
    )
    async def toggle_setting(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not is_admin(interaction.user):
            await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True)
            return
        key, val = select.values[0].split(":", 1)
        bool_keys = ["enabled","ban_bad_links","ban_invite_links","anti_nuke","anti_spam","anti_caps","anti_mass_mention","anti_raid"]
        if key in bool_keys:
            config["automod"][key] = val == "true"
        else:
            config["automod"][key] = val
        save_json(CONFIG_FILE, config)
        await interaction.response.send_message(embed=success_embed("AutoMod Updated", f"`{key}` → `{val}`"), view=NavView())

# ── Poll view ──
class PollModal(discord.ui.Modal, title="📊 Create Poll"):
    question = discord.ui.TextInput(label="Question", max_length=256)
    options  = discord.ui.TextInput(label="Options (separated by |)", placeholder="Yes | No | Maybe", max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        opts = [o.strip() for o in self.options.value.split("|")][:10]
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        e = discord.Embed(title=f"📊 {self.question.value}", color=0x9b59b6)
        e.description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(opts))
        e.set_footer(text=f"Poll by {interaction.user}")
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for i in range(len(opts)):
            await msg.add_reaction(emojis[i])

# ── Giveaway modal ──
class GiveawayModal(discord.ui.Modal, title="🎉 Start Giveaway"):
    prize    = discord.ui.TextInput(label="Prize", max_length=256)
    duration = discord.ui.TextInput(label="Duration (minutes)", default="60", max_length=5)
    winners  = discord.ui.TextInput(label="Number of winners", default="1", max_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mins = max(1, int(self.duration.value))
            w    = max(1, int(self.winners.value))
        except:
            mins, w = 60, 1
        end_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=mins)
        e = discord.Embed(title="🎉 GIVEAWAY!", color=0xe91e63)
        e.description = f"**Prize:** {self.prize.value}\n**Winners:** {w}\n**Ends:** {discord.utils.format_dt(end_time,'R')}\n\nReact with 🎉 to enter!"
        e.set_footer(text=f"Hosted by {interaction.user}")
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")
        await asyncio.sleep(mins * 60)
        msg = await interaction.channel.fetch_message(msg.id)
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        if reaction:
            users = [u async for u in reaction.users() if not u.bot]
            if users:
                winners_list = random.sample(users, min(w, len(users)))
                mentions = ", ".join(u.mention for u in winners_list)
                await interaction.channel.send(embed=discord.Embed(title="🎉 Giveaway Ended!", description=f"Winners: {mentions}\n**Prize:** {self.prize.value}", color=0xe91e63))
            else:
                await interaction.channel.send("No one entered the giveaway.")

# ─── AUTO MODERATION ─────────────────────────────────────────────────────────

BAD_LINK_PATTERNS = [
    r"(discord\.gg|discordapp\.com/invite)/[a-zA-Z0-9]+",
    r"(grabify|iplogger|bmwforum|yip\.su|2no\.co|lovebird\.guru|stopify\.co)",
    r"(pornhub|xvideos|xnxx|onlyfans)",
    r"(phishing|free-nitro|discord-nitro-free|steamgift)",
    r"(nitro.*free|free.*nitro)",
]

async def log_automod(guild, action, user, reason, channel=None):
    inc_automod(action.lower().replace(" ","_"))
    ch_id = config.get("mod_log_channel") or config.get("log_channel")
    if not ch_id: return
    ch = guild.get_channel(ch_id)
    if not ch: return
    e = discord.Embed(title=f"🤖 AutoMod: {action}", color=0xff6b35)
    e.add_field(name="User",   value=f"{user.mention} ({user.id})")
    e.add_field(name="Reason", value=reason)
    if channel: e.add_field(name="Channel", value=channel.mention)
    e.timestamp = datetime.datetime.utcnow()
    await ch.send(embed=e)

async def add_warning(guild, user, reason, moderator):
    uid = str(user.id)
    if uid not in warnings:
        warnings[uid] = []
    warnings[uid].append({"reason": reason, "moderator": str(moderator), "time": datetime.datetime.utcnow().isoformat()})
    save_json(WARNINGS_FILE, warnings)
    count   = len(warnings[uid])
    max_w   = config["automod"].get("max_warnings", 3)
    action  = config["automod"].get("warn_action",  "mute")
    if count >= max_w:
        try:
            if action == "ban":
                await guild.ban(user,   reason=f"Auto-ban: {count} warnings")
            elif action == "kick":
                await guild.kick(user,  reason=f"Auto-kick: {count} warnings")
            elif action == "mute":
                dur   = config["automod"].get("mute_duration", 10)
                until = datetime.datetime.utcnow() + datetime.timedelta(minutes=dur)
                m     = guild.get_member(user.id)
                if m: await m.timeout(until, reason=f"Auto-mute: {count} warnings")
        except: pass
    return count

@bot.event
async def on_message(message):
    if message.author.bot: return
    if not message.guild:
        await handle_dm(message); return

    automod = config.get("automod", {})
    if not automod.get("enabled", True):
        await bot.process_commands(message); return

    member  = message.author
    content = message.content.lower()

    bot_ch_id = config.get("bot_commands_channel")
    if bot_ch_id and message.channel.id != bot_ch_id:
        if message.content.startswith(bot.command_prefix) and not is_staff(member):
            await message.delete()
            return

    cnt_ch_id = config.get("counting_channel")
    if cnt_ch_id and message.channel.id == cnt_ch_id:
        await handle_counting(message); return

    if automod.get("ban_bad_links", True):
        for pattern in BAD_LINK_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                whitelist = automod.get("whitelist_links", [])
                if not any(w in content for w in whitelist):
                    await message.delete()
                    cnt = await add_warning(message.guild, member, "Bad/unsafe link", "AutoMod")
                    await log_automod(message.guild, "Bad Link Removed", member, f"Pattern: {pattern}", message.channel)
                    try: await member.send(embed=error_embed("Link Removed", f"Blocked link detected. Warning #{cnt}."))
                    except: pass
                    await bot.process_commands(message); return

    if automod.get("ban_invite_links", True) and not is_staff(member):
        if re.search(r"discord\.(gg|io|me|li)/[a-zA-Z0-9]+", content):
            await message.delete()
            await add_warning(message.guild, member, "Discord invite link", "AutoMod")
            await log_automod(message.guild, "Invite Link", member, "Sent invite link", message.channel)
            return

    if automod.get("anti_caps", True) and len(message.content) > 10:
        caps_ratio = sum(1 for c in message.content if c.isupper()) / len(message.content)
        if caps_ratio > automod.get("caps_threshold", 0.7):
            await message.delete()
            await message.channel.send(f"{member.mention} ⚠️ Please don't use excessive caps.", delete_after=5)
            return

    if automod.get("anti_mass_mention", True) and len(message.mentions) > automod.get("max_mentions", 5):
        await message.delete()
        await add_warning(message.guild, member, "Mass mention", "AutoMod")
        await log_automod(message.guild, "Mass Mention", member, f"{len(message.mentions)} mentions", message.channel)
        return

    if automod.get("anti_spam", True):
        now = time.time()
        uid = member.id
        spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < 5]
        spam_tracker[uid].append(now)
        if len(spam_tracker[uid]) > automod.get("spam_threshold", 5):
            await message.delete()
            await add_warning(message.guild, member, "Spamming", "AutoMod")
            await log_automod(message.guild, "Spam Detected", member, f"{len(spam_tracker[uid])} msgs/5s", message.channel)
            spam_tracker[uid] = []
            return

    for word in automod.get("bad_words", []):
        if word.lower() in content:
            await message.delete()
            await message.channel.send(f"{member.mention} ⚠️ Inappropriate language.", delete_after=5)
            await add_warning(message.guild, member, f"Bad word: {word}", "AutoMod")
            return

    await bot.process_commands(message)

async def handle_counting(message):
    try: num = int(message.content.strip())
    except:
        await message.delete()
        await message.channel.send(f"{message.author.mention} Only numbers allowed!", delete_after=5); return
    expected = counting["count"] + 1
    if num != expected:
        await message.delete()
        await message.channel.send(f"❌ {message.author.mention} broke the count! Next was **{expected}**. Restarting.", delete_after=8)
        counting["count"] = 0; counting["last_user"] = None
    elif counting.get("last_user") == message.author.id:
        await message.delete()
        await message.channel.send(f"❌ {message.author.mention} can't count twice in a row!", delete_after=5); return
    else:
        counting["count"] = num; counting["last_user"] = message.author.id
        await message.add_reaction("🎉" if num % 100 == 0 else "✅")
    save_json(COUNTING_FILE, counting)

async def handle_dm(message):
    staff_ch_id = config.get("staff_channel"); guild = bot.get_guild(config.get("guild_id"))
    if not staff_ch_id or not guild: return
    ch = guild.get_channel(staff_ch_id)
    if not ch: return
    e = discord.Embed(title="📩 New DM", color=0x9b59b6)
    e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    e.add_field(name="User ID", value=message.author.id)
    e.description = message.content
    if message.attachments:
        e.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments))
    e.set_footer(text=f"Reply: /dmreply {message.author.id} <msg>")
    await ch.send(embed=e)

# ─── ANTI-NUKE ────────────────────────────────────────────────────────────────

@bot.event
async def on_guild_channel_delete(channel):
    if not config["automod"].get("anti_nuke"): return
    now = time.time()
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        uid = entry.user.id
        nuke_tracker[uid] = [t for t in nuke_tracker[uid] if now - t < 10]
        nuke_tracker[uid].append(now)
        if len(nuke_tracker[uid]) >= 3:
            member = channel.guild.get_member(uid)
            if member and not member.guild_permissions.administrator:
                await channel.guild.ban(member, reason="Anti-Nuke: Mass channel deletion")
                await log_automod(channel.guild, "NUKE ATTEMPT BLOCKED", member, "Mass channel deletion")

@bot.event
async def on_member_ban(guild, user):
    if not config["automod"].get("anti_nuke"): return
    now = time.time()
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        uid = entry.user.id
        key = f"ban_{uid}"
        nuke_tracker[key] = [t for t in nuke_tracker.get(key,[]) if now - t < 10]
        nuke_tracker[key].append(now)
        if len(nuke_tracker[key]) >= 5:
            member = guild.get_member(uid)
            if member and not member.guild_permissions.administrator:
                await guild.ban(member, reason="Anti-Nuke: Mass banning")
                await log_automod(guild, "MASS BAN BLOCKED", member, "Mass ban attempt")

@bot.event
async def on_member_join(member):
    if config["automod"].get("anti_raid"):
        now = time.time()
        raid_tracker.append((member.id, now))
        recent = [t for _, t in raid_tracker if now - t < 10]
        if len(recent) >= 10:
            ch_id = config.get("mod_log_channel")
            if ch_id:
                ch = member.guild.get_channel(ch_id)
                if ch:
                    await ch.send(embed=discord.Embed(title="🚨 RAID ALERT", description="10+ users joined in 10 seconds!", color=0xff0000))
    welcome_ch = config.get("welcome_channel")
    if welcome_ch:
        ch = member.guild.get_channel(welcome_ch)
        if ch:
            e = discord.Embed(title=f"👋 Welcome to {member.guild.name}!", description=f"Hey {member.mention}, welcome!", color=0x2ecc71)
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)

@bot.event
async def on_member_update(before, after):
    if config.get("nickname_logs") and before.nick != after.nick:
        ch_id = config.get("log_channel")
        if ch_id:
            ch = after.guild.get_channel(ch_id)
            if ch:
                e = discord.Embed(title="📝 Nickname Changed", color=0xf39c12)
                e.add_field(name="User",   value=after.mention)
                e.add_field(name="Before", value=before.nick or "None")
                e.add_field(name="After",  value=after.nick  or "None")
                await ch.send(embed=e)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild: return
    ch_id = config.get("log_channel")
    if ch_id:
        ch = message.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="🗑️ Message Deleted", color=0xe74c3c)
            e.add_field(name="Author",  value=message.author.mention)
            e.add_field(name="Channel", value=message.channel.mention)
            e.description = message.content or "*(no text)*"
            await ch.send(embed=e)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content or not before.guild: return
    ch_id = config.get("log_channel")
    if ch_id:
        ch = before.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="✏️ Message Edited", color=0xf39c12)
            e.add_field(name="Author",  value=before.author.mention)
            e.add_field(name="Channel", value=before.channel.mention)
            e.add_field(name="Before",  value=before.content[:500] or "*empty*", inline=False)
            e.add_field(name="After",   value=after.content[:500]  or "*empty*", inline=False)
            await ch.send(embed=e)

# ═══════════════════════════════════════════════════════════════════════════════
#  SLASH COMMANDS  (UI-driven with select menus & modals)
# ═══════════════════════════════════════════════════════════════════════════════

# ── /mod — unified moderation panel ──
@tree.command(name="mod", description="[STAFF] Open the moderation action panel")
async def mod(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    view = ModActionSelect()
    await interaction.response.send_message("**🛡️ Moderation Panel** — Select a user, then choose an action.", view=view, ephemeral=True)

# ── /channel — channel management ──
@tree.command(name="channel", description="[STAFF] Open the channel management panel")
async def channel_cmd(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    view = ChannelActionView()
    await interaction.response.send_message("**📡 Channel Panel** — Select a channel, then choose an action.", view=view, ephemeral=True)

# ── /role — role management ──
@tree.command(name="role", description="[ADMIN] Add or remove a role from a user")
async def role_cmd(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    view = RoleActionView()
    await interaction.response.send_message("**🎭 Role Manager** — Select user → role → action.", view=view, ephemeral=True)

# ── /automod — automod panel ──
@tree.command(name="automod", description="[ADMIN] Configure AutoMod settings")
async def automod_cmd(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    view = AutomodToggleView()
    await interaction.response.send_message("**🤖 AutoMod Settings** — Pick a setting to toggle.", view=view, ephemeral=True)

# ── /poll ──
@tree.command(name="poll", description="Create an interactive poll")
async def poll(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    await interaction.response.send_modal(PollModal())

# ── /giveaway ──
@tree.command(name="giveaway", description="[STAFF] Start a giveaway")
async def giveaway(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    await interaction.response.send_modal(GiveawayModal())

# ── /announce ──
@tree.command(name="announce", description="[ADMIN] Send an announcement")
@app_commands.describe(channel="Channel to announce in")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    await interaction.response.send_modal(AnnounceModal(channel))

# ── /embed ──
@tree.command(name="embed", description="[STAFF] Send a custom embed")
@app_commands.describe(channel="Channel to send in")
async def send_embed(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    await interaction.response.send_modal(EmbedModal(channel))

# ── /purge ──
@tree.command(name="purge", description="[STAFF] Bulk delete messages")
async def purge(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    await interaction.response.send_modal(PurgeModal())

# ── /lockdown / unlockdown ──
@tree.command(name="lockdown", description="[ADMIN] Lock ALL channels")
async def lockdown(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except: pass
    await interaction.followup.send(embed=success_embed("🚨 SERVER LOCKDOWN", f"Locked {count} channels."), view=NavView())

@tree.command(name="unlockdown", description="[ADMIN] Unlock ALL channels")
async def unlockdown(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = True
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except: pass
    await interaction.followup.send(embed=success_embed("Lockdown Lifted", f"Unlocked {count} channels."), view=NavView())

# ── /timer ──
@tree.command(name="timer", description="Set a reminder/timer")
@app_commands.describe(minutes="Minutes until reminder", message="Reminder message")
async def timer(interaction: discord.Interaction, minutes: int, message: str = "Your timer is up!"):
    if minutes > 1440:
        await interaction.response.send_message(embed=error_embed("Too Long","Max 1440 minutes."), ephemeral=True); return
    await interaction.response.send_message(embed=success_embed("Timer Set", f"Reminding in **{minutes}m**: {message}"), view=NavView())
    await asyncio.sleep(minutes * 60)
    try:
        await interaction.user.send(embed=discord.Embed(title="⏰ Timer Up!", description=message, color=0x2ecc71))
        await interaction.channel.send(f"⏰ {interaction.user.mention} — {message}")
    except: pass

@tree.command(name="remindme", description="Set a personal reminder")
@app_commands.describe(time_str="e.g. 10m 2h 1d", reminder="What to remind you about")
async def remindme(interaction: discord.Interaction, time_str: str, reminder: str):
    multipliers = {"m":60,"h":3600,"d":86400}
    try:
        unit    = time_str[-1].lower()
        amount  = int(time_str[:-1])
        seconds = amount * multipliers[unit]
    except:
        await interaction.response.send_message(embed=error_embed("Invalid Format","Use `10m`, `2h`, `1d`"), ephemeral=True); return
    await interaction.response.send_message(embed=success_embed("Reminder Set", f"**{reminder}** in **{time_str}**"), view=NavView())
    await asyncio.sleep(seconds)
    try: await interaction.user.send(embed=discord.Embed(title="🔔 Reminder!", description=reminder, color=0x9b59b6))
    except: await interaction.channel.send(f"🔔 {interaction.user.mention} Reminder: **{reminder}**")

# ── /staff ──
@tree.command(name="staff", description="Access the staff panel (requires daily code)")
@app_commands.describe(code="Today's staff code")
async def staff_panel(interaction: discord.Interaction, code: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("Access Denied","Not a staff member."), ephemeral=True); return
    if not check_daily_code(interaction.user.id, code):
        await interaction.response.send_message(embed=error_embed("Invalid Code","Wrong daily code."), ephemeral=True); return
    e = discord.Embed(title="🛡️ Staff Control Panel", color=0x9b59b6)
    e.add_field(name="🎛️ Moderation",   value="`/mod` (unified panel)\n`/channel` (channel panel)\n`/lockdown` `/unlockdown`", inline=False)
    e.add_field(name="🎭 Roles",         value="`/role` (add/remove roles)", inline=False)
    e.add_field(name="⚙️ AutoMod",       value="`/automod` (toggle settings)", inline=False)
    e.add_field(name="📢 Announcements", value="`/announce` `/embed` `/poll` `/giveaway`", inline=False)
    e.add_field(name="📊 Info",          value="`/userinfo` `/serverinfo` `/auditlog` `/stafflist`", inline=False)
    e.add_field(name="📩 Messages",      value="`/dmreply` `/broadcast`", inline=False)
    dash = config.get("dashboard","https://yourdashboard.com")
    e.add_field(name="🔗 Links", value=f"[Dashboard]({dash})", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True, view=NavView())

@tree.command(name="generatecode", description="[OWNER] Generate today's staff code")
async def generate_code(interaction: discord.Interaction):
    if interaction.user.id != config.get("owner_id"):
        await interaction.response.send_message(embed=error_embed("Forbidden","Owner only."), ephemeral=True); return
    code  = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    today = get_today_str()
    config.setdefault("daily_codes", {})[today] = code
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=discord.Embed(title="🔐 Code Generated", description=f"**Date:** {today}\n**Code:** `{code}`", color=0x2ecc71), ephemeral=True)
    for member in interaction.guild.members:
        if is_staff(member) and not member.bot:
            try: await member.send(embed=discord.Embed(title="🔐 Today's Staff Code", description=f"**{today}**\nCode: `{code}`\nUse `/staff {code}`", color=0x9b59b6))
            except: pass

# ── INFO COMMANDS ──
@tree.command(name="userinfo", description="View info about a user")
@app_commands.describe(user="User to look up")
async def userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    e = discord.Embed(title=f"👤 {user}", color=user.color)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="ID",       value=user.id)
    e.add_field(name="Nickname", value=user.nick or "None")
    e.add_field(name="Joined",   value=discord.utils.format_dt(user.joined_at,"R") if user.joined_at else "?")
    e.add_field(name="Created",  value=discord.utils.format_dt(user.created_at,"R"))
    e.add_field(name="Roles",    value=" ".join(r.mention for r in user.roles[1:]) or "None", inline=False)
    e.add_field(name="Warnings", value=len(warnings.get(str(user.id),[])))
    e.add_field(name="Is Staff", value="✅" if is_staff(user) else "❌")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="serverinfo", description="View server information")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    e = discord.Embed(title=f"🏠 {g.name}", color=0x3498db)
    e.set_thumbnail(url=g.icon.url if g.icon else None)
    e.add_field(name="Owner",    value=g.owner.mention if g.owner else "?")
    e.add_field(name="Members",  value=g.member_count)
    e.add_field(name="Channels", value=len(g.channels))
    e.add_field(name="Roles",    value=len(g.roles))
    e.add_field(name="Boosts",   value=g.premium_subscription_count)
    e.add_field(name="Created",  value=discord.utils.format_dt(g.created_at,"R"))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="avatar", description="View a user's avatar")
@app_commands.describe(user="User to view")
async def avatar(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    e = discord.Embed(title=f"🖼️ {user}'s Avatar", color=0x3498db)
    e.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="stafflist", description="View all staff members")
async def stafflist(interaction: discord.Interaction):
    staff_ids = set(config.get("staff_roles",[]) + config.get("admin_roles",[]) + config.get("mod_roles",[]))
    members_list = [f"• {m.mention} ({', '.join(r.name for r in m.roles if r.id in staff_ids)})"
                    for m in interaction.guild.members if any(r.id in staff_ids for r in m.roles)]
    e = discord.Embed(title="👥 Staff List", color=0x3498db)
    e.description = "\n".join(members_list) if members_list else "No staff members found."
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="auditlog", description="[STAFF] View recent audit log")
@app_commands.describe(limit="Number of entries (max 20)")
async def auditlog(interaction: discord.Interaction, limit: int = 10):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    limit = min(limit, 20)
    entries = []
    async for entry in interaction.guild.audit_logs(limit=limit):
        entries.append(f"• **{entry.action.name}** by {entry.user.mention} — {discord.utils.format_dt(entry.created_at,'R')}")
    e = discord.Embed(title="📋 Audit Log", color=0x3498db, description="\n".join(entries) or "No entries.")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(embed=discord.Embed(title="🏓 Pong!", description=f"Latency: **{round(bot.latency*1000)}ms**", color=0x2ecc71), view=NavView())

@tree.command(name="botinfo", description="View bot information")
async def botinfo(interaction: discord.Interaction):
    e = discord.Embed(title="🤖 UltraBot", color=0x9b59b6)
    e.add_field(name="Guilds",   value=len(bot.guilds))
    e.add_field(name="Latency",  value=f"{round(bot.latency*1000)}ms")
    e.add_field(name="Features", value="AutoMod, Anti-Nuke, AI, Staff System, Counting, Timers")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="help", description="View all commands")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(title="📚 UltraBot Commands", color=0x9b59b6)
    e.add_field(name="🛡️ Moderation",   value="`/mod` `/channel` `/role` `/lockdown` `/unlockdown`", inline=False)
    e.add_field(name="🤖 AutoMod",       value="`/automod` (menu-driven)", inline=False)
    e.add_field(name="📢 Community",     value="`/poll` `/giveaway` `/announce` `/embed`", inline=False)
    e.add_field(name="⏰ Timers",        value="`/timer` `/remindme`", inline=False)
    e.add_field(name="🎮 Roblox / AI",   value="`/ask` `/clearai` `/roblox` `/portfolio`", inline=False)
    e.add_field(name="📊 Info",          value="`/userinfo` `/serverinfo` `/avatar` `/stafflist` `/ping`", inline=False)
    e.add_field(name="🎉 Fun",           value="`/coinflip` `/8ball` `/dice` `/choose`", inline=False)
    e.add_field(name="📋 Utility",       value="`/report` `/bugreport` `/suggest` `/feedback` `/note` `/notes`", inline=False)
    e.add_field(name="⚙️ Config (Admin)",value="`/config` `/setlog` `/setmodlog` `/setwelcome` `/setreport`\n`/setbotchannel` `/setcounting` `/setstaff` `/addstaffrole` `/addadminrole`\n`/addbadword` `/removebadword` `/setwebsite` `/setdashboard`", inline=False)
    e.add_field(name="🔐 Owner",         value="`/generatecode` `/setowner`", inline=False)
    await interaction.response.send_message(embed=e, view=NavView())

# ── FUN ──
@tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(embed=info_embed("Coin Flip", random.choice(["Heads 🪙","Tails 🪙"]), color=0xf1c40f), view=NavView())

@tree.command(name="8ball", description="Ask the magic 8 ball")
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    answers = ["It is certain ✅","Without a doubt ✅","Yes ✅","Most likely ✅","Signs point to yes ✅",
               "Ask again later ⚠️","Cannot predict now ⚠️","Better not tell you now ⚠️",
               "Don't count on it ❌","My reply is no ❌","Very doubtful ❌"]
    e = discord.Embed(title="🎱 Magic 8 Ball", color=0x1a1a2e)
    e.add_field(name="Question", value=question)
    e.add_field(name="Answer",   value=random.choice(answers))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="dice", description="Roll some dice")
@app_commands.describe(sides="Sides (default 6)", count="Number of dice (default 1)")
async def dice(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    rolls = [random.randint(1, sides) for _ in range(min(count, 20))]
    e = discord.Embed(title=f"🎲 Rolled {count}d{sides}", color=0x9b59b6)
    e.add_field(name="Results", value=" + ".join(str(r) for r in rolls))
    e.add_field(name="Total",   value=sum(rolls))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="choose", description="Choose between options")
@app_commands.describe(options="Options separated by | (e.g. pizza|burger|tacos)")
async def choose(interaction: discord.Interaction, options: str):
    opts   = [o.strip() for o in options.split("|")]
    choice = random.choice(opts)
    e = discord.Embed(title="🎯 I Choose…", description=f"**{choice}**", color=0xe67e22)
    e.add_field(name="From", value=" • ".join(opts))
    await interaction.response.send_message(embed=e, view=NavView())

# ── REPORT / NOTE / FEEDBACK ──
@tree.command(name="report", description="Report a user")
@app_commands.describe(user="User to report", reason="Reason")
async def report_user(interaction: discord.Interaction, user: discord.Member, reason: str):
    reports["users"].append({"type":"user","reporter":str(interaction.user),"reporter_id":interaction.user.id,
                              "reported":str(user),"reported_id":user.id,"reason":reason,
                              "time":datetime.datetime.utcnow().isoformat()})
    save_json(REPORTS_FILE, reports)
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="🚨 User Report", color=0xe74c3c)
            e.add_field(name="Reporter", value=interaction.user.mention)
            e.add_field(name="Reported", value=user.mention)
            e.add_field(name="Reason",   value=reason, inline=False)
            await ch.send(embed=e)
    await interaction.response.send_message(embed=success_embed("Report Submitted","Staff will review this."), ephemeral=True, view=NavView())

@tree.command(name="bugreport", description="Report a bug")
async def bugreport(interaction: discord.Interaction):
    await interaction.response.send_modal(BugReportModal())

@tree.command(name="feedback", description="Submit server feedback")
@app_commands.describe(feedback="Your feedback")
async def feedback(interaction: discord.Interaction, feedback: str):
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="💬 Feedback", color=0x2ecc71)
            e.add_field(name="From",     value=interaction.user.mention)
            e.add_field(name="Feedback", value=feedback, inline=False)
            await ch.send(embed=e)
    await interaction.response.send_message(embed=success_embed("Feedback Sent","Thank you!"), ephemeral=True, view=NavView())

@tree.command(name="suggest", description="Submit a suggestion")
@app_commands.describe(suggestion="Your suggestion")
async def suggest(interaction: discord.Interaction, suggestion: str):
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="💡 Suggestion", color=0xf1c40f)
            e.add_field(name="From",       value=interaction.user.mention)
            e.add_field(name="Suggestion", value=suggestion, inline=False)
            msg = await ch.send(embed=e)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
    await interaction.response.send_message(embed=success_embed("Suggestion Submitted","Your idea has been sent!"), ephemeral=True, view=NavView())

@tree.command(name="note", description="[STAFF] Add a note about a user")
@app_commands.describe(user="Target user", note="The note")
async def add_note(interaction: discord.Interaction, user: discord.Member, note: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    uid = str(user.id)
    notes.setdefault(uid, []).append({"note": note,"by": str(interaction.user),"time": datetime.datetime.utcnow().isoformat()})
    save_json(NOTES_FILE, notes)
    await interaction.response.send_message(embed=success_embed("Note Added", f"Note added for {user.mention}."), ephemeral=True)

@tree.command(name="notes", description="[STAFF] View notes about a user")
@app_commands.describe(user="Target user")
async def view_notes(interaction: discord.Interaction, user: discord.Member):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    uid = str(user.id)
    user_notes = notes.get(uid, [])
    if not user_notes:
        await interaction.response.send_message(embed=info_embed("No Notes", f"No notes for {user.mention}."), ephemeral=True); return
    e = discord.Embed(title=f"📝 Notes for {user}", color=0xf39c12)
    for i, n in enumerate(user_notes, 1):
        e.add_field(name=f"#{i} by {n['by']}", value=f"{n['note']}\n*{n['time'][:10]}*", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

# ── DM COMMANDS ──
@tree.command(name="dmreply", description="[STAFF] Reply to a user's DM")
@app_commands.describe(user_id="User ID", message="Reply message")
async def dm_reply(interaction: discord.Interaction, user_id: str, message: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Staff only."), ephemeral=True); return
    try:
        user = await bot.fetch_user(int(user_id))
        e = discord.Embed(title=f"📩 Staff Reply from {interaction.guild.name}", description=message, color=0x9b59b6)
        await user.send(embed=e)
        await interaction.response.send_message(embed=success_embed("Replied", f"Sent to {user}."), ephemeral=True)
    except Exception as ex:
        await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

@tree.command(name="broadcast", description="[ADMIN] DM all members")
@app_commands.describe(message="Message to broadcast")
async def broadcast(interaction: discord.Interaction, message: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    sent = failed = 0
    for member in interaction.guild.members:
        if not member.bot:
            try:
                e = discord.Embed(title=f"📢 Broadcast from {interaction.guild.name}", description=message, color=0xe67e22)
                await member.send(embed=e)
                sent += 1
            except: failed += 1
    await interaction.followup.send(embed=success_embed("Broadcast", f"Sent: {sent} | Failed: {failed}"), ephemeral=True)

# ── PREMIUM ──
@tree.command(name="premium", description="Check premium status")
async def check_premium(interaction: discord.Interaction):
    uid    = str(interaction.user.id)
    is_prem= uid in premium
    e = discord.Embed(title="⭐ Premium Status", color=0xf1c40f if is_prem else 0x95a5a6)
    e.description = f"**Status:** {'⭐ Premium' if is_prem else '🔒 Standard'}"
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="addpremium", description="[ADMIN] Grant premium to a user")
@app_commands.describe(user="User to grant premium")
async def add_premium(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user): return
    premium[str(user.id)] = {"granted_by": str(interaction.user), "time": datetime.datetime.utcnow().isoformat()}
    save_json(PREMIUM_USERS_FILE, premium)
    await interaction.response.send_message(embed=success_embed("Premium Added", f"{user.mention} has premium."), view=NavView())

@tree.command(name="removepremium", description="[ADMIN] Remove premium from a user")
@app_commands.describe(user="User to remove premium from")
async def remove_premium(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user): return
    premium.pop(str(user.id), None)
    save_json(PREMIUM_USERS_FILE, premium)
    await interaction.response.send_message(embed=success_embed("Premium Removed", f"{user.mention}'s premium removed."), view=NavView())

# ── ROBLOX / AI ──
ai_conversations = {}

@tree.command(name="ask", description="Ask the Roblox AI assistant")
@app_commands.describe(question="Your Roblox-related question")
async def ask_ai(interaction: discord.Interaction, question: str):
    if not config["ai"].get("enabled", True):
        await interaction.response.send_message(embed=error_embed("AI Disabled","AI is currently off."), ephemeral=True); return
    roblox_keywords = ["roblox","robux","studio","game","avatar","ugc","developer","script","lua","badge","pass",
                       "gamepass","group","place","experience","npc","tool","datastore","remote","bindable",
                       "module","localscript","serverscript","animation","morph","model","plugin","leaderboard"]
    if config["ai"].get("roblox_only", True):
        if not any(kw in question.lower() for kw in roblox_keywords):
            await interaction.response.send_message(embed=error_embed("Off-Topic","I only answer Roblox-related questions!"), ephemeral=True); return
    await interaction.response.defer()
    uid = str(interaction.user.id)
    roblox_context = "You are RobloxBot, an expert Roblox assistant. Answer ONLY Roblox questions (Studio, Lua, avatars, DataStore, etc.). Format code in code blocks."
    ai_conversations.setdefault(uid, [])
    ai_conversations[uid].append({"role":"user","content":question})
    if len(ai_conversations[uid]) > 20:
        ai_conversations[uid] = ai_conversations[uid][-20:]
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"model":"claude-sonnet-4-20250514","max_tokens":1000,"system":roblox_context,"messages":ai_conversations[uid]}
            headers = {"x-api-key":os.environ.get("ANTHROPIC_API_KEY",""),"anthropic-version":"2023-06-01","content-type":"application/json"}
            async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers) as resp:
                data   = await resp.json()
                answer = data["content"][0]["text"]
        ai_conversations[uid].append({"role":"assistant","content":answer})
        e = discord.Embed(title="🤖 Roblox AI", color=0xff4444)
        e.add_field(name="❓ Question", value=question,        inline=False)
        e.add_field(name="💡 Answer",   value=answer[:1000],   inline=False)
        e.set_footer(text=f"Asked by {interaction.user}")
        await interaction.followup.send(embed=e, view=NavView())
    except Exception as ex:
        await interaction.followup.send(embed=error_embed("AI Error", str(ex)))

@tree.command(name="clearai", description="Clear your AI conversation history")
async def clear_ai(interaction: discord.Interaction):
    ai_conversations.pop(str(interaction.user.id), None)
    await interaction.response.send_message(embed=success_embed("Cleared","AI history cleared."), ephemeral=True)

@tree.command(name="portfolio", description="View a Roblox portfolio")
@app_commands.describe(user_id="Roblox User ID", image_url="Optional portfolio image URL")
async def portfolio(interaction: discord.Interaction, user_id: str, image_url: str = None):
    obf  = obfuscate_roblox_link(user_id)
    base = config.get("roblox_portfolio","https://www.roblox.com/users/")
    e = discord.Embed(title="🎮 Roblox Portfolio", color=0xff4444)
    e.add_field(name="Profile",       value=f"[View Profile]({base}{user_id}/profile)", inline=False)
    e.add_field(name="Portfolio ID",  value=f"`{obf}`", inline=True)
    if image_url: e.set_image(url=image_url)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="roblox", description="Look up a Roblox user")
@app_commands.describe(username="Roblox username")
async def roblox_lookup(interaction: discord.Interaction, username: str):
    e = discord.Embed(title=f"🎮 Roblox: {username}", color=0xff4444)
    e.add_field(name="Search",      value=f"[Search](https://www.roblox.com/search/users?keyword={username})")
    e.add_field(name="Direct Link", value=f"[Profile](https://www.roblox.com/user.aspx?username={username})")
    await interaction.response.send_message(embed=e, view=NavView())

# ── CONFIG COMMANDS ──
@tree.command(name="config", description="[ADMIN] View bot configuration")
async def view_config(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission","Admin only."), ephemeral=True); return
    e = discord.Embed(title="⚙️ Bot Configuration", color=0x3498db)
    for key, label in [("log_channel","Log"), ("mod_log_channel","Mod Log"), ("welcome_channel","Welcome"),
                        ("report_channel","Reports"), ("bot_commands_channel","Bot Commands"), ("counting_channel","Counting")]:
        ch = interaction.guild.get_channel(config.get(key) or 0)
        e.add_field(name=label, value=ch.mention if ch else "Not set")
    e.add_field(name="AutoMod",   value="✅" if config["automod"]["enabled"]   else "❌")
    e.add_field(name="Anti-Nuke", value="✅" if config["automod"]["anti_nuke"] else "❌")
    e.add_field(name="Anti-Raid", value="✅" if config["automod"]["anti_raid"] else "❌")
    await interaction.response.send_message(embed=e, view=NavView())

def _make_set_channel_cmd(name, desc, config_key):
    @tree.command(name=name, description=desc)
    @app_commands.describe(channel="Target channel")
    async def _cmd(interaction: discord.Interaction, channel: discord.TextChannel):
        if not is_admin(interaction.user): return
        config[config_key] = channel.id
        save_json(CONFIG_FILE, config)
        await interaction.response.send_message(embed=success_embed(f"{name} Set", f"{channel.mention}"), view=NavView())
    return _cmd

_make_set_channel_cmd("setlog",        "[ADMIN] Set log channel",          "log_channel")
_make_set_channel_cmd("setmodlog",     "[ADMIN] Set mod log channel",      "mod_log_channel")
_make_set_channel_cmd("setwelcome",    "[ADMIN] Set welcome channel",      "welcome_channel")
_make_set_channel_cmd("setreport",     "[ADMIN] Set report channel",       "report_channel")
_make_set_channel_cmd("setbotchannel", "[ADMIN] Set bot commands channel", "bot_commands_channel")
_make_set_channel_cmd("setcounting",   "[ADMIN] Set counting channel",     "counting_channel")
_make_set_channel_cmd("setstaff",      "[ADMIN] Set staff channel",        "staff_channel")

@tree.command(name="addstaffrole", description="[ADMIN] Add a staff role")
@app_commands.describe(role="Staff role")
async def add_staff_role(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user): return
    if role.id not in config["staff_roles"]:
        config["staff_roles"].append(role.id); save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Staff Role Added", f"{role.mention} added."), view=NavView())

@tree.command(name="addadminrole", description="[ADMIN] Add an admin role")
@app_commands.describe(role="Admin role")
async def add_admin_role(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user): return
    if role.id not in config["admin_roles"]:
        config["admin_roles"].append(role.id); save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Admin Role Added", f"{role.mention} added."), view=NavView())

@tree.command(name="addbadword", description="[ADMIN] Add a word to the filter")
@app_commands.describe(word="Word to filter")
async def add_bad_word(interaction: discord.Interaction, word: str):
    if not is_admin(interaction.user): return
    if word.lower() not in config["automod"]["bad_words"]:
        config["automod"]["bad_words"].append(word.lower()); save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Word Added", f"`{word}` added."), ephemeral=True)

@tree.command(name="removebadword", description="[ADMIN] Remove a word from the filter")
@app_commands.describe(word="Word to remove")
async def remove_bad_word(interaction: discord.Interaction, word: str):
    if not is_admin(interaction.user): return
    if word.lower() in config["automod"]["bad_words"]:
        config["automod"]["bad_words"].remove(word.lower()); save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Word Removed", f"`{word}` removed."), ephemeral=True)

@tree.command(name="setwebsite", description="[OWNER] Set the website URL")
@app_commands.describe(url="Website URL")
async def set_website(interaction: discord.Interaction, url: str):
    if interaction.user.id != config.get("owner_id"): return
    config["website"] = url; save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Website Set", url), ephemeral=True)

@tree.command(name="setdashboard", description="[OWNER] Set the dashboard URL")
@app_commands.describe(url="Dashboard URL")
async def set_dashboard(interaction: discord.Interaction, url: str):
    if interaction.user.id != config.get("owner_id"): return
    config["dashboard"] = url; save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Dashboard Set", url), ephemeral=True)

@tree.command(name="setowner", description="[FIRST RUN] Set yourself as bot owner")
async def set_owner(interaction: discord.Interaction):
    if config.get("owner_id"):
        await interaction.response.send_message(embed=error_embed("Already Set","Owner already configured."), ephemeral=True); return
    config["owner_id"] = interaction.user.id; config["guild_id"] = interaction.guild.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Owner Set", f"{interaction.user.mention} is now the owner."), ephemeral=True)

# ─── MOD LOG HELPER ──────────────────────────────────────────────────────────

async def _mod_log(guild, action, moderator, target, reason):
    push_mod_log(action, moderator, target, reason)
    ch_id = config.get("mod_log_channel") or config.get("log_channel")
    if not ch_id: return
    ch = guild.get_channel(ch_id)
    if not ch: return
    colors = {"BAN":0xe74c3c,"KICK":0xe67e22,"MUTE":0xf39c12,"WARN":0xf1c40f,"UNBAN":0x2ecc71}
    e = discord.Embed(title=f"🔨 {action}", color=colors.get(action, 0x3498db))
    e.add_field(name="Moderator", value=moderator.mention if hasattr(moderator,"mention") else str(moderator))
    e.add_field(name="Target",    value=target.mention    if hasattr(target,"mention")    else str(target))
    e.add_field(name="Reason",    value=reason, inline=False)
    e.timestamp = datetime.datetime.utcnow()
    await ch.send(embed=e)

# ─── DAILY CODE TASK ─────────────────────────────────────────────────────────

@tasks.loop(hours=24)
async def daily_code_task():
    code  = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    today = get_today_str()
    config.setdefault("daily_codes",{})[today] = code
    save_json(CONFIG_FILE, config)
    guild_id = config.get("guild_id")
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            for member in guild.members:
                if is_staff(member) and not member.bot:
                    try: await member.send(embed=discord.Embed(title="🔐 Daily Staff Code", description=f"Code: `{code}`\nUse `/staff {code}`", color=0x9b59b6))
                    except: pass

# ─── READY ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    print(f"📊 Guilds: {len(bot.guilds)}")
    try:
        synced = await tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the server 👁️"))
    daily_code_task.start()

# ═══════════════════════════════════════════════════════════════════════════════
#  REST API  (keep-alive + live dashboard data)
# ═══════════════════════════════════════════════════════════════════════════════

from aiohttp import web as aiohttp_web

@aiohttp_web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return aiohttp_web.Response(headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
        })
    resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

def check_api_key(request):
    api_key = os.environ.get("DASHBOARD_API_KEY", "")
    if not api_key: return True
    return request.headers.get("X-API-Key") == api_key

def json_response(data, status=200):
    return aiohttp_web.Response(text=json.dumps(data), status=status, content_type="application/json")

# ── Route handlers ──

async def route_health(request):
    return aiohttp_web.Response(text="✅ UltraBot is online!")

async def route_dashboard(request):
    """Serve the dashboard HTML file."""
    if os.path.exists(DASHBOARD_FILE):
        with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
            html = f.read()
        return aiohttp_web.Response(text=html, content_type="text/html", charset="utf-8")
    return aiohttp_web.Response(text="<h1>Dashboard file not found. Place dashboard.html next to bot.py</h1>",
                                content_type="text/html", status=404)

async def route_stats(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    guild_id = config.get("guild_id")
    guild    = bot.get_guild(guild_id) if guild_id else None
    return json_response({
        "online":          True,
        "latency_ms":      round(bot.latency * 1000),
        "guild_name":      guild.name if guild else "Unknown",
        "guild_icon":      str(guild.icon.url) if guild and guild.icon else None,
        "member_count":    guild.member_count if guild else 0,
        "channel_count":   len(guild.channels) if guild else 0,
        "role_count":      len(guild.roles) if guild else 0,
        "boost_count":     guild.premium_subscription_count if guild else 0,
        "total_warnings":  sum(len(v) for v in warnings.values()),
        "premium_count":   len(premium),
        "bug_reports":     len(reports.get("bugs", [])),
        "user_reports":    len(reports.get("users", [])),
        "automod":         dict(automod_counts),
        "automod_config":  config.get("automod", {}),
        "counting_count":  counting.get("count", 0),
    })

async def route_warnings(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    guild_id = config.get("guild_id")
    guild    = bot.get_guild(guild_id) if guild_id else None
    result   = []
    for uid, warns in warnings.items():
        member = guild.get_member(int(uid)) if guild else None
        result.append({
            "user_id":  uid,
            "username": str(member) if member else f"Unknown ({uid})",
            "avatar":   str(member.display_avatar.url) if member else None,
            "count":    len(warns),
            "warns":    warns,
        })
    result.sort(key=lambda x: x["count"], reverse=True)
    return json_response(result)

async def route_modlog(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    return json_response(list(reversed(mod_log_cache)))

async def route_reports(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    return json_response(reports)

async def route_config(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    safe = {k: v for k, v in config.items() if k not in ("staff_code","daily_codes")}
    return json_response(safe)

async def route_members(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    guild_id = config.get("guild_id")
    guild    = bot.get_guild(guild_id) if guild_id else None
    if not guild: return json_response([])
    staff_ids = set(config.get("staff_roles",[]) + config.get("admin_roles",[]) + config.get("mod_roles",[]))
    result = []
    for m in guild.members:
        if m.bot: continue
        result.append({
            "id":       str(m.id), "username": str(m), "nick": m.nick,
            "avatar":   str(m.display_avatar.url),
            "is_staff": any(r.id in staff_ids for r in m.roles),
            "is_admin": m.guild_permissions.administrator,
            "warnings": len(warnings.get(str(m.id),[])),
            "premium":  str(m.id) in premium,
            "joined":   m.joined_at.isoformat() if m.joined_at else None,
        })
    return json_response(result)

async def route_premium_list(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    guild_id = config.get("guild_id")
    guild    = bot.get_guild(guild_id) if guild_id else None
    result   = []
    for uid, data in premium.items():
        member = guild.get_member(int(uid)) if guild else None
        result.append({"user_id": uid, "username": str(member) if member else f"Unknown ({uid})",
                        "avatar": str(member.display_avatar.url) if member else None, **data})
    return json_response(result)

async def route_update_automod(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    try:
        data = await request.json()
        config["automod"].update(data); save_json(CONFIG_FILE, config)
        return json_response({"ok": True})
    except Exception as e:
        return json_response({"error": str(e)}, 400)

async def route_clear_warnings(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    try:
        data = await request.json()
        warnings.pop(str(data.get("user_id")), None); save_json(WARNINGS_FILE, warnings)
        return json_response({"ok": True})
    except Exception as e:
        return json_response({"error": str(e)}, 400)

async def route_dismiss_report(request):
    if not check_api_key(request): return json_response({"error":"Unauthorized"}, 401)
    try:
        data  = await request.json()
        rtype = data.get("type", "users")
        idx   = data.get("index", -1)
        if 0 <= idx < len(reports.get(rtype, [])):
            reports[rtype].pop(idx); save_json(REPORTS_FILE, reports)
        return json_response({"ok": True})
    except Exception as e:
        return json_response({"error": str(e)}, 400)

async def start_api_server():
    app = aiohttp_web.Application(middlewares=[cors_middleware])
    app.router.add_get("/",                        route_health)
    app.router.add_get("/health",                  route_health)
    app.router.add_get("/dashboard",               route_dashboard)   # ← THE FIX
    app.router.add_get("/api/stats",               route_stats)
    app.router.add_get("/api/warnings",            route_warnings)
    app.router.add_get("/api/modlog",              route_modlog)
    app.router.add_get("/api/reports",             route_reports)
    app.router.add_get("/api/config",              route_config)
    app.router.add_get("/api/members",             route_members)
    app.router.add_get("/api/premium",             route_premium_list)
    app.router.add_post("/api/automod",            route_update_automod)
    app.router.add_post("/api/warnings/clear",     route_clear_warnings)
    app.router.add_post("/api/reports/dismiss",    route_dismiss_report)
    app.router.add_options("/{tail:.*}",           route_health)

    runner = aiohttp_web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = aiohttp_web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 API server running on port {port}")
    print(f"📊 Dashboard: http://0.0.0.0:{port}/dashboard")

# ─── RUN ─────────────────────────────────────────────────────────────────────

async def main():
    TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
    await start_api_server()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
