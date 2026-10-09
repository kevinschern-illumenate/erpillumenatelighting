import type { SymbolDef } from '../model';
import type { Bounds } from './router';

export type LayoutNode = {
  id: string;
  tag: string;
  symbol: SymbolDef;
  partition: number;
  terminal?: boolean;
  enclosure: string;
  control: boolean;
  panel: string;
  circuit: string;
  psu: string;
};
export type LayoutResult = {
  width: number;
  height: number;
  nodes: Map<string, Bounds>;
};
