# orar_utm_fcim_bot version 0.6.0
### changelog:
# fixed wrong is_even check
# better logs
# added contacts
# implimented notification for the next course and for the next day
#                                         ^                      ^
#                       (15 mins before the course start)   (at 20:00)
# changed the "restarter" logic
# other minor changes

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import configparser # read
import datetime

from functions import print_day, print_sapt, print_next_course, curr_time_logs, button_grid
from functions import cur_group, hours, week_days, is_even
from group_lists import group_list, specialties

import pandas as pd
import numpy as np
import cProfile
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
        Button.text('Orarul saptamainii 🗓️', resize=True),
        Button.text('Orele ⏰', resize=True),
    ]

df = pd.read_csv('BD.csv') #DB
cur_speciality = 'TI'
week_day = int(datetime.datetime.today().weekday()) #weekday today(0-6)

#/start
@client.on(events.NewMessage(pattern="/(?i)start")) 
async def startt(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Salut!\nIn primul rand alege grupa - /alege_grupa \nPentru a afisa toate comenzile - /help\nContacte - /contacts\n"
    text += "Atentie! __**Orarul poate nu fi actual**__, nu raspund pentru absente"
    buttons_in_row = 2
    #bot_kb.append(types.KeyboardButtonSimpleWebView("Orar pdf🥱", "https://fcim.utm.md/procesul-de-studii/orar/#toggle-id-2-closed",))
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
        print(curr_time_logs() + "New user! - " + "U"+str(SENDER))
    
    text = "Doresti sa pornesti notificarile pentru pereche?"
    buttons = [ Button.inline("Da", data=b"on"),
                Button.inline("Nu", data=b"off")]
    await client.send_message(SENDER, text, parse_mode="Markdown", buttons=buttons)

#notif button handle
@client.on(events.CallbackQuery())
async def speciality_callback(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = ""
    if event.data==b"off":
        text = "Notificarile sunt stinse"
        df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "off"
        df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
        await event.answer('Notificarile sunt stinse')
    elif event.data==b"on":
        text = "Notificarile sunt pornite(se vor porni maine)"
        df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "on"
        df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
        await event.answer('Notificarile sunt pornite')
    await client.send_message(SENDER, text, parse_mode="HTML")

#/help
@client.on(events.NewMessage(pattern='/(?i)help')) 
async def helpp(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text  = "/help - toate comenzile\n"
    text += "/contacts - contacte\n"
    text += "/azi - orarul de azi\n"
    text += "/maine - orarul de maine\n"
    text += "/ore - orarul orelor(perechi + pauze)\n"
    text += "/alege_grupa - alegerea grupei\n"
    text += "/sapt_curenta - orar pe saptamana curenta\n"
    text += "/sapt_viitoare - orar pe saptamana viitoare\n"
    text += "/notifon - notificari on\n"
    text += "/notifoff - notificari off\n"
    #text += "/alege - NOT IMPLEMENTED orar pe o zi concreta cu butoane\n"
    #text += "/sesiuni - NOT IMPLEMENTED orarul sesiunilor\n"
    await client.send_message(SENDER, text, parse_mode="HTML")

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
    await client.send_message(SENDER, text, parse_mode="Markdown")

#/notifon
@client.on(events.NewMessage(pattern='/(?i)notifon'))
async def notifonn(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Notificarile sunt pornite!\n"
    text += "__daca erau stinse, se vor porni maine__"
    await client.send_message(SENDER, text, parse_mode="Markdown")
    #noti is on
    df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "on"
    df.to_csv('BD.csv', encoding='utf-8', index=False)

#/notifoff
@client.on(events.NewMessage(pattern='/(?i)notifoff'))
async def notifofff(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Notificarile sunt stinse!\n"
    text += "__daca erau pornite, se vor stinge maine__"
    await client.send_message(SENDER, text, parse_mode="Markdown")
    #noti is on
    df.loc[df['SENDER'] == "U"+str(SENDER), 'noti'] = "off"
    df.to_csv('BD.csv', encoding='utf-8', index=False)

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
    await client.send_message(SENDER, text, parse_mode="HTML")

#/maine
@client.on(events.NewMessage(pattern='/(?i)maine|Orarul de maine 📅')) 
async def mainee(event):
    global df, cur_group
    week_day = int((datetime.datetime.today() + datetime.timedelta(days=1)).weekday()) #weekday tomorrow(0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    try:
        #get the user's selected group
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            temp_is_even = (datetime.datetime.today() + datetime.timedelta(days=1)).isocalendar().week % 2
            #send the schedule
            day_sch = print_day(week_day, cur_group, temp_is_even)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de maine(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi azi(" + week_days[week_day] +")"
            await client.send_message(SENDER, text, parse_mode="HTML")
            print(curr_time_logs() + "U"+str(SENDER) + " " + cur_group + " - used tomor")
    except Exception as error:
        print(curr_time_logs() + "An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")
    
#/azi
@client.on(events.NewMessage(pattern='/(?i)azi|Orarul de azi 📅')) 
async def azii(event):
    global df, cur_group
    week_day = int(datetime.datetime.today().weekday()) #weekday today(0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            is_even = datetime.datetime.today().isocalendar().week % 2
            day_sch = print_day(week_day, cur_group, is_even)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de azi(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi azi(" + week_days[week_day] +")"
            await client.send_message(SENDER, text, parse_mode="HTML")
            print(curr_time_logs() + "U"+str(SENDER) + " " + cur_group + " - used today")
    except Exception as error:
        print(curr_time_logs() + "An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")

#/sapt_cur
@client.on(events.NewMessage(pattern='/(?i)sapt_curenta|Orarul saptamainii 🗓️')) 
async def sapt_curr(event):
    global df, cur_group, is_even
    sender = await event.get_sender()
    SENDER = sender.id
    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            is_even = datetime.datetime.today().isocalendar().week % 2
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana aceasta:" + print_sapt(is_even, cur_group)
            await client.send_message(SENDER, text, parse_mode="HTML")
            print(curr_time_logs() + "U"+str(SENDER) + " " + cur_group + " - used curr week")
    except Exception as error:
        print(curr_time_logs() + "An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")

#/sapt_viit
@client.on(events.NewMessage(pattern='/(?i)sapt_viitoare')) 
async def sapt_viit(event):
    global df, cur_group, is_even
    sender = await event.get_sender()
    SENDER = sender.id

    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            is_even = datetime.datetime.today().isocalendar().week % 2
            is_even = not is_even
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana viitoare:" + print_sapt(is_even, cur_group)
            await client.send_message(SENDER, text, parse_mode="HTML")
            print(curr_time_logs() + "U"+str(SENDER) + " " + cur_group + " - used next week")
    except Exception as error:
        print(curr_time_logs() + "An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")

#/alege_grupa
@client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
async def alege_grupaa(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Alege specialitea:"
    spec_butt = [Button.inline(spec, data=data) for data, spec in specialties.items()]
    button_per_r = 4
    global button_rows_spec
    button_rows_spec = button_grid(spec_butt, button_per_r)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows_spec)

#speciality click event handle
@client.on(events.CallbackQuery())
async def speciality_callback(event):
    #client.edit_message(event.sender_id, event.message_id)
    global cur_speciality
    sender = await event.get_sender()
    SENDER = sender.id
    if event.data in specialties:
        cur_speciality = specialties.get(event.data).replace(" ", "")
        if cur_speciality:
            text = f"Alege grupa pentru {cur_speciality}:"
            group_items = group_list.get(cur_speciality, {})
            df.loc[df['SENDER'] == "U"+str(SENDER), 'spec'] = cur_speciality #send cur_speciality to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
            buttons = [Button.inline(group, data=data) for data, group in group_items.items()]
            buttons.append(Button.inline("Back", data=b"back"))
            button_per_r = 4
            button_rows = button_grid(buttons, button_per_r)
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
            await event.answer('Specialitatea a fost selectata!')

#group click event handle
@client.on(events.CallbackQuery())
async def group_callback(event):
    global df, cur_group
    sender = await event.get_sender()
    SENDER = sender.id
    if event.data == b"back":
        await event.answer()
        await client.edit_message(SENDER, event.message_id, "Alege specialitea:", parse_mode="HTML", buttons=button_rows_spec)
    csv_spec = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'spec'])[0]
    cur_speciality = csv_spec
    group_items = group_list.get(cur_speciality, {})
    if event.data in group_items:
        cur_group = group_items.get(event.data).replace(" ", "")
        if cur_group:
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
                print(curr_time_logs() + "New user! - " + "U"+str(SENDER))

            #updates the current group
            df.loc[df['SENDER'] == "U"+str(SENDER), 'group'] = cur_group #send cur_group to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df

            print(curr_time_logs() + df.loc[df['SENDER'] == "U"+str(SENDER)])

            text = f"Grupa ta este: {cur_group}"
            await event.answer('Grupa a fost selectata!')
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")

#extract all users with notifications on
async def send_curr_course_users(df, week_day, is_even):
    users_with_notification_on = df.loc[df['noti'] == 'on', 'SENDER'].values
    tasks = []
    for user in users_with_notification_on:
        sender = int(user[1:])
        csv_gr = df.loc[df['SENDER'] == "U"+str(sender), 'group'].values[0]
        task = asyncio.create_task(send_curr_course(week_day, csv_gr, is_even, sender))
        tasks.append(task)
    await asyncio.gather(*tasks)

#send the next course to users with notifications on
async def send_curr_course(week_day, csv_gr, is_even, sender):
    #current time
    current_time = datetime.datetime.now()
    current_time = current_time + datetime.timedelta(hours=3)
    current_time = datetime.datetime.strptime(str(current_time).split(" ")[1][:-7], "%H:%M:%S")
    #next course time index
    for course_index, hour in enumerate(hours):
        course_time = datetime.datetime.strptime(hour[0].split(" - ")[0], "%H:%M")
        if (course_time - datetime.timedelta(minutes=15)).time() > current_time.time():
            break

    #15 min before the next course
    time_before_course = course_time - datetime.timedelta(minutes=15)
    
    #if seconds is negative
    if (time_before_course - current_time).total_seconds() < 1:
        print(curr_time_logs() + "waiting for positive - 01:00:00")
        await asyncio.sleep(3600)
        await send_curr_course(week_day, csv_gr, is_even, sender)
    else:
        print(curr_time_logs() + "waiting for next course - " + str((time_before_course - current_time)))
        await asyncio.sleep((time_before_course - current_time).total_seconds())
        #send the schedule
        print(curr_time_logs() + f"send schedule to U{sender} at {time_before_course.strftime('%H:%M')}")
        next_course = print_next_course(week_day, csv_gr, is_even, course_index)
        if next_course != "":
            await client.send_message(sender, "\nPerechea urmatoare:" + next_course, parse_mode="HTML")
        await send_curr_course(week_day, csv_gr, is_even, sender)

async def send_schedule_tomorrow(df):
    while True:
        now = datetime.datetime.now()
        now = now + datetime.timedelta(hours=3)
        if now.hour == 20 and now.minute == 0:
            users_with_notification_on = df.loc[df['noti'] == 'on', 'SENDER'].values
            for user in users_with_notification_on:
                sender = int(user[1:])
                try:
                    await client.send_message(sender, mainee(sender), parse_mode="HTML")
                    print(curr_time_logs() + f"send sch tommor to {sender}")
                except Exception as e:
                    print(curr_time_logs() + f"Error sending sch tommor to {sender}: {e}")
        await asyncio.sleep(60)

### MAIN
if __name__ == '__main__':
    print(curr_time_logs() + "Bot Started!")
    #cProfile.run('aaaaa(week_day, cur_group, is_even)', sort='tottime')
    loop = client.loop
    loop.create_task(send_curr_course_users(df, week_day, is_even))
    loop.create_task(send_schedule_tomorrow(df))
    client.run_until_disconnected()
