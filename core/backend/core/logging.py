import logging
import sys
from pythonjsonlogger import jsonlogger
from datetime import datetime

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            log_record['timestamp'] = now
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname
            
        if not log_record.get('service'):
            log_record['service'] = "backend"
            
        if hasattr(record, 'workspace_id'):
            log_record['workspace_id'] = record.workspace_id
            
        if record.exc_info:
            log_record['error_type'] = record.exc_info[0].__name__

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(message)s %(service)s %(workspace_id)s %(error_type)s')
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
