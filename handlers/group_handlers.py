import pandas as pd
import pytz

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

from functions import button_grid, send_logs, is_rate_limited

moldova_tz = pytz.timezone('Europe/Chisinau')

def register_group_handlers(client, df, years, specialties, group_list):
    if df.empty:
        send_logs("DataFrame is empty!", "error")
    #/alege_grupa
    @client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
    async def alege_grupaa(event):
        nonlocal df
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        text = "Alege anul:"
        year_butt = [Button.inline("  " + year + "  ", data=data) for data, year in years.items()]
        button_per_r = 4
        global button_rows_year
        button_rows_year = button_grid(year_butt, button_per_r)

        #if user is not in list, add it
        if "U"+str(SENDER) not in "U"+str(df['SENDER'].to_list()):
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
        await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows_year)
        
    #year click event handle
    @client.on(events.CallbackQuery())
    async def year_callback(event):
        nonlocal df
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
                send_logs("U"+str(SENDER) + " - /alege_grupa year - " + cur_year, "info")

    #speciality click event handle
    @client.on(events.CallbackQuery())
    async def speciality_callback(event):
        nonlocal df
        sender = await event.get_sender()
        SENDER = sender.id
        year = int(list(df.loc[df['SENDER'] == "U"+str(SENDER), 'year'])[0])
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
                send_logs("U"+str(SENDER) + " - /alege_grupa spec - " + cur_speciality, "info")

    #group click event handle
    @client.on(events.CallbackQuery())
    async def group_callback(event):
        nonlocal df
        sender = await event.get_sender()
        SENDER = sender.id
        cur_speciality = list(df.loc[df['SENDER'] == "U"+str(SENDER), 'spec'])[0]
        year = int(list(df.loc[df['SENDER'] == "U"+str(SENDER), 'year'])[0])
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
                await alege_subgrupa(event)
    
    #/alege_subgrupa
    @client.on(events.NewMessage(pattern='/(?i)alege_subgrupa'))
    async def alege_subgrupa(event):
        nonlocal df
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        text = "Alege subgrupa:" # -1/1/deselect(0)
        subgrupa_butt = [Button.inline("   1   ", data=b"sub1"),
                        Button.inline("   2   ", data=b"sub2"),
                        Button.inline("Deselecteaza", data=b"sub0"),
        ]
        button_per_r = 2
        button_rows = button_grid(subgrupa_butt, button_per_r)
        await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)

    #subgrupa click event handle
    @client.on(events.CallbackQuery())
    async def subgrupa_callback(event):
        nonlocal df
        sender = await event.get_sender()
        SENDER = sender.id
        if event.data == b"sub0":
            df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'] = 0
            df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
            await event.answer('Subgrupa a fost deselectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa a fost deselectata!", parse_mode="HTML")
            send_logs("U"+str(SENDER) + " - /alege_subgrupa - deselect(0)", "info")
        elif event.data == b"sub1":
            df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'] = 1
            df.to_csv('BD.csv', encoding='utf-8', index=False)
            await event.answer('Subgrupa 1 a fost selectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa 1 a fost selectata!", parse_mode="HTML")
            send_logs("U"+str(SENDER) + " - /alege_subgrupa - 1", "info")
        elif event.data == b"sub2":
            df.loc[df['SENDER'] == "U"+str(SENDER), 'subgrupa'] = 2
            df.to_csv('BD.csv', encoding='utf-8', index=False)
            await event.answer('Subgrupa 2 a fost selectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa 2 a fost selectata!", parse_mode="HTML")
            send_logs("U"+str(SENDER) + " - /alege_subgrupa - 2", "info")
