import { buildDrawing } from '@ill/drawing/build';
import type { DrawingOptions } from '@ill/drawing/options';
import { ProjectSchema } from '@ill/core-schemas/project';
import { LibrarySnapshotSchema } from '@ill/core-schemas/library';
import { EngineResultSchema } from '@ill/engine/model';
self.onmessage = async (
  event: MessageEvent<{ id: number; project: unknown; library: unknown; result: unknown; options?: DrawingOptions }>,
) => {
  const { id, project, library, result, options } = event.data;
  try {
    self.postMessage({
      id,
      drawing: await buildDrawing(
        ProjectSchema.parse(project),
        LibrarySnapshotSchema.parse(library),
        EngineResultSchema.parse(result),
        options,
      ),
    });
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : 'Layout failed' });
  }
};
