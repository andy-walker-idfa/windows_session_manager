import customtkinter

from test_config import MyLimitsFrame, MyTabView

class CheckboxFrame4FirstWindow(customtkinter.CTkScrollableFrame):
    def __init__(self, master, values: list[dict]):
        super().__init__(master)
        self.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.values = values
        self.checkboxes = []
        for i, value in enumerate(values):
            var = customtkinter.BooleanVar(value=False)
            self.checkbox = customtkinter.CTkCheckBox(self, text=f"User: {values[i]['Name']}; Enabled: {values[i]['Enabled']}", variable=var)
            self.checkbox.grid(row=i, column=0, padx=20, pady=10, sticky="w")
            self.checkboxes.append((value, var))
    
    def get_selected(self):
        return [
            item for item, var in self.checkboxes if var.get()
        ]


class FirstWindow(customtkinter.CTk):
    def __init__(self, values: list[dict], button_title, app_title, window_title):
        super().__init__()

        self.title(app_title)
        self.button_title = button_title
        self.window_title = window_title
        self.geometry("400x600")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.selected_values = []

        self.label = customtkinter.CTkLabel(self, text=f"{self.window_title}: ", font=customtkinter.CTkFont(size=20, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(20, 0))

        self.frame = CheckboxFrame4FirstWindow(self, values)
        self.frame.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

        self.button = customtkinter.CTkButton(self, text=button_title,command=self.button_callback)
        self.button.grid(row=2, column=0, padx=20, pady=20, sticky="s")

    def button_callback(self):
        self.selected_values = self.frame.get_selected()
        self.destroy()
    
class SecondWindow(customtkinter.CTk):
    def __init__(self, app_name="My App", window_title=None, tab_values=None):
        super().__init__()
        self.title(app_name)
        self.geometry("600x600")
        self.label = customtkinter.CTkLabel(self, text=window_title, font=customtkinter.CTkFont(size=19, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="w")
        self.tab_view = MyTabView(self, tab_values)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.tab_view.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

        #Configuring Defaults tab
        TabLabel4SecondWindow(self.tab_view.tab("Defaults"), "These values apply to all managed users unless overridden in user settings.").grid(row=0, \
            column=0, padx=20, pady=(20, 0), sticky="wn")
        LimitsFrame4SecondWindow(self.tab_view.tab("Defaults"), "Weekday", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}]).grid(row=1, column=0, padx=0, pady=20, sticky="nsew")
        LimitsFrame4SecondWindow(self.tab_view.tab("Defaults"), "Weekend", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}]).grid(row=2, column=0, padx=0, pady=20, sticky="nsew")

        #Configuring User Settings tab
        TabLabel4SecondWindow(self.tab_view.tab("User Settings"), "Configure limits for selected users").grid(row=0, \
            column=0, padx=20, pady=(20, 0), sticky="wn")
        

class TabView4SecondWindow(customtkinter.CTkTabview):
    def __init__(self, master, values):
        super().__init__(master, anchor="nw")
        for tab in values:
            self.add(tab["Name"])

class LimitsFrame4SecondWindow(customtkinter.CTkFrame):
    def __init__(self, master, frame_title, limits_values):
        super().__init__(master)
        self.label = customtkinter.CTkLabel(self, text=frame_title, font=customtkinter.CTkFont(size=18, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(0, 0), sticky="wn")
        self.lables = []
        self.entry = []
        for limit in limits_values:
            label = customtkinter.CTkLabel(self, text=limit["Name"])
            entry = customtkinter.CTkEntry(self)
            label.grid(row=1, column=limits_values.index(limit), padx=20, pady=0, sticky="w")
            entry.grid(row=2, column=limits_values.index(limit), padx=20, pady=0, sticky="w")
            self.entry.append(entry)
            self.lables.append(label)

class TabLabel4SecondWindow(customtkinter.CTkLabel):
    def __init__(self, master, text):
        super().__init__(master, text=text, font=customtkinter.CTkFont(size=13, weight="normal"))