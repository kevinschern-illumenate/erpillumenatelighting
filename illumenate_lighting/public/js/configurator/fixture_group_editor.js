/** One member editor around the scoped family controls, shared by Portal and Desk. */
(function (root) {
    'use strict';
    var $ = root.jQuery, API = root.IllConfigurator;
    var SHARED = {
        'Linear Fixture': ['finish_code', 'lens_appearance_code', 'mounting_method_code', 'environment_rating_code', 'endcap_color_code', 'tape_offering_id', 'led_package_code', 'cct_code', 'delivered_output_value'],
        'LED Tape': ['cct', 'output_level', 'environment_rating', 'finish', 'tape_spec', 'mounting_accessory_item', 'mounting_accessory_qty', 'pcb_finish', 'pcb_mounting'],
        'LED Neon': ['cct', 'output_level', 'environment_rating', 'finish', 'tape_spec', 'mounting_accessory_item', 'mounting_accessory_qty', 'pcb_finish', 'pcb_mounting'],
        'LED Sheet': ['spec', 'options']
    };
    function clone(value) { return JSON.parse(JSON.stringify(value)); }
    function button(text, handler) { return $('<button type="button" class="btn btn-sm btn-outline-secondary mr-2"></button>').text(__(text)).on('click', handler); }
    function geometry(request) {
        var values = request.selections || {};
        if (request.family === 'LED Sheet') {
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
    function Editor(instance) {
        this.instance = instance;
        this.readMember = instance.exportRequest.bind(instance);
        this.members = clone((instance.context.initial_group || {}).members || []);
        this.enabled = !!instance.context.initial_group;
        this.active = 0;
        this.result = null;
        this.$panel = $('<section class="card mb-3 ill-group-editor" aria-label="Fixture group"></section>');
        var body = $('<div class="card-body"></div>').appendTo(this.$panel), self = this;
        var id = instance.instanceId + '-group';
        this.$toggle = $('<input type="checkbox" class="mr-2">').attr('id', id).prop('checked', this.enabled);
        $('<label class="font-weight-bold"></label>').attr('for', id).append(this.$toggle, document.createTextNode(__('Configure independent members as one group'))).appendTo(body);
        this.$content = $('<div></div>').appendTo(body);
        $('<p class="small text-muted"></p>').text(__('Specifications and power settings apply to every member. Edit the selected member with the controls below. Quantity repeats the complete group.')).appendTo(this.$content);
        this.$list = $('<div class="d-flex flex-wrap mb-2" role="group" aria-label="Members"></div>').appendTo(this.$content);
        this.$label = $('<input class="form-control form-control-sm mb-2" maxlength="100">').attr('aria-label', __('Member label')).appendTo(this.$content);
        this.$label.on('input', function () { if (self.members[self.active]) self.members[self.active].label = this.value; self.invalidate(); });
        button('Add independent member', function () { self.add(); }).appendTo(this.$content);
        button('Remove member', function () { self.remove(); }).appendTo(this.$content);
        this.$calculate = button('Calculate complete group', function () { self.calculate(); }).addClass('btn-primary').appendTo(this.$content);
        this.$save = button('Save complete group', function () { self.save(); }).prop('disabled', true).appendTo(this.$content);
        this.$result = $('<div class="mt-3" aria-live="polite"></div>').appendTo(this.$content);
        instance.$root.prepend(this.$panel);
        this.$toggle.on('change', function () {
            if (this.checked && self.readMember().selections.ordering_mode === 'BULK_REEL') {
                this.checked = false;
                frappe.msgprint(__('Choose cut tape before creating a fixture group.'));
                return;
            }
            self.enabled = this.checked;
            if (self.enabled && !self.members.length) self.members.push(self.newMember(geometry(self.readMember())));
            instance.invalidateValidation();
            self.render();
        });
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
        instance._disposers.push(function () { self.$panel.remove(); });
        this.render();
    }
    Editor.prototype.newMember = function (input) { return {member_id: root.crypto.randomUUID(), label: __('Member') + ' ' + (this.members.length + 1), input: clone(input)}; };
    Editor.prototype.capture = function () {
        if (this.members[this.active]) this.members[this.active].input = geometry(this.readMember());
    };
    Editor.prototype.invalidate = function () {
        this.result = null;
        this.$save.prop('disabled', true);
        this.$result.empty();
    };
    Editor.prototype.render = function () {
        var self = this;
        this.$content.toggle(this.enabled);
        this.instance.$root.toggleClass('ill-group-active', this.enabled);
        this.$list.empty();
        this.members.forEach(function (member, index) {
            button(member.label || __('Member') + ' ' + (index + 1), function () { self.select(index); })
                .attr('aria-pressed', index === self.active ? 'true' : 'false')
                .toggleClass('btn-info', index === self.active).appendTo(self.$list);
        });
        this.$label.val((this.members[this.active] || {}).label || '');
        // Family calculation/save actions are replaced by the aggregate actions while grouping.
        this.instance.$('#calculateBtn, #tnCalculateBtn, #brCalculateBtn, #saveBtn, #tnSaveBtn, #brSaveBtn, #buildItemBtn, #tnBuildItemBtn, [data-action="validate"], [data-action="add-to-schedule"]').addClass('ill-single-action').toggle(!this.enabled);
        this.instance.$('[data-coordinator-action="setTapeMode-4"], [data-coordinator-action="setTapeMode-5"]').toggle(!this.enabled);
    };
    Editor.prototype.select = function (index) {
        this.capture();
        this.active = index;
        this.instance.restoreGeometry(clone(this.members[index].input));
        this.instance.invalidateValidation();
        this.render();
    };
    Editor.prototype.add = function () {
        this.capture();
        if (this.members.length >= 12) { frappe.msgprint(__('A group supports up to 12 independent members.')); return; }
        this.members.push(this.newMember(this.members[this.active].input));
        this.select(this.members.length - 1);
    };
    Editor.prototype.remove = function () {
        if (this.members.length < 2) return;
        this.members.splice(this.active, 1);
        this.active = Math.min(this.active, this.members.length - 1);
        this.instance.restoreGeometry(clone(this.members[this.active].input));
        this.instance.invalidateValidation();
        this.render();
    };
    Editor.prototype.request = function () {
        this.capture();
        var request = this.readMember(), values = request.selections || {}, shared = {};
        (SHARED[request.family] || []).forEach(function (key) { if (values[key] != null && values[key] !== '') shared[key] = values[key]; });
        return {schema_version: 3, family: request.family, template: request.template, shared: shared,
            power: {include_power_supply: values.include_power_supply, dimming_protocol_code: values.dimming_protocol_code || null, override_max_run_ft: values.override_max_run_ft == null || values.override_max_run_ft === '' ? null : values.override_max_run_ft}, members: clone(this.members)};
    };
    Editor.prototype.calculate = function () {
        var self = this, instance = this.instance;
        if (!instance.canCalculateRestored()) return;
        instance.invalidateValidation();
        var request = this.request(), signature = JSON.stringify(request);
        this.$calculate.prop('disabled', true);
        instance.request({method: 'illumenate_lighting.illumenate_lighting.api.fixture_group_configurator.preview',
            args: {request: JSON.stringify(request)},
            isCurrent: function () { return self.enabled && JSON.stringify(self.request()) === signature; },
            callback: function (response) {
                var result = response.message;
                if (!result || !result.success) { self.$result.text((result || {}).error || __('Group could not be calculated.')); return; }
                self.result = result;
                self.validatedRequest = request;
                self.renderResult(result);
                self.$save.prop('disabled', false);
            },
            error: function () { self.$result.text(__('The group could not be calculated. Review the validation message and retry.')); },
            always: function () { self.$calculate.prop('disabled', false); }
        });
    };
    Editor.prototype.renderResult = function (result) {
        var target = this.$result.empty(), build = result.build, labels = {};
        (result.presentation || []).forEach(function (row) { labels[row.member_key] = row.label; });
        $('<strong></strong>').text(build.members.length + ' ' + __('independent members') + ' · ' + build.total_watts + ' W').appendTo(target);
        build.members.forEach(function (member) {
            var block = $('<div class="mt-2"></div>').appendTo(target);
            $('<strong></strong>').text(member.member_key + (labels[member.member_key] ? ' ? ' + labels[member.member_key] : '')).appendTo(block);
            var dimensions = member.geometry;
            (dimensions.segments || []).forEach(function (segment, index) { $('<div></div>').text(__('Segment') + ' ' + (index + 1) + ': ' + segment.requested_length_mm + ' mm · ' + segment.end_type).appendTo(block); });
            if (dimensions.coverage_width_ft != null) $('<div></div>').text(dimensions.coverage_width_ft + ' × ' + dimensions.coverage_height_ft + ' ft · ' + member.build.panels_needed + ' ' + __('panels')).appendTo(block);
            (member.build.groups || []).forEach(function (feed) { $('<div class="small"></div>').text(__('Feed') + ' ' + feed.group_number + ': ' + feed.sheet_count + ' ' + __('panels') + ', ' + feed.group_watts + ' W ? ' + __('one leader')).appendTo(block); });
            (member.build.cables || []).forEach(function (cable) { $('<div class="small"></div>').text(cable.role + ': ' + cable.length_mm + ' mm · ' + cable.item_code).appendTo(block); });
        });
        $('<p class="mt-2"></p>').text(build.power_plan.status === 'excluded' ? __('External power required; supplies are excluded from the BOM and price.') : __('Included supplies')).appendTo(target);
        if (build.power_plan.drivers.reduce(function (count, row) { return count + row.qty; }, 0) > 1) $('<p></p>').text(__('Multiple supplies are required to satisfy all independent circuits within the eligible total and per-output capacities.')).appendTo(target);
        build.power_plan.drivers.forEach(function (driver) { $('<div></div>').text(driver.qty + ' × ' + driver.driver_item).appendTo(target); });
        build.power_plan.requirements.forEach(function (circuit) { $('<div class="small"></div>').text(circuit.run_key + ': ' + circuit.watts + ' W').appendTo(target); });
        build.power_plan.allocations.forEach(function (a) { $('<div class="small"></div>').text(a.run_key + ' → ' + a.item_code + ', ' + __('supply') + ' ' + a.supply + ', ' + __('output') + ' ' + a.output).appendTo(target); });
        if (this.instance.context.show_pricing !== false) {
            var table = $('<table class="table table-sm mt-2"><thead><tr><th>Member / component</th><th>Qty</th><th>Unit MSRP</th><th>Extended MSRP</th></tr></thead></table>').appendTo(target), body = $('<tbody></tbody>').appendTo(table);
            result.pricing.breakdown.forEach(function (row) {
                var tr = $('<tr></tr>').appendTo(body);
                [row.member || row.item_code, row.qty, row.unit_msrp.toFixed(2), row.extended_msrp.toFixed(2)].forEach(function (value) { $('<td></td>').text(value).appendTo(tr); });
            });
            $('<div class="font-weight-bold"></div>').text(__('Group unit MSRP') + ': ' + result.pricing.msrp_unit.toFixed(2)).appendTo(target);
            var qty = Number(this.instance.context.qty || (this.instance.context.draft_line || {}).qty || 1);
            $('<div></div>').text(__('Group quantity') + ': ' + qty + ' ? ' + __('Extended MSRP') + ': ' + (result.pricing.msrp_unit * qty).toFixed(2)).appendTo(target);
            if (result.pricing.tier_unit != null) $('<div></div>').text(__('Your estimated group unit price') + ': ' + result.pricing.tier_unit.toFixed(2)).appendTo(target);
        }
    };
    Editor.prototype.save = function () {
        if (!this.result || JSON.stringify(this.request()) !== JSON.stringify(this.validatedRequest)) { this.invalidate(); return; }
        var request = this.validatedRequest, instance = this.instance;
        if (instance.context.saveHandler) return instance.context.saveHandler({product_type: request.family,
            selections: {group_request: request}, validation: this.result, instance: instance});
        var target = instance.scheduleTarget;
        return instance.saveScheduleConfiguration({family: request.family, selections: {group_request: request},
            template: request.template, schedule_name: target ? target.scheduleName() : undefined,
            line_idx: target ? (target.lineValue() === '__new__' ? null : target.lineValue()) : undefined});
    };
    API.GroupEditor = Editor;
    API.attachGroupEditor = function (instance) {
        if (instance.destroyed || instance.groupEditor || !instance.exportRequest || !instance.restoreGeometry) return;
        if (!instance.context.groups_enabled && !instance.context.initial_group) return;
        instance.groupEditor = new Editor(instance);
    };
}(window));
