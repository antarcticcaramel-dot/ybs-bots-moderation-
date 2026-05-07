"""
╔══════════════════════════════════════════════════════════════════╗
║           ULTRA MODERATION BOT - Full Feature Discord Bot        ║
║           GitHub: Replace with your repo                         ║
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

CONFIG_FILE = "config.json"
WARNINGS_FILE = "warnings.json"
STAFF_CODES_FILE = "staff_codes.json"
TIMERS_FILE = "timers.json"
REPORTS_FILE = "reports.json"
PREMIUM_USERS_FILE = "premium.json"
COUNTING_FILE = "counting.json"
NOTES_FILE = "notes.json"

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
        "warn_action": "mute",  # mute / kick / ban
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
    "staff_code": None,  # Set by owner
    "daily_codes": {},
    "nickname_logs": True,
}

# ─── LOAD / SAVE HELPERS ─────────────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default.copy() if isinstance(default, dict) else default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

config   = load_json(CONFIG_FILE, DEFAULT_CONFIG)
warnings = load_json(WARNINGS_FILE, {})
staff_codes = load_json(STAFF_CODES_FILE, {})
reports  = load_json(REPORTS_FILE, {"bugs": [], "users": []})
premium  = load_json(PREMIUM_USERS_FILE, {})
counting = load_json(COUNTING_FILE, {"count": 0, "last_user": None})
notes    = load_json(NOTES_FILE, {})

# ─── BOT SETUP ───────────────────────────────────────────────────────────────

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.get("prefix", "/"), intents=intents)
tree = bot.tree

# Spam tracker
spam_tracker = defaultdict(list)
nuke_tracker = defaultdict(list)
raid_tracker = []

# ─── ROBLOX LINK OBFUSCATOR ──────────────────────────────────────────────────

def obfuscate_roblox_link(user_id: str) -> str:
    """Mix numbers with letters so Roblox IDs stay shareable but obfuscated"""
    mapping = {'0':'O','1':'l','2':'Z','3':'E','4':'A','5':'S','6':'G','7':'T','8':'B','9':'q'}
    result = ""
    for i, ch in enumerate(str(user_id)):
        if i % 2 == 0 and ch in mapping:
            result += mapping[ch]
        else:
            result += ch
    return result

def deobfuscate_roblox_link(obf: str) -> str:
    reverse = {'O':'0','l':'1','Z':'2','E':'3','A':'4','S':'5','G':'6','T':'7','B':'8','q':'9'}
    result = ""
    for ch in obf:
        result += reverse.get(ch, ch)
    return result

# ─── PERMISSION HELPERS ──────────────────────────────────────────────────────

def is_staff(member: discord.Member) -> bool:
    staff_ids = config.get("staff_roles", [])
    admin_ids = config.get("admin_roles", [])
    mod_ids   = config.get("mod_roles", [])
    all_ids   = set(staff_ids + admin_ids + mod_ids)
    return any(r.id in all_ids for r in member.roles) or member.guild_permissions.administrator

def is_admin(member: discord.Member) -> bool:
    admin_ids = set(config.get("admin_roles", []))
    return any(r.id in admin_ids for r in member.roles) or member.guild_permissions.administrator

def get_today_str():
    return datetime.date.today().isoformat()

def check_daily_code(user_id: int, code: str) -> bool:
    today = get_today_str()
    daily = config.get("daily_codes", {})
    return daily.get(today) == code

# ─── EMBED HELPERS ───────────────────────────────────────────────────────────

def success_embed(title, desc, ctx_or_interaction=None):
    e = discord.Embed(title=f"✅ {title}", description=desc, color=0x2ecc71)
    e.timestamp = datetime.datetime.utcnow()
    _add_nav_buttons_to_embed(e)
    return e

def error_embed(title, desc):
    e = discord.Embed(title=f"❌ {title}", description=desc, color=0xe74c3c)
    e.timestamp = datetime.datetime.utcnow()
    return e

def info_embed(title, desc, color=0x3498db):
    e = discord.Embed(title=f"ℹ️ {title}", description=desc, color=color)
    e.timestamp = datetime.datetime.utcnow()
    _add_nav_buttons_to_embed(e)
    return e

def _add_nav_buttons_to_embed(e: discord.Embed):
    website  = config.get("website", "https://yourwebsite.com")
    dash     = config.get("dashboard", "https://yourdashboard.com")
    e.add_field(name="🔗 Quick Links", value=f"[🌐 Website]({website}) • [📊 Dashboard]({dash})", inline=False)

class NavView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        website = config.get("website", "https://yourwebsite.com")
        dash    = config.get("dashboard", "https://yourdashboard.com")
        self.add_item(discord.ui.Button(label="🌐 Website", url=website, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="📊 Dashboard", url=dash, style=discord.ButtonStyle.link))

    @discord.ui.button(label="📢 Report Issue", style=discord.ButtonStyle.secondary, emoji="🚨")
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = BugReportModal()
        await interaction.response.send_modal(modal)

class BugReportModal(discord.ui.Modal, title="🐛 Bug / Issue Report"):
    description = discord.ui.TextInput(label="Describe the bug", style=discord.TextStyle.paragraph, placeholder="What went wrong?", max_length=1000)
    steps       = discord.ui.TextInput(label="Steps to reproduce", style=discord.TextStyle.paragraph, required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        report = {
            "type": "bug",
            "user": str(interaction.user),
            "user_id": interaction.user.id,
            "description": self.description.value,
            "steps": self.steps.value,
            "time": datetime.datetime.utcnow().isoformat()
        }
        reports["bugs"].append(report)
        save_json(REPORTS_FILE, reports)
        ch_id = config.get("report_channel")
        if ch_id:
            ch = interaction.guild.get_channel(ch_id)
            if ch:
                e = discord.Embed(title="🐛 New Bug Report", color=0xe67e22)
                e.add_field(name="Reporter", value=interaction.user.mention)
                e.add_field(name="Description", value=self.description.value, inline=False)
                if self.steps.value:
                    e.add_field(name="Steps", value=self.steps.value, inline=False)
                await ch.send(embed=e)
        await interaction.response.send_message(embed=success_embed("Bug Reported", "Thank you! Staff will look into it."), ephemeral=True)

# ─── AUTO MODERATION ─────────────────────────────────────────────────────────

BAD_LINK_PATTERNS = [
    r"(discord\.gg|discordapp\.com/invite)/[a-zA-Z0-9]+",
    r"(grabify|iplogger|bmwforum|yip\.su|2no\.co|lovebird\.guru|stopify\.co)",
    r"(bit\.ly|tinyurl\.com|t\.co|goo\.gl)",  # short links (configurable)
    r"(pornhub|xvideos|xnxx|onlyfans)",
    r"(phishing|free-nitro|discord-nitro-free|steamgift)",
    r"(nitro.*free|free.*nitro)",
]

NUKE_COMMANDS = ["ban_all", "delete_all", "mass_kick", "purge_all"]

async def log_automod(guild, action, user, reason, channel=None):
    ch_id = config.get("mod_log_channel") or config.get("log_channel")
    if not ch_id:
        return
    ch = guild.get_channel(ch_id)
    if not ch:
        return
    e = discord.Embed(title=f"🤖 AutoMod: {action}", color=0xff6b35)
    e.add_field(name="User", value=f"{user.mention} ({user.id})")
    e.add_field(name="Reason", value=reason)
    if channel:
        e.add_field(name="Channel", value=channel.mention)
    e.timestamp = datetime.datetime.utcnow()
    await ch.send(embed=e)

async def add_warning(guild, user, reason, moderator):
    uid = str(user.id)
    if uid not in warnings:
        warnings[uid] = []
    warnings[uid].append({
        "reason": reason,
        "moderator": str(moderator),
        "time": datetime.datetime.utcnow().isoformat()
    })
    save_json(WARNINGS_FILE, warnings)
    count = len(warnings[uid])
    max_w = config["automod"].get("max_warnings", 3)
    action = config["automod"].get("warn_action", "mute")

    if count >= max_w:
        try:
            if action == "ban":
                await guild.ban(user, reason=f"Auto-ban: {count} warnings")
            elif action == "kick":
                await guild.kick(user, reason=f"Auto-kick: {count} warnings")
            elif action == "mute":
                dur = config["automod"].get("mute_duration", 10)
                until = datetime.datetime.utcnow() + datetime.timedelta(minutes=dur)
                member = guild.get_member(user.id)
                if member:
                    await member.timeout(until, reason=f"Auto-mute: {count} warnings")
        except:
            pass
    return count

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        # DM - relay to staff
        await handle_dm(message)
        return

    automod = config.get("automod", {})
    if not automod.get("enabled", True):
        await bot.process_commands(message)
        return

    member = message.author
    content = message.content.lower()

    # ── bot-commands channel enforcement ──
    bot_ch_id = config.get("bot_commands_channel")
    if bot_ch_id and message.channel.id != bot_ch_id:
        if message.content.startswith(bot.command_prefix) and not is_staff(member):
            await message.delete()
            try:
                bot_ch = message.guild.get_channel(bot_ch_id)
                await member.send(embed=error_embed("Wrong Channel", f"Please use bot commands in {bot_ch.mention if bot_ch else 'the bot commands channel'}."))
            except:
                pass
            return

    # ── counting channel ──
    cnt_ch_id = config.get("counting_channel")
    if cnt_ch_id and message.channel.id == cnt_ch_id:
        await handle_counting(message)
        return

    # ── bad links ──
    if automod.get("ban_bad_links", True):
        for pattern in BAD_LINK_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                whitelist = automod.get("whitelist_links", [])
                if not any(w in content for w in whitelist):
                    await message.delete()
                    cnt = await add_warning(message.guild, member, "Bad/unsafe link", "AutoMod")
                    await log_automod(message.guild, "Bad Link Removed", member, f"Pattern: {pattern}", message.channel)
                    try:
                        await member.send(embed=error_embed("Link Removed", f"Your message contained a blocked link. Warning #{cnt}."))
                    except:
                        pass
                    await bot.process_commands(message)
                    return

    # ── invite links ──
    if automod.get("ban_invite_links", True) and not is_staff(member):
        if re.search(r"discord\.(gg|io|me|li)/[a-zA-Z0-9]+", content):
            await message.delete()
            cnt = await add_warning(message.guild, member, "Discord invite link", "AutoMod")
            await log_automod(message.guild, "Invite Link", member, "Sent invite link", message.channel)
            return

    # ── caps check ──
    if automod.get("anti_caps", True) and len(message.content) > 10:
        caps_ratio = sum(1 for c in message.content if c.isupper()) / len(message.content)
        threshold = automod.get("caps_threshold", 0.7)
        if caps_ratio > threshold:
            await message.delete()
            await message.channel.send(f"{member.mention} ⚠️ Please don't use excessive caps.", delete_after=5)
            return

    # ── mass mention ──
    max_m = automod.get("max_mentions", 5)
    if automod.get("anti_mass_mention", True) and len(message.mentions) > max_m:
        await message.delete()
        cnt = await add_warning(message.guild, member, "Mass mention", "AutoMod")
        await log_automod(message.guild, "Mass Mention", member, f"{len(message.mentions)} mentions", message.channel)
        return

    # ── spam check ──
    if automod.get("anti_spam", True):
        now = time.time()
        uid = member.id
        spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < 5]
        spam_tracker[uid].append(now)
        threshold = automod.get("spam_threshold", 5)
        if len(spam_tracker[uid]) > threshold:
            await message.delete()
            cnt = await add_warning(message.guild, member, "Spamming", "AutoMod")
            await log_automod(message.guild, "Spam Detected", member, f"{len(spam_tracker[uid])} msgs in 5s", message.channel)
            spam_tracker[uid] = []
            return

    # ── bad words ──
    bad_words = automod.get("bad_words", [])
    for word in bad_words:
        if word.lower() in content:
            await message.delete()
            await message.channel.send(f"{member.mention} ⚠️ Inappropriate language.", delete_after=5)
            await add_warning(message.guild, member, f"Bad word: {word}", "AutoMod")
            return

    await bot.process_commands(message)

async def handle_counting(message):
    try:
        num = int(message.content.strip())
    except:
        await message.delete()
        await message.channel.send(f"{message.author.mention} Only numbers allowed here!", delete_after=5)
        return
    expected = counting["count"] + 1
    if num != expected:
        await message.delete()
        await message.channel.send(f"❌ {message.author.mention} broke the count! Next number was **{expected}**. Restarting from 0.", delete_after=8)
        counting["count"] = 0
        counting["last_user"] = None
    elif counting.get("last_user") == message.author.id:
        await message.delete()
        await message.channel.send(f"❌ {message.author.mention} you can't count twice in a row!", delete_after=5)
        return
    else:
        counting["count"] = num
        counting["last_user"] = message.author.id
        if num % 100 == 0:
            await message.add_reaction("🎉")
        else:
            await message.add_reaction("✅")
    save_json(COUNTING_FILE, counting)

async def handle_dm(message):
    """Relay DMs to staff channel and allow replies"""
    staff_ch_id = config.get("staff_channel")
    if not staff_ch_id:
        return
    guild = bot.get_guild(config.get("guild_id"))
    if not guild:
        return
    ch = guild.get_channel(staff_ch_id)
    if not ch:
        return
    e = discord.Embed(title="📩 New DM Received", color=0x9b59b6)
    e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    e.add_field(name="User ID", value=message.author.id)
    e.description = message.content
    if message.attachments:
        e.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments))
    e.set_footer(text=f"Reply with: /dmreply {message.author.id} <message>")
    await ch.send(embed=e)

# ─── ANTI-NUKE ────────────────────────────────────────────────────────────────

@bot.event
async def on_guild_channel_delete(channel):
    if not config["automod"].get("anti_nuke"):
        return
    guild = channel.guild
    now = time.time()
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        uid = entry.user.id
        nuke_tracker[uid] = [t for t in nuke_tracker[uid] if now - t < 10]
        nuke_tracker[uid].append(now)
        if len(nuke_tracker[uid]) >= 3:
            member = guild.get_member(uid)
            if member and not member.guild_permissions.administrator:
                await guild.ban(member, reason="Anti-Nuke: Mass channel deletion")
                await log_automod(guild, "NUKE ATTEMPT BLOCKED", member, "Mass channel deletion")

@bot.event
async def on_member_ban(guild, user):
    if not config["automod"].get("anti_nuke"):
        return
    now = time.time()
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        uid = entry.user.id
        nuke_tracker[f"ban_{uid}"] = [t for t in nuke_tracker.get(f"ban_{uid}", []) if now - t < 10]
        nuke_tracker[f"ban_{uid}"].append(now)
        if len(nuke_tracker[f"ban_{uid}"]) >= 5:
            member = guild.get_member(uid)
            if member and not member.guild_permissions.administrator:
                await guild.ban(member, reason="Anti-Nuke: Mass banning users")
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
                    await ch.send(embed=discord.Embed(title="🚨 RAID ALERT", description=f"10+ users joined in 10 seconds! Consider enabling lockdown.", color=0xff0000))

    welcome_ch = config.get("welcome_channel")
    if welcome_ch:
        ch = member.guild.get_channel(welcome_ch)
        if ch:
            e = discord.Embed(title=f"👋 Welcome to {member.guild.name}!", description=f"Hey {member.mention}, welcome! Make sure to read the rules.", color=0x2ecc71)
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
                e.add_field(name="User", value=after.mention)
                e.add_field(name="Before", value=before.nick or "None")
                e.add_field(name="After", value=after.nick or "None")
                await ch.send(embed=e)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    ch_id = config.get("log_channel")
    if ch_id:
        ch = message.guild.get_channel(ch_id) if message.guild else None
        if ch:
            e = discord.Embed(title="🗑️ Message Deleted", color=0xe74c3c)
            e.add_field(name="Author", value=message.author.mention)
            e.add_field(name="Channel", value=message.channel.mention)
            e.description = message.content or "*(no text)*"
            if message.attachments:
                e.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments))
            await ch.send(embed=e)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    ch_id = config.get("log_channel")
    if ch_id and before.guild:
        ch = before.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="✏️ Message Edited", color=0xf39c12)
            e.add_field(name="Author", value=before.author.mention)
            e.add_field(name="Channel", value=before.channel.mention)
            e.add_field(name="Before", value=before.content[:500] or "*empty*", inline=False)
            e.add_field(name="After", value=after.content[:500] or "*empty*", inline=False)
            await ch.send(embed=e)

# ─── MODERATION COMMANDS ─────────────────────────────────────────────────────

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="User to ban", reason="Reason for ban", delete_days="Delete message history (days)")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason", delete_days: int = 0):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "You need staff permissions."), ephemeral=True)
        return
    await interaction.guild.ban(user, reason=reason, delete_message_days=delete_days)
    await interaction.response.send_message(embed=success_embed("User Banned", f"{user.mention} has been banned.\n**Reason:** {reason}"), view=NavView())
    await _mod_log(interaction.guild, "BAN", interaction.user, user, reason)
    try:
        await user.send(embed=error_embed("You've Been Banned", f"You were banned from **{interaction.guild.name}**\n**Reason:** {reason}"))
    except:
        pass

@tree.command(name="unban", description="Unban a user by ID")
@app_commands.describe(user_id="User ID to unban", reason="Reason")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        await interaction.response.send_message(embed=success_embed("Unbanned", f"{user} has been unbanned."), view=NavView())
    except Exception as e:
        await interaction.response.send_message(embed=error_embed("Error", str(e)), ephemeral=True)

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="User to kick", reason="Reason")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    await interaction.guild.kick(user, reason=reason)
    await interaction.response.send_message(embed=success_embed("User Kicked", f"{user.mention} kicked.\n**Reason:** {reason}"), view=NavView())
    await _mod_log(interaction.guild, "KICK", interaction.user, user, reason)

@tree.command(name="mute", description="Timeout (mute) a user")
@app_commands.describe(user="User to mute", minutes="Duration in minutes", reason="Reason")
async def mute(interaction: discord.Interaction, user: discord.Member, minutes: int = 10, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    until = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    await user.timeout(until, reason=reason)
    await interaction.response.send_message(embed=success_embed("User Muted", f"{user.mention} muted for {minutes}m.\n**Reason:** {reason}"), view=NavView())
    await _mod_log(interaction.guild, "MUTE", interaction.user, user, reason)

@tree.command(name="unmute", description="Remove timeout from a user")
@app_commands.describe(user="User to unmute")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    await user.timeout(None)
    await interaction.response.send_message(embed=success_embed("Unmuted", f"{user.mention} has been unmuted."), view=NavView())

@tree.command(name="warn", description="Warn a user")
@app_commands.describe(user="User to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    count = await add_warning(interaction.guild, user, reason, interaction.user)
    await interaction.response.send_message(embed=success_embed("Warning Issued", f"{user.mention} has been warned (#{count}).\n**Reason:** {reason}"), view=NavView())
    await _mod_log(interaction.guild, "WARN", interaction.user, user, reason)
    try:
        await user.send(embed=error_embed("Warning Received", f"You received a warning in **{interaction.guild.name}**\n**Reason:** {reason}\n**Total Warnings:** {count}"))
    except:
        pass

@tree.command(name="warnings", description="View warnings for a user")
@app_commands.describe(user="User to check")
async def view_warnings(interaction: discord.Interaction, user: discord.Member):
    uid = str(user.id)
    user_warns = warnings.get(uid, [])
    if not user_warns:
        await interaction.response.send_message(embed=info_embed("No Warnings", f"{user.mention} has no warnings."))
        return
    e = discord.Embed(title=f"⚠️ Warnings for {user}", color=0xe67e22)
    for i, w in enumerate(user_warns, 1):
        e.add_field(name=f"Warning #{i}", value=f"**Reason:** {w['reason']}\n**By:** {w['moderator']}\n**Time:** {w['time'][:10]}", inline=False)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="clearwarnings", description="Clear all warnings for a user")
@app_commands.describe(user="User to clear warnings for")
async def clear_warnings(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    warnings.pop(str(user.id), None)
    save_json(WARNINGS_FILE, warnings)
    await interaction.response.send_message(embed=success_embed("Warnings Cleared", f"All warnings cleared for {user.mention}."), view=NavView())

@tree.command(name="purge", description="Delete a number of messages")
@app_commands.describe(amount="Number of messages to delete (1-500)", user="Only delete messages from this user")
async def purge(interaction: discord.Interaction, amount: int, user: Optional[discord.Member] = None):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    amount = min(amount, 500)
    if user:
        deleted = await interaction.channel.purge(limit=amount * 5, check=lambda m: m.author == user)
        deleted = deleted[:amount]
    else:
        deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(embed=success_embed("Purge Complete", f"Deleted {len(deleted)} messages."), ephemeral=True)

@tree.command(name="slowmode", description="Set slowmode for a channel")
@app_commands.describe(seconds="Seconds (0 to disable)", channel="Channel (defaults to current)")
async def slowmode(interaction: discord.Interaction, seconds: int, channel: Optional[discord.TextChannel] = None):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    ch = channel or interaction.channel
    await ch.edit(slowmode_delay=seconds)
    status = f"Set to {seconds}s" if seconds > 0 else "Disabled"
    await interaction.response.send_message(embed=success_embed("Slowmode Updated", f"Slowmode in {ch.mention}: {status}"), view=NavView())

@tree.command(name="lock", description="Lock a channel")
@app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason")
async def lock(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    ch = channel or interaction.channel
    overwrite = ch.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message(embed=success_embed("Channel Locked", f"{ch.mention} has been locked.\n**Reason:** {reason}"), view=NavView())
    await ch.send(embed=discord.Embed(description=f"🔒 This channel has been locked by {interaction.user.mention}. **Reason:** {reason}", color=0xe74c3c))

@tree.command(name="unlock", description="Unlock a channel")
@app_commands.describe(channel="Channel to unlock")
async def unlock(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    ch = channel or interaction.channel
    overwrite = ch.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message(embed=success_embed("Channel Unlocked", f"{ch.mention} is now unlocked."), view=NavView())
    await ch.send(embed=discord.Embed(description=f"🔓 Channel unlocked by {interaction.user.mention}.", color=0x2ecc71))

@tree.command(name="lockdown", description="Lock ALL channels (emergency)")
async def lockdown(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except:
            pass
    await interaction.followup.send(embed=success_embed("🚨 SERVER LOCKDOWN", f"Locked {count} channels. Use `/unlockdown` to revert."), view=NavView())

@tree.command(name="unlockdown", description="Unlock ALL channels")
async def unlockdown(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = True
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except:
            pass
    await interaction.followup.send(embed=success_embed("Lockdown Lifted", f"Unlocked {count} channels."), view=NavView())

@tree.command(name="nick", description="Change a user's nickname")
@app_commands.describe(user="Target user", nickname="New nickname (leave blank to remove)")
async def nick(interaction: discord.Interaction, user: discord.Member, nickname: str = ""):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    old = user.nick
    await user.edit(nick=nickname if nickname else None)
    await interaction.response.send_message(embed=success_embed("Nickname Changed", f"{user.mention}: `{old}` → `{nickname or 'None'}`"), view=NavView())

@tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(user="Target user", role="Role to add/remove", action="add or remove")
async def role_cmd(interaction: discord.Interaction, user: discord.Member, role: discord.Role, action: str = "add"):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    if action.lower() == "add":
        await user.add_roles(role)
        await interaction.response.send_message(embed=success_embed("Role Added", f"{role.mention} added to {user.mention}."), view=NavView())
    else:
        await user.remove_roles(role)
        await interaction.response.send_message(embed=success_embed("Role Removed", f"{role.mention} removed from {user.mention}."), view=NavView())

@tree.command(name="softban", description="Ban and immediately unban (clears messages)")
@app_commands.describe(user="User to softban", reason="Reason")
async def softban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    await interaction.guild.ban(user, reason=f"Softban: {reason}", delete_message_days=7)
    await interaction.guild.unban(user)
    await interaction.response.send_message(embed=success_embed("User Softbanned", f"{user.mention} softbanned.\n**Reason:** {reason}"), view=NavView())

@tree.command(name="tempban", description="Temporarily ban a user")
@app_commands.describe(user="User to ban", hours="Duration in hours", reason="Reason")
async def tempban(interaction: discord.Interaction, user: discord.Member, hours: int, reason: str = "No reason"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    await interaction.guild.ban(user, reason=f"Tempban ({hours}h): {reason}")
    await interaction.response.send_message(embed=success_embed("Tempban", f"{user.mention} banned for {hours}h.\n**Reason:** {reason}"), view=NavView())
    await asyncio.sleep(hours * 3600)
    try:
        await interaction.guild.unban(user)
    except:
        pass

@tree.command(name="userinfo", description="Get detailed info about a user")
@app_commands.describe(user="User to look up")
async def userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    e = discord.Embed(title=f"👤 User Info: {user}", color=user.color)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="ID", value=user.id)
    e.add_field(name="Nickname", value=user.nick or "None")
    e.add_field(name="Joined Server", value=discord.utils.format_dt(user.joined_at, "R") if user.joined_at else "Unknown")
    e.add_field(name="Account Created", value=discord.utils.format_dt(user.created_at, "R"))
    e.add_field(name="Roles", value=" ".join(r.mention for r in user.roles[1:]) or "None")
    e.add_field(name="Warnings", value=len(warnings.get(str(user.id), [])))
    e.add_field(name="Is Staff", value="✅" if is_staff(user) else "❌")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="serverinfo", description="Get server information")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    e = discord.Embed(title=f"🏠 {g.name}", color=0x3498db)
    e.set_thumbnail(url=g.icon.url if g.icon else None)
    e.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown")
    e.add_field(name="Members", value=g.member_count)
    e.add_field(name="Channels", value=len(g.channels))
    e.add_field(name="Roles", value=len(g.roles))
    e.add_field(name="Boosts", value=g.premium_subscription_count)
    e.add_field(name="Boost Level", value=g.premium_tier)
    e.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"))
    e.add_field(name="Verification", value=str(g.verification_level))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="avatar", description="View a user's avatar")
@app_commands.describe(user="User to view avatar for")
async def avatar(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    e = discord.Embed(title=f"🖼️ {user}'s Avatar", color=0x3498db)
    e.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="report", description="Report a user for breaking rules")
@app_commands.describe(user="User to report", reason="Reason for report")
async def report_user(interaction: discord.Interaction, user: discord.Member, reason: str):
    report = {
        "type": "user",
        "reporter": str(interaction.user),
        "reporter_id": interaction.user.id,
        "reported": str(user),
        "reported_id": user.id,
        "reason": reason,
        "time": datetime.datetime.utcnow().isoformat()
    }
    reports["users"].append(report)
    save_json(REPORTS_FILE, reports)
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="🚨 User Report", color=0xe74c3c)
            e.add_field(name="Reporter", value=interaction.user.mention)
            e.add_field(name="Reported", value=user.mention)
            e.add_field(name="Reason", value=reason, inline=False)
            await ch.send(embed=e)
    await interaction.response.send_message(embed=success_embed("Report Submitted", "Thank you! Staff will review this."), ephemeral=True, view=NavView())

@tree.command(name="bugreport", description="Report a bug")
async def bugreport(interaction: discord.Interaction):
    await interaction.response.send_modal(BugReportModal())

@tree.command(name="announce", description="Send an announcement to a channel")
@app_commands.describe(channel="Channel to announce in", message="Announcement message", ping="Role to ping")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str, ping: Optional[discord.Role] = None):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    e = discord.Embed(title="📢 Announcement", description=message, color=0xe67e22)
    e.set_footer(text=f"By {interaction.user}", icon_url=interaction.user.display_avatar.url)
    content = ping.mention if ping else None
    await channel.send(content=content, embed=e)
    await interaction.response.send_message(embed=success_embed("Announced", f"Announcement sent to {channel.mention}."), ephemeral=True)

@tree.command(name="embed", description="Send a custom embed")
@app_commands.describe(channel="Channel", title="Title", description="Description", color="Hex color (e.g. ff0000)")
async def send_embed(interaction: discord.Interaction, channel: discord.TextChannel, title: str, description: str, color: str = "3498db"):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    try:
        col = int(color.strip("#"), 16)
    except:
        col = 0x3498db
    e = discord.Embed(title=title, description=description, color=col)
    await channel.send(embed=e)
    await interaction.response.send_message(embed=success_embed("Embed Sent", f"Sent to {channel.mention}."), ephemeral=True)

@tree.command(name="poll", description="Create a poll")
@app_commands.describe(question="Poll question", options="Options separated by | (max 10)")
async def poll(interaction: discord.Interaction, question: str, options: str):
    opts = [o.strip() for o in options.split("|")][:10]
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    e = discord.Embed(title=f"📊 {question}", color=0x9b59b6)
    desc = ""
    for i, opt in enumerate(opts):
        desc += f"{emojis[i]} {opt}\n"
    e.description = desc
    e.set_footer(text=f"Poll by {interaction.user}")
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    for i in range(len(opts)):
        await msg.add_reaction(emojis[i])

@tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(prize="What are you giving away?", duration="Duration in minutes", winners="Number of winners")
async def giveaway(interaction: discord.Interaction, prize: str, duration: int, winners: int = 1):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    end_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration)
    e = discord.Embed(title="🎉 GIVEAWAY!", color=0xe91e63)
    e.description = f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {discord.utils.format_dt(end_time, 'R')}\n\nReact with 🎉 to enter!"
    e.set_footer(text=f"Hosted by {interaction.user}")
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("🎉")

    await asyncio.sleep(duration * 60)
    msg = await interaction.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if reaction:
        users = [u async for u in reaction.users() if not u.bot]
        if users:
            w = random.sample(users, min(winners, len(users)))
            mentions = ", ".join(u.mention for u in w)
            await interaction.channel.send(embed=discord.Embed(title="🎉 Giveaway Ended!", description=f"Winner(s): {mentions}\n**Prize:** {prize}", color=0xe91e63))
        else:
            await interaction.channel.send("No one entered the giveaway.")

# ─── TIMER COMMAND ────────────────────────────────────────────────────────────

@tree.command(name="timer", description="Set a reminder/timer")
@app_commands.describe(minutes="Minutes until reminder", message="What to remind you about")
async def timer(interaction: discord.Interaction, minutes: int, message: str = "Your timer is up!"):
    if minutes > 1440:
        await interaction.response.send_message(embed=error_embed("Too Long", "Max timer is 1440 minutes (24 hours)."), ephemeral=True)
        return
    end = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    await interaction.response.send_message(embed=success_embed("Timer Set", f"I'll remind you in **{minutes} minutes**.\n**Message:** {message}"), view=NavView())
    await asyncio.sleep(minutes * 60)
    try:
        await interaction.user.send(embed=discord.Embed(title="⏰ Timer Up!", description=message, color=0x2ecc71))
        await interaction.channel.send(f"⏰ {interaction.user.mention} your timer is up! **{message}**")
    except:
        pass

@tree.command(name="remindme", description="Remind yourself of something")
@app_commands.describe(time_str="e.g. 10m, 2h, 1d", reminder="What to remind you about")
async def remindme(interaction: discord.Interaction, time_str: str, reminder: str):
    multipliers = {"m": 60, "h": 3600, "d": 86400}
    try:
        unit = time_str[-1].lower()
        amount = int(time_str[:-1])
        seconds = amount * multipliers[unit]
    except:
        await interaction.response.send_message(embed=error_embed("Invalid Format", "Use formats like `10m`, `2h`, `1d`"), ephemeral=True)
        return
    await interaction.response.send_message(embed=success_embed("Reminder Set", f"I'll remind you about: **{reminder}** in **{time_str}**"), view=NavView())
    await asyncio.sleep(seconds)
    try:
        await interaction.user.send(embed=discord.Embed(title="🔔 Reminder!", description=reminder, color=0x9b59b6))
    except:
        await interaction.channel.send(f"🔔 {interaction.user.mention} Reminder: **{reminder}**")

# ─── STAFF SYSTEM ────────────────────────────────────────────────────────────

@tree.command(name="staff", description="Access the staff panel (requires daily code)")
@app_commands.describe(code="Your daily staff code")
async def staff_panel(interaction: discord.Interaction, code: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("Access Denied", "You are not a staff member."), ephemeral=True)
        return
    if not check_daily_code(interaction.user.id, code):
        await interaction.response.send_message(embed=error_embed("Invalid Code", "Wrong daily code. Check your DMs for today's code."), ephemeral=True)
        return

    e = discord.Embed(title="🛡️ Staff Control Panel", color=0x9b59b6)
    e.add_field(name="📋 Moderation", value="`/ban` `/kick` `/mute` `/warn` `/purge`\n`/lock` `/unlock` `/lockdown` `/slowmode`", inline=False)
    e.add_field(name="📊 Information", value="`/userinfo` `/serverinfo` `/warnings`\n`/auditlog` `/stafflist`", inline=False)
    e.add_field(name="⚙️ Management", value="`/announce` `/embed` `/role`\n`/nick` `/tempban` `/softban`", inline=False)
    e.add_field(name="🔧 Config", value="`/config` `/automod` `/setlog`\n`/setwelcome` `/setreport`", inline=False)
    e.add_field(name="📩 Messages", value="`/dmuser` `/dmreply` `/broadcast`", inline=False)
    website = config.get("website", "https://yourwebsite.com")
    dash = config.get("dashboard", "https://yourdashboard.com")
    e.add_field(name="🔗 Links", value=f"[Dashboard]({dash}) • [Website]({website})", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True, view=NavView())

@tree.command(name="generatecode", description="[OWNER] Generate today's staff code")
async def generate_code(interaction: discord.Interaction):
    if interaction.user.id != config.get("owner_id"):
        await interaction.response.send_message(embed=error_embed("Forbidden", "Owner only."), ephemeral=True)
        return
    code = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    today = get_today_str()
    if "daily_codes" not in config:
        config["daily_codes"] = {}
    config["daily_codes"][today] = code
    save_json(CONFIG_FILE, config)
    e = discord.Embed(title="🔐 Daily Staff Code Generated", description=f"**Date:** {today}\n**Code:** `{code}`\n\nShare this ONLY with staff.", color=0x2ecc71)
    await interaction.response.send_message(embed=e, ephemeral=True)

    # DM all staff
    staff_role_ids = config.get("staff_roles", [])
    for member in interaction.guild.members:
        if is_staff(member) and not member.bot:
            try:
                await member.send(embed=discord.Embed(title="🔐 Today's Staff Code", description=f"**{today}**\nYour code: `{code}`\nUse `/staff {code}` to access the panel.", color=0x9b59b6))
            except:
                pass

@tree.command(name="setstaffcode", description="[OWNER] Set a permanent staff verification code")
@app_commands.describe(code="The permanent code")
async def set_staff_code(interaction: discord.Interaction, code: str):
    if interaction.user.id != config.get("owner_id"):
        await interaction.response.send_message(embed=error_embed("Forbidden", "Owner only."), ephemeral=True)
        return
    config["staff_code"] = hashlib.sha256(code.encode()).hexdigest()
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Code Set", "Staff verification code updated."), ephemeral=True)

# ─── PORTFOLIO / ROBLOX ───────────────────────────────────────────────────────

@tree.command(name="portfolio", description="View a Roblox portfolio")
@app_commands.describe(user_id="Roblox User ID", image_url="Optional portfolio image URL")
async def portfolio(interaction: discord.Interaction, user_id: str, image_url: str = None):
    obf = obfuscate_roblox_link(user_id)
    base = config.get("roblox_portfolio", "https://www.roblox.com/users/")
    e = discord.Embed(title="🎮 Roblox Portfolio", color=0xff4444)
    e.add_field(name="Profile", value=f"[View Profile]({base}{user_id}/profile)", inline=False)
    e.add_field(name="Portfolio ID", value=f"`{obf}`", inline=True)
    if image_url:
        e.set_image(url=image_url)
    e.set_footer(text="Powered by UltraBot")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="roblox", description="Look up a Roblox user")
@app_commands.describe(username="Roblox username")
async def roblox_lookup(interaction: discord.Interaction, username: str):
    e = discord.Embed(title=f"🎮 Roblox: {username}", color=0xff4444)
    e.add_field(name="Search", value=f"[Search on Roblox](https://www.roblox.com/search/users?keyword={username})")
    e.add_field(name="Direct Link", value=f"[Try Profile](https://www.roblox.com/user.aspx?username={username})")
    await interaction.response.send_message(embed=e, view=NavView())

# ─── CUSTOM AI (ROBLOX ONLY) ──────────────────────────────────────────────────

ai_conversations = {}

@tree.command(name="ask", description="Ask the Roblox AI assistant")
@app_commands.describe(question="Your Roblox-related question")
async def ask_ai(interaction: discord.Interaction, question: str):
    if not config["ai"].get("enabled", True):
        await interaction.response.send_message(embed=error_embed("AI Disabled", "The AI assistant is currently disabled."), ephemeral=True)
        return

    roblox_keywords = ["roblox", "robux", "studio", "game", "avatar", "ugc", "developer", "script", "lua", "badge", "pass", "gamepass", "group", "team create", "place", "experience", "npc", "tool", "gear", "hat", "shirt", "pants", "animation", "morph", "model", "plugin", "leaderboard", "datastore", "remote", "bindable", "module", "localscript", "serverscript"]

    if config["ai"].get("roblox_only", True):
        if not any(kw in question.lower() for kw in roblox_keywords):
            await interaction.response.send_message(embed=error_embed("Off-Topic", "I only answer Roblox-related questions! Ask me about Roblox Studio, scripting, games, avatars, etc."), ephemeral=True)
            return

    await interaction.response.defer()
    uid = str(interaction.user.id)

    roblox_context = """You are RobloxBot, an expert Roblox assistant. You ONLY answer questions about Roblox - including:
- Roblox Studio and game development
- Lua scripting for Roblox
- Roblox avatars, items, UGC
- Roblox groups, experiences, game passes
- DataStore, RemoteEvents, ModuleScripts
- Game monetization and developer tips
If asked anything not related to Roblox, politely decline and redirect to Roblox topics.
Be helpful, detailed, and friendly. Format code in code blocks."""

    if uid not in ai_conversations:
        ai_conversations[uid] = []

    ai_conversations[uid].append({"role": "user", "content": question})
    if len(ai_conversations[uid]) > 20:
        ai_conversations[uid] = ai_conversations[uid][-20:]

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "system": roblox_context,
                "messages": ai_conversations[uid]
            }
            headers = {
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers) as resp:
                data = await resp.json()
                answer = data["content"][0]["text"]

        ai_conversations[uid].append({"role": "assistant", "content": answer})

        e = discord.Embed(title="🤖 Roblox AI", color=0xff4444)
        e.add_field(name="❓ Question", value=question, inline=False)
        e.add_field(name="💡 Answer", value=answer[:1000], inline=False)
        e.set_footer(text=f"Asked by {interaction.user}")
        await interaction.followup.send(embed=e, view=NavView())
    except Exception as ex:
        await interaction.followup.send(embed=error_embed("AI Error", f"Failed to get response: {ex}"))

@tree.command(name="clearai", description="Clear your AI conversation history")
async def clear_ai(interaction: discord.Interaction):
    ai_conversations.pop(str(interaction.user.id), None)
    await interaction.response.send_message(embed=success_embed("Cleared", "Your AI conversation history has been cleared."), ephemeral=True)

# ─── DM COMMANDS ─────────────────────────────────────────────────────────────

@tree.command(name="dmuser", description="DM a user as the bot")
@app_commands.describe(user="User to DM", message="Message to send")
async def dmuser(interaction: discord.Interaction, user: discord.Member, message: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    try:
        e = discord.Embed(title=f"📩 Message from {interaction.guild.name}", description=message, color=0x3498db)
        e.set_footer(text="You can reply to this message and staff will see it.")
        await user.send(embed=e)
        await interaction.response.send_message(embed=success_embed("DM Sent", f"Message sent to {user.mention}."), ephemeral=True)
    except Exception as ex:
        await interaction.response.send_message(embed=error_embed("Failed", f"Could not DM user: {ex}"), ephemeral=True)

@tree.command(name="dmreply", description="Reply to a user's DM")
@app_commands.describe(user_id="User ID to reply to", message="Reply message")
async def dm_reply(interaction: discord.Interaction, user_id: str, message: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        e = discord.Embed(title=f"📩 Staff Reply from {interaction.guild.name}", description=message, color=0x9b59b6)
        await user.send(embed=e)
        await interaction.response.send_message(embed=success_embed("Replied", f"Reply sent to {user}."), ephemeral=True)
    except Exception as ex:
        await interaction.response.send_message(embed=error_embed("Error", str(ex)), ephemeral=True)

@tree.command(name="broadcast", description="Broadcast a message to all members")
@app_commands.describe(message="Message to broadcast")
async def broadcast(interaction: discord.Interaction, message: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    sent = 0
    failed = 0
    for member in interaction.guild.members:
        if not member.bot:
            try:
                e = discord.Embed(title=f"📢 Broadcast from {interaction.guild.name}", description=message, color=0xe67e22)
                await member.send(embed=e)
                sent += 1
            except:
                failed += 1
    await interaction.followup.send(embed=success_embed("Broadcast Complete", f"Sent: {sent} | Failed: {failed}"), ephemeral=True)

# ─── CONFIG COMMANDS ──────────────────────────────────────────────────────────

@tree.command(name="config", description="[ADMIN] View current bot configuration")
async def view_config(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Admin only."), ephemeral=True)
        return
    e = discord.Embed(title="⚙️ Bot Configuration", color=0x3498db)
    log_ch = interaction.guild.get_channel(config.get("log_channel") or 0)
    mod_ch = interaction.guild.get_channel(config.get("mod_log_channel") or 0)
    wel_ch = interaction.guild.get_channel(config.get("welcome_channel") or 0)
    rep_ch = interaction.guild.get_channel(config.get("report_channel") or 0)
    bot_ch = interaction.guild.get_channel(config.get("bot_commands_channel") or 0)
    cnt_ch = interaction.guild.get_channel(config.get("counting_channel") or 0)
    e.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set")
    e.add_field(name="Mod Log", value=mod_ch.mention if mod_ch else "Not set")
    e.add_field(name="Welcome", value=wel_ch.mention if wel_ch else "Not set")
    e.add_field(name="Reports", value=rep_ch.mention if rep_ch else "Not set")
    e.add_field(name="Bot Commands", value=bot_ch.mention if bot_ch else "Not set")
    e.add_field(name="Counting", value=cnt_ch.mention if cnt_ch else "Not set")
    e.add_field(name="AutoMod", value="✅ Enabled" if config["automod"]["enabled"] else "❌ Disabled")
    e.add_field(name="Anti-Nuke", value="✅" if config["automod"]["anti_nuke"] else "❌")
    e.add_field(name="Anti-Raid", value="✅" if config["automod"]["anti_raid"] else "❌")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="setlog", description="[ADMIN] Set the log channel")
@app_commands.describe(channel="Log channel")
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["log_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Log Channel Set", f"Logs → {channel.mention}"), view=NavView())

@tree.command(name="setmodlog", description="[ADMIN] Set the mod log channel")
@app_commands.describe(channel="Mod log channel")
async def setmodlog(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["mod_log_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Mod Log Set", f"Mod logs → {channel.mention}"), view=NavView())

@tree.command(name="setwelcome", description="[ADMIN] Set the welcome channel")
@app_commands.describe(channel="Welcome channel")
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["welcome_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Welcome Channel Set", f"Welcome → {channel.mention}"), view=NavView())

@tree.command(name="setreport", description="[ADMIN] Set the report channel")
@app_commands.describe(channel="Report channel")
async def setreport(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["report_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Report Channel Set", f"Reports → {channel.mention}"), view=NavView())

@tree.command(name="setbotchannel", description="[ADMIN] Set the bot commands channel")
@app_commands.describe(channel="Bot commands channel")
async def setbotchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["bot_commands_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Bot Commands Channel Set", f"Bot commands → {channel.mention}"), view=NavView())

@tree.command(name="setcounting", description="[ADMIN] Set the counting channel")
@app_commands.describe(channel="Counting channel")
async def setcounting(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["counting_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Counting Channel Set", f"Counting → {channel.mention}"), view=NavView())

@tree.command(name="setstaff", description="[ADMIN] Set the staff channel")
@app_commands.describe(channel="Staff channel")
async def setstaff_ch(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return
    config["staff_channel"] = channel.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Staff Channel Set", f"Staff → {channel.mention}"), view=NavView())

@tree.command(name="addstaffrole", description="[ADMIN] Add a staff role")
@app_commands.describe(role="Staff role to add")
async def add_staff_role(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user): return
    if role.id not in config["staff_roles"]:
        config["staff_roles"].append(role.id)
        save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Staff Role Added", f"{role.mention} is now a staff role."), view=NavView())

@tree.command(name="addadminrole", description="[ADMIN] Add an admin role")
@app_commands.describe(role="Admin role to add")
async def add_admin_role(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user): return
    if role.id not in config["admin_roles"]:
        config["admin_roles"].append(role.id)
        save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Admin Role Added", f"{role.mention} is now an admin role."), view=NavView())

@tree.command(name="automod", description="[ADMIN] Configure automod settings")
@app_commands.describe(setting="Setting name", value="true/false or number")
async def automod_cmd(interaction: discord.Interaction, setting: str, value: str):
    if not is_admin(interaction.user): return
    bool_settings = ["enabled","ban_bad_links","ban_invite_links","anti_nuke","anti_spam","anti_caps","anti_mass_mention","anti_raid","anti_ghost_ping"]
    if setting in bool_settings:
        config["automod"][setting] = value.lower() in ("true","yes","1","on")
    elif setting in ["max_mentions","spam_threshold","max_warnings","mute_duration"]:
        config["automod"][setting] = int(value)
    elif setting == "caps_threshold":
        config["automod"][setting] = float(value)
    elif setting == "warn_action":
        config["automod"][setting] = value  # mute/kick/ban
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("AutoMod Updated", f"`{setting}` set to `{value}`"), view=NavView())

@tree.command(name="addbadword", description="[ADMIN] Add a word to the filter")
@app_commands.describe(word="Word to filter")
async def add_bad_word(interaction: discord.Interaction, word: str):
    if not is_admin(interaction.user): return
    if word not in config["automod"]["bad_words"]:
        config["automod"]["bad_words"].append(word.lower())
        save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Word Added", f"`{word}` added to filter."), ephemeral=True)

@tree.command(name="removebadword", description="[ADMIN] Remove a word from the filter")
@app_commands.describe(word="Word to remove")
async def remove_bad_word(interaction: discord.Interaction, word: str):
    if not is_admin(interaction.user): return
    if word.lower() in config["automod"]["bad_words"]:
        config["automod"]["bad_words"].remove(word.lower())
        save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Word Removed", f"`{word}` removed from filter."), ephemeral=True)

@tree.command(name="setwebsite", description="[OWNER] Set the website URL")
@app_commands.describe(url="Website URL")
async def set_website(interaction: discord.Interaction, url: str):
    if interaction.user.id != config.get("owner_id"): return
    config["website"] = url
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Website Set", f"Website: {url}"), ephemeral=True)

@tree.command(name="setdashboard", description="[OWNER] Set the dashboard URL")
@app_commands.describe(url="Dashboard URL")
async def set_dashboard(interaction: discord.Interaction, url: str):
    if interaction.user.id != config.get("owner_id"): return
    config["dashboard"] = url
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Dashboard Set", f"Dashboard: {url}"), ephemeral=True)

# ─── INFO / UTILITY COMMANDS ─────────────────────────────────────────────────

@tree.command(name="help", description="View all available commands")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(title="📚 UltraBot Commands", color=0x9b59b6)
    e.add_field(name="🛡️ Moderation (Staff)", value="`/ban` `/unban` `/kick` `/mute` `/unmute`\n`/warn` `/warnings` `/clearwarnings` `/purge`\n`/lock` `/unlock` `/lockdown` `/slowmode`\n`/nick` `/role` `/softban` `/tempban`", inline=False)
    e.add_field(name="📊 Information", value="`/userinfo` `/serverinfo` `/avatar`\n`/stafflist` `/botinfo` `/ping`", inline=False)
    e.add_field(name="🎮 Roblox", value="`/roblox` `/portfolio` `/ask`", inline=False)
    e.add_field(name="⏰ Timers", value="`/timer` `/remindme`", inline=False)
    e.add_field(name="🎉 Fun / Community", value="`/poll` `/giveaway` `/coinflip`\n`/8ball` `/dice` `/choose`", inline=False)
    e.add_field(name="📋 Utility", value="`/report` `/bugreport` `/feedback`\n`/suggest` `/embed` `/announce`", inline=False)
    e.add_field(name="🔐 Staff", value="`/staff` (requires daily code)", inline=False)
    e.add_field(name="⚙️ Config (Admin)", value="`/config` `/setlog` `/setmodlog` `/setwelcome`\n`/setreport` `/setbotchannel` `/setcounting`\n`/automod` `/addbadword` `/addstaffrole`", inline=False)
    website = config.get("website", "https://yourwebsite.com")
    dash = config.get("dashboard", "https://yourdashboard.com")
    e.add_field(name="🔗 Links", value=f"[🌐 Website]({website}) • [📊 Dashboard]({dash})", inline=False)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    e = discord.Embed(title="🏓 Pong!", description=f"Latency: **{round(bot.latency * 1000)}ms**", color=0x2ecc71)
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="botinfo", description="View information about this bot")
async def botinfo(interaction: discord.Interaction):
    e = discord.Embed(title="🤖 UltraBot", color=0x9b59b6)
    e.add_field(name="Guilds", value=len(bot.guilds))
    e.add_field(name="Commands", value="50+")
    e.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms")
    e.add_field(name="Features", value="AutoMod, Anti-Nuke, AI, Staff System, Counting, Timers")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="stafflist", description="View all current staff members")
async def stafflist(interaction: discord.Interaction):
    staff_ids = set(config.get("staff_roles", []) + config.get("admin_roles", []) + config.get("mod_roles", []))
    members_list = []
    for member in interaction.guild.members:
        if any(r.id in staff_ids for r in member.roles):
            members_list.append(f"• {member.mention} ({', '.join(r.name for r in member.roles if r.id in staff_ids)})")
    e = discord.Embed(title="👥 Staff List", color=0x3498db)
    e.description = "\n".join(members_list) if members_list else "No staff members found."
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="auditlog", description="View recent audit log entries")
@app_commands.describe(limit="Number of entries (max 20)")
async def auditlog(interaction: discord.Interaction, limit: int = 10):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    limit = min(limit, 20)
    e = discord.Embed(title="📋 Recent Audit Log", color=0x3498db)
    entries = []
    async for entry in interaction.guild.audit_logs(limit=limit):
        entries.append(f"• **{entry.action.name}** by {entry.user.mention} — {discord.utils.format_dt(entry.created_at, 'R')}")
    e.description = "\n".join(entries) if entries else "No entries."
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="note", description="[STAFF] Add a note about a user")
@app_commands.describe(user="User to note", note="The note")
async def add_note(interaction: discord.Interaction, user: discord.Member, note: str):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    uid = str(user.id)
    if uid not in notes:
        notes[uid] = []
    notes[uid].append({"note": note, "by": str(interaction.user), "time": datetime.datetime.utcnow().isoformat()})
    save_json(NOTES_FILE, notes)
    await interaction.response.send_message(embed=success_embed("Note Added", f"Note added for {user.mention}."), ephemeral=True)

@tree.command(name="notes", description="[STAFF] View notes about a user")
@app_commands.describe(user="User to view notes for")
async def view_notes(interaction: discord.Interaction, user: discord.Member):
    if not is_staff(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Permission", "Staff only."), ephemeral=True)
        return
    uid = str(user.id)
    user_notes = notes.get(uid, [])
    if not user_notes:
        await interaction.response.send_message(embed=info_embed("No Notes", f"No notes for {user.mention}."), ephemeral=True)
        return
    e = discord.Embed(title=f"📝 Notes for {user}", color=0xf39c12)
    for i, n in enumerate(user_notes, 1):
        e.add_field(name=f"Note #{i} by {n['by']}", value=f"{n['note']}\n*{n['time'][:10]}*", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

# ─── FUN COMMANDS ─────────────────────────────────────────────────────────────

@tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads 🪙", "Tails 🪙"])
    await interaction.response.send_message(embed=info_embed("Coin Flip", result, color=0xf1c40f), view=NavView())

@tree.command(name="8ball", description="Ask the magic 8 ball")
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    answers = ["It is certain ✅", "Without a doubt ✅", "Yes, definitely ✅", "You may rely on it ✅",
               "As I see it, yes ✅", "Most likely ✅", "Outlook good ✅", "Yes ✅",
               "Signs point to yes ✅", "Reply hazy, try again ⚠️", "Ask again later ⚠️",
               "Better not tell you now ⚠️", "Cannot predict now ⚠️", "Concentrate and ask again ⚠️",
               "Don't count on it ❌", "My reply is no ❌", "My sources say no ❌",
               "Outlook not so good ❌", "Very doubtful ❌"]
    e = discord.Embed(title="🎱 Magic 8 Ball", color=0x1a1a2e)
    e.add_field(name="Question", value=question)
    e.add_field(name="Answer", value=random.choice(answers))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="dice", description="Roll some dice")
@app_commands.describe(sides="Number of sides (default 6)", count="Number of dice (default 1)")
async def dice(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    count = min(count, 20)
    rolls = [random.randint(1, sides) for _ in range(count)]
    e = discord.Embed(title=f"🎲 Rolled {count}d{sides}", color=0x9b59b6)
    e.add_field(name="Results", value=" + ".join(str(r) for r in rolls))
    e.add_field(name="Total", value=sum(rolls))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="choose", description="Choose between options")
@app_commands.describe(options="Options separated by | (e.g. pizza|burger|tacos)")
async def choose(interaction: discord.Interaction, options: str):
    opts = [o.strip() for o in options.split("|")]
    choice = random.choice(opts)
    e = discord.Embed(title="🎯 I Choose...", description=f"**{choice}**", color=0xe67e22)
    e.add_field(name="From", value=" • ".join(opts))
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="feedback", description="Submit feedback about the server")
@app_commands.describe(feedback="Your feedback")
async def feedback(interaction: discord.Interaction, feedback: str):
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="💬 Feedback Received", color=0x2ecc71)
            e.add_field(name="From", value=interaction.user.mention)
            e.add_field(name="Feedback", value=feedback, inline=False)
            await ch.send(embed=e)
    await interaction.response.send_message(embed=success_embed("Feedback Sent", "Thank you for your feedback!"), ephemeral=True, view=NavView())

@tree.command(name="suggest", description="Submit a suggestion")
@app_commands.describe(suggestion="Your suggestion")
async def suggest(interaction: discord.Interaction, suggestion: str):
    ch_id = config.get("report_channel")
    if ch_id:
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(title="💡 New Suggestion", color=0xf1c40f)
            e.add_field(name="From", value=interaction.user.mention)
            e.add_field(name="Suggestion", value=suggestion, inline=False)
            msg = await ch.send(embed=e)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
    await interaction.response.send_message(embed=success_embed("Suggestion Submitted", "Your suggestion has been sent!"), ephemeral=True, view=NavView())

@tree.command(name="premium", description="Check your premium status")
async def check_premium(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    is_prem = uid in premium
    prem_channels = config.get("premium_channels", [])
    ch_mentions = [interaction.guild.get_channel(c).mention for c in prem_channels if interaction.guild.get_channel(c)]
    e = discord.Embed(title="⭐ Premium Status", color=0xf1c40f if is_prem else 0x95a5a6)
    e.description = f"**Status:** {'⭐ Premium' if is_prem else '🔒 Standard'}"
    if prem_channels:
        e.add_field(name="Premium Channels", value="\n".join(ch_mentions) or "None configured")
    await interaction.response.send_message(embed=e, view=NavView())

@tree.command(name="addpremium", description="[ADMIN] Add premium to a user")
@app_commands.describe(user="User to grant premium")
async def add_premium(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user): return
    premium[str(user.id)] = {"granted_by": str(interaction.user), "time": datetime.datetime.utcnow().isoformat()}
    save_json(PREMIUM_USERS_FILE, premium)
    await interaction.response.send_message(embed=success_embed("Premium Added", f"{user.mention} now has premium."), view=NavView())

@tree.command(name="removepremium", description="[ADMIN] Remove premium from a user")
@app_commands.describe(user="User to remove premium from")
async def remove_premium(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user): return
    premium.pop(str(user.id), None)
    save_json(PREMIUM_USERS_FILE, premium)
    await interaction.response.send_message(embed=success_embed("Premium Removed", f"{user.mention}'s premium has been removed."), view=NavView())

@tree.command(name="setowner", description="[FIRST RUN] Set yourself as bot owner")
async def set_owner(interaction: discord.Interaction):
    if config.get("owner_id"):
        await interaction.response.send_message(embed=error_embed("Already Set", "Owner is already configured."), ephemeral=True)
        return
    config["owner_id"] = interaction.user.id
    config["guild_id"] = interaction.guild.id
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(embed=success_embed("Owner Set", f"{interaction.user.mention} is now the bot owner."), ephemeral=True)

# ─── MOD LOG HELPER ───────────────────────────────────────────────────────────

async def _mod_log(guild, action, moderator, target, reason):
    ch_id = config.get("mod_log_channel") or config.get("log_channel")
    if not ch_id:
        return
    ch = guild.get_channel(ch_id)
    if not ch:
        return
    colors = {"BAN": 0xe74c3c, "KICK": 0xe67e22, "MUTE": 0xf39c12, "WARN": 0xf1c40f, "UNBAN": 0x2ecc71}
    e = discord.Embed(title=f"🔨 {action}", color=colors.get(action, 0x3498db))
    e.add_field(name="Moderator", value=moderator.mention)
    e.add_field(name="Target", value=target.mention if hasattr(target, 'mention') else str(target))
    e.add_field(name="Reason", value=reason, inline=False)
    e.timestamp = datetime.datetime.utcnow()
    await ch.send(embed=e)

# ─── TASKS ────────────────────────────────────────────────────────────────────

@tasks.loop(hours=24)
async def daily_code_task():
    """Auto-generate and distribute daily staff codes"""
    code = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    today = get_today_str()
    if "daily_codes" not in config:
        config["daily_codes"] = {}
    config["daily_codes"][today] = code
    save_json(CONFIG_FILE, config)

    guild_id = config.get("guild_id")
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            for member in guild.members:
                if is_staff(member) and not member.bot:
                    try:
                        await member.send(embed=discord.Embed(title="🔐 Daily Staff Code", description=f"Today's code: `{code}`\nUse `/staff {code}` to access the staff panel.", color=0x9b59b6))
                    except:
                        pass

# ─── READY ────────────────────────────────────────────────────────────────────

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

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
    bot.run(TOKEN)
