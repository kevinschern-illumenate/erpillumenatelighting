import { mergeSpecOverrides, type CatalogItem } from '../schemas/catalog';
import type { Project, Source, Equipment, Load, ValidationMessage } from '../schemas/project';
import type { Protocol } from '../schemas/common';
import { message } from './messages';

export type GraphNode = {
  id: string;
  tag: string;
  entity: Source | Equipment | Load;
  kind: 'source' | 'equipment' | 'load';
  item?: CatalogItem;
};
export type Edge = {
  id: string;
  from: string;
  to: string;
  fromPort?: string;
  toPort?: string;
  lengthFt: number;
  protocol?: Protocol;
  entityRef: string;
  env: Equipment['env'];
  universe?: number;
};
export function buildGraph(project: Project, products: CatalogItem[]) {
  const nodes = new Map<string, GraphNode>();
  const aliases = new Map<string, string>();
  const messages: ValidationMessage[] = [];
  for (const [kind, entities] of [
    ['source', project.sources],
    ['equipment', project.equipment],
    ['load', project.loads],
  ] as const)
    for (const entity of entities) {
      const tag = 'tag' in entity ? entity.tag : entity.typeTag;
      let item =
        'catalogId' in entity ? products.find((p) => p.id === entity.catalogId) : undefined;
      if ('catalogId' in entity && !item)
        messages.push(
          message(
            'UNRESOLVED_REF',
            'error',
            entity.id,
            `Catalog item ${entity.catalogId} was not found.`,
          ),
        );
      if (
        item &&
        item.specs.kind !== 'incomplete' &&
        'specOverrides' in entity &&
        entity.specOverrides
      ) {
        try {
          item = mergeSpecOverrides(item, entity.specOverrides);
        } catch {
          messages.push(
            message(
              'INVALID_SPEC',
              'error',
              entity.id,
              'Specification overrides are incompatible with the catalog item.',
            ),
          );
          item = undefined;
        }
      }
      if (item?.specs.kind === 'incomplete')
        messages.push(
          message(
            'INCOMPLETE_SPEC',
            'error',
            entity.id,
            `${item.sku}: needs specifications (${item.specs.missingFields.join(', ')}). Complete this product in Libraries before calculation.`,
          ),
        );
      if (item?.isExample)
        messages.push(
          message(
            'EXAMPLE_PRODUCT_IN_USE',
            'warning',
            entity.id,
            `${item.sku}: EXAMPLE – replace with real data.`,
          ),
        );
      if (kind === 'load' && item && !['tape', 'fixture', 'incomplete'].includes(item.specs.kind))
        messages.push(
          message(
            'INVALID_SPEC',
            'error',
            entity.id,
            'A load requires a tape or fixture catalog item.',
          ),
        );
      if (kind === 'equipment' && item && 'category' in entity && entity.category !== item.category)
        messages.push(
          message(
            'INVALID_SPEC',
            'error',
            entity.id,
            'Equipment category and catalog category differ.',
          ),
        );
      const node: GraphNode = { id: entity.id, tag, entity, kind, item };
      nodes.set(entity.id, node);
      aliases.set(entity.id, entity.id);
      if ('tag' in entity) aliases.set(entity.tag, entity.id);
    }
  const resolve = (ref: string) => aliases.get(ref);
  const power: Edge[] = [];
  const control: Edge[] = [];
  function edge(
    target: Edge[],
    fromRef: { ref: string; port?: string },
    toRef: { ref: string; port?: string },
    rest: Omit<Edge, 'from' | 'to' | 'fromPort' | 'toPort'>,
  ) {
    const from = resolve(fromRef.ref);
    const to = resolve(toRef.ref);
    if (!from || !to) {
      messages.push(
        message(
          'UNRESOLVED_REF',
          'error',
          rest.entityRef,
          `Unresolved ${!from ? fromRef.ref : toRef.ref}.`,
        ),
      );
      return;
    }
    target.push({ ...rest, from, to, fromPort: fromRef.port, toPort: toRef.port });
  }
  for (const e of project.equipment) {
    edge(
      power,
      e.fedFrom,
      { ref: e.id },
      { id: `power:${e.id}`, lengthFt: e.feedLengthFt, entityRef: e.id, env: e.env },
    );
    if (e.controlFrom) {
      const spec = nodes.get(e.id)?.item?.specs;
      const protocol = e.dmx
        ? 'DMX512'
        : spec && 'protocolIn' in spec
          ? (spec.protocolIn.find((p) => p !== 'none') ?? 'DMX512')
          : 'DMX512';
      // An explicit physical control link replaces the shorthand incoming link
      // for that receiver/protocol, so editing a chain never retains a home run.
      if (
        project.controlLinks.some(
          (link) => resolve(link.to.ref) === e.id && link.protocol === protocol,
        )
      )
        continue;
      edge(
        control,
        e.controlFrom,
        { ref: e.id },
        {
          id: `control:${e.id}`,
          lengthFt: e.controlLengthFt ?? 0,
          entityRef: e.id,
          env: e.env,
          protocol,
          universe: e.dmx?.universe,
        },
      );
    }
  }
  for (const load of project.loads)
    edge(
      power,
      load.fedFrom,
      { ref: load.id },
      { id: `power:${load.id}`, lengthFt: load.homeRunLengthFt, entityRef: load.id, env: load.env },
    );
  for (const link of project.controlLinks)
    edge(control, link.from, link.to, {
      id: `control:${link.id}`,
      lengthFt: link.lengthFt,
      protocol: link.protocol,
      entityRef: link.id,
      env: link.env,
      universe: link.universe,
    });
  // Identical explicit and implicit links represent one physical connection.
  const deduped = [
    ...new Map(
      control.map((e) => [
        `${e.from}|${e.to}|${e.fromPort ?? ''}|${e.toPort ?? ''}|${e.protocol}`,
        e,
      ]),
    ).values(),
  ];
  const cycleNodes = new Set<string>();
  for (const [name, edges] of [
    ['power', power],
    ['control', deduped],
  ] as const) {
    const state = new Map<string, number>();
    const stack: string[] = [];
    function visit(id: string) {
      if (state.get(id) === 2) return;
      if (state.get(id) === 1) {
        for (const n of stack.slice(stack.indexOf(id))) cycleNodes.add(n);
        messages.push(
          message(
            'CYCLE',
            'error',
            id,
            `A cycle exists in the ${name} graph at ${nodes.get(id)?.tag}.`,
          ),
        );
        return;
      }
      state.set(id, 1);
      stack.push(id);
      for (const e of edges.filter((e) => e.from === id)) visit(e.to);
      stack.pop();
      state.set(id, 2);
    }
    for (const id of nodes.keys()) visit(id);
  }
  return { nodes, power, control: deduped, messages, cycleNodes, resolve };
}
export type Graph = ReturnType<typeof buildGraph>;
