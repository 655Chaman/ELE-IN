import re

with open("/Users/krdeeksha/Ele-in/backend/app/services/linkedin_worker.py", "r") as f:
    content = f.read()

retry_code = """
import time
from functools import wraps

def with_retries(max_retries=3):
    \"\"\"
    Layer 2: Add structural guards against developer mistakes.
    # RESILIENCE: All DB mutations in workers MUST be wrapped in this retry logic.
    \"\"\"
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            delay = 1
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Layer 1 Paranoia: What if the error is a 400 Bad Request?
                    # Retrying a bad request is pointless and wastes time.
                    err_str = str(e).lower()
                    if "400" in err_str or "bad request" in err_str:
                        raise e
                    
                    if attempt == max_retries - 1:
                        raise e
                    
                    time.sleep(delay)
                    delay *= 2
            return func(*args, **kwargs)
        return wrapper
    return decorator
"""

if "def with_retries" not in content:
    content = content.replace("class LinkedInWorker:", retry_code + "\nclass LinkedInWorker:")
    with open("/Users/krdeeksha/Ele-in/backend/app/services/linkedin_worker.py", "w") as f:
        f.write(content)
