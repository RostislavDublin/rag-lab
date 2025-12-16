"""Logging configuration with console and rotating file handlers"""
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_file: str = "logs/rag-lab.log", console_level: int = logging.INFO, file_level: int = logging.DEBUG):
    """
    Configure logging with two destinations:
    - Console: Brief logs (INFO by default)
    - File: Detailed logs (DEBUG by default) with rotation
    
    Rotation policy:
    - New log file on each server restart (timestamp-based naming)
    - Keep last 10 log files
    - Auto-rotate when file reaches 10MB
    
    Args:
        log_file: Base path to log file (relative to project root)
        console_level: Console logging level (INFO = brief)
        file_level: File logging level (DEBUG = verbose)
    """
    # Create logs directory if needed
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped log filename for new session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = log_path.stem
    session_log = log_path.parent / f"{base_name}_{timestamp}.log"
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filter in handlers
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Console handler - brief output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # Rotating file handler - detailed output
    # maxBytes=10MB, backupCount=10 (keep 10 old files)
    file_handler = RotatingFileHandler(
        session_log, 
        mode='a', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers in console (but keep in file)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    logging.info(f"Logging configured: console={logging.getLevelName(console_level)}, file={session_log} ({logging.getLevelName(file_level)})")
    logging.info(f"Session started at {timestamp}")
