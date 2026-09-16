// ⚠️  ONE-TIME MIGRATION SCRIPT — DO NOT RE-RUN
// This script was used to migrate from the monolith (frontend/src/) to the modular
// layout (core/, campaigns/, etc.). The migration is complete. Re-running this
// script will corrupt the current codebase. Safe to delete after team review.
const fs = require('fs');

const path = '/Users/krdeeksha/Ele-in/core/frontend/components/dashboard/EleInAnalyticsView.tsx';
let content = fs.readFileSync(path, 'utf8');

// Step 1: Extract the Live Feed block
const liveFeedStartStr = '          {/* Live Feed */}';
const liveFeedEndStr = '          </div>\n        </div>\n\n        {/* Drill-down Slide Panel */}';
const liveFeedStartIndex = content.indexOf(liveFeedStartStr);
const liveFeedEndIndex = content.indexOf(liveFeedEndStr);

if (liveFeedStartIndex === -1 || liveFeedEndIndex === -1) {
  console.error('Could not find Live Feed block');
  process.exit(1);
}

// Get the Live feed block text (up to `          </div>\n`)
const liveFeedBlock = content.substring(liveFeedStartIndex, liveFeedEndIndex + '          </div>\n'.length);

// Remove the Live Feed block from its original location
content = content.substring(0, liveFeedStartIndex) + content.substring(liveFeedEndIndex + '          </div>\n'.length);


// Step 2: Modify Row 2
// Replace Row 2 container grid
content = content.replace(
  '<div className="grid grid-cols-1 gap-6">\n          {/* Area Chart: Volume */}',
  '<div className="grid grid-cols-1 xl:grid-cols-3 gap-6">\n          {/* Area Chart: Volume */}\n'
);

// Replace Row 2 Area Chart col-span
content = content.replace(
  '          {/* Area Chart: Volume */}\n          <div className="rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col relative overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none">',
  '          {/* Area Chart: Volume */}\n          <div className="xl:col-span-2 rounded-3xl border border-slate-200 dark:border-border/50 bg-white dark:bg-card/40 backdrop-blur-md p-6 flex flex-col relative overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-none">'
);

// Insert Live Feed block into Row 2 (before its closing </div>)
// Looking for where Area Chart ends and Row 2 ends
const row2EndStr = '              )}\n            </div>\n          </div>\n        </div>\n\n        {/* Row 3: Funnel & Heatmaps & Radar */}';

if (!content.includes(row2EndStr)) {
  console.error('Could not find end of Row 2');
  process.exit(1);
}

content = content.replace(
  '              )}\n            </div>\n          </div>\n        </div>\n\n        {/* Row 3: Funnel & Heatmaps & Radar */}',
  '              )}\n            </div>\n          </div>\n\n' + liveFeedBlock + '        </div>\n\n        {/* Row 3: Funnel & Heatmaps & Radar */}'
);


// Step 3: Modify Row 3
content = content.replace(
  '{/* Row 3: Funnel & Heatmaps & Radar */}\n        <div className="grid grid-cols-1 xl:grid-cols-4 lg:grid-cols-2 gap-6">',
  '{/* Row 3: Funnel & Heatmaps & Radar */}\n        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">'
);

fs.writeFileSync(path, content, 'utf8');
console.log('Successfully modified layout.');
