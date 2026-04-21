from pathlib import Path
import shared.defaults as defaults
import tomllib
import tomli_w
from datetime import date

#Function to get the path of configuration limits file, if config folder does not exist it will be created
def get_config_path():
    root_folder = Path(__file__).resolve().parent.parent
    try:
        Path.mkdir(root_folder / "config", exist_ok=True)
    except PermissionError:
        print("Permission denied: Could not create 'config' directory. Please run the program with appropriate permissions.")
        exit(1)
    
    return root_folder / "config" / defaults.limits_config_file

#Function to load config values from configuration limits file
def load_config():
    config_file_path = get_config_path()
    if Path.exists(config_file_path):
        try:
            with open(config_file_path, "rb") as f:
                return tomllib.load(f)
        except Exception as e:
            print(f"Error loading config file: {e}")
            return {}
    else:
        return {}
    
#Function to save config values to configuration limits file
def save_config(config: dict):
    config_file_path = get_config_path()
    try:
        with open(config_file_path, "wb") as f:
            tomli_w.dump(config, f)
        return True
    except Exception as e:
        print(f"Error saving config file: {e}")
        return False

#Function to get user specific config values from configuration limits file
def get_user_config(user_name):
    config = load_config()
    if user_name in config.get("users", {}):
        return config["users"][user_name]
    else:
        return None

#Function to get default config values from configuration limits file
def get_defaults_config():
    config = load_config()
    return config.get("defaults", {})

#Function to get effective limits for a user
def get_effective_limits(user_name, target_day=None):
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if target_day:
        week_day = days[target_day.weekday()]
    else:
        week_day = days[date.today().weekday()]
    if week_day in ["saturday", "sunday"]:
        day_type = "weekend"
        effective_limits = get_defaults_config().get("weekend",{})
    else:
        day_type = "weekday"
        effective_limits = get_defaults_config().get("weekday",{})

    user_config = get_user_config(user_name)
    if user_config:
        user_config_of_this_day_type = user_config.get(day_type, {})
        if user_config_of_this_day_type:
            for key in defaults.limits_keys:
                effective_limits.update({key: user_config_of_this_day_type.get(key, effective_limits.get(key, None))})

        user_config_of_today = user_config.get(week_day, {})
        if user_config_of_today:
            for key in defaults.limits_keys:
                effective_limits.update({key: user_config_of_today.get(key, effective_limits.get(key, None))})
    return effective_limits