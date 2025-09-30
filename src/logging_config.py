"""structured json logging configuration"""

import logging
import json
import sys
from datetime import datetime

class JsonFormatter(logging.Formatter):
    """format logs as json"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        # add request_id if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        
        # add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

def setup_logging(log_level='INFO'):
    """configure structured json logging (thread-safe by default)"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    
    # configure root logger
    # python logging module is already thread-safe, uses locks internally
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # clear existing handlers to avoid duplicates
    logger.handlers.clear()
    logger.addHandler(handler)
    
    return logger

