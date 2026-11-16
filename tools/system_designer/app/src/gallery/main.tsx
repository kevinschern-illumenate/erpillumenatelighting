import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Portal tokens, so the gallery shows the components as the portal skins them.
import '../../../../../illumenate_lighting/public/css/portal.css';
import '../ui/tokens.css';
import '../ui/ui.css';
import { Gallery } from './Gallery';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Gallery />
  </StrictMode>,
);
