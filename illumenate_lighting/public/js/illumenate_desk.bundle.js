// Desk (app_include_js) bundle — esbuild emits a content-hashed filename so
// browsers pick up new code on every deploy instead of a year-long cached copy.
import "./configurator/shared_configurator.js";
import "./configurator/fixture_group_editor.js";
import "./configurator/fixture_steps.js";
import "./configurator/tape_neon_steps.js";
import "./configurator/led_sheet_steps.js";
import "./configurator/coordinator.js";
import "./desk/desk_dialog.js";

import "./commercial_tasks.js";
