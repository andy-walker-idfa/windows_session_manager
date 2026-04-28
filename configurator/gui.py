import customtkinter
import shared.config_manager
from tkinter import messagebox

class CheckboxFrame4FirstWindow(customtkinter.CTkScrollableFrame):
    def __init__(self, master, values: list[dict]):
        super().__init__(master)
        self.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.values = values
        self.checkboxes = []
        for i, value in enumerate(values):
            var = customtkinter.BooleanVar(value=False)
            self.checkbox = customtkinter.CTkCheckBox(self, text=f"User: {values[i]['Name']};    Enabled: {values[i]['Enabled']}", variable=var)
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
        self.geometry("450x600")
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
    def __init__(self, selected_users, app_name="My App", window_title=None, tab_values=None):
        super().__init__()
        self.title(app_name)
        self.geometry("600x800")
        self.label = customtkinter.CTkLabel(self, text=window_title, font=customtkinter.CTkFont(size=19, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="w")
        self.tab_view = TabView4SecondWindow(self, tab_values)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.tab_view.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

        #Configuring Defaults tab
        defaults_tab = self.tab_view.tab("Defaults")
        defaults_tab.grid_columnconfigure(0, weight=1)
        defaults_tab.grid_rowconfigure(0, weight=1)
        defaults_scroll = customtkinter.CTkScrollableFrame(defaults_tab)
        defaults_scroll.grid(row=0, column=0, sticky="nsew")
        defaults_scroll.grid_columnconfigure(0, weight=1)

        TabLabel4SecondWindow(defaults_scroll, "These values apply to all managed users unless overridden in user settings.").grid(row=0, \
            column=0, padx=20, pady=(20, 0), sticky="wn")
        self.defaults_frames = []
        self.defaults_frames.append(LimitsFrame4SecondWindow(defaults_scroll, "Weekday", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}]))
        self.defaults_frames[0].grid(row=1, column=0, padx=0, pady=20, sticky="nsew")
        self.defaults_frames.append(LimitsFrame4SecondWindow(defaults_scroll, "Weekend", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}]))
        self.defaults_frames[1].grid(row=2, column=0, padx=0, pady=20, sticky="nsew")

        #Configuring User Settings tab
        user_settings_tab = self.tab_view.tab("User Settings")
        user_settings_tab.grid_columnconfigure(0, weight=1)
        user_settings_tab.grid_rowconfigure(0, weight=1)
        user_settings_scroll = customtkinter.CTkScrollableFrame(user_settings_tab)
        user_settings_scroll.grid(row=0, column=0, sticky="nsew")
        user_settings_scroll.grid_columnconfigure(0, weight=1)

        self.user_frames = []
        for user in selected_users:
            config_settings = [{"Name": "Inherit defaults only"}, {"Name": "Custom weekday / weekend"}, {"Name": "Per-day overrides"}]
            user_frame = UserSettingsFrame4SecondWindow(user_settings_scroll, user["Name"], config_settings)
            user_frame.grid(row=selected_users.index(user), column=0, padx=0, pady=20, sticky="nsew")
            self.user_frames.append(user_frame)
        
        #Placing buttons for saving/canceling changes
        self.button_frame = customtkinter.CTkFrame(self)
        self.button_frame.grid(row=2, column=0, padx=20, pady=20)
        self.button_frame.grid_columnconfigure(0)
        self.button_frame.grid_columnconfigure(1)
        self.save_button = customtkinter.CTkButton(self.button_frame, text="Save", command=self.save_changes, width=100)
        self.save_button.grid(row=0, column=0, padx=10, pady=0)
        self.cancel_button = customtkinter.CTkButton(self.button_frame, text="Cancel", command=self.cancel, width=100)
        self.cancel_button.grid(row=0, column=1, padx=10, pady=0)

            
    def save_changes(self):
        #In the future this function will save changes to database or configuration file, currently it just prints them to console
        defaults = {}
        for frame in self.defaults_frames:
            limits = frame.get_limits()
            defaults[frame.label.cget("text")] = limits
        if "Error" in defaults.values():
            return

        users = {}
        for user_frame in self.user_frames:
            user_limits = user_frame.get_user_limits()
            users[user_frame.label1.cget("text")] = user_limits
        if "Error" in users.values():
            return
        data2save = shared.config_manager.build_config(defaults,users)
        shared.config_manager.save_config(data2save)
        self.destroy()
    
    def cancel(self):
        self.destroy()


class TabView4SecondWindow(customtkinter.CTkTabview):
    def __init__(self, master, values):
        super().__init__(master, anchor="nw")
        for tab in values:
            self.add(tab["Name"])

class LimitsFrame4SecondWindow(customtkinter.CTkFrame):
    def __init__(self, master, frame_title, limits_values, padx=20):
        super().__init__(master)
        self.label = customtkinter.CTkLabel(self, text=frame_title, font=customtkinter.CTkFont(size=18, weight="bold"))
        self.label.grid(row=0, column=0, padx=padx, pady=(0, 0), sticky="wn")
        self.lables = []
        self.entry = []
        for limit in limits_values:
            label = customtkinter.CTkLabel(self, text=limit["Name"])
            entry = customtkinter.CTkEntry(self)
            label.grid(row=1, column=limits_values.index(limit), padx=padx, pady=0, sticky="w")
            entry.grid(row=2, column=limits_values.index(limit), padx=padx, pady=0, sticky="w")
            self.entry.append(entry)
            self.lables.append(label)
    
    def get_limits(self):
        limits = {}
        for label, entry in zip(self.lables, self.entry):
            limits[label.cget("text")] = entry.get()
        if not shared.config_manager.validate_limits(limits):
            messagebox.showerror("Validation Error", f"Invalid values in {self.label.cget('text')} section. Minutes must be 0-1440, times must be HH:MM format")
            return "Error"
        return limits

class TabLabel4SecondWindow(customtkinter.CTkLabel):
    def __init__(self, master, text):
        super().__init__(master, text=text, font=customtkinter.CTkFont(size=13, weight="normal"))

class UserSettingsFrame4SecondWindow(customtkinter.CTkFrame):
    def __init__(self, master, frame_title, limits_values):
        super().__init__(master)
        self.label1 = customtkinter.CTkLabel(self, text=frame_title, font=customtkinter.CTkFont(size=18, weight="bold"))
        self.label1.grid(row=0, column=0, padx=0, pady=(0, 0), sticky="wn")
        self.label2 = customtkinter.CTkLabel(self, text="Configuration level:", font=customtkinter.CTkFont(size=13, weight="normal"))
        self.label2.grid(row=1, column=0, padx=0, pady=(0, 0), sticky="wn")
        self.selected_radiobutton = customtkinter.StringVar(value="")
        for limit in limits_values:
            radioButton = RadioButton4SecondWindow(self, text=limit["Name"], on_radiobutton_selected=self.on_radiobutton_selected, variable=self.selected_radiobutton, value=limit["Name"])
            radioButton.grid(row=limits_values.index(limit)+2, column=0, padx=0, pady=0, sticky="w")
        #Create frame for limits that will be shown when "Inherit defaults only" is selected and hidden by default
        
        #Create frame for limits that will be shown when "Custom weekday / weekend" is selected and hidden by default
        self.inherit_defaults_frame1 = LimitsFrame4SecondWindow(self, "Weekday", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}])
        self.inherit_defaults_frame2 = LimitsFrame4SecondWindow(self, "Weekend", [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}])
        self.day_overrides_frame = DayOverridesFrame4SecondWindow(self, "Day overrides (optional)")
        
        #Create frame for limits that will be shown when "Per-day overrides" is selected and hidden by default
        self.per_day_overrides_frame = PerDayOverridesFrame4SecondWindow(self)

    def on_radiobutton_selected(self):
        selected_option = self.selected_radiobutton.get()
        if selected_option == "Inherit defaults only":
            # Handle the case when "Inherit defaults only" is selected
            self.inherit_defaults_frame1.grid_remove()
            self.inherit_defaults_frame2.grid_remove()
            self.day_overrides_frame.grid_remove()
            self.per_day_overrides_frame.grid_remove()
        elif selected_option == "Custom weekday / weekend":
            # Handle the case when "Custom weekday / weekend" is selected
            self.inherit_defaults_frame1.grid(row=5, column=0, padx=0, pady=20, sticky="nsew")
            self.inherit_defaults_frame2.grid(row=6, column=0, padx=0, pady=20, sticky="nsew")
            self.day_overrides_frame.grid(row=7, column=0, padx=20, pady=0, sticky="nsew")
            self.per_day_overrides_frame.grid_remove()
        elif selected_option == "Per-day overrides":
            # Handle the case when "Per-day overrides" is selected
            self.inherit_defaults_frame1.grid_remove()
            self.inherit_defaults_frame2.grid_remove()
            self.day_overrides_frame.grid_remove()
            self.per_day_overrides_frame.grid(row=5, column=0, padx=0, pady=20, sticky="nsew")

    def get_user_limits(self):
        selected_option = self.selected_radiobutton.get()
        limits = {}
        if selected_option == "Inherit defaults only":
            limits["Configuration level"] = "Inherit defaults only"
        elif selected_option == "Custom weekday / weekend":
            limits["Configuration level"] = "Custom weekday / weekend"
            limits["Weekday"] = self.inherit_defaults_frame1.get_limits()
            limits["Weekend"] = self.inherit_defaults_frame2.get_limits()
            day_overrides = {}
            for day, frame in self.day_overrides_frame.day_frames.items():
                day_limits = frame.limits.get_limits()
                if any(value != "" for value in day_limits.values()):
                    day_overrides[day] = day_limits
            limits["Day overrides"] = day_overrides
        elif selected_option == "Per-day overrides":
            limits["Configuration level"] = "Per-day overrides"
            limits["Per-day overrides"] = self.per_day_overrides_frame.get_limits()
        if "Error" in limits.values():
            return "Error"
        return limits

class RadioButton4SecondWindow(customtkinter.CTkRadioButton):
    def __init__(self, master, text, on_radiobutton_selected, variable, value):
        super().__init__(master, text=text, command=lambda: on_radiobutton_selected(), variable=variable, value=value)

class DayOverridesFrame4SecondWindow(customtkinter.CTkFrame):
    def __init__(self, master, frame_title):
        super().__init__(master)
        self.label = customtkinter.CTkLabel(self, text=frame_title, font=customtkinter.CTkFont(size=18, weight="normal"))
        self.label.grid(row=0, column=0, padx=0, pady=(0, 0), sticky="wn", columnspan =7)
        self.button_selected = None
        self.buttons = {}
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        self.day_frames = {}
        for day in days:
            self.day_frames[day] = customtkinter.CTkFrame(self)
            self.day_frames[day].limits = LimitsFrame4SecondWindow(self.day_frames[day], day.capitalize(), [{"Name": "Max minutes"}, {"Name": "Earliest login"}, {"Name": "Latest login"}], padx=0) 
            self.day_frames[day].limits.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
            button = customtkinter.CTkButton(self, text=day, width=45, height=28, command=lambda d=day: self.DayButtonCallback(d))
            button.grid(row=1, column=days.index(day), padx=0, pady=1, sticky="w")
            self.buttons[day] = button
            
    def DayButtonCallback(self, day):
        self.button_selected = day
        # Highlight buttons
        for d, button in self.buttons.items():
            if d == day:
                button.configure(fg_color=button.cget("hover_color"))
            else:
                button.configure(fg_color="grey")
        # Show/hide day frames
        for d, frame in self.day_frames.items():
            if d == day:
                frame.grid(row=2, column=0, padx=0, pady=0, sticky="nsew", columnspan=7)
            else:
                frame.grid_remove()

class PerDayOverridesFrame4SecondWindow(customtkinter.CTkFrame):
    def __init__(self, master, frame_title=None):
        super().__init__(master)
        self.label1 = customtkinter.CTkLabel(self, text=None, font=customtkinter.CTkFont(size=15, weight="normal"))
        self.label1.grid(row=0, column=0, padx=0, pady=(0, 0), sticky="wn")
        self.label2 = customtkinter.CTkLabel(self, text="Max minutes", font=customtkinter.CTkFont(size=15, weight="normal"))
        self.label2.grid(row=0, column=1, padx=0, pady=(0, 0), sticky="wn")
        self.label3 = customtkinter.CTkLabel(self, text="Earliest login", font=customtkinter.CTkFont(size=15, weight="normal"))
        self.label3.grid(row=0, column=2, padx=0, pady=(0, 0), sticky="wn")
        self.label4 = customtkinter.CTkLabel(self, text="Latest login", font=customtkinter.CTkFont(size=15, weight="normal"))
        self.label4.grid(row=0, column=3, padx=0, pady=(0, 0), sticky="wn")
        self.labels = {}
        self.entry = {}
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days:
            self.labels[day] = customtkinter.CTkLabel(self, text=day, font=customtkinter.CTkFont(size=13, weight="normal"))
            self.labels[day].grid(row=days.index(day)+1, column=0, padx=0, pady=0, sticky="wn")
            self.entry[day] = {}
            self.entry[day]["Max minutes"] = customtkinter.CTkEntry(self)
            self.entry[day]["Max minutes"].grid(row=days.index(day)+1, column=1, padx=0, pady=0, sticky="wn")
            self.entry[day]["Earliest login"] = customtkinter.CTkEntry(self)
            self.entry[day]["Earliest login"].grid(row=days.index(day)+1, column=2, padx=0, pady=0, sticky="wn")
            self.entry[day]["Latest login"] = customtkinter.CTkEntry(self)
            self.entry[day]["Latest login"].grid(row=days.index(day)+1, column=3, padx=0, pady=0, sticky="wn")
    
    def get_limits(self):
        limits = {}
        for day, entries in self.entry.items():
            day_limits = {}
            for limit_name, entry in entries.items():
                day_limits[limit_name] = entry.get()
            if any(value != "" for value in day_limits.values()):
                if not shared.config_manager.validate_limits(day_limits):
                    messagebox.showerror("Validation Error", f"Invalid values in {day} section. Minutes must be 0-1440, times must be HH:MM format")
                    return "Error"
            limits[day] = day_limits
        return limits