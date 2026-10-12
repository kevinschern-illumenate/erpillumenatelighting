export function downloadFile(
  name: string,
  content: string | Uint8Array,
  type = 'application/json',
) {
  const bytes = typeof content === 'string' ? content : new Uint8Array(content).buffer;
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function filename(value: string) {
  return value.replace(/[^\w .-]/g, '_').trim() || 'riser';
}
