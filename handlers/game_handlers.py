import asyncio
from telethon import events, types
from telethon.tl.custom import Button
from telethon.tl.types import InputMediaDice

import pandas as pd

from functions import button_grid, send_logs, is_rate_limited

def register_games_handlers(client, bot_kb, df):
    #/games menu
    @client.on(events.NewMessage(pattern='/(?i)games|Jocuri 🎮'))
    async def games_help(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        text = "Meniu jocuri\n"
        buttons = [
            Button.text('Slot 🎰', resize=True),
            Button.text('Baschet 🏀', resize=True),
            Button.text('Fotbal ⚽', resize=True),
            Button.text('Zar 🎲', resize=True),
            Button.text('Bowling 🎳', resize=True),
            Button.text('Darts 🎯', resize=True),
            Button.text('Înapoi 🔙', resize=True),
        ]
        button_rows = button_grid(buttons, 3)
        await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)
        send_logs("U"+str(SENDER) + " - /games", 'info')

    #back button
    @client.on(events.NewMessage(pattern='Înapoi 🔙'))
    async def back(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        #change the buttons back to the main menu
        buttons_in_row = 2
        button_rows = button_grid(bot_kb, buttons_in_row)
        await client.send_message(SENDER, "Meniu principal", parse_mode="HTML", buttons=button_rows)
        send_logs("U"+str(SENDER) + " - back", 'info')

    #/spin
    @client.on(events.NewMessage(pattern='/(?i)spin|Slot 🎰')) 
    async def spin(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        if check_enough_money(df, SENDER, 20) == False:
            await event.respond("❌ Nu ai destui bani ❌")
            return
        user_score -= 20
        save_score(df, SENDER, user_score)
        try:
            await event.respond("🎰 -20$ 🎰")
            dice_value = await send_dice(event, '🎰')
            
            current_score = get_score_change_spin(dice_value)
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)

            if current_score <= 0:
                result_text = "❌ Ai pierdut ❌"
            else:
                result_text = f"🎰 Ai castigat {current_score}$! 🎰"
            combo_text = get_combo_text(dice_value)
            text = f"Combinatia ta: {combo_text}\n" + f"{result_text}"
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(2)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /spin", 'info')
        except Exception as e:
            send_logs(f"Error in spin command for {str(SENDER)}: {e}", 'error')

    def get_score_change_spin(dice_value):
        if dice_value in (1, 22, 43):
            return 200
        elif dice_value in (16, 32, 48):
            return 100
        elif dice_value == 64:
            return 777
        else:
            return 0
    
    #/basketball
    @client.on(events.NewMessage(pattern='/(?i)basketball|Baschet 🏀'))
    async def basketball(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        if check_enough_money(df, SENDER, 20) == False:
            await event.respond("❌ Nu ai destui bani ❌")
            return
        user_score -= 20
        save_score(df, SENDER, user_score)
        try:
            await event.respond("🏀 -20$ 🏀")
            dice_value = await send_dice(event, '🏀')
            current_score = get_score_change_basketball(dice_value)
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)


            if dice_value in [4, 5]:
                text = f"🏀 Ai castigat {current_score}$! 🏀"
            else:
                text = "❌ Ai ratat! ❌"
            
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(4)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /basketball", 'info')
        except Exception as e:
            send_logs(f"Error in basketball command for {str(SENDER)}: {e}", 'error')

    def get_score_change_basketball(dice_value):
        if dice_value >= 4:
            return 60
        else:
            return 0
    
    #/football
    @client.on(events.NewMessage(pattern='/(?i)football|Fotbal ⚽'))
    async def football(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        if check_enough_money(df, SENDER, 20) == False:
            await event.respond("❌ Nu ai destui bani ❌")
            return
        user_score -= 20
        save_score(df, SENDER, user_score)
        try:
            await event.respond("⚽ -20$ ⚽")
            dice_value = await send_dice(event, '⚽')
            current_score = get_score_change_football(dice_value)
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)

            if dice_value in [3, 4, 5]:
                text = f"⚽ Ai castigat {current_score}$! ⚽"
            else:
                text = "❌ Ai ratat! ❌"
                
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(4)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /football", 'info')
        except Exception as e:
            send_logs(f"Error in football command for {str(SENDER)}: {e}", 'error')
    
    def get_score_change_football(dice_value):
        if dice_value in [3, 4, 5]:
            return 40
        else:
            return 0

    #/dice
    @client.on(events.NewMessage(pattern='/(?i)dice|Zar 🎲'))
    async def dice(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        try:
            dice_value = await send_dice(event, '🎲')
            current_score = dice_value * 5
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)
            
            text = f"🎲 Ai castigat {current_score}$! 🎲"
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(3.5)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /dice", 'info')
        except Exception as e:
            send_logs(f"Error in dice command for {str(SENDER)}: {e}", 'error')

    #/bowling
    @client.on(events.NewMessage(pattern='/(?i)bowling|Bowling 🎳'))
    async def bowling(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        if check_enough_money(df, SENDER, 20) == False:
            await event.respond("❌ Nu ai destui bani ❌")
            return
        user_score -= 20
        save_score(df, SENDER, user_score)
        try:
            await event.respond("🎳 -20$ 🎳")
            dice_value = await send_dice(event, '🎳')
            current_score = get_score_change_bowling(dice_value)
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)
            
            if dice_value == 6:
                text = f"🎳 STRIKE! Ai castigat {current_score}$ 🎳"
            elif dice_value == 1:
                text = f"❌ EPIC FAIL {current_score}$ ❌"
            elif dice_value == 2:
                text = "❌ Ai dat jos doar 1 ❌"
            else:
                text = f"❌ Ai dat jos doar {dice_value} ❌"
                
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(3)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /bowling", 'info')
        except Exception as e:
            send_logs(f"Error in bowling command for {str(SENDER)}: {e}", 'error')

    def get_score_change_bowling(dice_value):
        if dice_value == 6:
            return 200
        elif dice_value == 1:
            return -200
        else:
            return 0
    #/darts
    @client.on(events.NewMessage(pattern='/(?i)darts|Darts 🎯'))
    async def darts(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER, df):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        user_score = get_user_money(df, SENDER)
        if check_enough_money(df, SENDER, 20) == False:
            await event.respond("❌ Nu ai destui bani ❌")
            return
        user_score -= 20
        save_score(df, SENDER, user_score)
        try:
            await event.respond("🎯 -20$ 🎯")
            dice_value = await send_dice(event, '🎯')
            current_score = get_score_change_darts(dice_value)
            new_score = user_score + current_score
            save_score(df, SENDER, new_score)
            
            if dice_value == 6:
                text = f"🎯 Ai castigat {current_score}$ 🎯"
            elif dice_value == 1:
                text = f"❌ EPIC FAIL {current_score}$ ❌"
            elif dice_value == 5:
                text = f"🎯 Ai castigat {current_score}$ 🎯"
            else:
                text = "❌ Ai pierdut! ❌"
            
            text += f"\nDepozit: {new_score}$\n"

            await asyncio.sleep(2.5)
            await event.respond(text)
            send_logs("U"+str(SENDER) + " - game - /darts", 'info')
        except Exception as e:
            send_logs(f"Error in darts command for {str(SENDER)}: {e}", 'error')

    def get_score_change_darts(dice_value):
        if dice_value == 6:
            return 200
        elif dice_value == 1:
            return -200
        elif dice_value == 5:
            return 20
        else:
            return 0
    
def get_combo_text(dice_value):
    values = ["BAR", "🍇", "🍋", "7️⃣"]
    dice_value -= 1
    result = []
    for _ in range(3):
        result.append(values[dice_value % 4])
        dice_value //= 4
    return " - ".join(result)

def get_user_money(df, sender_id):
    user_score = list(df.loc[df['SENDER'] == "U"+str(sender_id), 'gamble'])[0]
    if (str(user_score) == "") or (str(user_score) == "NaN") or (str(user_score) == "nan"):
        user_score = 1000
        df.loc[df['SENDER'] == "U"+str(sender_id), 'gamble'] = 1000
        df.to_csv('BD.csv', encoding='utf-8', index=False) #save df
    user_score = int(user_score)
    return user_score

def check_enough_money(df, sender_id, bet):
    user_score = get_user_money(df, sender_id)
    if user_score < bet:
        return False
    return True

def save_score(df, sender_id, score):
    df.loc[df['SENDER'] == "U"+str(sender_id), 'gamble'] = score
    df.to_csv('BD.csv', encoding='utf-8', index=False) #save df

async def send_dice(event, emoji):
    try:
        dice_message = await event.respond(file=InputMediaDice(emoji))
        dice_value = dice_message.media.value
        return dice_value
    except Exception as e:
        send_logs(f"Error sending dice: {e}", 'error')