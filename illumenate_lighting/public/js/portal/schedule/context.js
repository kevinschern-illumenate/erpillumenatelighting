// Schedule detail page (context). The page renders its server values as JSON in
// #schedule-context instead of interpolating Jinja into JavaScript (plan 2.1).
// These scripts are classic (non-module) scripts, so their top-level names stay
// global exactly as they were in the old inline script.
var scheduleContext = JSON.parse(document.getElementById('schedule-context').textContent || '{}');
function scheduleText(text) {
	var strings = scheduleContext.i18n || {};
	return Object.prototype.hasOwnProperty.call(strings, text) ? strings[text] : text;
}
