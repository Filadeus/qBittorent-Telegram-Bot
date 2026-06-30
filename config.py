import os
import logging
from dotenv import load_dotenv

# Set up logging format
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("qbit_bot")

# Load environment variables from .env file
load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    SQLITE_DB_PATH = os.getenv(
        "SQLITE_DB_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
    )
    
    # Parse allowed user IDs into a set of ints
    allowed_users_str = os.getenv("ALLOWED_USER_IDS", "")
    ALLOWED_USER_IDS = set()
    if allowed_users_str:
        for uid in allowed_users_str.split(","):
            uid = uid.strip()
            if uid.isdigit():
                ALLOWED_USER_IDS.add(int(uid))
                
    QBIT_HOST = os.getenv("QBIT_HOST", "localhost")
    try:
        QBIT_PORT = int(os.getenv("QBIT_PORT", "8080"))
    except ValueError:
        QBIT_PORT = 8080
        
    QBIT_USERNAME = os.getenv("QBIT_USERNAME", "admin")
    QBIT_PASSWORD = os.getenv("QBIT_PASSWORD", "")
    
    try:
        ALERT_INTERVAL_MINUTES = int(os.getenv("ALERT_INTERVAL_MINUTES", "15"))
    except ValueError:
        ALERT_INTERVAL_MINUTES = 15

    @classmethod
    def validate(cls):
        errors = []
        if not cls.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN environment variable is missing.")
        if not cls.ALLOWED_USER_IDS:
            errors.append("ALLOWED_USER_IDS is empty. You must specify at least one user ID for security reasons.")
        if not cls.QBIT_PASSWORD:
            errors.append("QBIT_PASSWORD is required to log in to qBittorrent WebUI.")
        return errors
