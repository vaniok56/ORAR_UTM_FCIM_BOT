import pytz

from telethon import events, functions, types
from telethon.tl.custom import Button

import handlers.db as db
from functions import button_grid, simu_button, send_logs, is_rate_limited, format_id
from localization import get_text, get_user_lang

moldova_tz = pytz.timezone('Europe/Chisinau')

temp_selection = {}

# Helper to get user lang
def _get_lang(SENDER):
    return get_user_lang(format_id(SENDER))

# Helper to get user id and lang
async def _get_sender_id_and_lang(event):
    sender = await event.get_sender()
    SENDER = sender.id
    lang = _get_lang(SENDER)
    return SENDER, lang

def register_group_handlers(client, years, specialties, group_list):

    def menu_context(event, phase):
        context = temp_selection.get(event.sender_id)
        if context and context.get("message_id") == event.message_id and context.get("phase") == phase:
            return context
        return None

    async def reset_menu(event, lang):
        context = temp_selection.get(event.sender_id)
        if context and context.get("message_id") == event.message_id:
            temp_selection.pop(event.sender_id, None)
        await event.answer(get_text(lang, "group_error_missing"), alert=True)
        await client.send_message(event.sender_id, get_text(lang, "error_no_group"))

    #choose_gr button
    @client.on(events.CallbackQuery(data=b"select_group"))
    async def select_group_callback(event):
        sender = await event.get_sender()
        SENDER = sender.id
        await event.delete()
        await alege_grupaa(event)

    #/choose_gr
    @client.on(events.NewMessage(pattern='/choose_gr|Alege grupa 🎓|Choose group 🎓|Выбрать группу 🎓')) 
    async def alege_grupaa(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        temp_selection.pop(SENDER, None)
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        
        # Remove keyboard buttons
        await client.send_message(SENDER, get_text(lang, "group_selecting"), buttons=Button.clear())

        await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
        text = get_text(lang, "group_choose_year")
        year_butt = [
            Button.inline("  " + year + "  ", data=b"group_year_" + data)
            for data, year in years.items()
            if group_list.get(year.strip())
        ]
        button_per_r = 4
        button_rows_year = button_grid(year_butt, button_per_r)

        #if user is not in list, add it
        if not db.is_user_exists(format_id(SENDER)):
            result = db.add_new_user(format_id(SENDER))
            if result:
                send_logs("New user! - " + format_id(SENDER), 'info')
                
            else:
                send_logs("Failed to add new user! - " + format_id(SENDER), 'error')
                await client.send_message(SENDER, get_text(lang, "group_add_error"), parse_mode="HTML")
                return
        if year_butt:
            message = await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows_year)
            temp_selection[SENDER] = {"message_id": message.id, "phase": "year"}
        else:
            await client.send_message(SENDER, get_text(lang, "group_year_unavailable"), parse_mode="HTML")
        
        
    #year click event handle
    @client.on(events.CallbackQuery(pattern=rb"^group_year_"))
    async def year_callback(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        context = menu_context(event, "year")
        value = years.get(event.data.removeprefix(b"group_year_"))
        if not context or not isinstance(value, str):
            await reset_menu(event, lang)
            return
        cur_year = value.strip()

        if cur_year:
            text = get_text(lang, "group_choose_spec", year=cur_year)
            spec_items = specialties.get(cur_year, {})
            if not spec_items:
                await reset_menu(event, lang)
                return
            spec_butt = [Button.inline(spec, data=b"group_spec_" + data) for data, spec in spec_items.items()]
            button_per_r = 4
            button_rows = button_grid(spec_butt, button_per_r)
            try:
                await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
                context.update(year=cur_year, phase="specialty")
                await event.answer(get_text(lang, "group_year_selected"))
                send_logs(format_id(SENDER) + " - /choose_gr year - " + cur_year, "info")
            except Exception as e:
                await event.answer(get_text(lang, "group_year_unavailable"))
                send_logs(f"Error editing message for {SENDER} selecting year {cur_year}: {e}", "error")

    #speciality click event handle
    @client.on(events.CallbackQuery(pattern=rb"^group_spec_"))
    async def speciality_callback(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        context = menu_context(event, "specialty")
        year = context.get('year') if context else None
        spec_items = specialties.get(str(year), {})
        value = spec_items.get(event.data.removeprefix(b"group_spec_"))
        if not isinstance(value, str):
            await reset_menu(event, lang)
            return
        cur_speciality = value.strip()
        
        if cur_speciality:
            text = get_text(lang, "group_choose_group", spec=cur_speciality)
            group_items = group_list.get(str(year), {})
            group_items = group_items.get(cur_speciality + str(year), {})
            if not group_items:
                await reset_menu(event, lang)
                return
            context.update(speciality=cur_speciality, phase="group")
            group_butt = [Button.inline(group, data=b"group_pick_" + data) for data, group in group_items.items()]
            button_per_r = 4
            button_rows = button_grid(group_butt, button_per_r)
            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML", buttons=button_rows)
            await event.answer(get_text(lang, "group_spec_selected"))
            send_logs(format_id(SENDER) + " - /choose_gr spec - " + cur_speciality, "info")

    #group click event handle
    @client.on(events.CallbackQuery(pattern=rb"^group_pick_"))
    async def group_callback(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        user_context = menu_context(event, "group") or {}
        cur_speciality = user_context.get('speciality')
        year = user_context.get('year')
        
        # Check if cur_speciality and year are valid
        if not cur_speciality or not year or cur_speciality == 'none':
            await reset_menu(event, lang)
            send_logs(f"U{SENDER} - group selection failed - Missing specialty or year", "warning")
            return
            
        group_items = group_list.get(str(year), {})
        key = cur_speciality + str(year)
        group_items = group_items.get(key, {})
        value = group_items.get(event.data.removeprefix(b"group_pick_"))
        if not isinstance(value, str) or not specialties.get(str(year), {}).get(f"{cur_speciality.lower()}{year}".encode()):
            await reset_menu(event, lang)
            return
        cur_group = value.strip()
        
        if cur_group:
            temp_selection.pop(SENDER, None)
            #updates all fields in db
            db.update_user_field(format_id(SENDER), 'group_n', cur_group)
            db.update_user_field(format_id(SENDER), 'year_s', int(year))
            db.update_user_field(format_id(SENDER), 'spec', cur_speciality)

            send_logs(format_id(SENDER) + " - /choose_gr - " + cur_group, "info")

            text = get_text(lang, "group_selected", group=cur_group)
            await event.answer(get_text(lang, "group_group_selected"))

            bot_kb = [
                Button.text(get_text(lang, 'btn_today'), resize=True),
                Button.text(get_text(lang, 'btn_tomorrow'), resize=True),
                Button.text(get_text(lang, 'btn_current_week'), resize=True),
                Button.text(get_text(lang, 'btn_next_week'), resize=True),
                simu_button(),
            ]
            buttons_kb = button_grid(bot_kb, 2)

            await client.edit_message(SENDER, event.message_id, text, parse_mode="HTML")
            await client.send_message(SENDER, get_text(lang, "group_selecting_subgroup"), parse_mode="HTML", buttons=buttons_kb)

            await alege_subgrupa(event)
            notification_text = get_text(lang, "notif_prompt")
            notification_buttons = [
                Button.inline(get_text(lang, "notif_yes"), data=b"noti_on"),
                Button.inline(get_text(lang, "notif_no"), data=b"noti_off")
            ]
            await client.send_message(SENDER, notification_text, parse_mode="Markdown", buttons=notification_buttons)

    #/choose_subgr
    @client.on(events.NewMessage(pattern='/choose_subgr'))
    async def alege_subgrupa(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        await client(functions.messages.SetTypingRequest(
            peer=SENDER,
            action=types.SendMessageTypingAction()
        ))
        text = get_text(lang, "subgroup_choose")
        subgrupa_butt = [Button.inline("   1   ", data=b"sub1"),
                        Button.inline("   2   ", data=b"sub2"),
                        Button.inline(get_text(lang, "subgroup_deselect_btn"), data=b"sub0"),
        ]
        button_per_r = 2
        button_rows = button_grid(subgrupa_butt, button_per_r)
        await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)

    #subgrupa click event handle
    @client.on(events.CallbackQuery(pattern=lambda x: x in [b"sub0", b"sub1", b"sub2"]))
    async def subgrupa_callback(event):
        SENDER, lang = await _get_sender_id_and_lang(event)
        if event.data == b"sub0":
            db.update_user_field(format_id(SENDER), 'subgrupa', 0)
            await event.answer(get_text(lang, "subgroup_deselected"))
            await client.edit_message(SENDER, event.message_id, get_text(lang, "subgroup_deselected"), parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /choose_subgr - deselect(0)", "info")
        elif event.data == b"sub1":
            db.update_user_field(format_id(SENDER), 'subgrupa', 1)
            await event.answer(get_text(lang, "subgroup_1_selected"))
            await client.edit_message(SENDER, event.message_id, get_text(lang, "subgroup_1_selected"), parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /choose_subgr - 1", "info")
        elif event.data == b"sub2":
            db.update_user_field(format_id(SENDER), 'subgrupa', 2)
            await event.answer(get_text(lang, "subgroup_2_selected"))
            await client.edit_message(SENDER, event.message_id, get_text(lang, "subgroup_2_selected"), parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /choose_subgr - 2", "info")
