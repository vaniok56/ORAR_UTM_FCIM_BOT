# orar_utm_fcim_bot version 0.8.6
### changelog:
# added the ability to chose the year of study(schedule not yet ready)
# improved message command
# improved and oprimised the print daily function(now it does not depend on not_dual array)
# other minor changes

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import configparser # read
import datetime
import pytz

from functions import print_day, print_sapt, print_next_course, button_grid, send_logs
from functions import cur_group, hours, week_days, is_even
from group_lists import years, group_list, specialties

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
    ]

df = pd.read_csv('BD.csv') #DB
#cur_speciality = 'TI'

moldova_tz = pytz.timezone('Europe/Chisinau')
week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)

#1 rank is higher
admins1 = df.loc[df['admin'] == 1, 'SENDER'].values
admins2 = df.loc[df['admin'] == 2, 'SENDER'].values
noti_send = 0

#/start
@client.on(events.NewMessage(pattern="/(?i)start")) 
async def startt(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Salut!\nIn primul rand alege grupa - /alege_grupa\nPentru a afisa toate comenzile - /help\nContacte - /contacts\n"
    text += "Atentie! __**Orarul poate nu fi actual**__, nu raspund pentru absente"
    buttons_in_row = 2
    button_rows = button_grid(bot_kb, buttons_in_row)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
    #add the user to users
    if "U"+str(SENDER) not in "U"+str(df['SENDER'].to_list()):
        data =  {'SENDER' : ["U"+str(SENDER)],
                 'group' : [""],
                 'spec' : [""],
                 'year' : [""],
                 'noti' : ["off"],}
        new_dat = pd.DataFrame(data)
        df = pd.concat([df, new_dat])
        df.to_csv('BD.csv', encoding='utf-8', index=False)
        send_logs("New user! - " + "U"+str(SENDER), 'info')

        await alege_grupaa(event)
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
    text = "/contacts - contacte\n"
    text += "/azi - orarul de azi\n"
    text += "/maine - orarul de maine\n"
    text += "/ore - orarul orelor(perechi + pauze)\n"
    text += "/alege_grupa - alegerea grupei\n"
    text += "/sapt_curenta - orar pe saptamana curenta\n"
    text += "/sapt_viitoare - orar pe saptamana viitoare\n"
    text += "/notifon - notificari on\n"
    text += "/notifoff - notificari off\n"
    text += "/donatii - donatii\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
    send_logs("U"+str(SENDER) + " - /help", 'info')

#/contacts
@client.on(events.NewMessage(pattern='/(?i)contacts')) 
async def contactt(event):
    sender = await event.get_sender()
    SENDER = sender.id
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
    text = "Notificarile sunt stinse!\n"
    button_rows = button_grid(bot_kb, 2)
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=button_rows)
    #noti is on
    df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "off"
    df.to_csv('BD.csv', encoding='utf-8', index=False)
    send_logs("U"+str(SENDER) + " - /notifoff", 'info')

#/hours
@client.on(events.NewMessage(pattern='/(?i)ore|Orele ⏰')) 
async def oree(event):
    sender = await event.get_sender()
    SENDER = sender.id
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
    try:
        #get the user's selected group
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            temp_is_even = (datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)).isocalendar().week % 2
            #send the schedule
            day_sch = print_day(week_day, cur_group, temp_is_even)
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
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            week_day = int((datetime.datetime.now(moldova_tz)).weekday()) #weekday today(0-6)
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            day_sch = print_day(week_day, cur_group, is_even)
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
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana aceasta:" + print_sapt(is_even, cur_group)
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
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError(str(sender) + 'no gr')
        else: 
            is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
            is_even = not is_even
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana viitoare:" + print_sapt(is_even, cur_group)
            button_rows = button_grid(bot_kb, 2)
            await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
            send_logs("U"+str(SENDER) + " - /sapt_viitoare", 'info')
    except Exception as e:
        send_logs(f"Error sending next week to {str(SENDER)}: {e}", 'error')
        await client.send_message(SENDER, "A intervenit o eroare, posibil nu ai ales grupa /alege_grupa", parse_mode="HTML")

#/alege_grupa
@client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
async def alege_grupaa(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Alege anul:"
    year_butt = [Button.inline(year, data=data) for data, year in years.items()]
    button_per_r = 4
    global button_rows_year
    button_rows_year = button_grid(year_butt, button_per_r)

    #if user is not in list, add it
    if "U"+str(SENDER) not in "U"+str(df['SENDER'].to_list()):
        data =  {'SENDER' : ["U"+str(SENDER)],
                'group' : [""],
                'spec' : [""],
                'year' : [""],
                'noti' : ["off"],}
        new_dat = pd.DataFrame(data)
        df = pd.concat([df, new_dat]) 
        df.to_csv('BD.csv', encoding='utf-8', index=False)
        send_logs("New user! - " + "U"+str(SENDER), 'info')
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows_year)
    
#year click event handle
@client.on(events.CallbackQuery())
async def year_callback(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    if event.data in years:
        cur_year = years.get(event.data).replace(" ", "")
        if cur_year:
            text = f"Alege specialitatea pentru anul {cur_year}:"
            spec_items = specialties.get(cur_year, {})
            spec_butt = [Button.inline(spec, data=data) for data, spec in spec_items.items()]
            button_per_r = 4
            button_rows = button_grid(spec_butt, button_per_r)
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
            df.loc[df['SENDER'] == "U"+str(SENDER), 'year'] = int(cur_year) #send cur_year to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
            await event.answer('Anul a fost selectat!')

#speciality click event handle
@client.on(events.CallbackQuery())
async def speciality_callback(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    year = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'year'])[0]
    spec_items = specialties.get(str(year), {})
    if event.data in spec_items:
        cur_speciality = spec_items.get(event.data).replace(" ", "")
        if cur_speciality:
            text = f"Alege grupa pentru {cur_speciality}:"
            group_items = group_list.get(str(year), {})
            group_items = group_items.get(cur_speciality + str(year), {})
            df.loc[df['SENDER'] == "U"+str(SENDER), 'spec'] = cur_speciality #send cur_speciality to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
            spec_butt = [Button.inline(group, data=data) for data, group in group_items.items()]
            button_per_r = 4
            button_rows = button_grid(spec_butt, button_per_r)
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
            await event.answer('Specialitatea a fost selectata!')

#group click event handle
@client.on(events.CallbackQuery())
async def group_callback(event):
    global df, cur_group
    sender = await event.get_sender()
    SENDER = sender.id
    cur_speciality = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'spec'])[0]
    year = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'year'])[0]
    group_items = group_list.get(str(year), {})
    group_items = group_items.get(cur_speciality + str(year), {})
    if event.data in group_items:
        cur_group = group_items.get(event.data).replace(" ", "")
        if cur_group:
            #updates the current group
            df.loc[df['SENDER'] == "U"+str(SENDER), 'group'] = cur_group #send cur_group to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df

            send_logs("U"+str(SENDER) + " - /alege_grupa - " + cur_group, "info")

            text = f"Grupa ta este: {cur_group}"
            await event.answer('Grupa a fost selectata!')
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")

#/stats
@client.on(events.NewMessage(pattern='/(?i)stats')) 
async def statsss(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if "U"+str(SENDER) in admins2 or "U"+str(SENDER) in admins1:
        text = "Stats:\n"
        counted = {}
        all_users = df.loc[df['group'].str.len() != "", 'SENDER'].values
        for user in all_users:
            user_id = int(user[1:])
            group_name = df.loc[df['SENDER'] == "U"+str(user_id), 'group'].values[0]
            if str(group_name) != "nan":
                if group_name not in counted:
                    counted[group_name] = 0
                counted[group_name] += 1

        #sort
        sorted_counted = dict(sorted(counted.items()))
        
        for group, count in sorted_counted.items():
            text += f"{group} - {count} users\n"
        text += "Total users - " + str(len(all_users)) + "\n"
        text += "Active users - " + str(len(df.loc[df['group'].str.len() > -1, 'SENDER'].values)) + "\n"
        text += "Users with notifications - " + str(len(df.loc[df['noti'] == 'on', 'SENDER'].values))
        
    else:
        text = "Nu ai acces!"
    await client.send_message(SENDER, text, parse_mode="HTML")
    send_logs("U"+str(SENDER) + " - /stats", "info")

@client.on(events.NewMessage(pattern='/(?i)donatii')) 
async def donatiii(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Buy me a coffee ☕️\n\n"
    text += "      Destinatorul:\n"
    text += "`Ivan Proscurchin`\n\n"
    text += "       **MIA**\n"
    text += "`79273147`\n\n"
    text += "       **MICB**\n"
    text += "`5574 8402 5994 1411`\n\n"
    text += "       **MAIB**\n"
    text += "`5102 1800 6389 5169`\n"

    await client.send_message(SENDER, text, parse_mode="Markdown")
    send_logs("U"+str(SENDER) + " - /donatii", 'info')


#send current course to users with notifications on
async def send_curr_course_users(week_day, is_even):
    global noti_send
    noti_send = 0
    current_time = datetime.datetime.now(moldova_tz).time()
    current_time = datetime.datetime.strptime(str(current_time)[:-7], "%H:%M:%S")
    #next course index
    for course_index, hour in enumerate(hours):
        course_time = datetime.datetime.strptime(hour[0].split("-")[0], "%H.%M")
        if (course_time - datetime.timedelta(minutes=15)).time() > current_time.time():
            break
    course_index += 1
    #15 min before the next course
    time_before_course = course_time - datetime.timedelta(minutes=15)

    #if negative
    if (time_before_course - current_time).total_seconds() < 1:
        send_logs(f"No more courses for today. Waiting - 4:00:00", 'info')
        await asyncio.sleep(14400)
    else:
        #get users with notif on and save all next courses into an array
        all_users = df.loc[df['group'].str.len() > -1, 'SENDER'].values
        next_courses = {}
        for user in all_users:
            sender = int(user[1:])
            csv_gr = df.loc[df['SENDER'] == "U"+str(sender), 'group'].values[0]
            if str(csv_gr) != 'nan' or str(csv_gr) != '':
                try:
                    next_courses[sender] = print_next_course(week_day, csv_gr, is_even, course_index)
                except Exception as e:
                    send_logs(f"Error preparing next course to {str(sender)}: {e}", 'error')

        current_time = datetime.datetime.now(moldova_tz).time()
        current_time = datetime.datetime.strptime(str(current_time)[:-7], "%H:%M:%S")
        #create tasks to send next courses simultaneously to all users
        tasks = []
        for sender, next_course in next_courses.items():
            if next_course != "":
                async def send_message_later(sender, next_course):
                    global noti_send
                    await asyncio.sleep((time_before_course - current_time).total_seconds())
                    if str(df.loc[df['SENDER'] == "U"+str(sender), 'noti'].values[0]) == 'on':
                        try:
                            await client.send_message(sender, "\nPerechea urmatoare:" + next_course, parse_mode="HTML")
                            #send_logs("U"+str(sender) + " - send next course", "info")
                            noti_send+=1
                        except Exception as e:
                            send_logs(f"Error sending next course to {str(sender)}: {e}", 'error')
                task = asyncio.create_task(send_message_later(sender, next_course))
                tasks.append(task)

        if tasks:
            send_logs(f"Waiting for next course - {str(time_before_course - current_time)}", 'info')
            await asyncio.gather(*tasks)
            send_logs(f"Send next course to {str(noti_send)} users",'info')
        #if there is no next course to any user
        else:
            send_logs(f"No users have the next course. Waiting - {str(time_before_course - current_time)}", 'info')
            await asyncio.sleep((time_before_course - current_time).total_seconds())
    #repeat
    await send_curr_course_users(week_day, is_even)

#send schedule for tomorrow to users with notifications on
async def send_schedule_tomorrow():
    noti_day = 0
    while True:
        #gain vars
        now = datetime.datetime.now(moldova_tz)
        current_time = datetime.datetime.strptime(str(now.time())[:-7], "%H:%M:%S")
        week_day = int((now + datetime.timedelta(days=1)).weekday())
        scheduled = datetime.datetime.strptime("20:00:00", "%H:%M:%S")
        #wait 4h 1s if waiting is negative
        if (scheduled - current_time).total_seconds() < 1:
            send_logs("waiting positive for tomorrow", 'info')
            await asyncio.sleep(14401)
        else:
            send_logs("waiting for tomorrow mess - " + str(scheduled - current_time), 'info')
            temp_is_even = (now + datetime.timedelta(days=1)).isocalendar().week % 2
            users_with_notification_on = df.loc[df['noti'] == 'on', 'SENDER'].values
            await asyncio.sleep((scheduled - current_time).total_seconds())
            for user in users_with_notification_on:
                sender = int(user[1:])
                csv_gr = list(df.loc[df['SENDER'] == "U"+str(sender), 'group'])[0]
                try:
                    if csv_gr == "" or str(csv_gr) == 'nan':
                        raise ValueError(str(sender) + 'no gr')
                    else:
                        #send the schedule
                        day_sch = print_day(week_day, csv_gr, temp_is_even)
                        if day_sch != "":
                            text = "\nOrarul de maine(" + week_days[week_day] +"):\n" + day_sch
                            await client.send_message(sender, text, parse_mode="HTML")
                            #send_logs("U"+str(sender) + " - send schedule for tomorrow", 'info')
                            noti_day+=1
                except Exception as e:
                    send_logs(f"Error sending sch tomorr to {str(sender)}: {e}", 'error')
        send_logs(f"Send next day to {str(noti_day)} users",'info')

#message command handle
@client.on(events.NewMessage(pattern='/(?i)message'))
async def message_command(event):
    sender = await event.get_sender()
    SENDER = sender.id
    if "U" + str(SENDER) in admins1:
        text = "Select the recipient:"
        buttons = [
            Button.inline("Myself", data=b"to1"),
            Button.inline("TI-241", data=b"to2"),
            Button.inline("Notifon users", data=b"to3"),
            Button.inline("A user", data=b"to4"),
            Button.inline("All users", data=b"to5")
        ]
        buttons = button_grid(buttons, 2)
        await client.send_message(SENDER, text, buttons=buttons)
    else:
        await client.send_message(SENDER, "You do not have permission to use this command.", parse_mode="HTML")

@client.on(events.CallbackQuery())
async def message_callback(event):
    sender = await event.get_sender()
    SENDER = sender.id
    data = event.data.decode('utf-8')
    
    if data.startswith("to"):
        global to_who, useridd, when, text, input_step
        useridd = 0
        to_who = int(data[2])
        input_step = 1
        recipient_dict = {
            1: "Myself",
            2: "TI-241",
            3: "Notifon users",
            4: "A user",
            5: "All users"
        }
        await event.answer()
        await client.edit_message(SENDER, event.message_id, "Selected: " + recipient_dict.get(to_who))
        if to_who == 4:
            await client.send_message(SENDER, "Please enter the user ID(as int):")
        else:
            input_step = 2
            await client.send_message(SENDER, "Please enter the time in HH:MM format or \"Now\":")

        @client.on(events.NewMessage(from_users=SENDER))
        async def handle_input(event):
            global input_step, useridd, when, text
            user_input = event.text

            if input_step == 1 and to_who == 4:
                useridd = int(user_input)
                input_step = 2
                await client.send_message(SENDER, "Please enter the time in HH:MM format or \"Now\":")
            elif input_step == 2:
                when = user_input
                input_step = 3
                await client.send_message(SENDER, "Please enter the text:")
            elif input_step == 3:
                text = user_input
                client.remove_event_handler(handle_input, events.NewMessage(from_users=SENDER))

                summary = f"\nSend to: {recipient_dict.get(to_who)}"
                if useridd != 0:
                    summary += f"\nUser ID: {useridd}"
                summary += f"\nTime: {when}\nMessage: \n{text}"
                await client.send_message(SENDER, summary)

                buttons = button_grid([Button.inline("Yes", data=b"yes"), Button.inline("No", data=b"no")], 2)
                await client.send_message(SENDER, "Send the message?", buttons=buttons)

                @client.on(events.CallbackQuery())
                async def confirmation_callback(event):
                    global to_who, when, useridd, df, text
                    sender = await event.get_sender()
                    SENDER = sender.id
                    if event.data == b"yes":
                        await event.answer()
                        await client.edit_message(SENDER, event.message_id, "Message scheduled successfully!")
                        await send_mess(to_who, when, useridd, df)
                    elif event.data == b"no":
                        await event.answer()
                        await client.edit_message(SENDER, event.message_id, "Message sending canceled.")

#send a custom message to all active users
async def send_mess(to_who, when, useridd, df):
    now = datetime.datetime.now(moldova_tz).time()
    current_time = datetime.datetime.strptime(str(now)[:-7], "%H:%M:%S")
    if when == "Now":
        scheduled = current_time
    else:
        scheduled = datetime.datetime.strptime(when, "%H:%M")
    if text != "":
        
        if to_who == 1:
            all_users = df.loc[df['SENDER'] == 'U500303890', 'SENDER'].values
            send_logs("Sending to myself", 'info')
        elif to_who == 2:
            all_users = df.loc[df['group'] == 'TI-241', 'SENDER'].values
            send_logs("Sending to TI-241", 'info')
        elif to_who == 3:
            all_users = df.loc[df['noti'] == 'on', 'SENDER'].values
            send_logs("Sending to notifon users", 'info')
        elif to_who == 4:
            all_users = df.loc[df['SENDER'] == 'U'+str(useridd), 'SENDER'].values
            send_logs("Sending to " + 'U'+str(useridd), 'info')
        elif to_who == 5:
            all_users = df.loc[df['group'].str.len() > -1, 'SENDER'].values
            send_logs("Sending to everyone", 'info')
        else:
            send_logs("No users to send a message", 'info')
            return
        if when != "Now":
            send_logs("waiting to send a message - " + str(scheduled - current_time), 'info')
            await asyncio.sleep((scheduled - current_time).total_seconds())
        for user in all_users:
            sender = int(user[1:])
            try:
                await client.send_message(sender, text, parse_mode="Markdown")
                send_logs("Send succeseful to " + user, 'info')
            except Exception as e:
                send_logs(f"Error sending message to {str(sender)}: {e}", 'error')

### MAIN
if __name__ == '__main__':
    send_logs("############################################", 'info')
    send_logs("Bot Started!", 'info')
    loop = client.loop
    loop.create_task(send_curr_course_users(week_day, is_even))
    loop.create_task(send_schedule_tomorrow())
    client.run_until_disconnected()
