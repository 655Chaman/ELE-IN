# ⚠️  ONE-TIME MIGRATION SCRIPT — DO NOT RE-RUN
# This script was used to migrate from the monolith (frontend/src/) to the modular
# layout (core/, campaigns/, etc.). The migration is complete. Re-running this
# script will corrupt the current codebase. Safe to delete after team review.
import json
import os

def fix_tsconfig_app():
    with open('tsconfig.app.json', 'r') as f:
        data = json.load(f)
    
    # Update includes to capture all frontend domains
    data['include'] = [
        "core/frontend",
        "accounts/frontend",
        "admin/frontend",
        "campaigns/frontend",
        "dashboard/frontend",
        "inbox/frontend",
        "integrations/frontend",
        "knowledge/frontend",
        "leads/frontend"
    ]
    
    # Update aliases
    paths = {
        "@/*": ["./core/frontend/*"], # Maps old "@/components" to new core structure
        "@core/*": ["./core/frontend/*"],
        "@accounts/*": ["./accounts/frontend/*"],
        "@admin/*": ["./admin/frontend/*"],
        "@campaigns/*": ["./campaigns/frontend/*"],
        "@dashboard/*": ["./dashboard/frontend/*"],
        "@inbox/*": ["./inbox/frontend/*"],
        "@integrations/*": ["./integrations/frontend/*"],
        "@knowledge/*": ["./knowledge/frontend/*"],
        "@leads/*": ["./leads/frontend/*"]
    }
    data['compilerOptions']['paths'] = paths
    
    with open('tsconfig.app.json', 'w') as f:
        json.dump(data, f, indent=2)

def fix_tsconfig_main():
    with open('tsconfig.json', 'r') as f:
        data = json.load(f)
        
    paths = {
        "@/*": ["./core/frontend/*"],
        "@core/*": ["./core/frontend/*"],
        "@accounts/*": ["./accounts/frontend/*"],
        "@admin/*": ["./admin/frontend/*"],
        "@campaigns/*": ["./campaigns/frontend/*"],
        "@dashboard/*": ["./dashboard/frontend/*"],
        "@inbox/*": ["./inbox/frontend/*"],
        "@integrations/*": ["./integrations/frontend/*"],
        "@knowledge/*": ["./knowledge/frontend/*"],
        "@leads/*": ["./leads/frontend/*"]
    }
    data['compilerOptions']['paths'] = paths
    
    with open('tsconfig.json', 'w') as f:
        json.dump(data, f, indent=2)

if __name__ == '__main__':
    fix_tsconfig_app()
    fix_tsconfig_main()
    print("TypeScript configs updated successfully.")
