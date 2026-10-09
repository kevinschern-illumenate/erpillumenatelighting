import { ArrowRight, Boxes, Cable, FileDown, PanelsTopLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

const stages = {
  tables: {
    icon: Boxes,
    phase: '03',
    title: 'Build the system, row by row.',
    text: 'Sources, equipment, loads, and control links will be entered here, with tag pickers and row validation.',
    items: ['Sources', 'Equipment', 'Loads', 'Control links'],
  },
  review: {
    icon: Cable,
    phase: '04',
    title: 'Every run, every calculation.',
    text: 'The calculation engine will produce wire recommendations, voltage drop, loading checks, DMX patching, and a bill of materials.',
    items: ['Derived runs', 'Loading', 'DMX patch', 'Issues'],
  },
  drawing: {
    icon: PanelsTopLeft,
    phase: '05–07',
    title: 'From system data to drawing sheets.',
    text: 'The shared drawing model, symbols, layout, and sheet composition will be built in the drawing phases.',
    items: ['Symbols', 'Layout', 'Sheet composition'],
  },
  export: {
    icon: FileDown,
    phase: '08–09',
    title: 'A drawing you can take into CAD.',
    text: 'Vector PDF with layers and native DXF with blocks and attributes will serialize the same drawing model.',
    items: ['Layered PDF', 'Native DXF', 'CSV schedules', 'Project JSON'],
  },
} as const;

export type FuturePage = keyof typeof stages;

export function PhasePage({ page }: { page: FuturePage }) {
  const stage = stages[page];
  const Icon = stage.icon;
  return (
    <section className="phase-page panel">
      <div className="phase-page-icon">
        <Icon size={32} strokeWidth={1.5} />
      </div>
      <div className="eyebrow">PLANNED · PHASE {stage.phase}</div>
      <h2>{stage.title}</h2>
      <p>{stage.text}</p>
      <div className="phase-items">
        {stage.items.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
      <div className="phase-boundary">
        Phase 1 includes project schemas, validated libraries, and local autosave. This workspace
        becomes active in its scheduled phase.
      </div>
      <Button asChild variant="outline">
        <Link to="/project">
          Back to project <ArrowRight />
        </Link>
      </Button>
    </section>
  );
}
