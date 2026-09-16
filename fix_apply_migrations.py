import re

with open("backend/scripts/apply_migrations.py", "r") as f:
    content = f.read()

# Add 025 to the list
content = content.replace(
    '"024_fix_leads_constraints.sql"',
    '"024_fix_leads_constraints.sql",\n    "025_phase2_infrastructure.sql"'
)

with open("backend/scripts/apply_migrations.py", "w") as f:
    f.write(content)

