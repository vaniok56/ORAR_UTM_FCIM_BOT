import numpy as np 
import openpyxl # excel read library
import datetime
import pytz
moldova_tz = pytz.timezone('Europe/Chisinau')

time_zone = pytz.timezone('Europe/Chisinau')
#logs
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s.%(msecs)03d | [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[
                        logging.FileHandler("orarbot.log"),
                        logging.StreamHandler()
                    ])

logging.Formatter.converter = lambda *args: \
    datetime.datetime.now(time_zone).timetuple()

is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2

#hours
hours =   [
    ["8.00-9.30"],
    ["9.45-11.15"],
    ["11.30-13.00"],
    ["13.30-15.00"],
    ["15.15-16.45"],
    ["17.00-18.30"],
    ["18.45-20.15"]
]

#week days
week_days = {
    0 : "Luni",
    1 : "Marţi",
    2 : "Miercuri",
    3 : "Joi",
    4 : "Vineri",
    5 : "Sâmbătă",
    6 : "Duminica"
}

cur_group = "TI-241" #initialise current group
#open the excel files
schedule1 = openpyxl.load_workbook('orar1.xlsx', data_only=True)["Table 2"] #open the excel file 1
schedule2 = openpyxl.load_workbook('orar2.xlsx', data_only=True)["Table 2"] #open the excel file 2
schedule3 = openpyxl.load_workbook('orar3.xlsx', data_only=True)["Table 2"] #open the excel file 3
schedule4 = openpyxl.load_workbook('orar4.xlsx', data_only=True)["Table 2"] #open the excel file 4
#group lists
groups1 = [schedule1.cell(row=1,column=i).value for i in range(3,40)] #group list 1
groups2 = [schedule2.cell(row=1,column=i).value for i in range(3,40)] #group list 2
groups3 = [schedule3.cell(row=1,column=i).value for i in range(3,40)] #group list 3
groups4 = [schedule4.cell(row=1,column=i).value for i in range(3,40)] #group list 4

def get_schedule_and_groups(cur_group):
    group_number = int(cur_group[-3:-1])
    if group_number == 24:
        return schedule1, groups1
    elif group_number == 23:
        return schedule2, groups2
    elif group_number == 22:
        return schedule3, groups3
    elif group_number == 21:
        return schedule4, groups4
    else:
        raise ValueError("Invalid group number")

#get value from a cell even if it's a merged cell
merged_cell_ranges = {}  # cache merged cell ranges
def get_merged_cell_ranges(sheet):
    global merged_cell_ranges
    if sheet not in merged_cell_ranges:
        merged_cell_ranges[sheet] = {(r.min_row, r.min_col): r for r in sheet.merged_cells.ranges}
    return merged_cell_ranges[sheet]
def getMergedCellVal(sheet, cell):
    merged_ranges = get_merged_cell_ranges(sheet)
    row, col = cell.row, cell.column
    for (r_min, c_min), rng in merged_ranges.items():
        if r_min <= row <= rng.max_row and c_min <= col <= rng.max_col:
            return sheet.cell(rng.min_row, rng.min_col).value
    return cell.value

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

#get daily schedule
def print_day(week_day, cur_group, is_even) :
    schedule, groups = get_schedule_and_groups(cur_group)[0:2]
    col_gr = groups.index(cur_group) + 3 #column with the selected group
    daily = print_daily(schedule, is_even, col_gr, week_day)
    return daily

def print_daily(schedule, is_even, col_gr, week_day):
    day_sch = []
    seen = set() 

    row_start = next((i for i in range(1, 84) if week_days[week_day] == getMergedCellVal(schedule, schedule.cell(row=i, column=1))), 84)

    orele = {i: getMergedCellVal(schedule, schedule.cell(row=i, column=2)) for i in range(row_start, row_start + 14)}
    #extract the daily schedule
    for i in range(row_start, row_start + 13):
        if orele[i] not in seen:
            if is_even and orele.get(i + 1) == orele[i]:
                day_sch.append(getMergedCellVal(schedule, schedule.cell(row=i + 1, column=col_gr)))
            else:
                day_sch.append(getMergedCellVal(schedule, schedule.cell(row=i, column=col_gr)))
            seen.add(orele[i])

    day_sch = [
        f"\nPerechea: #{i + 1}\n<b>{course}</b>\nOra : {hours[i][0].replace('.', ':')}\n" if course else ""
        for i, course in enumerate(day_sch)
    ]

    return "".join(day_sch)

def print_next_course(week_day, cur_group, is_even, course_index):
    global hours
    schedule, groups = get_schedule_and_groups(cur_group)[0:2]
    col_gr = groups.index(cur_group) + 3

    #get the daily schedule
    is_even = datetime.datetime.today().isocalendar().week % 2
    daily = print_daily(schedule, is_even, col_gr, week_day)
    courses = daily.split("Perechea: #")

    #correct the course index
    for i in range(1,9):
        try:
            if int(courses[i][0]) == course_index:
                course_index = i
                break
        except Exception as e:
            #print(curr_time_logs() + "An exception occurred at courses==course_index:", e)
            return ""

    try:
        course = courses[course_index]
        #extract the course name and time
        course_name = course.split("Ora : ")[0][1:]
        course_time = course.split("Ora : ")[1]
        return f"<b>{course_name}</b>Ora: {course_time}"
    except Exception as e:
        send_logs(f"An exception occurred at print_next_course: {e}", 'error')
        return ""

#get weekly schedule
def print_sapt(is_even, cur_group) :
    schedule, groups = get_schedule_and_groups(cur_group)[0:2]
    col_gr = groups.index(cur_group) + 3 #column with the selected group

    week_sch = ""
    for j in range(1, 7):
        daily = print_daily(schedule, is_even, col_gr, j-1)
        #do not print an empty weekday
        if str(daily) != "":
            week_sch += "\n\n&emsp;&emsp;&emsp;&emsp;<b>" + week_days[j-1] + ":</b>" + "\n" + daily
    return week_sch

def send_logs(message, type):
    if type =='info':
        logging.info(message)
    elif type =='warning':
        logging.warning(message)
    elif type =='error':
        logging.error(message)
    elif type =='critical':
        logging.critical(message)
    else: 
        logging.info(message)