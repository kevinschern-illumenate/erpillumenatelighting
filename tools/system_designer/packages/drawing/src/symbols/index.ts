import symbol0 from './panel';
import symbol1 from './psu';
import symbol2 from './cc-driver';
import symbol3 from './decoder';
import symbol4 from './console';
import symbol5 from './gateway';
import symbol6 from './network';
import symbol7 from './wireless-tx';
import symbol8 from './wireless-rx';
import symbol9 from './opto';
import symbol10 from './terminator';
import symbol11 from './pixel';
import symbol12 from './lutron';
import symbol13 from './keypad';
import symbol14 from './dimmer';
import symbol15 from './relay';
import symbol16 from './junction';
import symbol17 from './distribution';
import symbol18 from './tape';
import symbol19 from './linear';
import symbol20 from './downlight';
import symbol21 from './landscape';
import symbol22 from './offsheet';
import converter from './converter';
import type { CatalogItem } from '@ill/core-schemas/catalog';
export const symbols = [
  symbol0,
  symbol1,
  symbol2,
  symbol3,
  symbol4,
  symbol5,
  symbol6,
  symbol7,
  symbol8,
  symbol9,
  symbol10,
  symbol11,
  symbol12,
  symbol13,
  symbol14,
  symbol15,
  symbol16,
  symbol17,
  symbol18,
  symbol19,
  symbol20,
  symbol21,
  symbol22,
  converter,
];

export function symbolFor(item?: CatalogItem, source = false) {
  if (source) return symbols[0]!;
  const category = item?.category;
  const ids: Record<string, string> = {
    psu: 'psu',
    driver: 'cc-driver',
    'dmx-decoder': 'decoder',
    'dmx-controller': 'console',
    'dmx-0-10v-converter': 'converter',
    'sacn-gateway': 'gateway',
    'network-switch': 'network',
    'wireless-tx': 'wireless-tx',
    'wireless-rx': 'wireless-rx',
    'opto-splitter': 'opto',
    'pixel-controller': 'pixel',
    'lutron-module': 'lutron',
    keypad: 'keypad',
    '0-10v-dimmer': 'dimmer',
    relay: 'relay',
    'junction-box': 'junction',
    'distribution-block': 'distribution',
    enclosure: 'junction',
    tape: 'tape',
    fixture: 'downlight',
  };
  return (
    symbols.find((s) => s.id === ids[category ?? '']) ?? symbols.find((s) => s.id === 'junction')!
  );
}
