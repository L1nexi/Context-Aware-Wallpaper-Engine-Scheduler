import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from utils.app_context import get_app_root

def setup_logger(name: str = "WEScheduler", log_file: str = "scheduler.log", level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a logger with console and file handlers.
    Logs are saved to the 'logs' directory in the project root.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Determine log path
    project_root = get_app_root()
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    # File Handler
    file_handler = RotatingFileHandler(log_path, maxBytes=1024*1024*5, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
