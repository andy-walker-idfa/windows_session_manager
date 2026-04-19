import customtkinter

class MyCheckboxFrame(customtkinter.CTkScrollableFrame):
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


class App(customtkinter.CTk):
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

        self.frame = MyCheckboxFrame(self, values)
        self.frame.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

        self.button = customtkinter.CTkButton(self, text=button_title,command=self.button_callback)
        self.button.grid(row=2, column=0, padx=20, pady=20, sticky="s")

    def button_callback(self):
        self.selected_values = self.frame.get_selected()
        self.destroy()