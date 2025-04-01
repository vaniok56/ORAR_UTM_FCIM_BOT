import asyncio
import pandas as pd
import numpy as np
import datetime
import pytz

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

from functions import button_grid, send_logs, print_next_course

moldova_tz = pytz.timezone('Europe/Chisinau')

def register_admin_handlers(client, df, admins1, admins2):
    #/admin_help admin
    @client.on(events.NewMessage(pattern='/(?i)admin_help'))
    async def admin_help(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if "U"+str(SENDER) not in admins1 and "U"+str(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Admin commands:\n"
        text += "/stats - show statistics\n"
        text += "/backup - manual database backup\n"
        text += "/message - send a message to users\n"
        text += "/debug_next - debug print next course\n"
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs("U"+str(SENDER) + " - /admin_help", 'info')
    
    #/stats admin
    @client.on(events.NewMessage(pattern='/(?i)stats')) 
    async def statsss(event):
        sender = await event.get_sender()
        SENDER = sender.id
        
        if "U"+str(SENDER) not in admins1 and "U"+str(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            send_logs("U"+str(SENDER) + " - /stats - no acces", "info")
            return
        
        users_with_groups = df[df['group'].notna() & (df['group'] != "")]
        
        group_counts = users_with_groups['group'].value_counts().to_dict()
        
        groups_by_year = {}
        categorized_groups = set()
        
        for group_name, count in group_counts.items():
            try:
                #TI-241 -> 24)
                year = int(group_name[-3:-1])
                
                if year not in groups_by_year:
                    groups_by_year[year] = {}
                
                groups_by_year[year][group_name] = count
                categorized_groups.add(group_name)
            except (ValueError, IndexError):
                pass
        
        text = "📊 Stats:\n\n"
        for year in sorted(groups_by_year.keys(), reverse=True):
            text += (f"🎓 Year {5-(year-20)}" if 20 <= year <= 24 else f"Year {year}")
            sorted_groups = sorted(groups_by_year[year].items(), key=lambda x: (-x[1], x[0]))
            text += f" - {len(sorted_groups)} groups, {sum(count for group, count in sorted_groups)} users\n"

            for group, count in sorted_groups:
                text += f"  • {group}: {count} users\n"
            text += "\n"
        
        other_groups = {g: c for g, c in group_counts.items() if g not in categorized_groups}
        
        if other_groups:
            text += "📋 Other groups:\n"
            for group, count in sorted(other_groups.items(), key=lambda x: (-x[1], x[0])):
                text += f"  • {group}: {count} users\n"
            text += "\n"
        
        total_users = len(df)
        users_with_groups_count = len(users_with_groups)
        users_with_notifications = len(df[df['noti'] == 'on'])
        users_with_subgroups = len(df[df['subgrupa'].astype(int) != 0])
        
        text += f"📈 Summary:\n"
        text += f"  • Total users: {total_users}\n"
        text += f"  • Total users with groups: {users_with_groups_count}\n"
        text += f"  • Users with notifications: {users_with_notifications}\n"
        text += f"  • Users with selected sub-group: {users_with_subgroups}\n"
            
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs("U"+str(SENDER) + " - /stats", "info")

    #/message admin
    @client.on(events.NewMessage(pattern='/(?i)message'))
    async def message_command(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if "U" + str(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
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

    #message callback
    @client.on(events.CallbackQuery())
    async def message_callback(event):
        sender = await event.get_sender()
        SENDER = sender.id
        data = event.data.decode('utf-8')
        
        if not data.startswith("to"):
            return
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
                    global to_who, when, useridd, text
                    sender = await event.get_sender()
                    SENDER = sender.id
                    if event.data == b"yes":
                        try:
                            await event.answer("Scheduling message...")
                            await client.edit_message(SENDER, event.message_id, "Message scheduled successfully!")
                            await send_mess(to_who, when, useridd, df)
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(yes): {e}", 'error')
                    elif event.data == b"no":
                        try:
                            await event.answer("Canceling...")
                            await client.edit_message(SENDER, event.message_id, "Message sending canceled.")
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(no): {e}", 'error')
                    client.remove_event_handler(confirmation_callback, events.CallbackQuery())

    #send the custom message
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

    #/debug_next admin
    @client.on(events.NewMessage(pattern='/(?i)debug_next'))
    async def debugg(event):
        subgrupa = list(df.loc[df['SENDER'] == "U"+str(event.sender_id), 'subgrupa'])[0]
        if "U"+str(event.sender_id) not in admins1:
            await client.send_message(event.sender_id, "Nu ai acces!", parse_mode="HTML")
            return
        sender = await event.get_sender()
        SENDER = sender.id
        week_day = int((datetime.datetime.now(moldova_tz)).weekday())
        is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
        for i in range(1, 8):
            text = "Perechea urmatore: #" + str(i)
            text += print_next_course(week_day, 'TI-241', is_even, i, subgrupa)
            if text:
                await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs("U"+str(SENDER) + " - /debug_next", 'info')
    
    #/backup admin
    @client.on(events.NewMessage(pattern='/(?i)backup')) 
    async def manual_backup(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if "U"+str(SENDER) != "U500303890":
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            #file
            now = datetime.datetime.now(moldova_tz)
            timestamp = now.strftime("%Y%m%d")
            backup_filename = f"BD_backup_{timestamp}.csv"
            import shutil
            shutil.copy2('BD.csv', backup_filename)

            #send
            await client.send_file(
                SENDER,
                backup_filename,
                caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {len(df)} users"
            )

            #delete
            import os
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
            send_logs(f"Manual backup sent to {SENDER}", 'info')
        except Exception as e:
            send_logs(f"Error sending manual backup: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error sending backup: {str(e)}", parse_mode="HTML")
