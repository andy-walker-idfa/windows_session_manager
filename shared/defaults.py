import logging
from pathlib import Path
import sys

#Application Name
app_name = "Time Manager"
#File name where configuration limits are stored
limits_config_file = "limits.toml"
#Configuration limits we are working with
limits_keys = ["limit_minutes", "earliest_login", "latest_login"]
#Time tracking file where time spent by users will be stored
time_tracking_file = "timeline.json"
#Time interval in minutes, which will be used by tracker script to check users' sessions and update time spent by them today, it is expected to be run with this period of time, but it can be changed if needed.
service_check_interval = 5
#Log file name
log_name = "app.log"
#Default logging level
log_level = "DEBUG"
#Configurting logging
def configure_logging():
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        handlers=[
            logging.FileHandler(get_project_root() / log_name),
            logging.StreamHandler()
        ]
    )
#Function to determine root folder. Depends how we execute it. Either directly py file or via PyInstaller from executable file
def get_project_root():
    if hasattr(sys,'_MEIPASS'):
        return Path(sys.executable).resolve().parent.parent
    else:
        return Path(__file__).resolve().parent.parent