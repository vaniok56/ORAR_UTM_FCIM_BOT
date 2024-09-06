import numpy as np
import openpyxl # excel read library
import datetime

#classes that are not splited by odd/even
not_dual = np.array([4, 11, 24, 25, 38, 49, 50, 51, 64, 65, 66, 67, 68])

is_even = datetime.datetime.today().isocalendar().week % 2

#hours
hours =   [
    ["8:00 - 9:30"],
    ["9:45 - 11:15"],
    ["11:30 - 13:00"],
    ["13:30 - 15:00"],
    ["15:15 - 16:45"],
    ["17:00 - 18:30"],
    ["18:45 - 20:15"]
]

#week days
week_days = {
    0 : "Luni",
    1 : "Marţi",
    2 : "Miercuri",
    3 : "Joi",
    4 : "Vineri",
    5 : "Sambata",
    6 : "Duminica"
}

wb = openpyxl.load_workbook('orar.xlsx', data_only=True)
schedule = wb["Table 2"]

cur_group = "TI-241" #initialise current group
groups = [schedule.cell(row=1,column=i).value for i in range(3,36)] #group list

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

#get daily schedule
def print_day(week_day, cur_group) :
    global schedule, is_even, groups
    col_gr = groups.index(cur_group) + 3 #column with the selected group
    row_start = 2 + (14 * week_day) #first course row
    daily = print_daily(schedule, row_start, is_even, col_gr)
    return daily

def print_daily(schedule, row_start, is_even, col_gr):
    day_sch = []
    seen = set() 

    #rowstart depending on not_dual
    row_start -= sum(1 for i in range(1, row_start) if np.isin(i, not_dual) and i != 51 and i<65)
    if is_even == True and row_start != 51 and row_start < 64:
        row_start+=1
    match_is_even = not is_even
    #get the hours list
    orele = {i: getMergedCellVal(schedule, schedule.cell(row=i, column=2)) for i in range(row_start, row_start + 13)}

    #export all courses into a dataframe
    for i in range(row_start, row_start + 13):
        ora = orele[i] #get curent hour
        is_not_dual = False
        match_is_even = not match_is_even

        #check if current row is in not_dual
        if np.isin(i, not_dual):
            is_not_dual = True
            match_is_even = not match_is_even
        #jump to next iteration if already seen this hour course
        if ora in seen:
            continue
        #Add the course if even/odd or a row was skiped
        if match_is_even == is_even or is_not_dual == True :
            seen.add(ora)
            day_sch.append(getMergedCellVal(schedule, schedule.cell(row=i, column=col_gr)))
        else: 
            continue #jump to next iteration if odd/even

    #modifying for beter visibility
    for i in range(len(day_sch)):
        day_sch[i] = "<b>" + str(day_sch[i]) + "</b>"
        if "None" in str(day_sch[i]):
            day_sch[i] = ""
        else: day_sch[i] = "\nPerechea: #" + str(i+1) + "\n" + str(day_sch[i]) + "\nOra : " + ''.join(hours[i]) + "\n"
    
    #dataframe to string
    day_sch = "".join(str(element) for element in day_sch)
    
    return day_sch

#get weekly schedule
def print_sapt(is_even, cur_group) :
    global schedule, groups
    col_gr = groups.index(cur_group) + 3 #column with the selected group
    row_start = 2 #first course row

    week_sch = ""
    for j in range(1, 7):
        daily = print_daily(schedule, row_start, is_even, col_gr)
        #do not print an empty weekday
        if str(daily) != "":
            week_sch += "\n\n&emsp;&emsp;&emsp;&emsp;<b>" + week_days[j-1] + ":</b>" + "\n" + daily
        
        row_start += 14
    return week_sch
