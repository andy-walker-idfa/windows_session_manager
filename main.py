from gui import App
from logic import get_users

if __name__ == "__main__":
    app = App(get_users(),button_title="Okay", window_title="Select users you want to manage", app_title="Windows Session Time Manager")
    app.mainloop()

selected_users = app.selected_values
for user in selected_users:
    print(user)