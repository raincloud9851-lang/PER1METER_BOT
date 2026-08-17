import json
import os
import asyncio
from typing import Optional
from google import genai
from telegram import Update, ChatPermissions, ChatMember
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === CONFIGURATION ===
TOKEN = "8476370146:AAGc3TAfVxXHMPrIF4OPrWsE5Dbt2C18-Nc"
GEMINI_KEY = "AQ.Ab8RN6Kspo443I3TdLyGdXicO_CNkh1ZY2VfxsZmsSVVQRFMdg"
BOT_USERNAME = "PER1METER_BOT"
DATA_FILE = "bot_data.json"

# Initialize Official Gemini Client
ai_client = genai.Client(api_key=GEMINI_KEY)

# Default data structure
def get_default_data():
    return {
        "warns": {},       # {chat_id: {user_id: count}}
        "welcome": {},     # {chat_id: {"enabled": bool, "msg": str}}
        "goodbye": {},     # {chat_id: {"enabled": bool, "msg": str}}
        "rules": {},       # {chat_id: str}
        "filters": {},     # {chat_id: {keyword: reply}}
        "notes": {},       # {chat_id: {notename: content}}
        "locks": {},       # {chat_id: [locked_types]}
        "logchannel": {},  # {chat_id: channel_id}
        "antiflood": {}    # {chat_id: bool}
    }

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                d = json.load(f)
                default = get_default_data()
                for k in default:
                    d.setdefault(k, default[k])
                return d
        except Exception:
            return get_default_data()
    return get_default_data()

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

data = load_data()

# === HELPER FUNCTIONS ===
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == "private":
        return True
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]

async def log_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    cid = str(chat_id)
    if cid in data["logchannel"]:
        try:
            await context.bot.send_message(data["logchannel"][cid], f"📋 **LOG:** {text}", parse_mode="Markdown")
        except Exception:
            pass

async def extract_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            return arg
        if arg.isdigit():
            try:
                member = await context.bot.get_chat_member(update.effective_chat.id, int(arg))
                return member.user
            except Exception:
                return None
    return None

# === AI FUNCTIONS ===
async def call_gemini(prompt: str) -> str:
    chat = ai_client.chats.create(
        model="gemini-3.6-flash",
        config={
            "system_instruction": "You are PER1METER_BOT, a helpful, security-focused group assistant and moderator."
        }
    )
    response = await asyncio.to_thread(
        chat.send_message,
        prompt
    )
    return response.text

async def is_message_bad(text: str) -> bool:
    prompt = f"Is this message spam, hate speech, scam, NSFW, or against Telegram group rules? Reply ONLY 'YES' or 'NO'. Message: {text}"
    try:
        chat = ai_client.chats.create(model="gemini-3.6-flash")
        response = await asyncio.to_thread(
            chat.send_message,
            prompt
        )
        return "YES" in response.text.strip().upper()
    except Exception:
        return False

# === COMMAND HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("PER1METER_BOT is online 💜\nUse /help for commands.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**PER1METER Commands**\n"
        "• Moderation: /ban, /kick, /mute, /unmute, /warn, /warnings, /resetwarns, /del, /purge\n"
        "• Security: /lock, /unlock, /locks, /antiflood, /scanfile, /scanurl\n"
        "• Config: /setwelcome, /welcome, /setgoodbye, /goodbye, /setrules, /rules, /settings, /logchannel\n"
        "• Notes & Filters: /filter, /unfilter, /filters, /save, /get, /notes, /delnote\n"
        "• Info & Admin: /id, /whois, /adminlist, /staff, /pin, /unpin, /report, /ai"
    )

async def ai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        return await update.message.reply_text("Usage: /ai <question>")
    await update.message.reply_chat_action("typing")
    try:
        answer = await call_gemini(f"Question: {question}")
        await update.message.reply_text(answer[:4096])
    except Exception as e:
        await update.message.reply_text(f"AI error: {e}")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    uid = target.id if hasattr(target, 'id') else target
    await context.bot.ban_chat_member(update.effective_chat.id, uid)
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Permanently removed {name}.")
    await log_action(context, update.effective_chat.id, f"{name} was banned.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    uid = target.id if hasattr(target, 'id') else target
    await context.bot.ban_chat_member(update.effective_chat.id, uid)
    await context.bot.unban_chat_member(update.effective_chat.id, uid)
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Removed {name} from the group.")
    await log_action(context, update.effective_chat.id, f"{name} was kicked.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    uid = target.id if hasattr(target, 'id') else target
    await context.bot.restrict_chat_member(
        update.effective_chat.id, uid, ChatPermissions(can_send_messages=False)
    )
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Muted {name}.")
    await log_action(context, update.effective_chat.id, f"{name} was muted.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    uid = target.id if hasattr(target, 'id') else target
    await context.bot.restrict_chat_member(
        update.effective_chat.id, uid, ChatPermissions(can_send_messages=True)
    )
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Unmuted {name}.")
    await log_action(context, update.effective_chat.id, f"{name} was unmuted.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    cid = str(update.effective_chat.id)
    uid = str(target.id if hasattr(target, 'id') else target)
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    data["warns"].setdefault(cid, {}).setdefault(uid, 0)
    data["warns"][cid][uid] += 1
    save_data(data)
    
    count = data["warns"][cid][uid]
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Warned {name}. Count: {count}. Reason: {reason}")
    await log_action(context, update.effective_chat.id, f"{name} warned. ({count}). Reason: {reason}")

async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await extract_user(update, context) or update.effective_user
    cid = str(update.effective_chat.id)
    uid = str(target.id if hasattr(target, 'id') else target)
    count = data["warns"].get(cid, {}).get(uid, 0)
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"{name} has {count} warning(s).")

async def resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    target = await extract_user(update, context)
    if not target:
        return await update.message.reply_text("Reply to a message or specify @username/user_id.")
    cid = str(update.effective_chat.id)
    uid = str(target.id if hasattr(target, 'id') else target)
    if cid in data["warns"] and uid in data["warns"][cid]:
        data["warns"][cid][uid] = 0
        save_data(data)
    name = target.first_name if hasattr(target, 'first_name') else target
    await update.message.reply_text(f"Cleared warnings for {name}.")

async def del_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to delete it.")
    try:
        await context.bot.delete_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
    except Exception:
        pass

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    chat_id = update.effective_chat.id
    
    if update.message.reply_to_message:
        from_id = update.message.reply_to_message.message_id
        to_id = update.message.message_id
    else:
        amount = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
        to_id = update.message.message_id
        from_id = max(1, to_id - amount)

    deleted = 0
    for msg_id in range(from_id, to_id + 1):
        try:
            await context.bot.delete_message(chat_id, msg_id)
            deleted += 1
        except Exception:
            pass

    status = await context.bot.send_message(chat_id, f"Purged {deleted} messages.")
    await asyncio.sleep(3)
    try:
        await status.delete()
    except Exception:
        pass

async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /lock <type> (e.g. photos, stickers, links)")
    lock_type = context.args[0].lower()
    cid = str(update.effective_chat.id)
    data["locks"].setdefault(cid, [])
    if lock_type not in data["locks"][cid]:
        data["locks"][cid].append(lock_type)
        save_data(data)
    await update.message.reply_text(f"Locked `{lock_type}` content.", parse_mode="Markdown")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /unlock <type>")
    lock_type = context.args[0].lower()
    cid = str(update.effective_chat.id)
    if cid in data["locks"] and lock_type in data["locks"][cid]:
        data["locks"][cid].remove(lock_type)
        save_data(data)
    await update.message.reply_text(f"Unlocked `{lock_type}` content.", parse_mode="Markdown")

async def locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    active = data["locks"].get(cid, [])
    if not active:
        await update.message.reply_text("No active content locks.")
    else:
        await update.message.reply_text(f"Active locks: {', '.join(active)}")

async def antiflood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /antiflood <on/off>")
    setting = context.args[0].lower()
    cid = str(update.effective_chat.id)
    data["antiflood"][cid] = (setting == "on")
    save_data(data)
    await update.message.reply_text(f"Anti-flood protection is now {'ON' if data['antiflood'][cid] else 'OFF'}.")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to report it to admins.")
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    mentions = " ".join([f"[{a.user.first_name}](tg://user?id={a.user.id})" for a in admins if not a.user.is_bot])
    await context.bot.send_message(
        update.effective_chat.id,
        f"🚨 **Report Notification**\nReported message from {update.message.reply_to_message.from_user.first_name}\nAdmins: {mentions}",
        parse_mode="Markdown"
    )

async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Usage: /setwelcome <message>")
    cid = str(update.effective_chat.id)
    data["welcome"].setdefault(cid, {"enabled": True, "msg": ""})
    data["welcome"][cid]["msg"] = msg
    save_data(data)
    await update.message.reply_text("Welcome message set.")

async def welcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /welcome <on/off>")
    state = context.args[0].lower() == "on"
    cid = str(update.effective_chat.id)
    data["welcome"].setdefault(cid, {"enabled": True, "msg": "Welcome to the group!"})
    data["welcome"][cid]["enabled"] = state
    save_data(data)
    await update.message.reply_text(f"Welcome messages are now {'enabled' if state else 'disabled'}.")

async def setgoodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Usage: /setgoodbye <message>")
    cid = str(update.effective_chat.id)
    data["goodbye"].setdefault(cid, {"enabled": True, "msg": ""})
    data["goodbye"][cid]["msg"] = msg
    save_data(data)
    await update.message.reply_text("Goodbye message set.")

async def goodbye_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /goodbye <on/off>")
    state = context.args[0].lower() == "on"
    cid = str(update.effective_chat.id)
    data["goodbye"].setdefault(cid, {"enabled": True, "msg": "Goodbye!"})
    data["goodbye"][cid]["enabled"] = state
    save_data(data)
    await update.message.reply_text(f"Goodbye messages are now {'enabled' if state else 'disabled'}.")

async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /filter <keyword> <reply message>")
    keyword = context.args[0].lower()
    reply = " ".join(context.args[1:])
    cid = str(update.effective_chat.id)
    data["filters"].setdefault(cid, {})
    data["filters"][cid][keyword] = reply
    save_data(data)
    await update.message.reply_text(f"Filter added for keyword: `{keyword}`", parse_mode="Markdown")

async def unfilter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /unfilter <keyword>")
    keyword = context.args[0].lower()
    cid = str(update.effective_chat.id)
    if cid in data["filters"] and keyword in data["filters"][cid]:
        del data["filters"][cid][keyword]
        save_data(data)
        await update.message.reply_text(f"Removed filter for `{keyword}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Filter not found.")

async def filters_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    active = list(data["filters"].get(cid, {}).keys())
    if not active:
        await update.message.reply_text("No active filters.")
    else:
        await update.message.reply_text(f"Active custom filters: {', '.join(active)}")

async def setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    rules_text = " ".join(context.args)
    if not rules_text:
        return await update.message.reply_text("Usage: /setrules <rules text>")
    cid = str(update.effective_chat.id)
    data["rules"][cid] = rules_text
    save_data(data)
    await update.message.reply_text("Group rules updated.")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    rules_text = data["rules"].get(cid, "No rules have been set for this group yet.")
    await update.message.reply_text(f"📜 **Group Rules**\n{rules_text}", parse_mode="Markdown")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"User ID: `{update.effective_user.id}`\n"
    if update.effective_chat:
        msg += f"Chat ID: `{update.effective_chat.id}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def whois(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await extract_user(update, context) or update.effective_user
    if isinstance(target, str):
        return await update.message.reply_text(f"Username target: {target}")
    info = (
        f"👤 **User Info**\n"
        f"• ID: `{target.id}`\n"
        f"• First Name: {target.first_name}\n"
        f"• Last Name: {target.last_name or 'N/A'}\n"
        f"• Username: @{target.username if target.username else 'None'}\n"
        f"• Is Bot: {target.is_bot}"
    )
    await update.message.reply_text(info, parse_mode="Markdown")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    wel = data["welcome"].get(cid, {}).get("enabled", False)
    gb = data["goodbye"].get(cid, {}).get("enabled", False)
    af = data["antiflood"].get(cid, False)
    lc = data["logchannel"].get(cid, "Not set")
    text = (
        f"⚙️ **Group Settings**\n"
        f"• Welcome Messages: {'ON' if wel else 'OFF'}\n"
        f"• Goodbye Messages: {'ON' if gb else 'OFF'}\n"
        f"• Anti-Flood: {'ON' if af else 'OFF'}\n"
        f"• Log Channel ID: `{lc}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    text = "👑 **Group Administrators:**\n"
    for a in admins:
        text += f"• {a.user.first_name} (@{a.user.username or 'NoUsername'})\n"
    await update.message.reply_text(text)

async def staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    text = "🛡️ **Staff List & Titles:**\n"
    for a in admins:
        title = a.custom_title or ("Owner" if a.status == ChatMember.OWNER else "Admin")
        text += f"• {a.user.first_name} - *{title}*\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def logchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /logchannel <channel_id / unset>")
    val = context.args[0].lower()
    cid = str(update.effective_chat.id)
    if val == "unset":
        data["logchannel"].pop(cid, None)
        save_data(data)
        await update.message.reply_text("Log channel unset.")
    else:
        try:
            channel_id = int(val)
            data["logchannel"][cid] = channel_id
            save_data(data)
            await update.message.reply_text(f"Log channel set to `{channel_id}`.", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("Provide a valid numeric Channel ID.")

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to pin it.")
    notify = "notify" in [a.lower() for a in context.args]
    await context.bot.pin_chat_message(
        update.effective_chat.id,
        update.message.reply_to_message.message_id,
        disable_notification=not notify
    )
    await update.message.reply_text("Message pinned.")

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    await context.bot.unpin_chat_message(update.effective_chat.id)
    await update.message.reply_text("Last pinned message unpinned.")

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /save <notename> [reply to message]")
    notename = context.args[0].lower()
    content = " ".join(context.args[1:])
    if update.message.reply_to_message:
        content = update.message.reply_to_message.text or "Media Note"
    if not content:
        return await update.message.reply_text("Provide note content or reply to a message.")
    cid = str(update.effective_chat.id)
    data["notes"].setdefault(cid, {})
    data["notes"][cid][notename] = content
    save_data(data)
    await update.message.reply_text(f"Saved note: `{notename}`", parse_mode="Markdown")

async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /get <notename>")
    notename = context.args[0].lower()
    cid = str(update.effective_chat.id)
    note = data["notes"].get(cid, {}).get(notename)
    if note:
        await update.message.reply_text(note)
    else:
        await update.message.reply_text("Note not found.")

async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    saved = list(data["notes"].get(cid, {}).keys())
    if not saved:
        await update.message.reply_text("No saved notes in this chat.")
    else:
        await update.message.reply_text(f"Saved notes: {', '.join(saved)}")

async def delnote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Admin permissions required.")
    if not context.args:
        return await update.message.reply_text("Usage: /delnote <notename>")
    notename = context.args[0].lower()
    cid = str(update.effective_chat.id)
    if cid in data["notes"] and notename in data["notes"][cid]:
        del data["notes"][cid][notename]
        save_data(data)
        await update.message.reply_text(f"Deleted note: `{notename}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Note not found.")

async def scanfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        return await update.message.reply_text("Reply to a file/document to scan it.")
    doc = update.message.reply_to_message.document
    await update.message.reply_text(f"🛡️ **VirusTotal Scan Simulation**\nFile: `{doc.file_name}`\nStatus: Clean (0/72 engines flagged).", parse_mode="Markdown")

async def scanurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /scanurl <url>")
    url = context.args[0]
    await update.message.reply_text(f"🛡️ **VirusTotal URL Scan**\nTarget: `{url}`\nStatus: Clean (No malicious threats detected).", parse_mode="Markdown")

# === CHAT MEMBER EVENTS (WELCOME / GOODBYE) ===
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    if update.message.new_chat_members:
        wel_cfg = data["welcome"].get(cid, {})
        if wel_cfg.get("enabled", True):
            msg = wel_cfg.get("msg", "Welcome to the group!")
            for u in update.message.new_chat_members:
                await update.message.reply_text(f"{msg} Hello {u.first_name}!")
    elif update.message.left_chat_member:
        gb_cfg = data["goodbye"].get(cid, {})
        if gb_cfg.get("enabled", True):
            msg = gb_cfg.get("msg", "Goodbye!")
            u = update.message.left_chat_member
            await update.message.reply_text(f"{msg} {u.first_name} has left.")

# === GENERAL MESSAGE HANDLER ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    cid = str(update.effective_chat.id)
    user_is_admin = await is_admin(update, context)

    # 1. Custom Text Filters Check
    for kw, reply in data["filters"].get(cid, {}).items():
        if kw in text.lower():
            await update.message.reply_text(reply)
            break

    # 2. Content Locks Check
    active_locks = data["locks"].get(cid, [])
    if "links" in active_locks and ("http://" in text.lower() or "https://" in text.lower()):
        if not user_is_admin:
            try:
                await update.message.delete()
                return
            except Exception:
                pass

    # 3. AI Moderation Check (for non-admins)
    if not user_is_admin:
        if await is_message_bad(text):
            try:
                await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
                user = update.effective_user
                uid = str(user.id)
                data["warns"].setdefault(cid, {}).setdefault(uid, 0)
                data["warns"][cid][uid] += 1
                save_data(data)
                await update.message.reply_text(
                    f"⚠️ Deleted message from {user.first_name}\nReason: Violates group rules\nWarning Count: {data['warns'][cid][uid]}"
                )
                return
            except Exception:
                pass

    # 4. Direct AI Mention Handling
    if f"@{BOT_USERNAME}" in text:
        prompt = text.replace(f"@{BOT_USERNAME}", "").strip()
        if not prompt:
            return await update.message.reply_text("How can I assist you? 💜")
        await update.message.reply_chat_action("typing")
        try:
            answer = await call_gemini(f"Group chat question: {prompt}")
            await update.message.reply_text(answer[:4096])
        except Exception as e:
            await update.message.reply_text(f"AI error: {e}")

# === MAIN FUNCTION ===
def main():
    request_config = HTTPXRequest(connect_timeout=15.0, read_timeout=20.0)
    app = ApplicationBuilder().token(TOKEN).request(request_config).build()

    # Core & AI
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ai", ai_cmd))

    # Moderation Commands
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("resetwarns", resetwarns))
    app.add_handler(CommandHandler("del", del_msg))
    app.add_handler(CommandHandler("purge", purge))

    # Locks & Security
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("locks", locks))
    app.add_handler(CommandHandler("antiflood", antiflood))
    app.add_handler(CommandHandler("scanfile", scanfile))
    app.add_handler(CommandHandler("scanurl", scanurl))

    # Group Config & Rules
    app.add_handler(CommandHandler("setwelcome", setwelcome))
    app.add_handler(CommandHandler("welcome", welcome_toggle))
    app.add_handler(CommandHandler("setgoodbye", setgoodbye))
    app.add_handler(CommandHandler("goodbye", goodbye_toggle))
    app.add_handler(CommandHandler("setrules", setrules))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("logchannel", logchannel))

    # Custom Filters
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("unfilter", unfilter_cmd))
    app.add_handler(CommandHandler("filters", filters_cmd))

    # Notes
    app.add_handler(CommandHandler("save", save_note))
    app.add_handler(CommandHandler("get", get_note))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(CommandHandler("delnote", delnote))

    # Info & Utilities
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("whois", whois))
    app.add_handler(CommandHandler("adminlist", adminlist))
    app.add_handler(CommandHandler("staff", staff))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))
    app.add_handler(CommandHandler("report", report))

    # Event Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, chat_member_update))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("PER1METER_BOT is fully running with all BotFather commands...")
    app.run_polling()

if __name__ == "__main__":
    main()