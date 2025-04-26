import asyncio
import pandas as pd
import numpy as np
import datetime
import pytz
import os

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import handlers.db as db
from functions import button_grid, send_logs, print_next_course, is_rate_limited, format_id

moldova_tz = pytz.timezone('Europe/Chisinau')

def register_admin_handlers(client, admins1, admins2):
    #/admin_help admin
    @client.on(events.NewMessage(pattern='/admin_help'))
    async def admin_help(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1 and format_id(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Admin commands:\n"
        text += "/stats - show statistics\n"
        text += "/backup - manual database backup\n"
        text += "/message - send a message to users\n"
        text += "/debug_next - debug print next course\n"
        text += "/ban - ban a user\n"
        text += "/unban - unban a user\n"
        text += "/list_ban - show banned users\n"
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /admin_help", 'info')
    
    #/stats admin
    @client.on(events.NewMessage(pattern='/stats')) 
    async def statsss(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1 and format_id(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /stats - no acces", "info")
            return
        
        users_with_groups = db.get_all_users_without('group_n', 'none')
        
        group_counts = users_with_groups['group_n'].value_counts().to_dict()
        
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
        
        total_users = db.get_user_count()
        users_with_groups_count = len(users_with_groups)
        users_with_notifications = len(db.get_all_users_with('noti', 'on'))
        users_with_subgroups = len(db.get_all_users_without('subgrupa', 0))
        
        text += f"📈 Summary:\n"
        text += f"  • Total users: {total_users}\n"
        text += f"  • Total users with groups: {users_with_groups_count}\n"
        text += f"  • Users with notifications: {users_with_notifications}\n"
        text += f"  • Users with selected sub-group: {users_with_subgroups}\n"
            
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /stats", "info")

    #/message admin
    @client.on(events.NewMessage(pattern='/message'))
    async def message_command(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
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
        global to_who, useridd, when, text, input_step, media_path
        useridd = 0
        to_who = int(data[2])
        input_step = 1
        media_path = None
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
            global input_step, useridd, when, text, media_path
            user_input = event.text

            if input_step == 1 and to_who == 4:
                useridd = int(user_input)
                input_step = 2
                await client.send_message(SENDER, "Please enter the time in HH:MM format or \"Now\":")
            elif input_step == 2:
                when = user_input
                input_step = 3
                await client.send_message(SENDER, "Send your message (text or attach image/file with caption):")
            elif input_step == 3:
                # Check if there's media attached
                has_media = event.media is not None
                
                if has_media:
                    try:
                        # Download the media
                        media_path = await event.download_media("temp/")
                        text = event.text  # Caption becomes the text
                    except Exception as e:
                        send_logs(f"Error downloading media: {e}", 'error')
                        await client.send_message(SENDER, f"Error with media: {e}")
                        return
                else:
                    text = user_input
                    media_path = None
                
                client.remove_event_handler(handle_input, events.NewMessage(from_users=SENDER))

                summary = f"\nSend to: {recipient_dict.get(to_who)}"
                if useridd != 0:
                    summary += f"\nUser ID: {useridd}"
                summary += f"\nTime: {when}"
                
                if media_path:
                    summary += f"\nMessage with media: \n{text}"
                else:
                    summary += f"\nMessage: \n{text}"
                
                await client.send_message(SENDER, summary)
                
                buttons = button_grid([Button.inline("Yes", data=b"yes"), Button.inline("No", data=b"no")], 2)
                await client.send_message(SENDER, "Send the message?", buttons=buttons)

                @client.on(events.CallbackQuery())
                async def confirmation_callback(event):
                    global to_who, when, useridd, text, media_path
                    sender = await event.get_sender()
                    SENDER = sender.id
                    if event.data == b"yes":
                        try:
                            await event.answer("Scheduling message...")
                            await client.edit_message(SENDER, event.message_id, "Message scheduled successfully!")
                            await send_mess(to_who, when, useridd)
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(yes): {e}", 'error')
                    elif event.data == b"no":
                        try:
                            await event.answer("Canceling...")
                            await client.edit_message(SENDER, event.message_id, "Message sending canceled.")
                            # Clean up media file if exists
                            if media_path and os.path.exists(media_path):
                                os.remove(media_path)
                                send_logs(f"Removed temp file: {media_path}", 'info')
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(no): {e}", 'error')
                    client.remove_event_handler(confirmation_callback, events.CallbackQuery())

    #send the custom message
    async def send_mess(to_who, when, useridd):
        global text, media_path
        
        now = datetime.datetime.now(moldova_tz).time()
        current_time = datetime.datetime.strptime(str(now)[:-7], "%H:%M:%S")
        if when == "Now":
            scheduled = current_time
        else:
            scheduled = datetime.datetime.strptime(when, "%H:%M")
        
        try:
            if to_who == 1:
                all_users = db.get_all_users_with('SENDER', 'U500303890')
            elif to_who == 2:
                all_users = db.get_all_users_with('group_n', 'TI-241')
                send_logs("Sending to TI-241", 'info')
            elif to_who == 3:
                all_users = db.get_all_users_with('noti', '1')
                send_logs("Sending to notifon users", 'info')
            elif to_who == 4:
                all_users = db.get_all_users_with('SENDER', 'U'+str(useridd))
                send_logs("Sending to " + 'U'+str(useridd), 'info')
            elif to_who == 5:
                all_users = db.get_all_users()
                send_logs("Sending to everyone", 'info')
            else:
                send_logs("No users to send a message", 'info')
                return
                
            if len(all_users) == 0:
                send_logs("No users found to send message to", 'warning')
                return
        except Exception as e:
            send_logs(f"Error retrieving users for message: {e}", 'error')
            return
            
        if when != "Now":
            send_logs("waiting to send a message - " + str(scheduled - current_time), 'info')
            await asyncio.sleep((scheduled - current_time).total_seconds())
            
        for _, row in all_users.iterrows():
            user = row['SENDER']
            sender = int(user[1:])
            try:
                if media_path and os.path.exists(media_path):
                    # Send with media
                    await client.send_file(
                        sender,
                        media_path,
                        caption=text,
                        parse_mode="Markdown"
                    )
                else:
                    # Send text only
                    await client.send_message(sender, text, parse_mode="Markdown")
                send_logs("Send successful to " + user, 'info')
            except Exception as e:
                send_logs(f"Error sending message to {str(sender)}: {e}", 'error')
        
        # Clean up after sending
        if media_path and os.path.exists(media_path):
            os.remove(media_path)
            send_logs(f"Removed temp file: {media_path}", 'info')

    #/debug_next admin
    @client.on(events.NewMessage(pattern='/debug_next'))
    async def debugg(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        subgrupa = db.locate_field("U"+str(event.sender_id), 'subgrupa')
        if "U"+str(event.sender_id) not in admins1:
            await client.send_message(event.sender_id, "Nu ai acces!", parse_mode="HTML")
            return
        
        week_day = int((datetime.datetime.now(moldova_tz)).weekday())
        is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
        for i in range(1, 8):
            text = "Perechea urmatore: #" + str(i)
            text += print_next_course(week_day, 'TI-241', is_even, i, subgrupa)
            if text:
                await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /debug_next", 'info')
    
    #/backup admin
    @client.on(events.NewMessage(pattern='/backup')) 
    async def manual_backup(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) != "U500303890":
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            #file
            now = datetime.datetime.now(moldova_tz)
            timestamp = now.strftime("%Y%m%d")
            backup_filename = f"BD_backup_{timestamp}.sql"
            db.create_mysql_backup(backup_filename)
            db_length = db.get_user_count()

            #send
            await client.send_file(
                SENDER,
                backup_filename,
                caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {db_length} users"
            )

            #delete
            import os
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
            send_logs(f"Manual backup sent to {SENDER}", 'info')
        except Exception as e:
            send_logs(f"Error sending manual backup: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error sending backup: {str(e)}", parse_mode="HTML")
    
    #/logs admin
    @client.on(events.NewMessage(pattern='/logs'))
    async def logs(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            #file
            now = datetime.datetime.now(moldova_tz)
            logs_filename = "orarbot.log"
            backup_filename = f"orarbot_{now.strftime('%Y%m%d')}.log"
            with open(logs_filename, 'r') as original_file:
                with open(backup_filename, 'w') as backup_file:
                    backup_file.write(original_file.read())
            #send
            await client.send_file(
                SENDER,
                backup_filename,
                caption=f"Logs\n{now.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            #delete
            import os
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
            send_logs(f"Manual backup sent to {SENDER}", 'info')
        except Exception as e:
            send_logs(f"Error sending manual backup: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error sending backup: {str(e)}", parse_mode="HTML")

    # Dictionary to track users in ban process
    ban_users_waiting = {}
    
    #/ban a user(ban=1) and set ban_time 1 day
    @client.on(events.NewMessage(pattern='/ban'))
    async def ban_user_command(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Please enter the user ID(as int):"
        await client.send_message(SENDER, text)
        # Mark this user as waiting for a user ID to ban
        ban_users_waiting[SENDER] = True
        send_logs(format_id(SENDER) + " - initiated /ban command", 'info')
    
    # Handle user input for ban command
    @client.on(events.NewMessage())
    async def ban_user_input_handler(event):
        if event.text.startswith('/'):
            return
        sender = await event.get_sender()
        SENDER = sender.id
        
        # Check if this user is waiting to provide a user ID to ban
        if SENDER in ban_users_waiting and ban_users_waiting[SENDER]:
            useridd = event.text
            try:
                useridd = int(useridd)
                #dd-mm-yyyy/hh:mm:ss
                ban_time = datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)
                ban_time = ban_time.strftime("%d-%m-%y %H:%M:%S")
                db.update_user_field("U"+str(useridd), "ban", 1)
                db.update_user_field("U"+str(useridd), "ban_time", str(ban_time))
                await client.send_message(SENDER, f"User U{useridd} banned", parse_mode="HTML")
                send_logs(format_id(SENDER) + " - /ban - U"+str(useridd), 'info')
            except ValueError:
                await client.send_message(SENDER, "Invalid user ID!", parse_mode="HTML")
            except Exception as e:
                send_logs(f"Error banning user {useridd}: {str(e)}", 'error')
            finally:
                # Remove user from waiting list
                del ban_users_waiting[SENDER]
                # Return True to prevent other handlers from processing this message
                return True

    # Dictionary to track users in unban process
    unban_users_waiting = {}
    
    #/unban user
    @client.on(events.NewMessage(pattern='/unban'))
    async def unban_user_command(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Please enter the user ID(as int):"
        await client.send_message(SENDER, text)
        # Mark this user as waiting for a user ID to unban
        unban_users_waiting[SENDER] = True
        send_logs(format_id(SENDER) + " - initiated /unban command", 'info')
    
    # Handle user input for unban command
    @client.on(events.NewMessage())
    async def unban_user_input_handler(event):
        if event.text.startswith('/'):
            return
        sender = await event.get_sender()
        SENDER = sender.id
        
        # Check if this user is waiting to provide a user ID to unban
        if SENDER in unban_users_waiting and unban_users_waiting[SENDER]:
            useridd = event.text
            try:
                useridd = int(useridd)
                db.update_user_field("U"+str(useridd), "ban", 0)
                db.update_user_field("U"+str(useridd), "ban_time", '')
                await client.send_message(SENDER, f"User U{useridd} unbanned", parse_mode="HTML")
                send_logs(format_id(SENDER) + " - /unban - U"+str(useridd), 'info')
            except ValueError:
                await client.send_message(SENDER, "Invalid user ID!", parse_mode="HTML")
            except Exception as e:
                send_logs(f"Error unbanning user {useridd}: {str(e)}", 'error')
            finally:
                # Remove user from waiting list
                del unban_users_waiting[SENDER]
                # Return True to prevent other handlers from processing this message
                return True
    #/ban_list admin
    @client.on(events.NewMessage(pattern='/list_ban'))
    async def ban_list(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Banned users:\n"
        banned_users = db.get_all_users_with('ban', 1)
        if not banned_users.empty:
            for _, row in banned_users.iterrows():
                user_id = row['SENDER']
                ban_time = row['ban_time']
                text += f"{user_id} - {ban_time}\n"
        else:
            text += "No banned users"
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /ban_list", 'info')