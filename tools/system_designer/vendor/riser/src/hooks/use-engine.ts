import { useEffect, useMemo } from 'react';
import { calculate } from '../engine/calculate';
import { useProjectStore } from '../state/project-store';
import { useLibraryStore } from '../state/library-store';

export function useEngine() {
  const project = useProjectStore((s) => s.draft);
  const library = useLibraryStore((s) => s.library);
  const result = useMemo(() => calculate(project, library), [project, library]);
  useEffect(() => {
    if (JSON.stringify(project.wireTagMap) === JSON.stringify(result.wireTagMap)) return;
    const history = useProjectStore.temporal.getState();
    history.pause();
    useProjectStore.getState().updateProject({ wireTagMap: result.wireTagMap });
    history.resume();
  }, [project.wireTagMap, result.wireTagMap]);
  return { project, library, result };
}
