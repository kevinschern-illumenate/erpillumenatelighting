/**
 * Multi-run groups: several independent runs of one product on a single
 * schedule / quote line. Shared by Portal and Desk.
 *
 * The family form keeps editing one run at a time (its length, leader and end
 * controls); this editor keeps the list of runs, swaps the selected run's
 * geometry in and out of that form, and replaces the single-run Calculate /
 * Save actions with group actions. Specifications and power are read once from
 * the form and apply to every run. The server recalculates everything on save.
 */
(function (root) {
    'use strict';
    var $ = root.jQuery, API = root.IllConfigurator;
    var MAX_RUNS = 12;
    var SHARED = {
        'Linear Fixture': ['finish_code', 'lens_appearance_code', 'mounting_method_code', 'environment_rating_code', 'endcap_color_code', 'tape_offering_id', 'led_package_code', 'cct_code', 'delivered_output_value'],
        'LED Tape': ['cct', 'output_level', 'environment_rating', 'finish', 'tape_spec', 'mounting_accessory_item', 'mounting_accessory_qty', 'pcb_finish', 'pcb_mounting'],
        'COB Tape': ['cct', 'output_level', 'environment_rating', 'finish', 'tape_spec', 'mounting_accessory_item', 'mounting_accessory_qty', 'pcb_finish', 'pcb_mounting'],
        'LED Neon': ['cct', 'output_level', 'environment_rating', 'finish', 'tape_spec', 'mounting_accessory_item', 'mounting_accessory_qty', 'pcb_finish', 'pcb_mounting'],
        'LED Sheet': ['spec', 'options']
    };
    // Single-run controls that do not apply while a group is being edited.
    var SINGLE_ONLY = '#calculateBtn, #tnCalculateBtn, #brCalculateBtn, #saveBtn, #tnSaveBtn, #brSaveBtn, '
        + '[data-action="validate"], [data-action="add-to-schedule"], #actionButtons, #tnActionButtons, #sheetActionButtons, '
        + '#noResults, #resultsContent, #tnResultsContent, #brResultsContent, #tapeModeToggleCard, #bulkReelCard, '
        + '[data-coordinator-action="setTapeMode-4"], [data-coordinator-action="setTapeMode-5"]';
    // Where the run list goes: just above the controls that edit one run.
    var GEOMETRY_ANCHORS = '#segmentsCard, #segmentsSection, #tapeModeToggleCard, #tapeLengthCard, #neonSegmentsCard, #sheetCoverageSection';
    var ACTION_ANCHORS = '#actionButtons, #tnActionButtons, #sheetActionButtons';
    var UNIT_MM = {mm: 1, cm: 10, m: 1000, in: 25.4, ft: 304.8};
    var LENGTH_KEYS = ['requested_length_mm', 'length_value', 'length_feet', 'length_inches', 'tape_length_value', 'tape_length_feet',
        'tape_length_inches', 'fixture_length_value', 'fixture_length_feet', 'fixture_length_inches'];

    function clone(value) { return JSON.parse(JSON.stringify(value)); }
    function isSheet(family) { return family === 'LED Sheet'; }
    function nouns(family) {
        return isSheet(family) ? {one: __('area'), many: __('areas'), One: __('Area')} : {one: __('run'), many: __('runs'), One: __('Run')};
    }
    function number(value) { var n = parseFloat(value); return isFinite(n) ? n : 0; }
    function money(value) {
        return '$' + Number(value || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
    /** 20' 6" style lengths, matching the quote and schedule descriptions. */
    function feetInches(mm) {
        var inches = Math.round(number(mm) / 25.4 * 10) / 10, feet = Math.floor(inches / 12);
        var rest = Math.round((inches - feet * 12) * 10) / 10;
        if (rest >= 12) { feet += 1; rest = 0; }
        var text = feet ? feet + "'" : '';
        if (rest || !feet) text += (text ? ' ' : '') + rest + '"';
        return text;
    }
    function segmentMm(segment) {
        if (segment.requested_length_mm != null && segment.requested_length_mm !== '') return number(segment.requested_length_mm);
        var prefix = segment.tape_length_unit != null ? 'tape_' : (segment.fixture_length_unit != null ? 'fixture_' : '');
        var unit = segment[prefix + 'length_unit'] || segment.length_unit || 'in';
        if (unit === 'ft_in') return (number(segment[prefix + 'length_feet']) * 12 + number(segment[prefix + 'length_inches'])) * 25.4;
        return number(segment[prefix + 'length_value']) * (UNIT_MM[unit] || 25.4);
    }
    function leaderMm(segment) {
        if (!segment) return 0;
        if (segment.start_leader_cable_length_mm != null) return number(segment.start_leader_cable_length_mm);
        return number(segment.start_lead_length_inches) * 25.4;
    }
    function areaFt(input, axis) {
        var key = 'coverage_' + axis, value = input[key + '_value'];
        if (value == null || value === '') return number(input[key + '_ft']);
        return number(value) * (UNIT_MM[input[key + '_unit'] || 'ft'] || 304.8) / 304.8;
    }
    /** What a run looks like right now, from its unsaved inputs. */
    function summarize(input, family) {
        input = input || {};
        if (isSheet(family)) {
            var width = areaFt(input, 'width'), height = areaFt(input, 'height');
            return {empty: !(width > 0 && height > 0), lengthMm: 0,
                text: width > 0 && height > 0 ? (Math.round(width * 100) / 100) + ' × ' + (Math.round(height * 100) / 100) + ' ft' : __('Enter the width and height')};
        }
        var segments = input.segments || [], total = 0;
        segments.forEach(function (segment) { total += segmentMm(segment); });
        var empty = !segments.length || segments.some(function (segment) { return segmentMm(segment) <= 0; });
        var parts = [total > 0 ? feetInches(total) : __('Enter a length')];
        if (segments.length > 1) parts.push(segments.length + ' ' + __('jumpered segments'));
        var leader = leaderMm(segments[0]);
        if (leader > 0) parts.push(feetInches(leader) + ' ' + __('leader'));
        return {empty: empty, lengthMm: total, text: parts.join(' · ')};
    }
    function geometry(request) {
        var values = request.selections || {};
        if (isSheet(request.family)) {
            var area = {};
            ['width', 'height'].forEach(function (axis) {
                ['value', 'unit', 'ft'].forEach(function (suffix) {
                    var key = 'coverage_' + axis + '_' + suffix;
                    if (values[key] != null) area[key] = values[key];
                });
            });
            return area;
        }
        return {segments: clone(request.segments || values.segments || [])};
    }
    /** A new run keeps the first segment's feed and leader settings but no length. */
    function blank(input) {
        input = clone(input || {});
        if (!input.segments) {
            ['width', 'height'].forEach(function (axis) {
                delete input['coverage_' + axis + '_ft'];
                input['coverage_' + axis + '_value'] = '';
            });
            return input;
        }
        var first = input.segments[0] || {};
        LENGTH_KEYS.forEach(function (key) { if (key in first) first[key] = ''; });
        first.end_type = 'Endcap';
        ['end_feed_direction', 'end_power_feed_type'].forEach(function (key) { if (key in first) first[key] = ''; });
        ['end_feed_length_inches', 'end_jumper_cable_length_mm'].forEach(function (key) { if (key in first) first[key] = 0; });
        return {segments: [first]};
    }
    function el(tag, className, text) {
        var node = $('<' + tag + '></' + tag + '>');
        if (className) node.addClass(className);
        if (text != null) node.text(text);
        return node;
    }
    function button(text, className, handler) {
        return $('<button type="button"></button>').addClass('btn btn-sm ' + (className || 'btn-outline-secondary')).text(text).on('click', handler);
    }
    function errorText(response) {
        var text = response && (response.exception || response.exc || '');
        if (Array.isArray(text)) text = text[0] || '';
        text = String(text || '').split('\n').filter(Boolean).pop() || '';
        return text.replace(/^[\w.]*(Error|Exception):\s*/, '');
    }

    function Editor(instance) {
        var self = this, id = instance.instanceId + '-group';
        this.instance = instance;
        this.readMember = instance.exportRequest.bind(instance);
        this.family = this.readMember().family || (instance.context.initial_group || {}).family;
        this.members = clone((instance.context.initial_group || {}).members || []);
        this.members.forEach(function (member, index) {
            member.member_id = member.member_id || self.newId();
            member.label = member.label || self.noun().One + ' ' + (index + 1);
        });
        this.enabled = !!instance.context.initial_group;
        this.active = 0;
        this.result = null;

        // ── Mode chooser and how-to ─────────────────────────────────
        this.$panel = $('<section class="ill-group-editor mb-3"></section>').attr('aria-labelledby', id + '-title');
        el('h5', 'ill-group-title', __('How is this fixture type installed?')).attr('id', id + '-title').appendTo(this.$panel);
        var modes = el('div', 'ill-group-modes').attr({role: 'radiogroup', 'aria-labelledby': id + '-title'}).appendTo(this.$panel);
        function mode(value, title, help) {
            var label = $('<label class="ill-group-mode"></label>').appendTo(modes);
            var input = $('<input type="radio">').attr({name: id + '-mode', value: value}).prop('checked', (value === 'group') === self.enabled).appendTo(label);
            var body = el('span', 'ill-group-mode-body').appendTo(label);
            el('strong', null, title).appendTo(body);
            el('small', null, help).appendTo(body);
            return input;
        }
        var sheet = isSheet(this.family);
        this.$single = mode('single', sheet ? __('Single area') : __('Single run'), sheet
            ? __('One coverage area of panels.')
            : __('One continuous fixture. It can still have segments joined by jumper cables.'));
        this.$toggle = mode('group', __('Multi-run group'), sheet
            ? __('Several separate coverage areas of this same panel, each with its own feed, quoted and ordered as one line.')
            : __('Several separate runs of this same product, each with its own leader and end, quoted and ordered as one line.'));
        var help = $('<details class="ill-group-help"></details>').appendTo(this.$panel);
        el('summary', null, __('When should I use a multi-run group?')).appendTo(help);
        var steps = el('ol').appendTo(help);
        (sheet ? [
            __('Use it when one fixture type covers several separate areas — for example, fixture type S1 is three lightbox faces: 2 × 4 ft, 2 × 4 ft and 4 × 8 ft.'),
            __('Choose the panel, colour temperature, finish and other options once. They apply to every area.'),
            __('Add an area for each separate surface and enter its width and height. Each area gets its own panel layout and feeds.'),
            __('Choose whether to include power supplies once for the whole group. Areas can share a supply; included supplies are added as their own line under the group.'),
            __('Calculate to check every area, then save. The group is quoted, ordered and built as one line; its quantity repeats the whole group.')
        ] : [
            __('Use it when one fixture type is installed as several separate pieces — for example, fixture type L1 is three cove runs in one room: 20 ft, 5 ft and 25 ft, each fed by its own leader cable.'),
            __('Choose the product, colour temperature, finish and other options once. They apply to every run.'),
            __('Add a run for each separate piece and enter its own length, leader and end. Pieces joined by a cable stay in one run: choose Jumper on a segment end.'),
            __('Choose whether to include power supplies once for the whole group. Runs can share a supply; included supplies are added as their own line under the group.'),
            __('Calculate to check every run, then save. The group is quoted, ordered and built as one line; its quantity repeats the whole group.')
        ]).forEach(function (text) { el('li', null, text).appendTo(steps); });

        // ── Run list ────────────────────────────────────────────────
        this.$content = el('div', 'ill-group-body').appendTo(this.$panel);
        var head = el('div', 'ill-group-head').appendTo(this.$content);
        this.$heading = el('strong', 'ill-group-count').appendTo(head);
        this.$total = el('span', 'ill-group-total text-muted small').appendTo(head);
        this.$list = $('<ol class="ill-run-list"></ol>').attr('aria-label', __('Runs in this group')).appendTo(this.$content);
        var tools = el('div', 'ill-group-tools').appendTo(this.$content);
        this.$add = button('+ ' + __('Add run'), 'btn-outline-primary', function () { self.add(); }).appendTo(tools);
        this.$duplicate = button(__('Duplicate selected'), 'btn-outline-secondary', function () { self.duplicate(self.active); }).appendTo(tools);
        this.$editing = $('<div class="ill-group-editing" aria-live="polite"></div>').appendTo(this.$content);

        // ── Group actions and results, where the single-run ones were ──
        this.$actions = el('div', 'ill-group-actions');
        this.$status = $('<div class="ill-group-status small" role="status"></div>').appendTo(this.$actions);
        var buttons = el('div', 'ill-group-buttons').appendTo(this.$actions);
        this.$calculate = button(__('Calculate group'), 'btn-primary', function () { self.calculate(); }).appendTo(buttons);
        this.$save = button(instance.context.saveHandler ? __('Add group') : __('Save group to schedule'), 'btn-success', function () { self.save(); })
            .prop('disabled', true).appendTo(buttons);
        this.$result = $('<div class="ill-group-result" aria-live="polite"></div>');

        this.mount();
        this.$panel.on('change', 'input[type=radio]', function () { self.setEnabled(this.value === 'group' && this.checked); });
        var originalInvalidate = instance.invalidateValidation;
        instance.invalidateValidation = function () {
            originalInvalidate.apply(instance, arguments);
            self.invalidate();
        };
        instance.exportRequest = function () {
            if (!self.enabled) return self.readMember();
            var request = self.request();
            return {schema_version: 3, family: request.family, template: request.template, selections: {group_request: request}};
        };
        // Keep the selected run's summary current as its length is typed.
        instance.$root.on('input.' + id + ' change.' + id, 'input, select', function (event) {
            if (self.enabled && !$(event.target).closest('.ill-group-editor').length) self.refreshSummaries();
        });
        instance._disposers.push(function () {
            instance.$root.off('.' + id);
            self.$panel.remove();
            self.$actions.remove();
            self.$result.remove();
            instance.$root.removeClass('ill-group-active');
        });
        this.render();
    }

    Editor.prototype.noun = function () { return nouns(this.family || this.readMember().family); };
    Editor.prototype.newId = function () {
        return root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : 'run-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    };
    Editor.prototype.mount = function () {
        var instance = this.instance;
        var geometryAnchor = instance.$(GEOMETRY_ANCHORS).first();
        if (geometryAnchor.length) geometryAnchor.before(this.$panel);
        else instance.$root.prepend(this.$panel);
        var actionAnchor = instance.$(ACTION_ANCHORS).first();
        if (actionAnchor.length) actionAnchor.before(this.$actions);
        else this.$content.append(this.$actions);
        var resultsAnchor = instance.$('#noResults').first();
        if (resultsAnchor.length) resultsAnchor.before(this.$result);
        else if (instance.$('#configSummary, #sheetConfigSummary').first().length) instance.$('#configSummary, #sheetConfigSummary').first().after(this.$result);
        else this.$actions.after(this.$result);
    };
    Editor.prototype.newMember = function (input) {
        return {member_id: this.newId(), label: this.noun().One + ' ' + (this.members.length + 1), input: clone(input)};
    };
    Editor.prototype.capture = function () {
        if (this.enabled && this.members[this.active]) this.members[this.active].input = geometry(this.readMember());
    };
    Editor.prototype.setEnabled = function (enabled) {
        if (enabled === this.enabled) return;
        if (enabled && this.readMember().selections.ordering_mode === 'BULK_REEL') {
            this.$single.prop('checked', true);
            frappe.msgprint(__('Bulk reels are ordered as reels. Choose Custom Length before creating a multi-run group.'));
            return;
        }
        if (enabled) {
            // The run on screen becomes the first run, or replaces the run it was before.
            this.enabled = true;
            if (!this.members.length) this.members.push(this.newMember(geometry(this.readMember())));
            this.capture();
        } else {
            // Back to one run: keep the selected run on screen.
            this.capture();
            this.enabled = false;
        }
        this.instance.invalidateValidation();
        this.render();
    };
    Editor.prototype.invalidate = function () {
        this.result = null;
        this.validatedRequest = null;
        this.$save.prop('disabled', true);
        this.$result.empty();
        this.setStatus(this.enabled ? __('Calculate the group to check every run, plan power and see the price before saving.') : '');
    };
    Editor.prototype.setStatus = function (text, tone) {
        this.$status.empty().removeClass('text-danger text-success');
        if (!text) return;
        if (tone) this.$status.addClass(tone === 'error' ? 'text-danger' : 'text-success');
        this.$status.text(text);
    };
    Editor.prototype.refreshSummaries = function () {
        var self = this, family = this.family, total = 0;
        this.capture();
        this.$list.children().each(function (index) {
            var summary = summarize((self.members[index] || {}).input, family);
            total += summary.lengthMm;
            $(this).find('.ill-run-summary').text(summary.text);
            $(this).toggleClass('ill-run-incomplete', summary.empty);
        });
        this.$total.text(total > 0 ? __('Total') + ' ' + feetInches(total) : '');
    };
    Editor.prototype.render = function () {
        var self = this, instance = this.instance, noun = this.noun(), count = this.members.length;
        this.family = this.readMember().family || this.family;
        instance.$root.toggleClass('ill-group-active', this.enabled);
        instance.$(SINGLE_ONLY).addClass('ill-single-action');
        this.$single.prop('checked', !this.enabled);
        this.$toggle.prop('checked', this.enabled);
        this.$panel.toggleClass('is-group', this.enabled);
        this.$content.toggle(this.enabled);
        this.$actions.toggle(this.enabled);
        this.$result.toggle(this.enabled);
        this.$list.empty();
        if (!this.enabled) return;
        this.$heading.text(count + ' ' + (count === 1 ? noun.one : noun.many) + ' ' + __('in this group'));
        this.members.forEach(function (member, index) {
            var active = index === self.active;
            var item = $('<li class="ill-run"></li>').toggleClass('is-active', active).appendTo(self.$list);
            var pick = $('<button type="button" class="ill-run-select"></button>').attr('aria-current', active ? 'true' : null)
                .attr('aria-label', __('Edit') + ' ' + (member.label || noun.One + ' ' + (index + 1)))
                .on('click', function () { self.select(index); }).appendTo(item);
            el('span', 'ill-run-number', String(index + 1)).appendTo(pick);
            el('span', 'ill-run-summary').appendTo(pick);
            if (active) el('span', 'ill-run-badge', __('Editing')).appendTo(pick);
            $('<input type="text" class="form-control form-control-sm ill-run-label" maxlength="100">')
                .attr('aria-label', noun.One + ' ' + (index + 1) + ' ' + __('label'))
                .attr('placeholder', noun.One + ' ' + (index + 1))
                .val(member.label || '')
                // Labels are not part of the build: keep them away from the form's change tracking.
                .on('input change', function (event) { event.stopPropagation(); if (event.type === 'input') self.rename(index, this.value); })
                .appendTo(item);
            var actions = el('span', 'ill-run-actions').appendTo(item);
            button(__('Duplicate'), 'btn-link', function () { self.duplicate(index); })
                .attr('aria-label', __('Duplicate') + ' ' + (member.label || noun.One + ' ' + (index + 1)))
                .prop('disabled', count >= MAX_RUNS).appendTo(actions);
            button(__('Remove'), 'btn-link text-danger', function () { self.remove(index); })
                .attr('aria-label', __('Remove') + ' ' + (member.label || noun.One + ' ' + (index + 1)))
                .prop('disabled', count < 2).appendTo(actions);
        });
        this.$add.text('+ ' + __('Add') + ' ' + noun.one).prop('disabled', count >= MAX_RUNS)
            .attr('title', count >= MAX_RUNS ? __('A group holds up to {0} {1}. Use another line for more.', [MAX_RUNS, noun.many]) : null);
        this.$duplicate.prop('disabled', count >= MAX_RUNS);
        var current = this.members[this.active] || {};
        this.$editing.empty();
        el('strong', null, __('Editing') + ' ' + (current.label || noun.One + ' ' + (this.active + 1))).appendTo(this.$editing);
        el('span', null, ' — ' + (isSheet(this.family)
            ? __('the coverage width and height below apply to this area only. Options and power apply to every area.')
            : __('the length, leader and end controls below apply to this run only. Options and power apply to every run.'))).appendTo(this.$editing);
        this.refreshSummaries();
        if (!this.result) this.setStatus(__('Calculate the group to check every run, plan power and see the price before saving.'));
    };
    Editor.prototype.rename = function (index, value) {
        if (!this.members[index]) return;
        this.members[index].label = value;
        if (index === this.active) this.$editing.find('strong').text(__('Editing') + ' ' + (value || this.noun().One + ' ' + (index + 1)));
        // Labels are presentation only: an existing calculation stays valid.
        if (this.result) {
            this.validatedRequest = this.request();
            this.relabel();
            this.renderResult(this.result);
        }
    };
    Editor.prototype.relabel = function () {
        var labels = {}, self = this;
        (this.result.presentation || []).forEach(function (row, position) {
            var member = self.members[position];
            if (member) row.label = member.label || self.noun().One + ' ' + (position + 1);
            labels[row.member_key] = row.label;
        });
        (this.result.runs || []).forEach(function (row) { if (labels[row.member_key]) row.label = labels[row.member_key]; });
    };
    Editor.prototype.select = function (index) {
        if (index === this.active || !this.members[index]) return;
        this.capture();
        this.active = index;
        this.instance.restoreGeometry(clone(this.members[index].input));
        this.render();
        this.$list.find('.ill-run-select').eq(index).trigger('focus');
    };
    Editor.prototype.add = function (input) {
        this.capture();
        if (this.members.length >= MAX_RUNS) {
            frappe.msgprint(__('A group holds up to {0} {1}. Add another line for more.', [MAX_RUNS, this.noun().many]));
            return;
        }
        this.members.push(this.newMember(input || blank(this.members[this.active].input)));
        this.instance.invalidateValidation();
        this.select(this.members.length - 1);
    };
    Editor.prototype.duplicate = function (index) {
        this.capture();
        var source = this.members[index];
        if (!source) return;
        this.add(source.input);
        var copy = this.members[this.members.length - 1];
        if (copy && source.label) {
            copy.label = source.label + ' ' + __('(copy)');
            this.render();
        }
    };
    Editor.prototype.remove = function (index) {
        if (this.members.length < 2 || !this.members[index]) return;
        this.capture();
        this.members.splice(index, 1);
        if (index < this.active || this.active >= this.members.length) this.active = Math.max(0, this.active - 1);
        this.instance.restoreGeometry(clone(this.members[this.active].input));
        this.instance.invalidateValidation();
        this.render();
    };
    Editor.prototype.request = function () {
        this.capture();
        var request = this.readMember(), values = request.selections || {}, shared = {};
        (SHARED[request.family] || []).forEach(function (key) { if (values[key] != null && values[key] !== '') shared[key] = values[key]; });
        return {schema_version: 3, family: request.family, template: request.template, shared: shared,
            power: {include_power_supply: values.include_power_supply, dimming_protocol_code: values.dimming_protocol_code || null, override_max_run_ft: values.override_max_run_ft == null || values.override_max_run_ft === '' ? null : values.override_max_run_ft,
                // Included supplies are saved as their own line under the group.
                separate_supply_line: true}, members: clone(this.members)};
    };
    /** Problems the dealer can fix before asking the server. */
    Editor.prototype.problem = function (request) {
        var noun = this.noun(), self = this;
        if (!request.template) return {text: __('Choose the product first. Its options apply to every {0}.', [noun.one])};
        var missing = -1;
        request.members.some(function (member, index) {
            if (summarize(member.input, request.family).empty) { missing = index; return true; }
            return false;
        });
        if (missing >= 0) {
            var label = request.members[missing].label || noun.One + ' ' + (missing + 1);
            return {index: missing, text: isSheet(request.family)
                ? __('Enter the width and height of {0}.', [label])
                : __('Enter a length for every segment of {0}.', [label])};
        }
        return self.members.length ? null : {text: __('Add at least one {0}.', [noun.one])};
    };
    Editor.prototype.calculate = function () {
        var self = this, instance = this.instance;
        if (!instance.canCalculateRestored()) return;
        instance.invalidateValidation();
        var request = this.request(), problem = this.problem(request);
        if (problem) {
            if (problem.index != null) this.select(problem.index);
            this.setStatus(problem.text, 'error');
            return;
        }
        var signature = JSON.stringify(request);
        this.$calculate.prop('disabled', true).text(__('Calculating…'));
        this.setStatus(__('Checking every run and planning power…'));
        instance.request({method: 'illumenate_lighting.illumenate_lighting.api.fixture_group_configurator.preview',
            args: {request: JSON.stringify(request)},
            isCurrent: function () { return self.enabled && JSON.stringify(self.request()) === signature; },
            callback: function (response) {
                var result = response.message;
                if (!result || !result.success) {
                    self.setStatus((result || {}).error || __('The group could not be calculated.'), 'error');
                    return;
                }
                self.result = result;
                self.validatedRequest = request;
                self.renderResult(result);
                self.$save.prop('disabled', false);
                self.setStatus(__('Group checked. Review the runs, power and price, then save.'), 'success');
            },
            error: function (response) {
                self.setStatus(errorText(response) || __('The group could not be calculated. Review the selections and try again.'), 'error');
            },
            always: function () { self.$calculate.prop('disabled', false).text(__('Calculate group')); }
        });
    };
    Editor.prototype.runLabel = function (runKey, labels) {
        var parts = String(runKey).split(':'), label = labels[parts[0]] || parts[0];
        return parts.length > 1 ? label + ', ' + __('circuit') + ' ' + parts[1] : label;
    };
    Editor.prototype.renderResult = function (result) {
        var self = this, target = this.$result.empty(), build = result.build || {}, plan = build.power_plan || {}, labels = {};
        var noun = this.noun(), runs = result.runs || [], qty = Number(this.instance.context.qty || (this.instance.context.draft_line || {}).qty || 1);
        (result.presentation || []).forEach(function (row) { labels[row.member_key] = row.label; });
        var card = el('div', 'ill-group-result-card').appendTo(target);
        var head = el('div', 'ill-group-result-head').appendTo(card);
        el('strong', null, __('Group checked')).appendTo(head);
        var total = 0;
        runs.forEach(function (row) { total += number(row.requested_length_mm); });
        el('span', 'text-muted small', [(build.members || []).length + ' ' + noun.many, total ? feetInches(total) : null,
            build.total_watts != null ? (Math.round(build.total_watts * 10) / 10) + ' W' : null].filter(Boolean).join(' · ')).appendTo(head);

        if (runs.length) {
            var table = $('<table class="table table-sm ill-group-table"><thead><tr></tr></thead><tbody></tbody></table>').appendTo(card);
            var sheet = isSheet(this.family);
            (sheet ? [noun.One, __('Area'), __('Panels'), __('Watts')] : [noun.One, __('Requested'), __('Built'), __('Circuits'), __('Watts')])
                .forEach(function (text) { el('th', null, text).appendTo(table.find('thead tr')); });
            runs.forEach(function (row) {
                var tr = $('<tr></tr>').appendTo(table.find('tbody'));
                var cells = sheet
                    ? [row.label, row.coverage_width_ft + ' × ' + row.coverage_height_ft + ' ft', row.panels != null ? row.panels : '—', row.watts + ' W']
                    : [row.label, feetInches(row.requested_length_mm) + (row.segments > 1 ? ' (' + row.segments + ' ' + __('segments') + ')' : ''),
                        row.manufactured_length_mm ? feetInches(row.manufactured_length_mm) : '—', row.circuits, row.watts + ' W'];
                cells.forEach(function (value) { el('td', null, value).appendTo(tr); });
            });
        }

        var power = el('div', 'ill-group-power').appendTo(card);
        el('h6', null, __('Power')).appendTo(power);
        var circuits = (plan.requirements || []).length;
        if (plan.status === 'excluded') {
            el('p', 'small mb-1', __('Power supplies are not included. Supply power for {0} circuit(s) at {1}, {2} control.',
                [circuits, build.voltage || '—', build.output_protocol || '—'])).appendTo(power);
        } else {
            var supplies = (plan.drivers || []).reduce(function (sum, row) { return sum + row.qty; }, 0);
            el('p', 'small mb-1', supplies > 1
                ? __('{0} supplies are needed to carry {1} circuits within each supply\'s total and per-output limits.', [supplies, circuits])
                : __('One supply carries all {0} circuit(s).', [circuits])).appendTo(power);
            var list = el('ul', 'small mb-1').appendTo(power);
            (plan.drivers || []).forEach(function (driver) { el('li', null, driver.qty + ' × ' + driver.driver_item).appendTo(list); });
            el('p', 'small text-muted mb-1', __('Supplies are added as their own line under this group, priced separately.')).appendTo(power);
            if ((plan.allocations || []).length) {
                var details = $('<details class="small"></details>').appendTo(power);
                el('summary', null, __('Which supply output feeds each run')).appendTo(details);
                (plan.allocations || []).forEach(function (a) {
                    el('div', null, self.runLabel(a.run_key, labels) + ' → ' + __('supply') + ' ' + a.supply + ' (' + a.item_code + '), '
                        + __('output') + ' ' + a.output + ' · ' + a.watts + ' W').appendTo(details);
                });
            }
        }

        if (this.instance.context.show_pricing !== false && result.pricing) {
            var pricing = el('div', 'ill-group-pricing').appendTo(card);
            el('h6', null, __('Price')).appendTo(pricing);
            var priceTable = $('<table class="table table-sm ill-group-table"><tbody></tbody></table>').appendTo(pricing);
            var order = {};
            (result.presentation || []).forEach(function (row, position) { order[row.member_key] = position; });
            (result.pricing.breakdown || []).slice().sort(function (a, b) {
                return (a.member in order ? order[a.member] : 99) - (b.member in order ? order[b.member] : 99);
            }).forEach(function (row) {
                var tr = $('<tr></tr>').appendTo(priceTable.find('tbody'));
                el('td', null, row.member ? (labels[row.member] || row.label || row.member) : row.qty + ' × ' + row.item_code).appendTo(tr);
                el('td', 'text-right', money(row.extended_msrp)).appendTo(tr);
            });
            var totals = el('dl', 'ill-group-totals').appendTo(pricing);
            function line(term, value, strong) {
                el('dt', null, term).appendTo(totals);
                el('dd', strong ? 'font-weight-bold' : null, value).appendTo(totals);
            }
            line(__('Group MSRP (each)'), money(result.pricing.msrp_unit));
            if (result.pricing.tier_unit != null) line(__('Your price (each)'), money(result.pricing.tier_unit), true);
            line(__('Quantity'), qty + ' × ' + __('complete group'));
            line(__('Extended'), money((result.pricing.tier_unit != null ? result.pricing.tier_unit : result.pricing.msrp_unit) * qty), true);
        }
    };
    Editor.prototype.save = function () {
        if (!this.result || !this.validatedRequest || JSON.stringify(this.request()) !== JSON.stringify(this.validatedRequest)) {
            this.invalidate();
            return;
        }
        var self = this, request = this.validatedRequest, instance = this.instance;
        if (instance.context.saveHandler) return instance.context.saveHandler({product_type: request.family,
            selections: {group_request: request}, validation: this.result, instance: instance});
        var target = instance.scheduleTarget;
        this.setStatus(__('Saving the group…'));
        return instance.saveScheduleConfiguration({family: request.family, selections: {group_request: request},
            template: request.template, schedule_name: target ? target.scheduleName() : undefined,
            line_idx: target ? (target.lineValue() === '__new__' ? null : target.lineValue()) : undefined}, {
            error: function (response) {
                self.setStatus(errorText(response) || __('The group could not be saved. Reload the schedule and try again.'), 'error');
            }
        });
    };
    API.GroupEditor = Editor;
    API.GroupEditor.feetInches = feetInches;
    API.GroupEditor.summarize = summarize;
    API.attachGroupEditor = function (instance) {
        if (instance.destroyed || instance.groupEditor || !instance.exportRequest || !instance.restoreGeometry) return;
        if (!instance.context.groups_enabled && !instance.context.initial_group) return;
        instance.groupEditor = new Editor(instance);
    };
}(window));
