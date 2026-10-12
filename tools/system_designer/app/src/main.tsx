import { mount } from './mount';

export { mount };
export type { MountOptions } from './mount';

declare global {
  interface Window {
    IllSystemDesigner: { mount: typeof mount };
  }
}

window.IllSystemDesigner = { mount };
