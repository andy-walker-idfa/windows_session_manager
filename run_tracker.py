from tracker.main import main
from shared import defaults
import logging

if __name__ == "__main__":
    defaults.configure_logging()
    main()