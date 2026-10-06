import { buildDrawing } from '../drawing/build';
import { ProjectSchema } from '../schemas/project';
import { LibrarySnapshotSchema } from '../schemas/library';
import { EngineResultSchema } from '../engine/model';
self.onmessage = async (
  event: MessageEvent<{ id: number; project: unknown; library: unknown; result: unknown }>,
) => {
  const { id, project, library, result } = event.data;
  try {
    self.postMessage({
      id,
      drawing: await buildDrawing(
        ProjectSchema.parse(project),
        LibrarySnapshotSchema.parse(library),
        EngineResultSchema.parse(result),
      ),
    });
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : 'Layout failed' });
  }
};
