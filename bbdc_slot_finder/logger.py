import logging

# Configure logging
logging.basicConfig(
    filename="log.txt",
    format="%(asctime)s - %(funcName)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Set logging level for seleniumwire to WARNING
logging.getLogger("seleniumwire").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

# set higher logging level for httpx to avoid all GET and POST requests being logged
# logging.getLogger("httpx").setLevel(logging.WARNING)

# Get logger
logger = logging.getLogger(__name__)
