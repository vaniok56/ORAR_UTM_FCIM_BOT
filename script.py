# Telethon utility
from telethon import TelegramClient, events
from telethon.tl.custom import Button

import configparser # Library for reading from a configuration file, # pip install configparser
import datetime # Library that we will need to get the day and time, # pip install datetime
import openpyxl # excel read library
import datetime

#### Access credentials
config = configparser.ConfigParser() # Define the method to read the configuration file
config.read('config.ini') # read config.ini file

api_id = config.get('default','api_id') # get the api id
api_hash = config.get('default','api_hash') # get the api hash
BOT_TOKEN = config.get('default','BOT_TOKEN') # get the bot token

# Create the client and the session called session_master. We start the session as the Bot (using bot_token)
client = TelegramClient('sessions/session_master', api_id, api_hash).start(bot_token=BOT_TOKEN)

#ore
ore =   [
    ["8:00 - 9:30"],
    ["9:45 - 11:15"],
    ["11:30 - 13:00"],
    ["13:30 - 15:00"],
    ["15:15 - 16:45"],
    ["17:00 - 18:30"],
    ["18:45 - 20:15"]
]

zile_sapt = {
    0 : "Luni",
    1 : "Marti",
    2 : "Miercuri",
    3 : "Joi",
    4 : "Vineri",
    5 : "Sambata",
    6 : "Duminica"
}

grupe = {
    b"41": "TI-241",
    b"42": "TI-242",
    b"43": "TI-243",
    b"44": "TI-244",
    b"45": "TI-245"
}

grupa = "TI-241"

#/start
@client.on(events.NewMessage(pattern='/(?i)start')) 
async def start(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Salut!"
    await client.send_message(SENDER, text, parse_mode="HTML")

#/maine
@client.on(events.NewMessage(pattern='/(?i)maine')) 
async def time(event):
    week_day = int((datetime.datetime.today() + datetime.timedelta(days=1)).weekday()) #ziua saptamanii(maine) in nr (0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "Grupa " + grupa + "\nOrarul de maine(" + zile_sapt[week_day] +"):\n\n" + printare(week_day)
    await client.send_message(SENDER, text, parse_mode="HTML")

#/azi
@client.on(events.NewMessage(pattern='/(?i)azi')) 
async def time(event):
    week_day = int(datetime.datetime.today().weekday()) #ziua saptamanii(azi) in nr (0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "Grupa " + grupa + "\nOrarul de azi(" + zile_sapt[week_day] +"):\n\n" + printare(week_day)
    await client.send_message(SENDER, text, parse_mode="HTML")




#/alege grupa
@client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
async def time(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Alege grupa(momentan nu lucreaza)"
    butoane = [Button.inline(group, data=data) for data, group in grupe.items()]
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=butoane)
    
@client.on(events.CallbackQuery())
async def callback(event):
    grupa = grupe.get(event.data)
    if grupa:
        edit_grupa(grupa)
        sender = await event.get_sender()
        SENDER = sender.id
        text = f"Grupa ta este: {grupa}"
        await client.send_message(SENDER, text, parse_mode="HTML")
        
#afisiaza value din cell chiar daca e merged cell
def getMergedCellVal(sheet, cell):
    rng = [s for s in sheet.merged_cells.ranges if cell.coordinate in s]
    return sheet.cell(rng[0].min_row, rng[0].min_col).value if len(rng)!=0 else cell.value

#afisare orar pe zi
def printare(week_day) :
    wb = openpyxl.load_workbook('orar test.xlsx', data_only=True)
    orar = wb["Table 2"]
    curr_date = datetime.datetime.today() # data de azi
    para = int(curr_date.isocalendar().week%2) #saptamana para?
    grupe = [orar.cell(row=1,column=i).value for i in range(3,8)] #lista toate grupe
    col_gr = grupe.index(orar['A1'].value) + 3 #coloana cu gupa selectata anterior
    row_start = 2 + (14 * week_day) + int(para) #randul la prima pereche de azi

    orar_azi = []
    vazute = set() 
    for i in range(row_start, row_start + 13):
        ora = getMergedCellVal(orar, orar.cell(row=i, column=2)) #ora
        if ora in vazute:
            continue  # skip
        vazute.add(ora)
        orar_azi.append(getMergedCellVal(orar, orar.cell(row=i, column=col_gr)))

    # orar_azi = [getMergedCellVal(orar, orar.cell(row=i,column=col_gr)) for i in range(row_start, row_start+13)] #orarul pe ziua de azi
    # orar_azi = orar_azi[::2] #skip la perechi din alta sapt(para/impara)

    for i in range(len(orar_azi)):
        orar_azi[i] = "<b>" + str(orar_azi[i]) + "</b>"
        if "None" in str(orar_azi[i]):
            orar_azi[i] = "<br>-----</br>"
        else: orar_azi[i] = "Perechea: #" + str(i+1) + "\n" + str(orar_azi[i]) + "\nOra : " + ''.join(ore[i])
    orar_azi = "\n\n".join(str(element) for element in orar_azi)
    
    wb.close()
    return orar_azi

def edit_grupa(grupa):
    wb = openpyxl.load_workbook('orar test.xlsx', data_only=True)
    orar = wb["Table 2"]
    orar['A1'] = grupa
    wb.save('orar test.xlsx')
    wb.close()

def update_gr():
    wb = openpyxl.load_workbook('orar test.xlsx', data_only=True)
    orar = wb["Table 2"]
    grupa = orar['A1'].value
    wb.close()
    return grupa

### MAIN
if __name__ == '__main__':
    print("Bot Started!")
    client.run_until_disconnected()
