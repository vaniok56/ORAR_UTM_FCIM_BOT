import pandas as pd
import pytz

from telethon import TelegramClient, events, functions, types
from telethon.tl.custom import Button

import handlers.db as db
from functions import button_grid, send_logs, is_rate_limited, format_id

moldova_tz = pytz.timezone('Europe/Chisinau')

temp_selection = {}

def register_group_handlers(client, years, specialties, group_list):

    #alege_grupa button
    @client.on(events.CallbackQuery(data=b"select_group"))
    async def select_group_callback(event):
        sender = await event.get_sender()
        SENDER = sender.id
        await event.delete()
        await alege_grupaa(event)

    #/alege_grupa
    @client.on(events.NewMessage(pattern='/alege_grupa')) 
    async def alege_grupaa(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
        text = "Alege anul:"
        year_butt = [Button.inline("  " + year + "  ", data=data) for data, year in years.items()]
        button_per_r = 4
        button_rows_year = button_grid(year_butt, button_per_r)

        #if user is not in list, add it
        if not db.is_user_exists(format_id(SENDER)):
            result = db.add_new_user(format_id(SENDER))
            if result:
                send_logs("New user! - " + format_id(SENDER), 'info')
                
            else:
                send_logs("Failed to add new user! - " + format_id(SENDER), 'error')
                await client.send_message(SENDER, "Eroare la adaugarea utilizatorului! Te rog sa incerci din nou mai tarziu.", parse_mode="HTML")
                return
        await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows_year)
        
        
    #year click event handle
    @client.on(events.CallbackQuery())
    async def year_callback(event):
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
                if SENDER not in temp_selection:
                    temp_selection[SENDER] = {}
                temp_selection[SENDER]['year'] = cur_year
                await event.answer('Anul a fost selectat!')
                send_logs(format_id(SENDER) + " - /alege_grupa year - " + cur_year, "info")

    #speciality click event handle
    @client.on(events.CallbackQuery())
    async def speciality_callback(event):
        is_specialty_event = False
        for year_key, specs in specialties.items():
            if event.data in specs:
                is_specialty_event = True
                break
                
        if not is_specialty_event:
            return
        sender = await event.get_sender()
        SENDER = sender.id
        year = temp_selection.get(SENDER, {}).get('year')
        spec_items = specialties.get(str(year), {})
        if event.data in spec_items:
            cur_speciality = spec_items.get(event.data).replace(" ", "")
            if cur_speciality:
                text = f"Alege grupa pentru {cur_speciality}:"
                group_items = group_list.get(str(year), {})
                group_items = group_items.get(cur_speciality + str(year), {})
                temp_selection[SENDER]['speciality'] = cur_speciality
                spec_butt = [Button.inline(group, data=data) for data, group in group_items.items()]
                button_per_r = 4
                button_rows = button_grid(spec_butt, button_per_r)
                await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
                await event.answer('Specialitatea a fost selectata!')
                send_logs(format_id(SENDER) + " - /alege_grupa spec - " + cur_speciality, "info")

    #group click event handle
    @client.on(events.CallbackQuery())
    async def group_callback(event):
        is_group_event = False
        for year_key, year_groups in group_list.items():
            for spec_key, groups in year_groups.items():
                if event.data in groups:
                    is_group_event = True
                    break
            if is_group_event:
                break
                
        if not is_group_event:
            return
        sender = await event.get_sender()
        SENDER = sender.id
        cur_speciality = temp_selection.get(SENDER, {}).get('speciality')
        year = temp_selection.get(SENDER, {}).get('year')
        
        # Check if cur_speciality and year are valid
        if not cur_speciality or not year or cur_speciality == 'none':
            await event.answer('Eroare: Lipsește specializarea sau anul. Te rog să începi din nou.')
            send_logs(f"U{SENDER} - group selection failed - Missing specialty or year", "warning")
            return
            
        group_items = group_list.get(str(year), {})
        key = cur_speciality + str(year)
        group_items = group_items.get(key, {})
        
        if event.data in group_items:
            cur_group = group_items.get(event.data).replace(" ", "")
            if cur_group:
                #updates all fields in db
                db.update_user_field(format_id(SENDER), 'group_n', cur_group)
                db.update_user_field(format_id(SENDER), 'year_s', int(year))
                db.update_user_field(format_id(SENDER), 'spec', cur_speciality)

                send_logs(format_id(SENDER) + " - /alege_grupa - " + cur_group, "info")

                text = f"Grupa ta este: {cur_group}"
                await event.answer('Grupa a fost selectata!')
                await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
                await alege_subgrupa(event)
                notification_text = "Dorești să primești notificări înainte de fiecare pereche?"
                notification_buttons = [
                    Button.inline("✅ Da", data=b"on"),
                    Button.inline("❌ Nu", data=b"off")
                ]
                await client.send_message(SENDER, notification_text, parse_mode="Markdown", buttons=notification_buttons)
    
    #/alege_subgrupa
    @client.on(events.NewMessage(pattern='/alege_subgrupa'))
    async def alege_subgrupa(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
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
        sender = await event.get_sender()
        SENDER = sender.id
        if event.data == b"sub0":
            db.update_user_field(format_id(SENDER), 'subgrupa', 0)
            await event.answer('Subgrupa a fost deselectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa a fost deselectata!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /alege_subgrupa - deselect(0)", "info")
        elif event.data == b"sub1":
            db.update_user_field(format_id(SENDER), 'subgrupa', 1)
            await event.answer('Subgrupa 1 a fost selectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa 1 a fost selectata!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /alege_subgrupa - 1", "info")
        elif event.data == b"sub2":
            db.update_user_field(format_id(SENDER), 'subgrupa', 2)
            await event.answer('Subgrupa 2 a fost selectata!')
            await client.edit_message(SENDER, event.message_id, "Subgrupa 2 a fost selectata!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /alege_subgrupa - 2", "info")
