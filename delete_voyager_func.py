import re

filepath = 'inbox/backend/routers/inbox.py'
with open(filepath, 'r') as f:
    content = f.read()

pattern = re.compile(r'def process_voyager_search_background.*?return\n', re.DOTALL)
new_content = pattern.sub('', content)

with open(filepath, 'w') as f:
    f.write(new_content)
