# ⚠️  ONE-TIME MIGRATION SCRIPT — DO NOT RE-RUN
# This script was used to migrate from the monolith (frontend/src/) to the modular
# layout (core/, campaigns/, etc.). The migration is complete. Re-running this
# script will corrupt the current codebase. Safe to delete after team review.
import re

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Replace "@/*": ["./src/*"] with the new mega block
    old_paths = r'"@/\*":\s*\["\./src/\*"\]'
    new_paths = (
        '"@/*": ["./core/frontend/*"],\n'
        '      "@core/*": ["./core/frontend/*"],\n'
        '      "@accounts/*": ["./accounts/frontend/*"],\n'
        '      "@admin/*": ["./admin/frontend/*"],\n'
        '      "@campaigns/*": ["./campaigns/frontend/*"],\n'
        '      "@dashboard/*": ["./dashboard/frontend/*"],\n'
        '      "@inbox/*": ["./inbox/frontend/*"],\n'
        '      "@integrations/*": ["./integrations/frontend/*"],\n'
        '      "@knowledge/*": ["./knowledge/frontend/*"],\n'
        '      "@leads/*": ["./leads/frontend/*"]'
    )
    content = re.sub(old_paths, new_paths, content)

    # For tsconfig.app.json, fix the include array
    if 'tsconfig.app' in filepath:
        old_include = r'"include":\s*\["src"\]'
        new_include = '"include": ["core/frontend", "accounts/frontend", "admin/frontend", "campaigns/frontend", "dashboard/frontend", "inbox/frontend", "integrations/frontend", "knowledge/frontend", "leads/frontend"]'
        content = re.sub(old_include, new_include, content)

    with open(filepath, 'w') as f:
        f.write(content)

patch_file('tsconfig.json')
patch_file('tsconfig.app.json')

# Fix Vite config
with open('vite.config.ts', 'r') as f:
    vite_content = f.read()
    
vite_old_alias = r'"@": path\.resolve\(__dirname,\s*"./src"\),'
vite_new_alias = (
    '"@": path.resolve(__dirname, "./core/frontend"),\n'
    '      "@core": path.resolve(__dirname, "./core/frontend"),\n'
    '      "@accounts": path.resolve(__dirname, "./accounts/frontend"),\n'
    '      "@admin": path.resolve(__dirname, "./admin/frontend"),\n'
    '      "@campaigns": path.resolve(__dirname, "./campaigns/frontend"),\n'
    '      "@dashboard": path.resolve(__dirname, "./dashboard/frontend"),\n'
    '      "@inbox": path.resolve(__dirname, "./inbox/frontend"),\n'
    '      "@integrations": path.resolve(__dirname, "./integrations/frontend"),\n'
    '      "@knowledge": path.resolve(__dirname, "./knowledge/frontend"),\n'
    '      "@leads": path.resolve(__dirname, "./leads/frontend"),'
)
vite_content = re.sub(vite_old_alias, vite_new_alias, vite_content)

with open('vite.config.ts', 'w') as f:
    f.write(vite_content)

print("All configs updated!")
