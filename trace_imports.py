import sys
import modulefinder
import os

sys.path.insert(0, os.path.abspath('.'))

finder = modulefinder.ModuleFinder(path=sys.path)
finder.run_script('core/backend/workers/orchestrator_worker.py')

pkgs = set()
for name, mod in finder.modules.items():
    top_level = name.split('.')[0]
    if top_level not in sys.builtin_module_names and top_level not in ['__main__', 'core', 'campaigns', 'integrations', 'accounts', 'leads', 'inbox', 'dashboard', 'knowledge']:
        pkgs.add(top_level)

print(sorted(list(pkgs)))
