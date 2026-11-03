// The schedule page scripts (plan 2.1), in the order templates/pages/schedule.html loads them.
const fs = require('node:fs');
const path = require('node:path');

const DIR = path.join(__dirname, '../../illumenate_lighting/public/js/portal/schedule');
const TEMPLATE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/templates/pages/schedule.html'), 'utf8');
const ORDER = ['context', 'lines', 'uploads', 'actions', 'packets', 'exports', 'reorder', 'versions', 'copy', 'bulk', 'part_number', 'line_import', 'pricing'];
const read = name => fs.readFileSync(path.join(DIR, `${name}.js`), 'utf8');
const SCRIPT = ORDER.map(read).join('\n');

module.exports = { DIR, ORDER, TEMPLATE, SCRIPT, read };
