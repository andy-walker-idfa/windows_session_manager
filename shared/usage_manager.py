#Scipt working with user sessions data.
from pathlib import Path
import shared.defaults as defaults
import json
import datetime
import logging

#Function to get the path of timeline file, if data folder does not exist it will be created
def get_timeline_path():
    root_folder = defaults.get_project_root()
    try:
        Path.mkdir(root_folder / "data", exist_ok=True)
    except PermissionError:
        logging.error("Permission denied: Could not create 'data' directory. Please run the program with appropriate permissions.")
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
            logging.error(f"Error loading timeline file: {e}")
            return {}
    else:
        return {}
#Function to write data to timeline file, data should be in format of minutes spent by user today,
# it will be stored in timeline file with current date as key. If there is already data for this user
#  and date, it will be updated with new value.
def write_timeline_data(user, data):
    data_to_write = load_timeline_data()
    today = datetime.date.today().isoformat()
    found_key_4date = None
    if data_to_write:
        #Case when there is a record for this user
        if data_to_write.get(user, {}):
            for key in data_to_write[user].keys():
                if key.startswith(today):
                    found_key_4date = key
                    break
            if found_key_4date:
                data_to_write[user].pop(found_key_4date)
            data_to_write[user].update({datetime.datetime.now().isoformat(): data})
        else:
            data_to_write.update({user: {datetime.datetime.now().isoformat(): data}})
    else:
        data_to_write = {user: {datetime.datetime.now().isoformat(): data}}
    try:
        with open(get_timeline_path(), "w") as f:
            json.dump(data_to_write, f)
        return True
    except Exception as e:
        logging.error(f"Error writing to timeline file: {e}")
        return False

#Function returning time spent by user today. As it is written in timeline file, it is expected to be in minutes, but it can be None if user has not spent any time today or if there is no data for this user.
def read_user_today_usage(user):
    data = load_timeline_data()
    today = datetime.date.today().isoformat()
    if data.get(user, {}):
        for key in data[user].keys():
            if key.startswith(today):
                return (data[user].get(key,None), key)
    return (None, None)

#Function to add time spent by user today, it will update timeline file with new value.
def add_user_today_usage(user, minutes):
    current_usage, last_active = read_user_today_usage(user)
    if current_usage is None:
        current_usage = 0
    if last_active:
        difference = round((datetime.datetime.now() - datetime.datetime.fromisoformat(last_active)).total_seconds()/60)
    else:
        difference = 1440
    if difference < defaults.service_check_interval:
        return (write_timeline_data(user, current_usage + difference))
    else:
        return (write_timeline_data(user, current_usage + minutes))

    
