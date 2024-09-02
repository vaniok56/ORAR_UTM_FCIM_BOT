# orar_utm_fcim_bot version 0.1
### changelog:
# adaugare mai multor comentarii
# improve la vizualizarea orarului
# implementare afisare saptamana aceasta si viitoare
# implementarea afisare ore
# adaugare comanda help
# adaugarea listei de grupe
# afisarea butoanelor mai eficienta

from telethon import TelegramClient, events
from telethon.tl.custom import Button

import configparser #read
import datetime
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

#zile
zile_sapt = {
    0 : "Luni",
    1 : "Marţi",
    2 : "Miercuri",
    3 : "Joi",
    4 : "Vineri",
    5 : "Sambata",
    6 : "Duminica"
}

#grupe
grupe = {
    b"ti241": "  TI-241  ",
    b"ti244": "  TI-244  ",
    b"ti242": "  TI-242  ",
    b"ti243": "  TI-243  ",
    b"ti245": "  TI-245  ",
    b"ti246": "  TI-246  ",
    b"ti247": "  TI-247  ",
    b"ti248": "  TI-248  ",
    b"fi241": "  FI-241  ",
    b"si243": "  SI-243  "
}

grupa = "  TI-241  "

#/start
@client.on(events.NewMessage(pattern='/(?i)start')) 
async def start(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Salut! In primul rand alege grupa - /alege_grupa \nPentru a afisa toate comenzile - /help"
    await client.send_message(SENDER, text, parse_mode="HTML")

#/help
@client.on(events.NewMessage(pattern='/(?i)help')) 
async def start(event):
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

#/ore
@client.on(events.NewMessage(pattern='/(?i)ore')) 
async def start(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Graficul de ore:\n"
    for i in range(0, 7):
        text += "\nPerechea: #" + str(i+1) + "\nOra : " + ''.join(ore[i]) + "\n"
        if i == 2 :
            text += "Pauza : " + "30 min\n"
        else:
            text += "Pauza : " + "15 min\n"
    await client.send_message(SENDER, text, parse_mode="HTML")

#/maine
@client.on(events.NewMessage(pattern='/(?i)maine')) 
async def time(event):
    week_day = int((datetime.datetime.today() + datetime.timedelta(days=1)).weekday()) #ziua saptamanii(maine) in nr (0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "\nGrupa " + grupa + "\nOrarul de maine(" + zile_sapt[week_day] +"):" + print_zi(week_day)
    await client.send_message(SENDER, text, parse_mode="HTML")

#/azi
@client.on(events.NewMessage(pattern='/(?i)azi')) 
async def time(event):
    week_day = int(datetime.datetime.today().weekday()) #ziua saptamanii(azi) in nr (0-6)
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "\nGrupa " + grupa + "\nOrarul de azi(" + zile_sapt[week_day] +"):" + print_zi(week_day)
    await client.send_message(SENDER, text, parse_mode="HTML")

#/sapt_cur
@client.on(events.NewMessage(pattern='/(?i)sapt_curenta')) 
async def time(event):
    para = datetime.datetime.today().isocalendar().week%2 #sapt para/imp(1/0)
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "\nGrupa " + grupa + "\nOrarul pe saptamana aceasta:" + print_sapt(para)
    await client.send_message(SENDER, text, parse_mode="HTML")

#/sapt_viit
@client.on(events.NewMessage(pattern='/(?i)sapt_viitoare')) 
async def time(event):
    para = datetime.datetime.today().isocalendar().week%2 #sapt para/imp(1/0)
    para = not para
    sender = await event.get_sender()
    SENDER = sender.id
    grupa = update_gr()
    text = "\nGrupa " + grupa + "\nOrarul pe saptamana viitoare:" + print_sapt(para)
    await client.send_message(SENDER, text, parse_mode="HTML")

def button_grid(butoane, butoane_rand):
    return [butoane[i:i + butoane_rand] for i in range(0, len(butoane), butoane_rand)]

#/alege grupa
@client.on(events.NewMessage(pattern='/(?i)alege_grupa')) 
async def time(event):
    sender = await event.get_sender()
    SENDER = sender.id
    text = "Alege grupa"
    butoane = [Button.inline(group, data=data) for data, group in grupe.items()]
    butoane_rand = 4
    button_rows = button_grid(butoane, butoane_rand)
    await client.send_message(SENDER, text, parse_mode="HTML", buttons=button_rows)

#button click event handle
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
def print_zi(week_day) :
    wb = openpyxl.load_workbook('orar.xlsx', data_only=True)
    orar = wb["Table 2"]
    curr_date = datetime.datetime.today() # data de azi
    para = curr_date.isocalendar().week%2 #saptamana para?
    grupe = [orar.cell(row=1,column=i).value for i in range(3,12)] #lista toate grupe
    col_gr = grupe.index(orar['A1'].value.replace(" ", "")) + 3 #coloana cu gupa selectata anterior
    row_start = 2 + (14 * week_day) #randul la prima pereche de azi

    orar_azi = []
    vazute = set() 
    #exporteaza toate perechile dintro zi intrun dataframe
    for i in range(row_start, row_start + 13):
        ora = getMergedCellVal(orar, orar.cell(row=i, column=2)) #ora
        if i%2 == para:
            if ora in vazute:
                continue  # skip
            vazute.add(ora)
            orar_azi.append(getMergedCellVal(orar, orar.cell(row=i, column=col_gr)))
        else: continue # skip

    #modifica formatarea pentru o afisare mai placuta
    for i in range(len(orar_azi)):
        orar_azi[i] = "<b>" + str(orar_azi[i]) + "</b>"
        if "None" in str(orar_azi[i]):
            orar_azi[i] = ""
        else: orar_azi[i] = "\nPerechea: #" + str(i+1) + "\n" + str(orar_azi[i]) + "\nOra : " + ''.join(ore[i]) + "\n"
    
    #converteaza orarul intr-un string
    orar_azi = "\n" + "".join(str(element) for element in orar_azi)
    
    wb.close()
    return orar_azi

#afisare orar pe saptamana
def print_sapt(para) :
    wb = openpyxl.load_workbook('orar.xlsx', data_only=True)
    orar = wb["Table 2"]
    grupe = [orar.cell(row=1,column=i).value for i in range(3,12)] #lista toate grupe
    col_gr = grupe.index(orar['A1'].value.replace(" ", "")) + 3 #coloana cu gupa selectata anterior
    row_start = 2 #randul la prima pereche de azi

    orar_sapt = ""
    for j in range(1, 6):
        orar_azi = []
        vazute = set() 
        #exporteaza toate perechile dintro zi intrun dataframe
        for i in range(row_start, row_start + 13):
            ora = getMergedCellVal(orar, orar.cell(row=i, column=2)) #ora
            if i%2 == para:
                if ora in vazute:
                    continue  # skip
                vazute.add(ora)
                orar_azi.append(getMergedCellVal(orar, orar.cell(row=i, column=col_gr)))
            else: continue

        #modifica formatarea pentru o afisare mai placuta
        for i in range(len(orar_azi)):
            orar_azi[i] = "<b>" + str(orar_azi[i]) + "</b>"
            if "None" in str(orar_azi[i]):
                orar_azi[i] = ""
            else: orar_azi[i] = "\nPerechea: #" + str(i+1) + "\n" + str(orar_azi[i]) + "\nOra : " + ''.join(ore[i]) + "\n"
        
        #converteaza orarul intr-un string
        orar_azi = "\n" + "".join(str(element) for element in orar_azi)
        wb.close()

        if str(orar_azi) == "":
            orar_sapt += "\n\n"
        else: 
            orar_sapt += "\n\n&emsp;&emsp;&emsp;&emsp;<b>" + zile_sapt[j-1] + ":</b>" + "\n" + orar_azi
        
        row_start += 14
    return orar_sapt

#editeaza grupa alesa in excell
def edit_grupa(grupa):
    wb = openpyxl.load_workbook('orar.xlsx', data_only=True)
    orar = wb["Table 2"]
    grupa.replace(" ", "")
    orar['A1'] = grupa
    wb.save('orar.xlsx')
    wb.close()

#scoate grupa selectata din excell
def update_gr():
    wb = openpyxl.load_workbook('orar.xlsx', data_only=True)
    orar = wb["Table 2"]
    grupa = orar['A1'].value
    grupa.replace(" ", "")
    wb.close()
    return grupa

### MAIN
if __name__ == '__main__':
    print("Bot Started!")
    client.run_until_disconnected()
