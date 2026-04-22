from configurator.main import main
import logging
from shared import defaults


if __name__ == "__main__":
    defaults.configure_logging()
    main()