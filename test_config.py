import shared.config_manager as config_manager
from datetime import date

print(f"Config path: {config_manager.get_config_path()}")

print(f"Values in configuration file are: {config_manager.load_config()}")

print(f"Effective limits for user 'andy' for 2026, 4, 20: {config_manager.get_effective_limits('andy', date(2026, 4, 20))}")

print(date.today().isoformat())

car = {
  "brand": "Ford",
  "model": "Mustang",
  "year": 1964,
  "color": "Yellow"
}

car.update({"color": "White"})

print(car)