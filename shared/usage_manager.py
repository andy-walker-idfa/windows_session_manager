#Scipt working with user sessions data.
from pathlib import Path
import shared.defaults as defaults
import json
from datetime import date

#Function to get the path of timeline file, if data folder does not exist it will be created
def get_timeline_path():
    root_folder = Path(__file__).resolve().parent.parent
    try:
        Path.mkdir(root_folder / "data", exist_ok=True)
    except PermissionError:
        print("Permission denied: Could not create 'data' directory. Please run the program with appropriate permissions.")
        exit(1)
    
    return root_folder / "data" / defaults.time_tracking_file

#Function to read data from timeline file
def load_timeline_data():
    timeline_file_path = get_timeline_path()
    if Path.exists(timeline_file_path):
        try:
            with open(timeline_file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading timeline file: {e}")
            return {}
    else:
        return {}
#Function to write data to timeline file, data should be in format of minutes spent by user today, it will be stored in timeline file with current date as key. If there is already data for this user and date, it will be updated with new value.
def write_timeline_data(user, data):
    data_to_write = load_timeline_data()
    if data_to_write:
        if data_to_write.get(user, {}):
            data_to_write[user].update({date.today().isoformat(): data})
        else:
            data_to_write.update({user: {date.today().isoformat(): data}})
    else:
        data_to_write = {user: {date.today().isoformat(): data}}
    try:
        with open(get_timeline_path(), "w") as f:
            json.dump(data_to_write, f)
        return True
    except Exception as e:
        print(f"Error writing to timeline file: {e}")
        return False

#Function returning time spent by user today. As it is written in timeline file, it is expected to be in minutes, but it can be None if user has not spent any time today or if there is no data for this user.
def read_user_today_usage(user):
    data = load_timeline_data()
    if data.get(user, {}):
        return data[user].get(date.today().isoformat(), None)
    else:
        return None

#Function to add time spent by user today, it will update timeline file with new value.
def add_user_today_usage(user, minutes):
    current_usage = read_user_today_usage(user)
    if current_usage is None:
        current_usage = 0
    return (write_timeline_data(user, current_usage + minutes))
