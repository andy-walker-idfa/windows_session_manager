import shared.config_manager as config_manager
import shared.usage_manager as usage_manager
import datetime
import json
import subprocess
import win32ts



def enumerate_active_user():
    sessions = win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE)
    active_sessions = [win32ts.WTSQuerySessionInformation(win32ts.WTS_CURRENT_SERVER_HANDLE,session['SessionId'],win32ts.WTSUserName) for session in sessions if session['State'] == 0]
    return active_sessions

sessions = enumerate_active_user()
print(sessions)

print(datetime.datetime.now().strftime("%H:%M"))