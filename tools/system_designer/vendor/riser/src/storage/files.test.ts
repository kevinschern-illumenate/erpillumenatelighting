import { afterEach, describe, expect, it, vi } from 'vitest';
import { createDraft } from '../schemas/workspace';
import { seedLibrary } from '../state/library-store';
import { RiserDatabase, saveCodeTable } from './database';
import { loadLibrary, saveLibrary } from './library';
import { parseProjectFile, saveProjectFile } from './project-file';
import { downloadFile } from '../lib/files';
vi.mock('../lib/files', () => ({ downloadFile: vi.fn(), filename: () => 'project' }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
describe('portable project and library data', () => {
  it('loads first-use seeds and legacy code-table overrides, then validates a saved snapshot', async () => {
    const db = new RiserDatabase(`files-${crypto.randomUUID()}`);
    try {
      const seed = seedLibrary();
      const table = { ...seed.codeTables[0]!, comment: 'Reviewed locally' };
      await saveCodeTable(table, db);
      expect((await loadLibrary(db)).codeTables[0]!.comment).toBe('Reviewed locally');
      seed.products[0]!.brand = 'Local';
      await saveLibrary(seed, db);
      expect((await loadLibrary(db)).products[0]!.brand).toBe('Local');
      await expect(saveLibrary({ bad: true }, db)).rejects.toThrow();
      expect((await loadLibrary(db)).products[0]!.brand).toBe('Local');
    } finally {
      await db.delete();
    }
  });
  it('round-trips project JSON, rejects incompatible versions and falls back to download', async () => {
    const p = createDraft();
    expect(parseProjectFile(JSON.stringify(p))).toEqual(p);
    expect(() => parseProjectFile(JSON.stringify({ ...p, schemaVersion: 999 }))).toThrow();
    vi.stubGlobal('window', {});
    expect(await saveProjectFile(p)).toBe(true);
    expect(downloadFile).toHaveBeenCalledWith('project.riser.json', JSON.stringify(p, null, 2));
  });
  it('writes and closes a chosen file, handles cancellation and propagates write failures', async () => {
    const p = createDraft();
    const writer = {
      write: vi.fn().mockResolvedValue(undefined),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const picker = vi.fn().mockResolvedValue({ createWritable: async () => writer });
    vi.stubGlobal('window', { showSaveFilePicker: picker });
    expect(await saveProjectFile(p)).toBe(true);
    expect(writer.write).toHaveBeenCalledWith(JSON.stringify(p, null, 2));
    expect(writer.close).toHaveBeenCalledOnce();
    picker.mockRejectedValueOnce(new DOMException('Cancelled', 'AbortError'));
    expect(await saveProjectFile(p)).toBe(false);
    writer.write.mockRejectedValueOnce(new Error('Disk full'));
    await expect(saveProjectFile(p)).rejects.toThrow('Disk full');
  });
});
