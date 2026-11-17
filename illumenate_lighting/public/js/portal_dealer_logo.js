/* Dealer logo self-service with a title-block preview (hardening plan 4.6). Text nodes only. */
(function () {
	const API = 'illumenate_lighting.illumenate_lighting.portal.accounts.set_dealer_logo';
	const t = (text, args) => (typeof __ === 'function' ? __(text, args) : String(text));

	function node(tag, className, text) {
		const element = document.createElement(tag);
		if (className) element.className = className;
		if (text !== undefined) element.textContent = text;
		return element;
	}

	/* A miniature of the System Designer title block: dealer logo above the ilLumenate mark. */
	function preview(container, src, company) {
		const block = node('div', 'ill-logo-preview');
		block.setAttribute('role', 'img');
		block.setAttribute('aria-label', src ? t('Title block preview with your logo') : t('Title block preview without a dealer logo'));
		const brand = node('div', 'ill-logo-preview__brand');
		if (src) {
			const image = node('img');
			image.src = src;
			image.alt = '';
			brand.append(image);
		}
		brand.append(node('strong', '', 'ilLumenate Lighting'));
		const fields = node('div', 'ill-logo-preview__fields');
		[t('PROJECT: Sample project'), t('CLIENT: {0}', [company || '']), t('SHEET: E-001')].forEach(line => fields.append(node('div', '', line)));
		block.append(brand, fields);
		container.replaceChildren(block);
		return block;
	}

	function mount(root) {
		if (!root || root._dealerLogo) return null;
		const input = root.querySelector('[data-logo-input]');
		const save = root.querySelector('[data-logo-save]');
		const remove = root.querySelector('[data-logo-remove]');
		const feedback = root.querySelector('[data-logo-feedback]');
		const box = root.querySelector('[data-logo-preview]');
		const company = root.dataset.company || '';
		let current = root.dataset.logoUrl || '';
		let objectUrl = null;
		let busy = false;
		function release() { if (objectUrl) { URL.revokeObjectURL?.(objectUrl); objectUrl = null; } }
		function draw(src) { preview(box, src, company); remove.hidden = !current; }
		function chosen() { return input.files && input.files[0]; }
		input.addEventListener('change', () => {
			release();
			const file = chosen();
			if (!file) { draw(current); feedback.textContent = ''; return; }
			if (!/\.(png|jpe?g)$/i.test(file.name)) { draw(current); feedback.textContent = t('Use a PNG or JPEG logo.'); return; }
			objectUrl = URL.createObjectURL(file);
			draw(objectUrl);
			feedback.textContent = t('Preview only. Select Save logo to use it on new drawings.');
		});
		save.addEventListener('click', async () => {
			const file = chosen();
			if (busy) return;
			if (!file || !/\.(png|jpe?g)$/i.test(file.name)) { feedback.textContent = t('Choose a PNG or JPEG logo first.'); return; }
			busy = true; save.disabled = true;
			feedback.textContent = t('Saving logo...');
			try {
				const receipt = await window.PortalUploads.upload(file);
				const result = await window.PortalUploads.call(API, {file_id: receipt.file_id});
				current = result.dealer_logo || '';
				input.value = '';
				release();
				draw(current);
				feedback.textContent = t('Logo saved. New drawings use it; issued drawings keep theirs.');
			} catch (error) { feedback.textContent = error.message; }
			finally { busy = false; save.disabled = false; }
		});
		remove.addEventListener('click', async () => {
			if (busy) return;
			busy = true; remove.disabled = true;
			try {
				await window.PortalUploads.call(API, {remove: 1});
				current = '';
				release();
				input.value = '';
				draw('');
				feedback.textContent = t('Logo removed from new drawings.');
			} catch (error) { feedback.textContent = error.message; }
			finally { busy = false; remove.disabled = false; }
		});
		root._dealerLogo = true;
		draw(current);
		return {draw};
	}

	window.PortalDealerLogo = {mount, preview};
	const start = () => mount(document.getElementById('dealerLogo'));
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
