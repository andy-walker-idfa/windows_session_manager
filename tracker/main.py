#Script which suppose to be executed every configured period of time, check what users are logged in
#check if they are managed by our program and if they are, it will check how much time they have spent today
#and if they have exceeded their limit, it will log them out. It is expected to be run with appropriate permissions to be able to log out users.

import shared.config_manager as config_manager
import shared.usage_manager as usage_manager
import shared.defaults as defaults
import win32ts
import datetime
import logging

def main():

    #Get all users who are currently logged in
    try:
        sessions = win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE)
    except Exception as e:
        logging.error(f"Error enumerating sessions: {e}")
        exit(1)

    active_users = [{"User": win32ts.WTSQuerySessionInformation(win32ts.WTS_CURRENT_SERVER_HANDLE,session['SessionId'],win32ts.WTSUserName), "SessionID": session['SessionId']} for session in sessions if session['State'] == 0]
    
    #For each active user, check if they are managed by our program
    time_now = datetime.datetime.now().strftime("%H:%M")
    for user in active_users:
        logging.debug(f"Checking user {user['User']} with session ID {user['SessionID']}")
        if config_manager.get_user_config(user["User"]):
            user_effective_limits = config_manager.get_effective_limits(user["User"])
            #If they are check if login is allowed at this time. If not, log them out.
            if time_now < user_effective_limits.get("earliest_login", "00:00") \
            or time_now > user_effective_limits.get("latest_login", "23:59"):
                try:
                    win32ts.WTSLogoffSession(win32ts.WTS_CURRENT_SERVER_HANDLE, user["SessionID"], False)
                    logging.info(f"User {user['User']} has been logged out due to login time restrictions.")
                    continue
                except Exception as e:
                    logging.error(f"Error logging out user {user['User']}: {e}")
            #Add service_check_interval to their time spent today                        
            usage_manager.add_user_today_usage(user["User"],defaults.service_check_interval)
            #Check if they have exceeded their limit, if they have, log them out
            if usage_manager.read_user_today_usage(user["User"]) > user_effective_limits.get("limit_minutes", 1440):
                try:
                    win32ts.WTSLogoffSession(win32ts.WTS_CURRENT_SERVER_HANDLE, user["SessionID"], False)
                    logging.info(f"User {user['User']} has been logged out due to time spent restrictions.")
                    logging.info(f"User {user['User']} has spent today {usage_manager.read_user_today_usage(user["User"])} which is more than configured limit of {user_effective_limits.get("limit_minutes", 1440)}")
                    continue
                except Exception as e:
                    logging.error(f"Error logging out user {user['User']}: {e}")