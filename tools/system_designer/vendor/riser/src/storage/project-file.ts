import { migrateDraft, type Draft } from '../schemas/workspace';
import { downloadFile, filename } from '../lib/files';

type Writable = { write: (data: string) => Promise<void>; close: () => Promise<void> };
type Handle = { createWritable: () => Promise<Writable> };
type PickerWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<Handle>;
};
export function parseProjectFile(text: string): Draft {
  return migrateDraft(JSON.parse(text));
}
export async function saveProjectFile(project: Draft): Promise<boolean> {
  const data = JSON.stringify(migrateDraft(project), null, 2);
  const name = `${filename(project.meta.name)}.riser.json`;
  const picker = (window as PickerWindow).showSaveFilePicker;
  if (!picker) {
    downloadFile(name, data);
    return true;
  }
  try {
    const handle = await picker({
      suggestedName: name,
      types: [{ description: 'Riser project', accept: { 'application/json': ['.riser.json'] } }],
    });
    const writer = await handle.createWritable();
    await writer.write(data);
    await writer.close();
    return true;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return false;
    throw e;
  }
}
