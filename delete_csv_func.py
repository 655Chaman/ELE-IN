import re

for filepath in ['inbox/backend/routers/inbox.py', 'core/backend/api/routers/approvals.py']:
    with open(filepath, 'r') as f:
        content = f.read()

    # Match def process_csv_background(...): until the start of class UploadUrlsRequest
    # (since we know it's followed by that in inbox.py and probably approvals.py)
    # Wait, let's use a regex that matches the function block precisely.
    
    pattern = re.compile(r'def process_csv_background.*?if os\.path\.exists\(file_path\):\n\s*os\.remove\(file_path\)', re.DOTALL)
    
    new_content = pattern.sub('', content)
    
    with open(filepath, 'w') as f:
        f.write(new_content)
