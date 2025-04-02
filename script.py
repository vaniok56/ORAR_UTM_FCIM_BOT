# orar_utm_fcim_bot version 0.9.1
### changelog:
# spam protection added
# ban, unban and list_bann functions added
# games ballanced
# minor fixes

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import configparser # read
import datetime
import pytz

from functions import print_day, print_sapt, print_next_course, button_grid, send_logs, get_next_course_time, is_rate_limited
from functions import cur_group, hours, week_days, is_even
from group_lists import years, group_list, specialties

from handlers.game_handlers import register_games_handlers
from handlers.admin_handlers import register_admin_handlers
from handlers.group_handlers import register_group_handlers

import pandas as pd
import numpy as np
import asyncio

#### Access credentials
config = configparser.ConfigParser() # Define the method to read the configuration file
config.read('config.ini') # read config.ini file 

api_id = config.get('default','api_id') # get the api id
api_hash = config.get('default','api_hash') # get the api hash
BOT_TOKEN = config.get('default','BOT_TOKEN') # get the bot token

# Create the client and the session called session_master.
client = TelegramClient('sessions/session_master', api_id, api_hash).start(bot_token=BOT_TOKEN)

#keyboard buttons
bot_kb = [
        Button.text('Orarul de azi 📅', resize=True),
        Button.text('Orarul de maine 📅', resize=True),
        Button.text('Săptămâna curentă 🗓️', resize=True),
        Button.text('Săptămâna viitoare 🗓️', resize=True),
        types.KeyboardButtonSimpleWebView("SIMU📚", "https://simu.utm.md/students/"),
        Button.text('Jocuri 🎮', resize=True),
    ]

df = pd.read_csv('BD.csv') #DB
#cur_speciality = 'TI'

moldova_tz = pytz.timezone('Europe/Chisinau')
week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)

#1 rank is higher
admins1 = df.loc[df['admin'] == 1, 'SENDER'].values
admins2 = df.loc[df['admin'] == 2, 'SENDER'].values
noti_send = 0

register_games_handlers(client, bot_kb, df)
register_admin_handlers(client, df, admins1, admins2)
register_group_handlers(client, df, years, specialties, group_list)

#/start
@client.on(events.NewMessage(pattern="/(?i)start")) 
async def startt(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Salut!\nIn primul rand alege grupa - /alege_grupa\nPentru a afisa toate comenzile - /help\nContacte - /contacts\n"
    text += "Atentie! __**Orarul poate nu fi actual**__, nu raspund pentru absente"
    buttons_in_row = 2
    button_rows = button_grid(bot_kb, buttons_in_row)
    #add the user to users
    if "U"+str(SENDER) not in "U"+str(df['SENDER'].to_list()):
        await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
        data =  {'SENDER' : ["U"+str(SENDER)],
                 'group' : [""],
                 'spec' : [""],
                 'year' : [""],
                 'noti' : ["off"],
                 'admin' : [0],
                 'prem' : [0],
                 'subgrupa' : [0],
                 'gamble' : [""],
                 'ban' : ['none'],
                 'ban_time' : ['none'],
                 'ban_reason' : [""],
                 'last_cmd' : [""]}
        new_dat = pd.DataFrame(data)
        df = pd.concat([df, new_dat])
        df.to_csv('BD.csv', encoding='utf-8', index=False)
        send_logs("New user! - " + "U"+str(SENDER), 'info')

    text = "Doresti sa pornesti notificarile pentru pereche?"
    buttons = [ Button.inline("Da", data=b"on"),
                Button.inline("Nu", data=b"off")]
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=buttons)

#notif button handle
@client.on(events.CallbackQuery())
async def notiff(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = ""
    if event.data == b"off":
        text = "Notificarile sunt stinse"
        df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "off"
        df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
        await event.answer('Notificarile sunt stinse')
        await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
        send_logs("U"+str(SENDER) + " - Notif off", 'info')
    elif event.data==b"on":
        text = "Notificarile sunt pornite"
        df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "on"
        df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
        await event.answer('Notificarile sunt pornite')
        await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
        send_logs("U"+str(SENDER) + " - Notif on", 'info')

#/help
@client.on(events.NewMessage(pattern='/(?i)help')) 
async def helpp(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "/contacts - contacte\n"
    text += "/azi - orarul de azi\n"
    text += "/maine - orarul de maine\n"
    text += "/ore - orarul orelor(perechi + pauze)\n"
    text += "/alege_grupa - alegerea grupei\n"
    text += "/alege_subgrupa - alegerea subgrupei\n"
    text += "/sapt_curenta - orar pe saptamana curenta\n"
    text += "/sapt_viitoare - orar pe saptamana viitoare\n"
    text += "/notifon - notificari on\n"
    text += "/notifoff - notificari off\n"
    text += "/games - jocuri\n"
    text += "/donatii - donatii\n"
    text += "/version - versiunea\n"
    text += "/admin_help - admin commands\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
    send_logs("U"+str(SENDER) + " - /help", 'info')

#/version
@client.on(events.NewMessage(pattern='/(?i)version'))
async def versionn(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Version 0.9.1\n"
    text += "Last update: 02-04-2025\n"
    text += "Github: [ORAR_UTM_FCIM_BOT](https://github.com/vaniok56/ORAR_UTM_FCIM_BOT)\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows, link_preview=False)
    send_logs("U"+str(SENDER) + " - /version", 'info')

#/contacts
@client.on(events.NewMessage(pattern='/(?i)contacts')) 
async def contactt(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Salut! Acest bot a fost creat din dorința de a simplifica accesul la orar. În prezent, botul este în faza de dezvoltare și îmbunătățire, deci unele funcții pot să nu fie operaționale, iar disponibilitatea poate varia. \n__**Orarul poate nu fi actual**__, nu raspund pentru absente\n\nSunt deschis pentru întrebări și sugestii:\n"
    text += "Telegram: "
    text += "[@vaniok56](https://t.me/vaniok56)\n"
    text += "Github repo: "
    text += "[ORAR_UTM_FCIM_BOT](https://github.com/vaniok56/ORAR_UTM_FCIM_BOT)\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
    send_logs("U"+str(SENDER) + " - /contacts", 'info')

#/notifon
@client.on(events.NewMessage(pattern='/(?i)notifon'))
async def notifonn(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Notificarile sunt pornite!\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
    #noti is on
    df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "on"
    df.to_csv('BD.csv', encoding='utf-8', index=False)
    send_logs("U"+str(SENDER) + " - /notifon", 'info')

#/notifoff
@client.on(events.NewMessage(pattern='/(?i)notifoff'))
async def notifofff(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Notificarile sunt stinse!\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
    #noti is on
    df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "off"
    df.to_csv('BD.csv', encoding='utf-8', index=False)
    send_logs("U"+str(SENDER) + " - /notifoff", 'info')

#/ore
@client.on(events.NewMessage(pattern='/(?i)ore|Orele ⏰')) 
async def oree(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Graficul de ore:\n"
    for i in range(0, 7):
        text += "\nPerechea: #" + str(i+1) + "\nOra : " + ''.join(hours[i]) + "\n"
        if i == 2 :
            text += "Pauza : " + "30 min\n"
        else:
            text += "Pauza : " + "15 min\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
    send_logs("U"+str(SENDER) + " - /hours", 'info')

#/maine
@client.on(events.NewMessage(pattern='/(?i)maine|Orarul de maine 📅')) 
async def mainee(event):
    global df, cur_group
    week_day = int((datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)).weekday()) #weekday tomorrow(0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    subgrupa = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'])[0]
    try:
        #get the user's selected group
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            temp_is_even = (datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)).isocalendar().week % 2
            #send the schedule
            day_sch = print_day(week_day, cur_group, temp_is_even, subgrupa)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de maine(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi maine(" + week_days[week_day] +")"
            button_rows = button_grid(bot_kb, 2)
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
            send_logs("U"+str(SENDER) + " - /maine", 'info')
    except Exception as e:
        send_logs(f"Error sending sch tomorr to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, "A intervenit o eroare, posibil nu ai ales grupa /alege_grupa", parse_mode="HTML")
    
#/azi
@client.on(events.NewMessage(pattern='/(?i)azi|Orarul de azi 📅')) 
async def azii(event):
    global df, cur_group
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    subgrupa = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'])[0]
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            day_sch = print_day(week_day, cur_group, is_even, subgrupa)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de azi(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi azi(" + week_days[week_day] +")"
            button_rows = button_grid(bot_kb, 2)
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
            send_logs("U"+str(SENDER) + " - /azi", 'info')
    except Exception as e:
        send_logs(f"Error sending sch today to {str(SENDER)}: {e}", 'info')
        await client.send_message(SENDER, "A intervenit o eroare, posibil nu ai ales grupa /alege_grupa", parse_mode="HTML")

#/sapt_cur
@client.on(events.NewMessage(pattern='/(?i)sapt_curenta|Săptămâna curentă 🗓️')) 
async def sapt_curr(event):
    global df, cur_group, is_even
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    subgrupa = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'])[0]
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana aceasta:" + print_sapt(is_even, cur_group, subgrupa)
            button_rows = button_grid(bot_kb, 2)
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
            send_logs("U"+str(SENDER) + " - /sapt_curenta", 'info')
    except Exception as e:
        send_logs(f"Error sending curr week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, "A intervenit o eroare, posibil nu ai ales grupa /alege_grupa", parse_mode="HTML")

#/sapt_viit
@client.on(events.NewMessage(pattern='/(?i)sapt_viitoare|Săptămâna viitoare 🗓️')) 
async def sapt_viit(event):
    global df, cur_group, is_even
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    subgrupa = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'])[0]
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            is_even = not is_even
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana viitoare:" + print_sapt(is_even, cur_group, subgrupa)
            button_rows = button_grid(bot_kb, 2)
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
            send_logs("U"+str(SENDER) + " - /sapt_viitoare", 'info')
    except Exception as e:
        send_logs(f"Error sending next week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, "A intervenit o eroare, posibil nu ai ales grupa /alege_grupa", parse_mode="HTML")

#/donatii
@client.on(events.NewMessage(pattern='/(?i)donatii')) 
async def donatiii(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if is_rate_limited(SENDER, df):
        send_logs(f"Rate limited user: {SENDER}", 'warning')
        return
    text = "Buy me a coffee ☕️\n\n"
    text += "      Destinatorul:\n"
    text += "`Ivan Proscurchin`\n\n"
    text += "       **MIA**\n"
    text += "`79273147`\n\n"
    text += "       **MICB**\n"
    text += "`5574 8402 5994 1411`\n\n"
    text += "       **MAIB**\n"
    text += "`5397 0200 3403 5186`\n"

    await client.send_message(SENDER, text, parse_mode="Markdown")
    send_logs("U"+str(SENDER) + " - /donatii", 'info')

def prepare_next_courses(week_day, is_even, course_index):
    next_courses = {}
    # Get all users with a group set and who are not banned
    all_users = df.loc[(df['group'].str.len() > -1) & (df['ban'] != 1) & (df['ban'] != '1'), 'SENDER'].values
    
    for user in all_users:
        sender = int(user[1:])
        csv_gr = df.loc[df['SENDER'] == f"U{sender}", 'group'].values[0]
        subgrupa = df.loc[df['SENDER'] == f"U{sender}", 'subgrupa'].values[0]
        if str(csv_gr) == 'nan' or str(csv_gr) == '':
            continue
        try:
            next_course = print_next_course(week_day, csv_gr, is_even, course_index, subgrupa)
            if next_course:
                next_courses[sender] = next_course
        except Exception as e:
            send_logs(f"Error preparing next course to {sender}: {e}", 'error')
    
    return next_courses

async def send_notification(sender, next_course, wait_time):
    global noti_send
    await asyncio.sleep(wait_time)
    
    #re-check if notifications are still enabled for this user
    if str(df.loc[df['SENDER'] == f"U{sender}", 'noti'].values[0]) != 'on':
        return
    
    try:
        await client.send_message(sender, f"\nPerechea urmatoare:{next_course}", parse_mode="HTML")
        noti_send += 1
        return True
    except Exception as e:
        send_logs(f"Error sending next course to {sender}: {e}", 'error')
        return False

#send current course to users with notifications on
async def send_curr_course_users(week_day, is_even):
    global noti_send
    noti_send = 0
    
    #get next course time, index and time before course
    current_time, course_index, time_before_course = get_next_course_time()
    
    #if no more courses today, wait and retry
    wait_time = (time_before_course - current_time).total_seconds()
    if wait_time < 1:
        send_logs("No more courses for today. Waiting - 4:00:00", 'info')
        await asyncio.sleep(14400)  # Wait 4 hours
        return await send_curr_course_users(week_day, is_even)
    
    #prepare next courses for all users
    next_courses = prepare_next_courses(week_day, is_even, course_index)
    
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
    
    return await send_curr_course_users(week_day, is_even)
    

#send schedule for tomorrow to users with notifications on
async def send_schedule_tomorrow():
    noti_day = 0
    #gain vars
    now = datetime.datetime.now(moldova_tz)
    current_time = datetime.datetime.strptime(str(now.time())[:-7], "%H:%M:%S")
    week_day = int((now + datetime.timedelta(days=1)).weekday())
    scheduled = datetime.datetime.strptime("20:00:00", "%H:%M:%S")
    #wait 4h 1s if waiting is negative
    if (scheduled - current_time).total_seconds() < 1:
        send_logs("waiting positive for tomorrow", 'info')
        await asyncio.sleep(14401)
        return await send_schedule_tomorrow()
    send_logs("waiting for tomorrow mess - " + str(scheduled - current_time), 'info')
    temp_is_even = (now + datetime.timedelta(days=1)).isocalendar().week % 2
    users_with_notification_on = df.loc[(df['group'].str.len() > -1) & (df['ban'] != 1) & (df['ban'] != '1'), 'SENDER'].values
    await asyncio.sleep((scheduled - current_time).total_seconds())
    for user in users_with_notification_on:
        sender = int(user[1:])
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(sender), 'group'])[0]
        subgrupa = list(df.loc[df['SENDER'] == "U"+str(sender), 'subgrupa'])[0]
        try:
            if csv_gr == "" or str(csv_gr) == 'nan':
                raise ValueError(str(sender) + 'no gr')
            #send the schedule
            day_sch = print_day(week_day, csv_gr, temp_is_even, subgrupa)
            if day_sch == "":
                continue
            text = "\nOrarul de maine(" + week_days[week_day] +"):\n" + day_sch
            await client.send_message(sender, text, parse_mode="HTML")
            #send_logs("U"+str(sender) + " - send schedule for tomorrow", 'info')
            noti_day+=1
        except Exception as e:
            send_logs(f"Error sending sch tomorr to {str(sender)}: {e}", 'error')
    send_logs(f"Send next day to {str(noti_day)} users",'info')
    return await send_schedule_tomorrow()

#backup BD automation
async def backup_database():
    try:
        admin_id = 500303890

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
        timestamp = now.strftime("%Y%m%d")
        backup_filename = f"BD_backup_{timestamp}.csv"
        import shutil
        shutil.copy2('BD.csv', backup_filename)
        
        #send
        await client.send_file(
            admin_id,
            backup_filename,
            caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {len(df)} users"
        )
        
        send_logs(f"Database backup sent to admin", 'info')
        
        #delete
        import os
        if os.path.exists(backup_filename):
            os.remove(backup_filename)
            
    except Exception as e:
        send_logs(f"Error in database backup: {str(e)}", 'error')

#keep network alive
async def keep_network_alive():
    import socket
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 53))
            s.close()
            #send_logs("Network keep-alive check successful", 'debug')
        except Exception as e:
            send_logs(f"Network keep-alive error: {str(e)}", 'warning')
        await asyncio.sleep(60)

### MAIN
if __name__ == '__main__':
    send_logs("############################################", 'info')
    send_logs("Bot Started!", 'info')
    loop = client.loop
    loop.create_task(send_curr_course_users(week_day, is_even))
    loop.create_task(send_schedule_tomorrow())
    loop.create_task(keep_network_alive())
    loop.create_task(backup_database())
    client.run_until_disconnected()
