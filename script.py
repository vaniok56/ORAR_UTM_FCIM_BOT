# orar_utm_fcim_bot version 0.5.1
### changelog:
# fixed group selector for multiple users

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import configparser # read
import datetime

from functions import print_day, print_sapt
from functions import cur_group, hours, week_days, is_even
from group_lists import group_list, specialties

import pandas as pd
import numpy as np
#import cProfile

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

#/start
@client.on(events.NewMessage(pattern="/(?i)start")) 
async def startt(event):
    global df
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Salut!\nIn primul rand alege grupa - /alege_grupa \nPentru a afisa toate comenzile - /help"
    buttons_in_row = 2
    #bot_kb.append(types.KeyboardButtonSimpleWebView("Orar pdf🥱", "https://fcim.utm.md/procesul-de-studii/orar/#toggle-id-2-closed",))
    button_rows = button_grid(bot_kb, buttons_in_row)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)

    #add the user to users
    if "U"+str(SENDER) not in "U"+str(df['SENDER'].to_list()):
        data =  {'SENDER' : ["U"+str(SENDER)],
                 'group' : [""],
                 'spec' : [""],
                 'year' : [""]}
        new_dat = pd.DataFrame(data)
        df = pd.concat([df, new_dat])
        df.to_csv('BD.csv', encoding='utf-8', index=False)

#/help
@client.on(events.NewMessage(pattern='/(?i)help')) 
async def helpp(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text  = "/start - start\n"
    text  = "/help - toate comenzile\n"
    text += "/azi - orarul de azi\n"
    text += "/maine - orarul de maine\n"
    text += "/ore - orarul orelor(perechi + pauze)\n"
    text += "/alege_grupa - alegerea grupei\n"
    text += "/sapt_curenta - orar pe saptamana curenta\n"
    text += "/sapt_viitoare - orar pe saptamana viitoare\n"
    #text += "/noti - NOT IMPLEMENTED notificari on/off\n"
    #text += "/alege - NOT IMPLEMENTED orar pe o zi concreta cu butoane\n"
    #text += "/sesiuni - NOT IMPLEMENTED orarul sesiunilor\n"
    await client.send_message(SENDER, text, parse_mode="HTML")

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
            #send the schedule
            day_sch = print_day(week_day, cur_group)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de maine(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi azi(" + week_days[week_day] +")"
            await client.send_message(SENDER, text, parse_mode="HTML")
    except Exception as error:
        print("An exception occurred:", error)
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
            day_sch = print_day(week_day, cur_group)
            if day_sch != "":
                text = "\n\nGrupa - " + cur_group + "\nOrarul de azi(" + week_days[week_day] +"):\n" + day_sch
            else: 
                text = "\nGrupa - " + cur_group + "\nNu ai perechi azi(" + week_days[week_day] +")"
            await client.send_message(SENDER, text, parse_mode="HTML")
    except Exception as error:
        print("An exception occurred:", error)
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
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana aceasta:" + print_sapt(is_even, cur_group)
            await client.send_message(SENDER, text, parse_mode="HTML")
    except Exception as error:
        print("An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")

#/sapt_viit
@client.on(events.NewMessage(pattern='/(?i)sapt_viitoare')) 
async def sapt_viit(event):
    global df, cur_group, is_even
    is_even = not is_even
    sender = await event.get_sender()
    SENDER = sender.id

    try:
        csv_gr = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'group'])[0]
        cur_group = csv_gr
        if cur_group == "":
            raise ValueError('no gr')
        else: 
            text = "\nGrupa - " + cur_group + "\nOrarul pe saptamana viitoare:" + print_sapt(is_even, cur_group)
            await client.send_message(SENDER, text, parse_mode="HTML")
    except Exception as error:
        print("An exception occurred:", error)
        await client.send_message(SENDER, "Inca nu ai ales grupa.\n/alege_grupa", parse_mode="HTML")

def button_grid(buttons, butoane_rand):
    grid = []
    row = []
    for button in buttons:
        if button.text == "Back":
            if row:
                grid.append(row)
            row = [button]
        else:
            row.append(button)
        if len(row) == butoane_rand:
            grid.append(row)
            row = []
    if row:
        grid.append(row)
    return grid

#/alege_grupa
@client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
async def alege_grupaa(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Alege specialitea"
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
            text = f"Alege grupa pentru {cur_speciality}"
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
        await client.edit_message(SENDER, event.message_id, "Alege specialitea", parse_mode="HTML", buttons=button_rows_spec)
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
                        'year' : [""]}
                new_dat = pd.DataFrame(data)
                df = pd.concat([df, new_dat]) 
                df.to_csv('BD.csv', encoding='utf-8', index=False)

            #updates the current group
            df.loc[df['SENDER'] == "U"+str(SENDER), 'group'] = cur_group #send cur_group to df
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df

            print(df.loc[df['SENDER'] == "U"+str(SENDER)])

            text = f"Grupa ta este: {cur_group}"
            await event.answer('Grupa a fost selectata!')
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")

### MAIN
if __name__ == '__main__':
    print("Bot Started!")
    #cProfile.run('print_sapt(is_even, cur_group)', sort='tottime')
    client.run_until_disconnected()
