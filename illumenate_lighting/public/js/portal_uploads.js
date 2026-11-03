/* Private, resumable upload intake. Never serialize File objects into JSON. */
window.PortalUploads = {
	async upload(file, parentType, parentName) {
		if (!file.size || file.size > 20 * 1024 * 1024) throw new Error(__('Each file must be between 1 byte and 20 MiB.'));
		if (!/\.(pdf|png|jpe?g|heic|heif)$/i.test(file.name)) throw new Error(__('Use PDF, JPEG, PNG or HEIC files.'));
		const body = new FormData();
		body.append('file', file);
		if (parentType) body.append('parent_type', parentType);
		if (parentName) body.append('parent_name', parentName);
		const response = await fetch('/api/method/illumenate_lighting.illumenate_lighting.portal.files.upload', {
			method: 'POST', credentials: 'same-origin', headers: {'X-Frappe-CSRF-Token': frappe.csrf_token}, body
		});
		const result = await response.json().catch(() => ({}));
		if (!response.ok || !result.message?.success) {
			const reason = this.serverMessage(result);
			throw new Error(__('Upload failed for {0}. Your draft is preserved; retry this file.', [file.name]) + (reason ? ' ' + reason : ''));
		}
		return result.message;
	},
	serverMessage(result) {
		try {
			const messages = JSON.parse(result?._server_messages || '[]');
			const first = messages.length ? JSON.parse(messages[0]) : null;
			const text = (first && (first.message || first)) || '';
			return String(text).replace(/<[^>]*>/g, '').slice(0, 300);
		} catch (error) {
			return '';
		}
	},
	async uploadAll(input, parentType, parentName) {
		const files = Array.from(input?.files || []);
		if (files.length > 10) throw new Error(__('Choose at most 10 files.'));
		input._uploadedFiles = input._uploadedFiles || new Map();
		const receipts = [];
		for (const file of files) {
			const key = `${parentType || ''}:${parentName || ''}:${file.name}:${file.size}:${file.lastModified}`;
			if (!input._uploadedFiles.has(key)) input._uploadedFiles.set(key, await this.upload(file, parentType, parentName));
			receipts.push(input._uploadedFiles.get(key));
		}
		return receipts.map(receipt => receipt.file_id);
	},
	async call(method, args) {
		const response = await frappe.call({method, args, type: 'POST'});
		if (!response.message?.success) throw new Error(response.message?.error || __('The request could not be completed.'));
		return response.message;
	}
};
