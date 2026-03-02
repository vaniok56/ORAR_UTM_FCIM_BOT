from telethon import TelegramClient, events, functions, types
from telethon.tl.custom import Button

import configparser # read
import datetime
import pytz
import os

import handlers.db as db
from functions import print_day, print_sapt, print_next_course, button_grid, send_logs, get_next_course_time, is_rate_limited, format_id, get_version, write_groups_to_json, get_online_schedule_versions, get_local_schedule_versions
write_groups_to_json()
from functions import cur_group, hours, week_days, is_even
from dynamic_group_lists import years, group_list, specialties

import handlers.admin_handlers as admin_handlers
import handlers.group_handlers as group_handlers

from localization import load_locales, get_text, get_user_lang, get_week_days, SUPPORTED_LANGS, DEFAULT_LANG
load_locales()

import pandas as pd
import numpy as np
import asyncio

#### Access credentials
config = configparser.ConfigParser()
config.read('configs/config2.ini') # read config.ini file

api_id = config.get('default','api_id') # get the api id
api_hash = config.get('default','api_hash') # get the api hash
BOT_TOKEN = config.get('default','BOT_TOKEN') # get the bot token

# Create the client and the session called session_master.
client = TelegramClient('sessions/session_master', api_id, api_hash)

#keyboard button factories (per-language)
def build_bot_kb(lang):
    return [
        Button.text(get_text(lang, 'btn_today'), resize=True),
        Button.text(get_text(lang, 'btn_tomorrow'), resize=True),
        Button.text(get_text(lang, 'btn_current_week'), resize=True),
        Button.text(get_text(lang, 'btn_next_week'), resize=True),
        types.KeyboardButtonSimpleWebView("SIMU📚", "https://simu.utm.md/students/"),
    ]

def build_start_kb(lang):
    return [
        Button.text(get_text(lang, 'btn_choose_group'), resize=True),
    ]

if not db.initialize_mysql_connection():
    send_logs("Failed to establish MySQL connection", 'critical')
    exit(1)

moldova_tz = pytz.timezone('Europe/Chisinau')
week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)

#1 rank is higher
admins1 = db.get_admins(1)
admins2 = db.get_admins(2)

noti_send = 0

latest_version, latest_date = get_version()

admin_handlers.register_admin_handlers(client, admins1, admins2)
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

#/start
@client.on(events.NewMessage(pattern="/start")) 
async def startt(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    first_name = sender.first_name

    #add the user to users
    if not db.is_user_exists(format_id(SENDER)):
        result = db.add_new_user(format_id(SENDER))
        if result:
            send_logs("New user! - " + format_id(SENDER), 'info')

    text = "🌐 Choose language / Alege limba / Выберите язык:"
    lang_buttons = [
        Button.inline(label, data=f"lang_{code}".encode())
        for code, label in SUPPORTED_LANGS.items()
    ]
    button_rows = button_grid(lang_buttons, 3)
    await client.send_message(SENDER, text, buttons=button_rows)

    @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"lang_")))
    async def start_lang_callback(event):
        lang = event.data.decode().replace("lang_", "")
        text = get_text(lang, "start_message", first_name=first_name)
        
        buttons_in_row = 2
        button_rows = button_grid(build_start_kb(lang), buttons_in_row)

        await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows, link_preview=False)

        # Kill this handler so no repeated start messages
        event.client.remove_event_handler(start_lang_callback)
        return

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
    local_schedule_versions = get_local_schedule_versions()
    online_schedule_versions = get_online_schedule_versions()
    text = get_text(lang, "version_schedule_info")
    for year in local_schedule_versions.keys():
        local_ver = local_schedule_versions.get(year, 0)
        online_ver = online_schedule_versions.get(year, 0)

        # Prepare display for online version (handle 'final')
        online_display = f"v{online_ver}" if isinstance(online_ver, int) else (str(online_ver) if online_ver else "v0")
        local_display = f"v{local_ver}" if isinstance(local_ver, int) else (str(local_ver) if local_ver else "v0")

        # Determine match: only mark as equal if both are integers and equal and non-zero,
        # or if online is 'final' and local equals that final marker (not applicable numerically).
        match = False
        if local_ver != 0 and local_ver == online_ver:
            match = True

        text += get_text(lang, "version_year", year=year, local=local_display, online=online_display) + (" ✅" if match else " ❌") + "\n"
    text += get_text(lang, "version_bot_info")
    text += get_text(lang, "version_label", version=latest_version)
    text += get_text(lang, "version_date", date=latest_date)
    text += get_text(lang, "version_github")
    await client.send_message(SENDER, text, parse_mode="Markdown", link_preview=False)
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
    text = get_text(lang, "hours_title")
    for i in range(len(hours)):
        text += "\n" + get_text(lang, "pair_label", index=i+1) + "\n" + get_text(lang, "hour_label", time=''.join(hours[i])) + "\n"
        if i == 2 :
            text += get_text(lang, "break_label", duration=get_text(lang, "break_30")) + "\n"
        else:
            text += get_text(lang, "break_label", duration=get_text(lang, "break_15")) + "\n"
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
            day_sch = print_day(week_day, cur_group, temp_is_even, subgrupa, lang)
            if day_sch != "":
                text = "\n\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_tomorrow", day=lang_week_days[week_day]) + day_sch
            else: 
                text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_no_pairs_tomorrow", day=lang_week_days[week_day])
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /tomorrow", 'info')
    except Exception as e:
        send_logs(f"Error sending sch tomorr to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML")
    
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
            day_sch = print_day(week_day, cur_group, is_even, subgrupa, lang)
            if day_sch != "":
                text = "\n\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_today", day=lang_week_days[week_day]) + day_sch
            else: 
                text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_no_pairs_today", day=lang_week_days[week_day])
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /today", 'info')
    except Exception as e:
        send_logs(f"Error sending sch today to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML")

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
            text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_current_week") + print_sapt(is_even, cur_group, subgrupa, lang)
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /curr_week", 'info')
    except Exception as e:
        send_logs(f"Error sending curr week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML")

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
            text = "\n" + get_text(lang, "schedule_group", group=cur_group) + "\n" + get_text(lang, "schedule_next_week") + print_sapt(is_even, cur_group, subgrupa, lang)
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /next_week", 'info')
    except Exception as e:
        send_logs(f"Error sending next week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, get_text(lang, "error_no_group"), parse_mode="HTML")

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

def prepare_next_courses(week_day, is_even, course_index):
    next_courses = {}
    # Get all users with a group set and who are not banned
    #only group != 'none' / ban != 1 / noti == 1
    try:
        all_users = db.get_all_users()
        filtered_users = all_users[
                (all_users['group_n'].astype(str) != 'none') & 
                (all_users['ban'] != 1) &
                (all_users['noti'] == 1)
            ]
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
                
                next_course = print_next_course(week_day, csv_gr, is_even, course_index, subgrupa, user_lang)
                if next_course:
                    next_courses[sender] = (next_course, user_lang)
            except Exception as e:
                #send_logs(f"Error preparing next course to {sender}: {e}", 'error')
                error_count += 1
        if error_count > 0:
            send_logs(f"Total errors preparing next courses: {error_count}", 'error')
        send_logs(f"Prepared next course to {len(next_courses)} users", "info")
    except Exception as e:
        send_logs(f"Error preparing next courses: {e}", 'error')
        return {}
    
    return next_courses

async def send_notification(sender, next_course_data, wait_time):
    global noti_send
    await asyncio.sleep(wait_time)
    
    #re-check if notifications are still enabled for this user
    if db.locate_field(format_id(sender), 'noti') != 1:
        return
    
    try:
        next_course, user_lang = next_course_data
        text = get_text(user_lang, "next_pair", course=next_course)
        await client.send_message(sender, text, parse_mode="HTML")
        #send_logs(f"Sent next course to {sender}", 'info')
        noti_send += 1
        return True
    except Exception as e:
        send_logs(f"Error sending next course to {sender}: {e}", 'error')
        return False

#send current course to users with notifications on
async def send_curr_course_users(week_day, is_even):
    global noti_send
    while True:
        noti_send = 0
        
        #get next course time, index and time before course
        current_time, course_index, time_before_course = get_next_course_time()

        #prepare next courses for all users
        next_courses = prepare_next_courses(week_day, is_even, course_index)

        #if no more courses today, wait and retry
        wait_time = (time_before_course - current_time).total_seconds()
        if wait_time < 1:
            send_logs("No more courses for today. Waiting - 4:00:00", 'info')
            await asyncio.sleep(14400)  # Wait 4 hours
            return await send_curr_course_users(week_day, is_even)
        
        if next_courses:
            send_logs(f"Waiting for next course - {time_before_course - current_time}", 'info')
            
            #create and schedule tasks for all notifications
            tasks = [
                send_notification(sender, course, wait_time) 
                for sender, course in next_courses.items()
            ]
            
            await asyncio.gather(*tasks)
            send_logs(f"Sent next course to {noti_send} users", 'info')
        else:
            send_logs(f"No users have the next course. Waiting - {time_before_course - current_time}", 'info')
            await asyncio.sleep(wait_time)
        

#send schedule for tomorrow to users with notifications on
async def send_schedule_tomorrow():
    while True:
        try:
            #gain vars
            now = datetime.datetime.now(moldova_tz)
            current_time = datetime.datetime.strptime(str(now.time())[:-7], "%H:%M:%S")
            
            # Calculate tomorrow and its weekday
            tomorrow = now + datetime.timedelta(days=1)
            week_day = int(tomorrow.weekday())
            temp_is_even = tomorrow.isocalendar().week % 2
            
            # Set target time to 20:00 today
            scheduled = datetime.datetime.strptime("20:00:00", "%H:%M:%S")
            
            # If it's already past 20:00, set target to tomorrow
            wait_seconds = (scheduled - current_time).total_seconds()
            if wait_seconds < 0:
                send_logs("Already past schedule time, waiting until tomorrow 20:00", 'info')
                target_time = now.replace(hour=20, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
                wait_seconds = (target_time - now).total_seconds()
            else:
                send_logs(f"Waiting until 20:00 to send tomorrow's schedule - {wait_seconds/60:.1f} minutes", 'info')
            
            # Wait until scheduled time
            await asyncio.sleep(wait_seconds)
            
            # Get users with notifications enabled
            all_users = db.get_all_users()
            filtered_users = all_users[
                    (all_users['group_n'].astype(str) != 'none') & 
                    (all_users['ban'] != 1) &
                    (all_users['noti'] == 1)
                ]
            
            noti_day = 0  # Counter for successful notifications
            send_logs(f"Starting to send tomorrow's schedule to {len(filtered_users)} eligible users", 'info')
            
            # Send notifications to each user
            for index, row in filtered_users.iterrows():
                try:
                    sender = int(row['SENDER'][1:])
                    csv_gr = row['group_n']
                    subgrupa = row['subgrupa']
                    user_lang = row.get('lang', DEFAULT_LANG)
                    if not user_lang or user_lang not in SUPPORTED_LANGS:
                        user_lang = DEFAULT_LANG
                    lang_week_days = get_week_days(user_lang)
                
                    if pd.isna(csv_gr) or csv_gr == '' or csv_gr == 'none':
                        continue
                        
                    # Get schedule and send if not empty
                    day_sch = print_day(week_day, csv_gr, temp_is_even, subgrupa, user_lang)
                    if day_sch:
                        text = get_text(user_lang, "notif_tomorrow_schedule", day=lang_week_days[week_day], schedule=day_sch)
                        await client.send_message(sender, text, parse_mode="HTML")
                        noti_day += 1
                except Exception as e:
                    send_logs(f"Error sending schedule to {row['SENDER']}: {e}", 'error')
                    
            send_logs(f"Successfully sent tomorrow's schedule to {noti_day} users", 'info')
            
        except Exception as e:
            send_logs(f"Error in send_schedule_tomorrow: {e}", 'error')
            await asyncio.sleep(60)  # Wait 1 min

#backup BD automation
async def backup_database():
    try:
        if not admins1:
            send_logs("No admins found for database backup", 'warning')
            return
            
        admin_id = int(admins1[0][1:])

        #wait
        now = datetime.datetime.now(moldova_tz)
        target_time = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now.time() >= target_time.time():
            target_time += datetime.timedelta(days=1)
        wait_seconds = (target_time - now).total_seconds()
        send_logs(f"Scheduled database backup in {wait_seconds/60/60:.2f} hours", 'info')
        await asyncio.sleep(wait_seconds)

        #file
        now = datetime.datetime.now(moldova_tz)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        os.makedirs("/backups", exist_ok=True)
        backup_filename = f"/backups/BD_backup_{timestamp}.sql"
        db.create_mysql_backup(backup_filename)
        db_len = db.get_user_count()
        
        #send
        await client.send_file(
            admin_id,
            backup_filename,
            caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {db_len} users"
        )
        
        send_logs(f"Database backup sent to admin", 'info')
            
    except Exception as e:
        send_logs(f"Error in database backup: {str(e)}", 'error')

### MAIN
if __name__ == '__main__':
    send_logs("############################################", 'info')
    send_logs("Bot Started!", 'info')
    
    async def main():
        await client.start(bot_token=BOT_TOKEN)
        loop = client.loop
        loop.create_task(send_curr_course_users(week_day, is_even))
        loop.create_task(send_schedule_tomorrow())
        loop.create_task(backup_database())
        await client.run_until_disconnected()
    
    asyncio.run(main())