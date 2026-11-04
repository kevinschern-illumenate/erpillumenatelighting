/* Shared dealer upload widget (hardening plan 4.1/4.2).
 *
 * PortalUploader.attach(input) progressively enhances a native file input with a drop zone,
 * per-file rows (thumbnail or type badge, name, size, progress, cancel/retry/remove) and
 * client-side photo preparation. The input keeps working for existing callers: its FileList
 * mirrors the accepted files, PortalUploads.uploadAll(input, ...) delegates here, and clearing
 * the input (value = '' or form.reset()) clears the widget. Server endpoints and limits are
 * unchanged; the server re-validates everything. Rendering uses DOM APIs and textContent only.
 * Kill switch: site config ill_portal_upload_widget = false restores the plain input.
 */
(function () {
	const MiB = 1024 * 1024;
	const LIMITS = {fileBytes: 20 * MiB, files: 10, totalBytes: 100 * MiB, concurrency: 3, downscaleBytes: 8 * MiB, maxEdge: 4096};
	const ALLOWED = /\.(pdf|png|jpe?g|heic|heif)$/i;
	const UPLOAD_URL = '/api/method/illumenate_lighting.illumenate_lighting.portal.files.upload';
	let sequence = 0;

	function el(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
	}

	function formatSize(bytes) {
		if (bytes >= MiB) return (bytes / MiB).toFixed(1) + ' MiB';
		if (bytes >= 1024) return Math.round(bytes / 1024) + ' KiB';
		return bytes + ' B';
	}

	function kind(name) {
		const match = /\.([a-z0-9]+)$/i.exec(name || '');
		const extension = match ? match[1].toLowerCase() : '';
		if (extension === 'pdf') return 'pdf';
		if (extension === 'heic' || extension === 'heif') return 'heic';
		if (extension === 'png' || extension === 'jpg' || extension === 'jpeg') return 'image';
		return 'other';
	}

	/* EXIF orientation of a JPEG (1 when absent or unreadable). Reads only the APP1 segment. */
	function jpegOrientation(buffer) {
		const view = new DataView(buffer);
		const length = view.byteLength;
		if (length < 4 || view.getUint16(0) !== 0xFFD8) return 1;
		let offset = 2;
		while (offset + 4 <= length) {
			const marker = view.getUint16(offset);
			if ((marker & 0xFF00) !== 0xFF00 || marker === 0xFFDA) return 1;
			const size = view.getUint16(offset + 2);
			if (marker === 0xFFE1 && offset + 18 <= length && view.getUint32(offset + 4) === 0x45786966) {
				const tiff = offset + 10;
				const little = view.getUint16(tiff) === 0x4949;
				const ifd = tiff + view.getUint32(tiff + 4, little);
				if (ifd + 2 > length) return 1;
				const count = view.getUint16(ifd, little);
				for (let index = 0; index < count; index++) {
					const entry = ifd + 2 + index * 12;
					if (entry + 12 > length) return 1;
					if (view.getUint16(entry, little) === 0x0112) return view.getUint16(entry + 8, little) || 1;
				}
				return 1;
			}
			offset += 2 + size;
		}
		return 1;
	}

	function flags() {
		const node = typeof document !== 'undefined' && document.getElementById('ill-portal-flags');
		if (!node) return {};
		try { return JSON.parse(node.textContent || '{}') || {}; } catch (error) { return {}; }
	}

	const PortalUploader = {
		LIMITS,
		jpegOrientation,

		enabled() {
			return flags().upload_widget !== false && typeof DataTransfer === 'function';
		},

		attach(input, options = {}) {
			if (!input || input.type !== 'file') return null;
			if (input._portalUploader) return input._portalUploader;
			if (!this.enabled() || !input.parentNode) return null;
			const state = {
				input, options, items: [], context: null,
				maxFiles: input.multiple ? LIMITS.files : 1,
				root: el('div', 'ill-uploader'),
			};
			const drop = el('div', 'ill-uploader__drop');
			drop.tabIndex = 0;
			drop.setAttribute('role', 'button');
			const hint = el('span', 'ill-uploader__hint', input.multiple
				? __('Drag files here or browse. PDF, JPEG, PNG or HEIC; up to 10 files, 20 MiB each.')
				: __('Drag a file here or browse. PDF, JPEG, PNG or HEIC; up to 20 MiB.'));
			const browse = el('button', 'btn btn-sm btn-outline-secondary ill-uploader__browse', __('Browse'));
			browse.type = 'button';
			drop.append(hint, browse);
			state.list = el('ul', 'ill-uploader__list list-unstyled');
			state.message = el('p', 'ill-uploader__message small');
			state.message.setAttribute('role', 'status');
			state.message.setAttribute('aria-live', 'polite');
			state.root.append(drop, state.list, state.message);
			input.classList.add('ill-uploader__input');
			input.parentNode.insertBefore(state.root, input.nextSibling);

			const open = event => { event.preventDefault(); input.click(); };
			browse.addEventListener('click', open);
			drop.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') open(event); });
			drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('is-dragover'); });
			drop.addEventListener('dragleave', () => drop.classList.remove('is-dragover'));
			drop.addEventListener('drop', event => {
				event.preventDefault();
				drop.classList.remove('is-dragover');
				this.add(state, Array.from(event.dataTransfer?.files || []));
			});
			input.addEventListener('change', () => {
				const picked = Array.from(input.files || []).filter(file => !state.items.some(item => item.original === file));
				this.add(state, picked);
			});
			if (input.form) input.form.addEventListener('reset', () => setTimeout(() => this.reset(input)));
			input._portalUploader = state;
			return state;
		},

		/* Clear the widget, for callers that clear their form after a successful submit. */
		reset(input) {
			const state = input?._portalUploader;
			if (!state) return;
			state.items.forEach(item => { item.xhr?.abort(); this.revoke(item); });
			state.items = [];
			state.list.textContent = '';
			state.message.textContent = '';
			this.sync(state);
		},

		add(state, files) {
			const reasons = [];
			if (state.maxFiles === 1 && files.length) {
				state.items.slice().forEach(item => this.remove(state, item));
				files = files.slice(0, 1);
			}
			for (const file of files) {
				const reason = this.rejection(state, file);
				if (reason) { reasons.push(reason); continue; }
				const item = {
					id: ++sequence, original: file, file, status: 'preparing', progress: 0,
					receipts: new Map(), error: '', xhr: null, preview: null,
				};
				state.items.push(item);
				this.renderRow(state, item);
				item.ready = this.prepare(file).then(prepared => {
					item.file = prepared;
					const late = this.sizeRejection(state, item);
					if (late) {
						this.remove(state, item);
						state.message.textContent = (state.message.textContent + ' ' + late).trim();
						return;
					}
					if (item.status === 'preparing') this.setStatus(state, item, 'pending');
					this.sync(state);
				});
			}
			this.sync(state);
			state.message.textContent = reasons.join(' ');
		},

		rejection(state, file) {
			if (!ALLOWED.test(file.name || '')) return __('{0} was not added: use PDF, JPEG, PNG or HEIC files.', [file.name]);
			if (!file.size) return __('{0} was not added: the file is empty.', [file.name]);
			if (state.items.length >= state.maxFiles) return __('{0} was not added: choose at most {1} files.', [file.name, state.maxFiles]);
			if (kind(file.name) !== 'image' && file.size > LIMITS.fileBytes) return __('{0} was not added: each file must be 20 MiB or smaller.', [file.name]);
			return '';
		},

		sizeRejection(state, item) {
			if (item.file.size > LIMITS.fileBytes) return __('{0} was not added: each file must be 20 MiB or smaller.', [item.original.name]);
			const total = state.items.reduce((sum, row) => sum + row.file.size, 0);
			if (total > LIMITS.totalBytes) return __('{0} was not added: all files together must be 100 MiB or smaller.', [item.original.name]);
			return '';
		},

		/* Normalize EXIF orientation and downscale very large JPEG/PNG photos to a JPEG.
		 * HEIC goes to the server unchanged (most browsers cannot decode it). */
		async prepare(file) {
			const isJpeg = /\.jpe?g$/i.test(file.name);
			if (!(isJpeg || /\.png$/i.test(file.name)) || typeof createImageBitmap !== 'function') return file;
			try {
				const orientation = isJpeg ? jpegOrientation(await file.slice(0, 256 * 1024).arrayBuffer()) : 1;
				const bitmap = await createImageBitmap(file, {imageOrientation: 'from-image'});
				const edge = Math.max(bitmap.width, bitmap.height);
				if (orientation <= 1 && edge <= LIMITS.maxEdge && file.size <= LIMITS.downscaleBytes) {
					bitmap.close?.();
					return file;
				}
				const scale = Math.min(1, LIMITS.maxEdge / edge);
				const canvas = document.createElement('canvas');
				canvas.width = Math.max(1, Math.round(bitmap.width * scale));
				canvas.height = Math.max(1, Math.round(bitmap.height * scale));
				const context = canvas.getContext('2d');
				context.fillStyle = '#fff';
				context.fillRect(0, 0, canvas.width, canvas.height);
				context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
				bitmap.close?.();
				const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
				if (!blob) return file;
				const name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
				return new File([blob], name, {type: 'image/jpeg', lastModified: file.lastModified});
			} catch (error) {
				return file;
			}
		},

		sync(state) {
			try {
				const transfer = new DataTransfer();
				state.items.forEach(item => transfer.items.add(item.file));
				state.input.files = transfer.files;
				state.synced = state.items.length;
			} catch (error) {
				/* Older engines: uploadAll still reads the widget's own list. */
				state.synced = 0;
			}
		},

		renderRow(state, item) {
			const row = el('li', 'ill-uploader__row');
			row.dataset.state = item.status;
			const type = kind(item.original.name);
			if (type === 'image' && typeof URL !== 'undefined' && URL.createObjectURL) {
				const thumb = el('img', 'ill-uploader__thumb');
				thumb.alt = '';
				item.preview = URL.createObjectURL(item.original);
				thumb.src = item.preview;
				row.append(thumb);
			} else {
				row.append(el('span', 'ill-uploader__badge', ({pdf: 'PDF', heic: 'HEIC', image: 'IMG'})[type] || 'FILE'));
			}
			const details = el('div', 'ill-uploader__details');
			const name = el('span', 'ill-uploader__name', item.original.name);
			const meta = el('span', 'ill-uploader__meta small text-muted');
			const progress = el('progress', 'ill-uploader__progress');
			progress.max = 100;
			progress.value = 0;
			progress.setAttribute('aria-label', __('Upload progress for {0}', [item.original.name]));
			const status = el('span', 'ill-uploader__status small');
			details.append(name, meta, progress, status);
			const actions = el('div', 'ill-uploader__actions');
			const cancel = el('button', 'btn btn-sm btn-link ill-uploader__cancel', __('Cancel'));
			const retry = el('button', 'btn btn-sm btn-link ill-uploader__retry', __('Retry'));
			const remove = el('button', 'btn btn-sm btn-link text-danger ill-uploader__remove', __('Remove'));
			[cancel, retry, remove].forEach(button => {
				button.type = 'button';
				button.setAttribute('aria-label', button.textContent + ' ' + item.original.name);
			});
			cancel.addEventListener('click', () => { item.cancelled = true; item.xhr?.abort(); this.remove(state, item); });
			remove.addEventListener('click', () => this.remove(state, item));
			retry.addEventListener('click', () => {
				this.setStatus(state, item, 'pending');
				if (state.context) this.uploadItem(state, item, state.context).catch(() => {});
			});
			actions.append(cancel, retry, remove);
			row.append(details, actions);
			item.row = {row, meta, progress, status, cancel, retry, remove};
			state.list.append(row);
			this.setStatus(state, item, item.status);
		},

		setStatus(state, item, status, detail) {
			item.status = status;
			if (detail !== undefined) item.error = detail;
			const parts = item.row;
			if (!parts) return;
			parts.row.dataset.state = status;
			const receipt = state.context ? item.receipts.get(state.context.key) : null;
			const size = formatSize(item.file.size);
			parts.meta.textContent = receipt?.pages ? size + ' · ' + __('{0} pages', [receipt.pages]) : size;
			parts.progress.value = status === 'done' ? 100 : Math.round(item.progress * 100);
			parts.progress.hidden = !(status === 'uploading' || status === 'done');
			const labels = {
				preparing: __('Preparing…'), pending: __('Ready to upload'), uploading: __('Uploading…'),
				done: __('Uploaded'), failed: __('Failed: {0}', [item.error || __('upload interrupted')]),
			};
			parts.status.textContent = labels[status] || '';
			parts.cancel.hidden = status !== 'uploading';
			parts.retry.hidden = status !== 'failed';
			parts.remove.hidden = status === 'uploading';
		},

		remove(state, item) {
			state.items = state.items.filter(row => row !== item);
			item.row?.row.remove();
			this.revoke(item);
			this.sync(state);
		},

		revoke(item) {
			if (item.preview && URL.revokeObjectURL) URL.revokeObjectURL(item.preview);
			item.preview = null;
		},

		uploadItem(state, item, context) {
			const cached = item.receipts.get(context.key);
			if (cached) return Promise.resolve(cached);
			item.progress = 0;
			this.setStatus(state, item, 'uploading', '');
			return new Promise((resolve, reject) => {
				const xhr = new XMLHttpRequest();
				item.xhr = xhr;
				const body = new FormData();
				body.append('file', item.file, item.file.name);
				if (context.parentType) body.append('parent_type', context.parentType);
				if (context.parentName) body.append('parent_name', context.parentName);
				xhr.open('POST', UPLOAD_URL);
				xhr.setRequestHeader('X-Frappe-CSRF-Token', frappe.csrf_token);
				xhr.setRequestHeader('Accept', 'application/json');
				xhr.upload.onprogress = event => {
					if (!event.lengthComputable) return;
					item.progress = event.loaded / event.total;
					item.row.progress.value = Math.round(item.progress * 100);
				};
				xhr.onload = () => {
					item.xhr = null;
					let result = {};
					try { result = JSON.parse(xhr.responseText || '{}'); } catch (error) { result = {}; }
					if (xhr.status >= 200 && xhr.status < 300 && result.message?.success) {
						item.receipts.set(context.key, result.message);
						this.setStatus(state, item, 'done');
						resolve(result.message);
					} else {
						const reason = window.PortalUploads?.serverMessage(result) || __('the server rejected the file');
						this.setStatus(state, item, 'failed', reason);
						reject(new Error(reason));
					}
				};
				xhr.onerror = () => {
					item.xhr = null;
					this.setStatus(state, item, 'failed', __('connection interrupted'));
					reject(new Error(__('connection interrupted')));
				};
				xhr.onabort = () => {
					item.xhr = null;
					const error = new Error(__('Upload cancelled'));
					error.cancelled = true;
					reject(error);
				};
				xhr.send(body);
			});
		},

		/* Upload every accepted file (3 at a time) and return File ids in the order shown. */
		async uploadAll(input, parentType, parentName) {
			const state = input._portalUploader;
			if (state.synced && !(input.files || []).length) this.reset(input);
			await Promise.all(state.items.map(item => item.ready));
			const context = {parentType, parentName, key: (parentType || '') + ':' + (parentName || '')};
			state.context = context;
			const queue = state.items.slice();
			const failures = [];
			const worker = async () => {
				while (queue.length) {
					const item = queue.shift();
					if (!state.items.includes(item)) continue;
					try {
						await this.uploadItem(state, item, context);
					} catch (error) {
						if (!error.cancelled) failures.push(item);
					}
				}
			};
			await Promise.all(Array.from({length: Math.min(LIMITS.concurrency, queue.length)}, worker));
			if (failures.length) {
				state.message.textContent = __('{0} of {1} files did not upload. Retry or remove them, then submit again.', [failures.length, state.items.length]);
				throw new Error(__('Upload failed for {0}. Your draft is preserved; retry this file.', [failures[0].original.name]) + (failures[0].error ? ' ' + failures[0].error : ''));
			}
			state.message.textContent = '';
			if (state.items.some(item => !item.receipts.has(context.key))) return this.uploadAll(input, parentType, parentName);
			return state.items.map(item => item.receipts.get(context.key).file_id);
		},

		/* Enhance inputs rendered by portal pages (data-portal-uploader). */
		enhance(root) {
			(root || document).querySelectorAll('input[type="file"][data-portal-uploader]').forEach(input => this.attach(input));
		},
	};

	window.PortalUploader = PortalUploader;
	if (typeof document !== 'undefined') {
		if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => PortalUploader.enhance());
		else PortalUploader.enhance();
	}
})();
