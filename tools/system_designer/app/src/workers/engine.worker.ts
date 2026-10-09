import { checkDesign, type CheckInput } from '@ill/engine/designCheck';

// Design checks off the main thread (plan WP-3.5), so typing and dragging stay responsive.
self.onmessage = (event: MessageEvent<{ id: number; input: CheckInput }>) => {
  const { id, input } = event.data;
  try {
    self.postMessage({ id, check: checkDesign(input) });
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : 'The checks could not run' });
  }
};
