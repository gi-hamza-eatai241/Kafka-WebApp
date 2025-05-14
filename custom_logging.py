"""This module contains a custom logger that dynamically creates year/month folders,
a new log file each day, and backs up the previous day's log file at rollover."""

import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from parameters import LOGS_FOLDER

# Function to create the log file path with year/month folder structure
def get_log_file_path(logs_folder, base_filename):
    current_date = datetime.now()
    current_month = current_date.strftime("%B")
    current_year = current_date.strftime("%Y")
    log_dir = os.path.join(logs_folder, current_year, current_month)
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, base_filename)

# Custom handler that updates its file path dynamically at rollover time
class DynamicTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, path_func, when="midnight", interval=1, backupCount=31,
                 encoding=None, delay=False, utc=False, atTime=None):
        # path_func: a callable that returns the current log file path.
        self.path_func = path_func
        # Compute the initial log file path.
        initial_log_file = os.path.abspath(self.path_func())
        super().__init__(initial_log_file, when=when, interval=interval,
                         backupCount=backupCount, encoding=encoding,
                         delay=delay, utc=utc, atTime=atTime)

    def doRollover(self):
        """
        Overrides the default doRollover method to update the log file's location.
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        # Determine the backup filename based on the old file.
        t = self.rolloverAt - self.interval
        timeTuple = time.localtime(t)
        dfn = self.baseFilename + "." + time.strftime(self.suffix, timeTuple)
        if os.path.exists(self.baseFilename):
            self.rotate(self.baseFilename, dfn)

        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)

        # Compute a new log file path (this will account for new year/month if needed).
        new_log_file = os.path.abspath(self.path_func())
        self.baseFilename = new_log_file

        # Re-open the stream with the new baseFilename.
        self.mode = 'w'
        self.stream = self._open()

        currentTime = int(time.time())
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt += self.interval
        self.rolloverAt = newRolloverAt

# create a directory for logs if it does not exist
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Define log file paths for each component
feedback_path_func = lambda: get_log_file_path(LOGS_FOLDER, f"raspberry.log")


# Function to configure a logger with our dynamic handler.
def configure_logger(name, path_func, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent adding multiple handlers
    if not logger.handlers:
        handler = DynamicTimedRotatingFileHandler(path_func, when="midnight", interval=1, backupCount=31)
        handler.suffix = "%d-%m-%Y"  # This suffix will be added to backup files.
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                      datefmt='%d-%m-%Y, %A %I:%M:%S %p')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Feedback Logger
feedback_client_logger = configure_logger('feedback', feedback_path_func)
