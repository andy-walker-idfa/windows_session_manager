from configurator.gui import FirstWindow, SecondWindow
from shared.users import get_users
import shared.defaults as defaults

def main():
    #Presenting first window where user can select which users he wants to manage, after closing the window selected users are printed to console, in the future this will be replaced with opening second window for managing limits for selected users
    app = FirstWindow(get_users(),button_title="Okay", window_title="Select users you want to manage", app_title=defaults.app_name)
    app.mainloop()

    selected_users = app.selected_values
    for user in selected_users:
        print(user)

    #Presenting second window where user can manage limits for selected users, currently it only shows default limits, in the future it will show effective limits for each selected user and allow to edit them
    app = SecondWindow(app_name=defaults.app_name, window_title="Configure limits for selected users", tab_values=[{"Name": "Defaults"}, {"Name": "User Settings"}])
    app.mainloop()