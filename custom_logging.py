"""This module contains custom logger which will be shared by all the modules"""

import logging
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime
from parameters import LOGS_FOLDER


# Function to create the log file path with monthly directory structure
def get_log_file_path(logs_folder, base_filename):
    current_date = datetime.now()
    current_month = current_date.strftime("%B")
    current_year = current_date.strftime("%Y")
    log_dir = os.path.join(logs_folder, current_year, current_month)
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, base_filename)


# create a directory for logs if it does not exist
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Define log file paths for each component
log_file = get_log_file_path(LOGS_FOLDER, f"raspberry.log")


# CONFIGURE THE LOGGERS FOR EACH COMPONENT
def configure_logger(name, log_file, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=31)
    handler.suffix = "%d-%m-%Y"
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%m-%Y, %A %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


# Feedback Logger
feedback_client_logger = configure_logger('feedback', log_file)
