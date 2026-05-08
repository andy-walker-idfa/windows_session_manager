from tracker.main import main
from shared import defaults
import logging
import time

if __name__ == "__main__":
    defaults.configure_logging()
    while True:
        try:
            main()
        except Exception as e:
            logging.error(f"Error: {e}")
        time.sleep(defaults.service_check_interval*60)