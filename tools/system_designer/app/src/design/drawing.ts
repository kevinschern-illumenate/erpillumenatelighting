import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { Project } from '@ill/core-schemas/project';
import type { Drawing } from '@ill/drawing/model';
import type { DrawingOptions } from '@ill/drawing/options';
import type { EngineResult } from '@ill/engine/model';

export interface DrawingInput {
  project: Project;
  library: LibrarySnapshot;
  result: EngineResult;
  options?: DrawingOptions;
}

type Reply = { id: number; drawing?: Drawing; error?: string };

/** Lays out the riser in a Web Worker when the browser has one, else on this thread (tests, old browsers). */
export function createDrawingRunner(): { run(input: DrawingInput): Promise<Drawing>; close(): void } {
  let worker: Worker | null = null;
  try {
    if (typeof Worker !== 'undefined')
      worker = new Worker(new URL('../workers/layout.worker.ts', import.meta.url), { type: 'module' });
  } catch {
    worker = null;
  }
  if (!worker)
    return {
      // Loaded on demand so the layout code stays out of the main bundle.
      run: async (input) =>
        (await import('@ill/drawing/build')).buildDrawing(input.project, input.library, input.result, input.options),
      close: () => undefined,
    };
  const pending = new Map<number, { resolve(drawing: Drawing): void; reject(error: Error): void }>();
  let next = 0;
  worker.onmessage = (event: MessageEvent<Reply>) => {
    const waiting = pending.get(event.data.id);
    pending.delete(event.data.id);
    if (!waiting) return;
    if (event.data.drawing) waiting.resolve(event.data.drawing);
    else waiting.reject(new Error(event.data.error ?? 'The riser could not be drawn'));
  };
  worker.onerror = () => {
    for (const waiting of pending.values()) waiting.reject(new Error('The riser could not be drawn'));
    pending.clear();
  };
  const active = worker;
  return {
    run(input) {
      const id = (next += 1);
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        active.postMessage({ id, ...input });
      });
    },
    close: () => active.terminate(),
  };
}

const LOGO_MAX_PX = 800;

/** A logo URL as a PNG data URL with its pixel size, or null when the browser cannot read it. */
export async function logoDataUrl(url: string): Promise<{ src: string; widthPx: number; heightPx: number } | null> {
  try {
    const image = new Image();
    image.decoding = 'async';
    image.src = url;
    await image.decode();
    // A title-block logo is under 3 in wide: 800 px is plenty and keeps the files small.
    const scale = Math.min(1, LOGO_MAX_PX / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(image.naturalWidth * scale);
    canvas.height = Math.round(image.naturalHeight * scale);
    const context = canvas.getContext('2d');
    if (!context || !canvas.width || !canvas.height) return null;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return { src: canvas.toDataURL('image/png'), widthPx: canvas.width, heightPx: canvas.height };
  } catch {
    return null;
  }
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as BufferSource);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
