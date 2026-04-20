from configurator.gui import App
from shared.users import get_users

def main():
    app = App(get_users(),button_title="Okay", window_title="Select users you want to manage", app_title="Windows Session Time Manager")
    app.mainloop()

    selected_users = app.selected_values
    for user in selected_users:
        print(user)
