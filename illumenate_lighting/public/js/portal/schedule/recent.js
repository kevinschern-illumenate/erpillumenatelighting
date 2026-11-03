// Schedule detail page (plan 3.7): "Recently used" product cards in the Add Line dialog. The cards
// list templates recently put on the dealer's schedules, each with its main (hero) image. Choosing
// one selects its Product Category and then the template in the same pickers a dealer uses by hand,
// so the usual configure / add steps follow. The server only lists templates the pickers offer.
var ScheduleRecent = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.recent_products.recent_products';
	var WAIT_MS = 8000;
	var PICKERS = {
		fixture: { select: '#add_fixture_template', flag: 'is-fixture-type' },
		tape_neon: { select: '#add_tape_neon_template', flag: 'is-tape-neon-type' },
		led_sheet: { select: '#add_led_sheet_template', flag: 'is-led-sheet-type' },
		kit: { select: '#add_kit_template', flag: 'is-extrusion-kit-type' },
		driver: { select: '#add_driver_template', flag: 'is-power-supply-type' },
	};
	var products = [];
	var pending = null;

	function show(text, failed) {
		$('#addLineRecentResult').text(text || '').toggleClass('text-danger', !!failed).toggleClass('text-muted', !failed);
	}

	function familyLabel(product) {
		switch (product.family) {
			case 'fixture': return scheduleText("Linear Fixture");
			case 'tape_neon': return product.category || scheduleText("LED Tape");
			case 'led_sheet': return scheduleText("LED Sheet");
			case 'kit': return scheduleText("Extrusion Kit");
			case 'driver': return scheduleText("Power Supply");
			default: return '';
		}
	}

	function card(product, index) {
		var button = document.createElement('button');
		button.type = 'button';
		button.className = 'ill-recent-card';
		button.setAttribute('role', 'listitem');
		button.setAttribute('data-index', String(index));
		var media = document.createElement('span');
		media.className = 'ill-recent-card-media';
		if (product.image) {
			var img = document.createElement('img');
			img.src = product.image;
			img.alt = product.image_alt || product.template_name || '';
			img.loading = 'lazy';
			img.addEventListener('error', function () {
				var placeholder = document.createElement('i');
				placeholder.className = 'fa fa-lightbulb-o';
				placeholder.setAttribute('aria-hidden', 'true');
				media.replaceChildren(placeholder);
			});
			media.appendChild(img);
		} else {
			var icon = document.createElement('i');
			icon.className = 'fa fa-lightbulb-o';
			icon.setAttribute('aria-hidden', 'true');
			media.appendChild(icon);
		}
		var body = document.createElement('span');
		body.className = 'ill-recent-card-body';
		[['ill-recent-card-name', product.template_name], ['ill-recent-card-code', product.template_code], ['ill-recent-card-family', familyLabel(product)]].forEach(function (part) {
			if (!part[1]) return;
			var span = document.createElement('span');
			span.className = part[0];
			span.textContent = part[1];
			body.appendChild(span);
		});
		button.appendChild(media);
		button.appendChild(body);
		return button;
	}

	function render() {
		var list = document.getElementById('addLineRecentList');
		if (!list) return;
		list.replaceChildren.apply(list, products.map(card));
		$('.ill-add-recent').toggleClass('d-none', !products.length);
	}

	function load() {
		cancel();
		show('', false);
		frappe.call({
			method: METHOD,
			type: 'GET',
			args: { schedule_name: schedule_name },
			callback: function (r) {
				var message = r.message || {};
				products = message.success ? (message.products || []) : [];
				render();
			},
			error: function () {
				products = [];
				render();
			},
		});
	}

	function cancel() {
		if (pending) pending();
		pending = null;
	}

	// Run ``done(true)`` once ``test()`` holds, or ``done(false)`` after WAIT_MS. The Add Line
	// pickers fill their selects asynchronously, so this waits on the dialog's DOM changes.
	function wait(test, done) {
		cancel();
		if (test()) return done(true);
		var root = document.getElementById('addLineModal') || document.body;
		var finished = false;
		var observer = new MutationObserver(function () {
			if (!finished && test()) finish(true);
		});
		var timer = setTimeout(function () { finish(false); }, ScheduleRecent.WAIT_MS);
		function stop() {
			finished = true;
			observer.disconnect();
			clearTimeout(timer);
		}
		function finish(ok) {
			stop();
			pending = null;
			done(ok);
		}
		pending = stop;
		observer.observe(root, { childList: true, subtree: true });
	}

	function categoryOption(product) {
		var picker = PICKERS[product.family];
		if (!picker) return null;
		return $('#add_product_type option').toArray().filter(function (option) {
			if (!option.value || $(option).attr('data-' + picker.flag) !== '1') return false;
			return product.family !== 'tape_neon' || $(option).attr('data-tape-neon-category') === product.category;
		})[0] || null;
	}

	function templateOption(product) {
		return $(PICKERS[product.family].select + ' option').toArray().filter(function (option) {
			return option.value === product.name;
		})[0] || null;
	}

	function choose(index) {
		var product = products[index];
		if (!product || !PICKERS[product.family]) return;
		$('#addLineForm select[name="manufacturer_type"]').val('ILLUMENATE').trigger('change');
		show(scheduleText("Loading..."), false);
		var categoriesLoaded = function () { return $('#add_product_type option').length > 1; };
		wait(function () { return categoriesLoaded() && !!categoryOption(product); }, function (found) {
			if (!found) {
				show(scheduleText("This product is not in the Add Line categories."), true);
				return;
			}
			$('#add_product_type').val(categoryOption(product).value).trigger('change');
			wait(function () { return !!templateOption(product); }, function (ready) {
				if (!ready) {
					show(scheduleText("This product is no longer offered."), true);
					return;
				}
				$(PICKERS[product.family].select).val(product.name).trigger('change');
				show(scheduleText("{0} selected.").replace('{0}', product.template_name), false);
			});
		});
	}

	if (scheduleContext.recent_products) {
		$(document).on('show.bs.modal', '#addLineModal', load);
		$(document).on('hide.bs.modal', '#addLineModal', cancel);
		$(document).on('click', '#addLineRecentList .ill-recent-card', function () {
			choose(Number(this.getAttribute('data-index')));
		});
	}

	return {
		WAIT_MS: WAIT_MS,
		load: load,
		choose: choose,
		cancel: cancel,
		products: function () { return products.slice(); },
	};
})();
