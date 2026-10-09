import {
  AWG_SMALL_TO_LARGE,
  CatalogCategorySchema,
  ProtocolSchema,
  RunTypeSchema,
} from '../../schemas/common';

export type Field = {
  key: string;
  label: string;
  type?:
    'number' | 'select' | 'boolean' | 'text' | 'textarea' | 'choices' | 'list' | 'rows' | 'voltage';
  options?: readonly string[];
  labels?: Record<string, string>;
  numeric?: boolean;
  optional?: boolean;
  hint?: string;
  scale?: number;
  fields?: Field[];
  itemLabel?: string;
  when?: { key: string; value: string };
};
export type Section = { title: string; hint?: string; fields: Field[] };
const n = (key: string, label: string, optional = false, hint?: string): Field => ({
  key,
  label,
  type: 'number',
  optional,
  hint,
});
const t = (key: string, label: string, optional = false): Field => ({ key, label, optional });
const s = (key: string, label: string, options: readonly string[], optional = false): Field => ({
  key,
  label,
  type: 'select',
  options,
  optional,
});
const b = (key: string, label: string, optional = false): Field => ({
  key,
  label,
  type: 'boolean',
  optional,
});
const l = (key: string, label: string, optional = false): Field => ({
  key,
  label,
  type: 'list',
  optional,
});
const protocols = (key: string, label: string, optional = false): Field => ({
  key,
  label,
  type: 'choices',
  options: ProtocolSchema.options,
  optional,
  labels: {
    none: 'Non-dimming',
    'phase-forward': 'Forward phase (TRIAC)',
    'phase-reverse': 'Reverse phase (ELV)',
  },
});
const terminals = (minOptional = false, maxOptional = false): Field[] => [
  s('terminalMinAwg', 'Smallest terminal conductor (AWG)', AWG_SMALL_TO_LARGE, minOptional),
  s('terminalMaxAwg', 'Largest terminal conductor (AWG)', AWG_SMALL_TO_LARGE, maxOptional),
];
const input: Field[] = [
  s('inputType', 'Input current type', ['AC', 'DC']),
  s('inputPhase', 'Input phase', ['1PH', '3PH'], true),
  n('inputVMin', 'Minimum input voltage (V)'),
  n('inputVMax', 'Maximum input voltage (V)'),
];
const inputCurrent: Field[] = [
  n('maxInputA', 'Maximum input current (A)', true),
  n(
    'maxInputAAtV',
    'Input voltage for current rating (V)',
    true,
    'Required when maximum input current is entered.',
  ),
];
const pf = (optional = false): Field => ({
  ...n('powerFactor', 'Power factor', optional),
  hint: 'Enter the manufacturer’s factor from 0 to 1, for example 0.95.',
});
export const categoryLabels: Record<string, string> = {
  psu: 'Power supply',
  driver: 'LED driver',
  'dmx-decoder': 'DMX decoder',
  'dmx-controller': 'DMX controller',
  'dmx-0-10v-converter': 'DMX to 0–10 V converter',
  'wireless-tx': 'Wireless transmitter',
  'wireless-rx': 'Wireless receiver',
  'pixel-controller': 'Pixel controller',
  'opto-splitter': 'Opto splitter',
  'sacn-gateway': 'sACN gateway',
  'network-switch': 'Network switch',
  'lutron-module': 'Lutron module',
  '0-10v-dimmer': '0–10 V dimmer',
  keypad: 'Keypad',
  relay: 'Relay',
  'junction-box': 'Junction box',
  enclosure: 'Enclosure',
  'distribution-block': 'Distribution block',
  tape: 'LED tape / neon',
  fixture: 'Fixture / LED sheet',
};
export const productDetails: Field[] = [
  t('sku', 'SKU / item code'),
  t('brand', 'Brand'),
  t('model', 'Model / product name'),
  { ...s('category', 'Product category', CatalogCategorySchema.options), labels: categoryLabels },
  { key: 'description', label: 'Description', type: 'textarea' },
  t('datasheetUrl', 'Datasheet URL', true),
  t('erpItemCode', 'ERPNext item code', true),
  { ...b('isExample', 'Example product'), hint: 'Only choose Yes for synthetic example data.' },
];
export const sourceFields: Field[] = [
  s(
    'source.kind',
    'Source type',
    ['example', 'user-supplied', 'manufacturer', 'code-reference', 'authored-draft'],
    true,
  ),
  t('source.reference', 'Source reference', true),
  t('source.url', 'Source URL', true),
  { ...t('source.checkedOn', 'Date checked', true), hint: 'YYYY-MM-DD' },
  { key: 'source.note', label: 'Source notes', type: 'textarea', optional: true },
];
const powerSections: Section[] = [
  {
    title: 'Electrical input',
    fields: [
      ...input,
      {
        ...n('efficiency', 'Efficiency (%)'),
        scale: 100,
        hint: 'Enter a percentage, for example 90. This is separate from the usable load factor.',
      },
      pf(),
      ...inputCurrent,
      n('inrushA', 'Inrush current (A)', true),
      n('maxUnitsPer20ABreaker', 'Maximum units per 20 A breaker', true),
    ],
  },
  {
    title: 'Power output',
    fields: [
      {
        ...s('outputType', 'Output mode', ['CV', 'CC']),
        labels: { CV: 'Constant voltage', CC: 'Constant current' },
      },
      s('outputCurrent', 'Output current type', ['AC', 'DC'], true),
      n('ratedW', 'Rated output power (W)'),
      n('outputV', 'Output voltage (V)', true, 'Required for constant-voltage output.'),
      n('outputmA', 'Output current (mA)', true, 'Required for constant-current output.'),
      n('outputVMin', 'Minimum compliance voltage (V)', true),
      n('outputVMax', 'Maximum compliance voltage (V)', true),
      {
        key: 'outputs',
        label: 'Output banks',
        type: 'rows',
        itemLabel: 'output',
        hint: 'Use the actual terminal name and verified Class 2 listing for each output.',
        fields: [
          t('name', 'Output name'),
          n('maxW', 'Maximum power (W)'),
          b('class2', 'Class 2 listed'),
        ],
      },
    ],
  },
  {
    title: 'Control and installation',
    fields: [
      protocols('dimming', 'Dimming protocols'),
      ...terminals(),
      l('listings', 'Listings / certifications'),
    ],
  },
];
export const specSections: Record<string, Section[]> = {
  psu: powerSections,
  driver: powerSections,
  decoder: [
    {
      title: 'Electrical ratings',
      fields: [
        {
          ...s('powerType', 'Power input and output', ['DC', 'AC']),
          hint: 'Choose AC for a line-voltage DMX phase dimmer; choose DC for a low-voltage LED decoder. Existing decoder products remain DC.',
        },
        n('inputVMin', 'Minimum input voltage (V)'),
        n('inputVMax', 'Maximum input voltage (V)'),
        n('channels', 'Number of channels'),
        n('maxAPerChannel', 'Maximum current per channel (A)'),
        n('maxATotal', 'Maximum total current (A)'),
        n('maxWPerChannel', 'Maximum load per channel (W)', true),
        n('maxWTotal', 'Maximum total load (W)', true),
        ...terminals(true),
      ],
    },
    {
      title: 'Control',
      fields: [
        {
          ...s('outputDimming', 'AC output dimming method', ['phase-forward', 'phase-reverse']),
          labels: {
            'phase-forward': 'Forward phase (TRIAC)',
            'phase-reverse': 'Reverse phase (ELV)',
          },
          hint: 'Required for AC decoders. Select the actual configured primary-side dimming method; connected fixtures must support it.',
        },
        n('dmxFootprint', 'DMX address footprint'),
        n('unitLoad', 'DMX unit load'),
        {
          ...b('dmxThru', 'Allow DMX daisy chaining / THRU'),
          hint: 'Allows DMX to continue from this decoder to the next receiver on the same segment. Verify the THRU or loop-through terminal arrangement; disable for an end-only receiver.',
        },
        protocols('protocolIn', 'Input protocols'),
        protocols('protocolOut', 'Output protocols', true),
      ],
    },
  ],
  controller: [
    {
      title: 'Electrical input',
      fields: [
        ...input.map((field) =>
          field.key === 'inputType'
            ? { ...field, options: ['AC', 'DC', 'AC/DC'], labels: { 'AC/DC': 'AC or DC' } }
            : field,
        ),
        ...[
          n('acInputVMin', 'AC minimum input voltage (V)', true),
          n('acInputVMax', 'AC maximum input voltage (V)', true),
          n('dcInputVMin', 'DC minimum input voltage (V)', true),
          n('dcInputVMax', 'DC maximum input voltage (V)', true),
        ].map((field) => ({
          ...field,
          when: { key: 'inputType', value: 'AC/DC' },
          hint: 'For different AC/DC ranges, enter both limits for that supply type. Otherwise the common input range above applies.',
        })),
        n(
          'ownPowerW',
          'Device power consumption (W)',
          false,
          'Power used by this device itself. Connected fixtures have their own power feeds.',
        ),
        pf(true),
        ...inputCurrent,
        {
          ...s('maxInputAType', 'Current rating supply type', ['AC', 'DC'], true),
          when: { key: 'inputType', value: 'AC/DC' },
          hint: 'Required for an entered maximum input current on an AC/DC device.',
        },
        ...terminals(true),
      ],
    },
    {
      title: 'Control and ports',
      fields: [
        protocols('protocolIn', 'Input protocols'),
        protocols('protocolOut', 'Output protocols'),
        {
          key: 'ports',
          label: 'Physical ports',
          type: 'rows',
          itemLabel: 'port',
          fields: [
            t('name', 'Port name'),
            s('direction', 'Direction', ['in', 'out', 'bidirectional']),
            s('protocol', 'Protocol', ProtocolSchema.options),
            n(
              'maxDevices',
              'Maximum controlled devices',
              true,
              'Optional verified receiver limit for this output. Fixture quantities count individually.',
            ),
          ],
        },
        n('dmxFootprint', 'DMX address footprint', true),
        n('unitLoad', 'DMX unit load', true),
        b('startsNewSegment', 'Starts a new DMX segment'),
        n('maxUniverses', 'Maximum universes', true),
        n('maxPixels', 'Maximum pixels', true),
        n('maxDataLengthFt', 'Maximum data length (ft)', true),
        n('maxBusDevices', 'Maximum bus devices', true),
      ],
    },
  ],
  tape: [
    {
      title: 'Tape ratings',
      fields: [
        { ...s('voltage', 'Nominal voltage (V)', ['12', '24', '48']), numeric: true },
        s('drive', 'Drive type', ['CV', 'CV-CC-IC']),
        n('wPerFtMax', 'Maximum power (W/ft)'),
        {
          ...s('powerBasis', 'Power rating basis', ['max-operating', 'all-channel-max']),
          labels: {
            'max-operating': 'Maximum operating power',
            'all-channel-max': 'All channels at maximum',
          },
          hint: 'Maximum operating power is the combined allowed demand; keep individual channel limits separate.',
        },
        n('minOperatingV', 'Minimum operating voltage (V)'),
        {
          ...b('freeCutting', 'Free-cutting tape'),
          hint: 'Yes: no fixed cut interval. No: enter the manufacturer’s cut interval below.',
        },
        {
          ...n('cutIntervalIn', 'Cut interval (in)'),
          hint: 'Required only for tape with fixed cutting points.',
        },
        n('reelLengthFt', 'Reel length (ft)', true),
        n('maxRunFtSingleFeed', 'Maximum single-feed run (ft)'),
        n('maxRunFtDoubleFeed', 'Maximum double-feed run (ft)'),
      ],
    },
    {
      title: 'Channels',
      fields: [
        n('channels', 'Number of channels'),
        l('channelMap', 'Channel names'),
        {
          ...l('channelWPerFtMax', 'Channel power limits (W/ft)', true),
          numeric: true,
          hint: 'One maximum for each channel, in the same order as the channel names.',
        },
        n(
          'maxSimultaneousPct',
          'Combined simultaneous limit (%)',
          false,
          'Sum across channels: 100% permits one full channel’s equivalent; two channels at full power total 200%.',
        ),
      ],
    },
    {
      title: 'Pixel data (if applicable)',
      hint: 'Leave all three fields blank for non-pixel tape.',
      fields: [
        s('pixel.protocol', 'Pixel chipset', ['WS2811', 'WS2815', 'SK6812', 'SPI-other'], true),
        n('pixel.pixelsPerFt', 'Pixels per foot', true),
        n('pixel.ampsPerPixelMax', 'Maximum current per pixel (A)', true),
      ],
    },
  ],
  fixture: [
    {
      title: 'Fixture ratings',
      fields: [
        {
          ...s('voltageClass', 'Voltage class', ['line', 'low']),
          labels: { line: 'Line voltage', low: 'Low voltage' },
        },
        { key: 'inputV', label: 'Input voltage (V)', type: 'voltage' },
        s('inputType', 'Input current type', ['AC', 'DC'], true),
        s('inputPhase', 'Input phase', ['1PH', '3PH'], true),
        n('watts', 'Power per fixture / whole sheet (W)'),
        s('drive', 'Drive mode', ['CV', 'CC'], true),
        n('mA', 'Constant-current rating (mA)', true),
        pf(true),
        ...inputCurrent,
        b('integralDriver', 'Integral driver'),
        protocols('dimming', 'Dimming protocols'),
      ],
    },
  ],
  accessory: [
    {
      title: 'Accessory specifications',
      fields: [
        s('function', 'Function', [
          'junction',
          'enclosure',
          'distribution',
          'termination',
          'other',
        ]),
        n('ratedV', 'Voltage rating (V)', true),
        n('ratedA', 'Current rating (A)', true),
        l('ports', 'Port names'),
        l('listings', 'Listings / certifications'),
        ...terminals(true, true),
        { key: 'notes', label: 'Installation notes', type: 'textarea', optional: true },
      ],
    },
  ],
};
export const wireSections: Section[] = [
  {
    title: 'Wire details',
    fields: [
      t('name', 'Wire / cable name'),
      s('category', 'Wire category', [
        'building-wire',
        'cable-assembly',
        'class2-power',
        'data',
        'control',
        'landscape',
        'flex-cord',
      ]),
      t('riserLabel', 'Drawing label'),
      t('listing', 'Listing'),
      b('isExample', 'Example wire'),
      b('verify', 'Needs verification'),
      { key: 'notes', label: 'Notes', type: 'textarea' },
      {
        key: 'applications',
        label: 'Applications',
        type: 'choices',
        options: RunTypeSchema.options,
      },
    ],
  },
  {
    title: 'Ratings and environment',
    fields: [
      n('ratedV', 'Voltage rating (V)'),
      { ...s('tempRatingC', 'Temperature rating (°C)', ['60', '75', '90', '105']), numeric: true },
      b('plenum', 'Plenum rated'),
      b('riser', 'Riser rated'),
      b('wet', 'Wet rated'),
      b('directBurial', 'Direct burial'),
      b('sunlightResistant', 'Sunlight resistant'),
      b('shielded', 'Shielded'),
      n('impedanceOhm', 'Impedance (Ω)', true),
      n('resistanceOhmPerKft', 'Resistance (Ω / 1,000 ft)', true),
      n('ampacityA', 'Ampacity (A)', true),
      n('odIn', 'Outside diameter (in)', true),
      n('costPerFt', 'Cost per foot', true),
      s('ampacityBasis', 'Ampacity basis', [
        '310.16',
        '402.5-fallback',
        'manufacturer',
        'example',
        'not-applicable',
      ]),
      {
        ...s('ampacityTempLimitC', 'Ampacity temperature limit (°C)', ['60', '75', '90'], true),
        numeric: true,
      },
      n('resistanceReferenceTempC', 'Resistance reference temperature (°C)', true),
    ],
  },
  {
    title: 'Conductor groups',
    fields: [
      {
        key: 'conductors',
        label: 'Conductor groups',
        type: 'rows',
        itemLabel: 'conductor group',
        hint: 'Each row describes conductors of one size and role. A data pair has two individual conductors.',
        fields: [
          n('count', 'Conductor count'),
          s('awg', 'Size (AWG)', AWG_SMALL_TO_LARGE),
          s('material', 'Material', ['Cu', 'Al']),
          s('stranding', 'Construction', ['solid', 'stranded']),
          s('role', 'Role', ['power', 'ground', 'signal', 'data-pair', 'channel']),
          l('colors', 'Conductor colors', true),
          n('resistanceOhmPerKft', 'Group resistance (Ω / 1,000 ft)', true),
          n('ampacityA', 'Group ampacity (A)', true),
        ],
      },
    ],
  },
  {
    title: 'Manufacturer references',
    hint: 'Reference entries remain marked for verification.',
    fields: [
      {
        key: 'manufacturerRefChecks',
        label: 'Manufacturer references',
        type: 'rows',
        itemLabel: 'reference',
        fields: [
          t('reference', 'Manufacturer / part number'),
          t('sourceUrl', 'Reference URL', true),
        ],
      },
    ],
  },
];

export function intendedKind(category: unknown): string {
  if (['psu', 'driver', 'tape', 'fixture'].includes(String(category))) return String(category);
  if (category === 'dmx-decoder') return 'decoder';
  if (['junction-box', 'enclosure', 'distribution-block'].includes(String(category)))
    return 'accessory';
  return 'controller';
}
