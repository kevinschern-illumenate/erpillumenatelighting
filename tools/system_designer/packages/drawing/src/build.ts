import type { Project } from '@ill/core-schemas/project';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { EngineResult } from '@ill/engine/model';
import { DrawingSchema, type Drawing } from './model';
import { layoutProject } from './layout/pages';
import { composeSheets } from './sheet/compose';
import type { DrawingOptions } from './options';
import { drawnRuns } from './wires';

export async function buildDrawing(
  project: Project,
  library: LibrarySnapshot,
  result: EngineResult,
  options: DrawingOptions = {},
): Promise<Drawing> {
  const start = performance.now();
  if (result.messages.some((m) => m.code === 'INCOMPLETE_SPEC'))
    throw new Error(
      'Drawing unavailable: this project uses products marked Needs specifications. Complete those products in Libraries before generating the drawing.',
    );
  const drawn = drawnRuns(result);
  // The client diagram has its own schedule page, so its diagrams use the paper the schedules would.
  const laidOut =
    options.style === 'client'
      ? { ...project, settings: { ...project.settings, showSchedules: false } }
      : project;
  const diagrams = await layoutProject(laidOut, library, drawn, options);
  const sheets = composeSheets(diagrams, project, library, result, options, drawn.members);
  sheets.forEach((sheet) => {
    sheet.fontFamily = project.settings.drawingFont;
  });
  return DrawingSchema.parse({
    sheets,
    elapsedMs: performance.now() - start,
    warnings: sheets.flatMap((s) => s.layoutWarnings.map((w) => `${s.number}: ${w}`)),
  });
}
