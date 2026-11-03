from telethon import TelegramClient, events, functions, types, utils
from telethon.tl.custom import Button
from telethon.errors import FloodWaitError, MessageNotModifiedError, UserIsBlockedError, InputUserDeactivatedError, UserDeactivatedError

import configparser # read
import datetime
import pytz
import os

import handlers.db as db
from functions import print_day, print_sapt, print_next_course, button_grid, build_bot_kb, schedule_reply_buttons, send_logs, get_next_course_time, is_rate_limited, format_id, get_version, write_groups_to_json, get_local_schedule_versions, reminder_eligible
import version_watch
write_groups_to_json()
from functions import cur_group, is_even, current_pair_index
from functions import emoji_preview, format_hours
from dynamic_group_lists import years, group_list, specialties

import handlers.admin_handlers as admin_handlers
import handlers.group_handlers as group_handlers

from localization import load_locales, get_text, get_user_lang, get_week_days, SUPPORTED_LANGS, DEFAULT_LANG
load_locales()

TRACKED_COMMANDS = {
    "/start", "/language", "/help", "/version", "/contacts", "/notifon",
    "/notifoff", "/hours", "/tomorrow", "/today", "/curr_week", "/next_week",
    "/donations", "/choose_gr", "/choose_subgr", "/cancel_message", "/admin_help",
    "/stats", "/message", "/debug_next", "/backup", "/logs",
    "/use_backup", "/cancel_restore", "/auto_migrate", "/admin", "/unadmin",
    "/list_admin", "/ban", "/unban", "/list_ban", "/update_schedule", "/contrib",
    "/holidays", "/edit_contrib", "/emoji",
}
TRACKED_BUTTONS = {
    get_text(lang, key)
    for lang in SUPPORTED_LANGS
    for key in ("btn_today", "btn_tomorrow", "btn_current_week", "btn_next_week", "btn_choose_group")
}
TRACKED_BUTTONS.add("Orele ⏰")

import pandas as pd
import asyncio
from contextvars import ContextVar
from collections import defaultdict
from contextlib import nullcontext
from bulk_delivery import SendGate, centered_start, estimated_batch_seconds, format_local_time, run_bulk, validate_settings

delivery_locks = defaultdict(asyncio.Lock)
send_rpc = ContextVar('send_rpc', default=False)
send_tasks = set()
send_gate = SendGate()
validate_settings(send_logs)
# shortcut: event ordering is process-local; add persisted observation time if stricter ordering is needed.
delivery_events = {}
delivered_pending = set()


def record_delivery(sender, status):
    try:
        db.set_delivery_status(format_id(sender), status)
    except Exception as error:
        send_logs(f"Delivery status write failed for {sender}: {type(error).__name__}", "error")


def flush_delivered_once():
    if not delivered_pending:
        return
    batch = list(delivered_pending)
    delivered_pending.clear()
    try:
        db.mark_delivered(batch)
    except Exception as error:
        send_logs(f"Delivery status batch failed: {type(error).__name__}", "error")


async def flush_delivered():
    while True:
        await asyncio.sleep(1)
        flush_delivered_once()


async def delivery_event(sender, at, stopped=False):
    async with delivery_locks[sender]:
        if sender in delivery_events and at < delivery_events[sender]:
            return
        try:
            if stopped and db.has_interaction_since(format_id(sender), at):
                return
            db.set_delivery_status(format_id(sender), 'blocked' if stopped else 'unknown', only_blocked=not stopped)
            delivery_events[sender] = at
        except Exception as error:
            send_logs(f"Delivery event write failed for {sender}: {type(error).__name__}", "error")


async def track_send(entity, operation, guard=None, bulk=False):
    task = asyncio.current_task()
    if task in send_tasks:
        return await operation()
    if isinstance(entity, int):
        sender = entity
    else:
        try:
            sender = utils.get_peer_id(entity)
        except (TypeError, ValueError):
            sender = None
    tracked = sender is not None and sender > 0
    lock = delivery_locks[sender] if tracked else asyncio.Lock()
    async with (send_gate.bulk_slots if bulk else nullcontext()):
        front = False
        while True:
            async with lock:
                ticket = send_gate.register(bulk, front=front)
                front = False
                try:
                    admitted, delay, event = send_gate.try_start(ticket, bulk, guard)
                except BaseException:
                    send_gate.remove(ticket, bulk)
                    raise
                if admitted is None:
                    send_gate.remove(ticket, bulk)
                    return None
                if admitted:
                    send_tasks.add(task)
                    at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                    try:
                        result = await operation()
                    except FloodWaitError as error:
                        if not isinstance(error.request, SEND_REQUESTS):
                            raise
                        send_gate.pause(error.seconds)
                    except (UserIsBlockedError, InputUserDeactivatedError, UserDeactivatedError) as error:
                        if tracked:
                            record_delivery(sender, 'blocked' if isinstance(error, UserIsBlockedError) else 'deleted')
                            delivery_events[sender] = at
                        raise
                    else:
                        if tracked:
                            delivered_pending.add(format_id(sender))
                            delivery_events[sender] = at
                        return result
                    finally:
                        send_tasks.remove(task)
            if not admitted:
                try:
                    while True:
                        await send_gate.wait(event, delay)
                        ready, delay, event = send_gate.ready(ticket, bulk)
                        if ready:
                            break
                finally:
                    send_gate.remove(ticket, bulk)
                # Rejoin at the front only after reacquiring the recipient lock.
                front = True


SEND_REQUESTS = (functions.messages.SendMessageRequest, functions.messages.SendMediaRequest,
                 functions.messages.SendMultiMediaRequest)


class DeliveryClient(TelegramClient):
    # Telethon 1.45 reads this inside _call; task-local scope preserves other RPCs.
    @TelegramClient.flood_sleep_threshold.getter
    def flood_sleep_threshold(self):
        return 0 if send_rpc.get() else self._flood_sleep_threshold

    async def _call(self, sender, request, ordered=False, flood_sleep_threshold=None):
        token = send_rpc.set(isinstance(request, SEND_REQUESTS))
        try:
            return await super()._call(sender, request, ordered=ordered, flood_sleep_threshold=flood_sleep_threshold)
        finally:
            send_rpc.reset(token)

    # event.reply/respond and send_message(file=...) use these methods too.
    async def send_message(self, entity, *args, delivery_guard=None, delivery_prepare=None, bulk=False, **kwargs):
        send = super().send_message
        args = list(args)

        def prepare():
            if delivery_guard is not None and not delivery_guard():
                return False
            if delivery_prepare is not None:
                text = delivery_prepare()
                if text is None:
                    return False
                args[0] = text
            return True

        return await track_send(entity, lambda: send(entity, *args, **kwargs),
                                prepare if delivery_guard or delivery_prepare else None, bulk)

    async def send_file(self, entity, *args, delivery_guard=None, bulk=False, **kwargs):
        send = super().send_file
        return await track_send(entity, lambda: send(entity, *args, **kwargs), delivery_guard, bulk)

#### Access credentials
config = configparser.ConfigParser()
config_path = os.environ.get("ORAR_CONFIG", "configs/config.ini")
if not config.read(config_path):
    raise RuntimeError(f"Configuration file unavailable: {config_path}")

api_id = config.get('default','api_id') # get the api id
api_hash = config.get('default','api_hash') # get the api hash
BOT_TOKEN = config.get('default','BOT_TOKEN') # get the bot token

# Keep the local test bot session separate from the production session.
client = DeliveryClient(os.environ.get('ORAR_SESSION', 'sessions/session_master'), api_id, api_hash)

# Register returns before command handlers so a successful reply is not cleared afterward.
@client.on(events.NewMessage(incoming=True))
async def delivery_message(event):
    if event.is_private and event.sender_id:
        await delivery_event(event.sender_id, event.date)


@client.on(events.CallbackQuery())
async def delivery_callback(event):
    if event.is_private:
        await delivery_event(event.sender_id, datetime.datetime.now(datetime.timezone.utc))


@client.on(events.Raw(types.UpdateBotStopped))
async def delivery_stopped(update):
    await delivery_event(update.user_id, update.date, update.stopped)

def build_start_kb(lang):
    return [
        Button.text(get_text(lang, 'btn_choose_group'), resize=True),
    ]

if not db.initialize_mysql_connection():
    send_logs("Failed to establish MySQL connection", 'critical')
    exit(1)
db.load_current_year()

moldova_tz = pytz.timezone('Europe/Chisinau')
week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)

#1 rank is higher
admins1 = db.get_admins(1)
admins2 = db.get_admins(2)

latest_version, latest_date = get_version()

admin_handlers.register_admin_handlers(client, admins1, admins2, specialties, group_list)
group_handlers.register_group_handlers(client, years, specialties, group_list)

# Helper to get user lang
def _get_lang(SENDER):
    return get_user_lang(format_id(SENDER))

# Helper to get user id and lang
async def _get_sender_id_and_lang(event):
    sender = await event.get_sender()
    SENDER = sender.id
    lang = _get_lang(SENDER)
    return SENDER, lang

#/language
@client.on(events.NewMessage(pattern='/language'))
async def languagee(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    
    text = "🌐 Choose language / Alege limba / Выберите язык:"
    lang_buttons = [
        Button.inline(label, data=f"lang_{code}".encode())
        for code, label in SUPPORTED_LANGS.items()
    ]
    button_rows = button_grid(lang_buttons, 3)
    await client.send_message(SENDER, text, buttons=button_rows)
    send_logs(format_id(SENDER) + " - /language", 'info')

#language selection callback
@client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"lang_")))
async def lang_callback(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    chosen_lang = event.data.decode().replace("lang_", "")
    if chosen_lang not in SUPPORTED_LANGS:
        return
    db.update_user_field(format_id(SENDER), 'lang', chosen_lang)

    text = get_text(chosen_lang, "lang_changed")
    await event.answer(text)
    button_rows = button_grid(build_bot_kb(chosen_lang), 2)
    #await client.edit_message(SENDER, event.message_id, text)
    await client.send_message(SENDER, text, buttons=button_rows)
    send_logs(format_id(SENDER) + f" - lang set to {chosen_lang}", 'info')

@client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"start_lang_")))
async def start_lang_callback(event):
    sender = await event.get_sender()
    chosen_lang = event.data.decode().replace("start_lang_", "")
    if chosen_lang not in SUPPORTED_LANGS:
        return

    db.update_user_field(format_id(sender.id), 'lang', chosen_lang)
    await event.answer()
    await client.send_message(
        sender.id,
        get_text(chosen_lang, "start_message", first_name=sender.first_name),
        parse_mode="Markdown",
        buttons=button_grid(build_start_kb(chosen_lang), 2),
        link_preview=False,
    )

#/start
@client.on(events.NewMessage(pattern="/start")) 
async def startt(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return

    #add the user to users
    if not db.is_user_exists(format_id(SENDER)):
        result = db.add_new_user(format_id(SENDER))
        if result:
            send_logs("New user! - " + format_id(SENDER), 'info')

    text = "🌐 Choose language / Alege limba / Выберите язык:"
    lang_buttons = [
        Button.inline(label, data=f"start_lang_{code}".encode())
        for code, label in SUPPORTED_LANGS.items()
    ]
    button_rows = button_grid(lang_buttons, 3)
    await client.send_message(SENDER, text, buttons=button_rows)

def emoji_button(sender, lang, enabled):
    return [[Button.inline(get_text(lang, "emoji_on" if enabled else "emoji_off"),
                           data=f"emoji:{sender}:{int(not enabled)}".encode())]]


@client.on(events.NewMessage(pattern=r'^/emoji(?:@\w+)?$'))
async def emoji_command(event):
    if not event.is_private:
        return
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        return
    if not db.is_user_exists(format_id(SENDER)):
        await event.respond(get_text(lang, "emoji_start"))
        return
    try:
        enabled = db.get_user_emoji(format_id(SENDER), strict=True)
        send_logs(format_id(SENDER) + " - /emoji", 'info')
        await event.respond(emoji_preview(lang, enabled), parse_mode="HTML",
                            buttons=emoji_button(SENDER, lang, enabled))
    except Exception as error:
        send_logs(f"Error reading emoji preference: {error}", "error")
        await event.respond(get_text(lang, "emoji_error"))


@client.on(events.CallbackQuery(pattern=rb'^emoji:\d+:[01]$'))
async def emoji_callback(event):
    _, owner, target = event.data.decode().split(":")
    if int(owner) != event.sender_id or not event.is_private:
        await event.answer()
        return
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        await event.answer()
        return
    if not db.is_user_exists(format_id(SENDER)):
        await event.answer(get_text(lang, "emoji_start"), alert=True)
        return
    try:
        enabled = target == "1"
        db.set_user_emoji(format_id(SENDER), enabled)
        send_logs(format_id(SENDER) + f" - emoji set to {'on' if enabled else 'off'}", 'info')
        try:
            await event.edit(emoji_preview(lang, enabled), parse_mode="HTML",
                             buttons=emoji_button(SENDER, lang, enabled))
        except MessageNotModifiedError:
            pass
        await event.answer(get_text(lang, "emoji_on" if enabled else "emoji_off"))
    except Exception as error:
        send_logs(f"Error updating emoji preference: {error}", "error")
        await event.answer(get_text(lang, "emoji_error"), alert=True)


#notif button handle
@client.on(events.CallbackQuery(pattern = lambda x: x in [b"noti_on", b"noti_off"]))
async def notiff(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    text = ""
    if event.data == b"noti_off":
        text = get_text(lang, "notif_off")
        db.update_user_field(format_id(SENDER), 'noti', 0)
        await event.answer(get_text(lang, "notif_off"))
        await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - Notif off", 'info')
    elif event.data==b"noti_on":
        text = get_text(lang, "notif_on")
        db.update_user_field(format_id(SENDER), 'noti', 1)
        await event.answer(get_text(lang, "notif_on"))
        await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - Notif on", 'info')

#/help
@client.on(events.NewMessage(pattern='/help')) 
async def helpp(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = get_text(lang, "help_contacts") + "\n"
    text += get_text(lang, "help_today") + "\n"
    text += get_text(lang, "help_tomorrow") + "\n"
    text += get_text(lang, "help_hours") + "\n"
    text += get_text(lang, "help_choose_group") + "\n"
    text += get_text(lang, "help_choose_subgroup") + "\n"
    text += get_text(lang, "help_current_week") + "\n"
    text += get_text(lang, "help_next_week") + "\n"
    text += get_text(lang, "help_notif_on") + "\n"
    text += get_text(lang, "help_notif_off") + "\n"
    text += get_text(lang, "help_donations") + "\n"
    text += get_text(lang, "help_version") + "\n"
    text += get_text(lang, "help_language") + "\n"
    text += get_text(lang, "help_emoji") + "\n"
    text += get_text(lang, "help_admin") + "\n"
    button_rows = button_grid(build_bot_kb(lang), 2)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
    send_logs(format_id(SENDER) + " - /help", 'info')

#/version
@client.on(events.NewMessage(pattern='/version'))
async def versionn(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = version_watch.version_text(get_local_schedule_versions(), lang=lang)
    text += get_text(lang, "version_bot_info")
    text += get_text(lang, "version_label", version=latest_version)
    text += get_text(lang, "version_date", date=latest_date)
    text += get_text(lang, "version_github")
    await client.send_message(SENDER, text, parse_mode="Markdown", link_preview=False,
                              buttons=version_watch.pdf_buttons(lang))
    send_logs(format_id(SENDER) + " - /version", 'info')

#/contacts
@client.on(events.NewMessage(pattern='/contacts')) 
async def contactt(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = get_text(lang, "contacts_text")
    await client.send_message(SENDER, text, parse_mode="Markdown")
    send_logs(f"{format_id(SENDER)} - /contacts", 'info')

#/notifon
@client.on(events.NewMessage(pattern='/notifon'))
async def notifonn(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = get_text(lang, "notif_on")
    await client.send_message(SENDER, text, parse_mode="Markdown")
    db.update_user_field(format_id(SENDER), 'noti', 1)
    send_logs(format_id(SENDER) + " - /notifon", 'info')

#/notifoff
@client.on(events.NewMessage(pattern='/notifoff'))
async def notifofff(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = get_text(lang, "notif_off")
    await client.send_message(SENDER, text, parse_mode="Markdown")
    db.update_user_field(format_id(SENDER), 'noti', 0)
    send_logs(format_id(SENDER) + " - /notifoff", 'info')

#/hours
@client.on(events.NewMessage(pattern='/hours|Orele ⏰')) 
async def oree(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = format_hours(lang, emoji=db.get_user_emoji(format_id(SENDER)))
    await client.send_message(SENDER, text, parse_mode="HTML")
    send_logs(format_id(SENDER) + " - /hours", 'info')

#/tomorrow
@client.on(events.NewMessage(pattern='/tomorrow|Orarul de maine 📅|Tomorrow\'s schedule 📅|Расписание на завтра 📅')) 
async def mainee(event):
    global cur_group
    week_day = int((datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)).weekday()) #weekday tomorrow(0-6)
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    lang_week_days = get_week_days(lang)
    subgrupa = db.locate_field(format_id(SENDER), 'subgrupa')
    try:
        #get the user's selected group
        csv_gr = db.locate_field(format_id(SENDER), 'group_n')
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            temp_is_even = (datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)).isocalendar().week % 2
            #send the schedule
            day_sch = print_day(week_day, cur_group, temp_is_even, subgrupa, lang,
                                study_year=db.locate_field(format_id(SENDER), 'year_s'), emoji=db.get_user_emoji(format_id(SENDER)))
            if day_sch != "":
                text = "\n\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_tomorrow", day=lang_week_days[week_day]) + day_sch
            else: 
                text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_no_pairs_tomorrow", day=lang_week_days[week_day])
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))
            send_logs(format_id(SENDER) + " - /tomorrow", 'info')
    except Exception as e:
        send_logs(f"Error sending sch tomorr to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))
    
#/today
@client.on(events.NewMessage(pattern='/today|Orarul de azi 📅|Today\'s schedule 📅|Расписание на сегодня 📅')) 
async def azii(event):
    global cur_group
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    lang_week_days = get_week_days(lang)
    subgrupa = db.locate_field(format_id(SENDER), 'subgrupa')
    try:
        csv_gr = db.locate_field(format_id(SENDER), 'group_n')
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(SENDER) + 'no gr')
        else: 
            week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            day_sch = print_day(week_day, cur_group, is_even, subgrupa, lang, current_pair_index(),
                                study_year=db.locate_field(format_id(SENDER), 'year_s'), emoji=db.get_user_emoji(format_id(SENDER)))
            if day_sch != "":
                text = "\n\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_today", day=lang_week_days[week_day]) + day_sch
            else: 
                text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_no_pairs_today", day=lang_week_days[week_day])
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))
            send_logs(format_id(SENDER) + " - /today", 'info')
    except Exception as e:
        send_logs(f"Error sending sch today to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))

#/curr_week
@client.on(events.NewMessage(pattern='/curr_week|Săptămâna curentă 🗓️|Current week 🗓️|Текущая неделя 🗓️')) 
async def sapt_curr(event):
    global cur_group, is_even
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    subgrupa = db.locate_field(format_id(SENDER), 'subgrupa')
    try:
        csv_gr = db.locate_field(format_id(SENDER), 'group_n')
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(SENDER) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_current_week") + print_sapt(is_even, cur_group, subgrupa, lang, study_year=db.locate_field(format_id(SENDER), 'year_s'), emoji=db.get_user_emoji(format_id(SENDER)))
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))
            send_logs(format_id(SENDER) + " - /curr_week", 'info')
    except Exception as e:
        send_logs(f"Error sending curr week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))

#/next_week
@client.on(events.NewMessage(pattern='/next_week|Săptămâna viitoare 🗓️|Next week 🗓️|Следующая неделя 🗓️')) 
async def sapt_viit(event):
    global cur_group, is_even
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    subgrupa = db.locate_field(format_id(SENDER), 'subgrupa')
    try:
        csv_gr = db.locate_field(format_id(SENDER), 'group_n')
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(SENDER) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            is_even = not is_even
            text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_next_week") + print_sapt(is_even, cur_group, subgrupa, lang, study_year=db.locate_field(format_id(SENDER), 'year_s'), emoji=db.get_user_emoji(format_id(SENDER)))
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))
            send_logs(format_id(SENDER) + " - /next_week", 'info')
    except Exception as e:
        send_logs(f"Error sending next week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML", buttons=schedule_reply_buttons(event.raw_text, lang))

#/donations
@client.on(events.NewMessage(pattern='/donations')) 
async def donatiii(event):
    SENDER, lang = await _get_sender_id_and_lang(event)
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
    text = get_text(lang, "donation_title")
    text += get_text(lang, "donation_name")
    text += get_text(lang, "donation_mia")
    text += get_text(lang, "donation_micb")
    text += get_text(lang, "donation_maib")

    await client.send_message(SENDER, text, parse_mode="Markdown")

    buttons = [
        [Button.url("☕️ Buy me a coffee", "https://www.buymeacoffee.com/orar_utm")]
    ]
    await client.send_message(SENDER, get_text(lang, "donation_online"), buttons=buttons)

    send_logs(format_id(SENDER) + " - /donations", 'info')


@client.on(events.NewMessage(incoming=True))
async def track_message_activity(event):
    if not event.is_private:
        return
    text = (event.raw_text or "").strip()
    command = text.split(maxsplit=1)[0].split("@", 1)[0] if text else ""
    if command in TRACKED_COMMANDS or text in TRACKED_BUTTONS:
        db.touch_user_safely(format_id(event.sender_id))


@client.on(events.CallbackQuery())
async def track_callback_activity(event):
    db.touch_user_safely(format_id(event.sender_id))

def prepare_next_courses(week_day, is_even, course_index, all_users):
    next_courses = {}
    # Get all users with a group set and who are not banned
    #only group != 'none' / ban != 1 / noti == 1
    try:
        if all_users.empty:
            return next_courses
        filtered_users = all_users[all_users.apply(
            lambda row: reminder_eligible(row.to_dict()), axis=1).astype(bool)]
        error_count = 0
        for index, row in filtered_users.iterrows():
            try:
                # Extract sender ID from the SENDER field
                sender_id = row['SENDER']
                if sender_id.startswith('U'):
                    sender = int(sender_id[1:])
                else:
                    sender = int(sender_id)
                
                # Get group, subgroup and language
                csv_gr = row['group_n']
                subgrupa = row['subgrupa']
                user_lang = row.get('lang', DEFAULT_LANG)
                if not user_lang or user_lang not in SUPPORTED_LANGS:
                    user_lang = DEFAULT_LANG
                
                if pd.isna(csv_gr) or csv_gr == '' or csv_gr == 'none':
                    continue
                
                next_course = print_next_course(week_day, csv_gr, is_even, course_index, subgrupa, user_lang,
                                                study_year=row.get('year_s'))
                if next_course:
                    next_courses[sender] = (week_day, csv_gr, is_even, course_index, subgrupa, user_lang, row.get('year_s'))
            except Exception as e:
                send_logs(f"Error preparing next course to {row['SENDER']}: {e}", 'error')
                error_count += 1
        if error_count > 0:
            send_logs(f"Total errors preparing next courses: {error_count}", 'error')
        send_logs(f"Prepared next course to {len(next_courses)} users", "info")
    except Exception as e:
        send_logs(f"Error preparing next courses: {e}", 'error')
        return {}
    
    return next_courses

async def send_notification(sender, next_course_data):
    try:
        week_day, group, parity, index, subgroup, _, year = next_course_data
        selected = {'group_n': group, 'year_s': year, 'subgrupa': subgroup}

        def prepare():
            user = db.get_user_for_delivery(format_id(sender))
            if not reminder_eligible(user, selection=selected):
                return None
            user_lang = user.get('lang') if user.get('lang') in SUPPORTED_LANGS else DEFAULT_LANG
            course = print_next_course(week_day, group, parity, index, subgroup, user_lang,
                                       study_year=year, emoji=bool(user['emoji']))
            return get_text(user_lang, "next_pair", course=course) if course else None

        sent = await client.send_message(sender, "", parse_mode="HTML", bulk=True, delivery_prepare=prepare)
        return sent is not None
    except Exception as e:
        send_logs(f"Error sending next course to {sender}: {e}", 'error')
        return None

#send current course to users with notifications on
async def send_curr_course_users():
    cursor = None
    batches = set()

    async def deliver(items, estimated):
        try:
            await run_bulk(items, lambda item: send_notification(*item), 'Next-class', send_logs,
                           success_kind='Current-class', estimate=estimated)
        except Exception as error:
            send_logs(f"Next-class batch failed: {error}", 'error')

    try:
        while True:
            now = datetime.datetime.now(moldova_tz)
            course_index, target = get_next_course_time(now, cursor)
            cursor = target
            all_users = db.get_all_users()
            next_courses = prepare_next_courses(target.weekday(), target.isocalendar().week % 2,
                                               course_index, all_users)
            estimated = estimated_batch_seconds(len(next_courses))
            start = centered_start(target, len(next_courses))
            now = datetime.datetime.now(moldova_tz)
            if start < now:
                send_logs(f"Next-class skipped: calculated start already passed | target {format_local_time(target)} | start {format_local_time(start)}", 'info')
                continue
            if not next_courses:
                send_logs(f"No users have the next course for {format_local_time(target)}", 'info')
            else:
                send_logs(f"Next-class planned | {len(next_courses)} recipients | target {format_local_time(target)} | start {format_local_time(start)} | est {estimated:.2f}s", 'info')
            await asyncio.sleep((start - now).total_seconds())
            if not next_courses:
                continue
            if db.get_app_setting("holiday_mode", "0") == "1":
                send_logs("Holiday mode active - skipping next course notifications", 'info')
                continue
            task = asyncio.create_task(deliver(list(next_courses.items()), estimated))
            batches.add(task)
            task.add_done_callback(batches.discard)
    finally:
        for task in batches:
            task.cancel()
        await asyncio.gather(*batches, return_exceptions=True)


async def send_tomorrow_recipient(sender, schedule_date):
    try:
        def prepare():
            user = db.get_user_for_delivery(format_id(sender))
            if not reminder_eligible(user):
                return None
            group, subgroup = user['group_n'], user['subgrupa']
            lang = user.get('lang') if user.get('lang') in SUPPORTED_LANGS else DEFAULT_LANG
            if pd.isna(group) or not group or group == 'none':
                return None
            weekday = schedule_date.weekday()
            schedule = print_day(weekday, group, schedule_date.isocalendar().week % 2, subgroup, lang,
                                 study_year=user.get('year_s'), emoji=bool(user['emoji']))
            return (get_text(lang, 'notif_tomorrow_schedule', day=get_week_days(lang)[weekday], schedule=schedule)
                    if schedule else None)

        sent = await client.send_message(sender, "", parse_mode='HTML', bulk=True, delivery_prepare=prepare)
        return sent is not None
    except Exception as error:
        send_logs(f"Error sending tomorrow's schedule to {sender}: {error}", 'error')
        return None

#send schedule for tomorrow to users with notifications on
async def send_schedule_tomorrow():
    next_date = None
    while True:
        try:
            now = datetime.datetime.now(moldova_tz)
            date = max(now.date(), next_date or now.date())
            target = moldova_tz.localize(datetime.datetime.combine(date, datetime.time(20)))
            if target < now:
                date += datetime.timedelta(days=1)
                target = moldova_tz.localize(datetime.datetime.combine(date, datetime.time(20)))
            recipients = [user['SENDER'] for user in db.get_all_users().to_dict('records')
                          if reminder_eligible(user)]
            estimated = estimated_batch_seconds(len(recipients))
            start = centered_start(target, len(recipients))
            now = datetime.datetime.now(moldova_tz)
            next_date = date + datetime.timedelta(days=1)
            if start < now:
                send_logs(f"Tomorrow-schedule skipped: calculated start already passed | target {format_local_time(target)} | start {format_local_time(start)}", 'info')
                continue
            send_logs(f"Tomorrow-schedule planned | {len(recipients)} recipients | target {format_local_time(target)} | start {format_local_time(start)} | est {estimated:.2f}s", 'info')
            await asyncio.sleep((start - now).total_seconds())
            if db.get_app_setting("holiday_mode", "0") == "1":
                send_logs("holiday_mode active - skipping tomorrow-schedule broadcast", "info")
                continue

            async def send_recipient(user_id):
                try:
                    sender = int(user_id[1:])
                except (ValueError, TypeError):
                    return None
                return await send_tomorrow_recipient(sender, date + datetime.timedelta(days=1))

            await run_bulk(recipients, send_recipient, 'Tomorrow-schedule', send_logs, estimate=estimated)
        except Exception as e:
            send_logs(f"Error in send_schedule_tomorrow: {e}", 'error')
            await asyncio.sleep(60)  # Wait 1 min

#backup BD automation
async def backup_database():
    while True:
        try:
            now = datetime.datetime.now(moldova_tz)
            date = now.date()
            target = moldova_tz.localize(datetime.datetime.combine(date, datetime.time(20)))
            if target <= now:
                date += datetime.timedelta(days=1)
                target = moldova_tz.localize(datetime.datetime.combine(date, datetime.time(20)))
            wait_seconds = (target - now).total_seconds()
            send_logs(f"Scheduled database backup in {wait_seconds/60/60:.2f} hours", 'info')
            await asyncio.sleep(wait_seconds)

            recipient = db.get_app_setting('fcim_owner_id', None, strict=True)
            if not recipient or not recipient.isdecimal() or int(recipient) <= 0:
                raise ValueError("Configure explicit fcim_owner_id for database backup and FCIM alerts")
            now = datetime.datetime.now(moldova_tz)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            os.makedirs("/backups", exist_ok=True)
            backup_filename = f"/backups/BD_backup_{timestamp}.sql"
            if not db.create_mysql_backup(backup_filename):
                raise RuntimeError("Database backup failed; no file sent")
            db_len = db.get_user_count()
            await client.send_file(
                int(recipient), backup_filename,
                caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {db_len} users"
            )
            send_logs("Database backup sent to admin", 'info')
        except Exception as e:
            send_logs(f"Error in database backup: {str(e)}", 'error')
            await asyncio.sleep(60)

### MAIN
if __name__ == '__main__':
    send_logs("############################################", 'info')
    send_logs("Bot Started!", 'info')
    
    async def main():
        await client.start(bot_token=BOT_TOKEN)
        loop = client.loop

        loop.create_task(send_curr_course_users())
        loop.create_task(send_schedule_tomorrow())
        loop.create_task(backup_database())
        loop.create_task(flush_delivered())
        loop.create_task(version_watch.run(client))
        await client.run_until_disconnected()
    
    asyncio.run(main())
