import { useState, useMemo, useRef, useEffect } from 'react';
import {
  Download, Copy, Plus, Trash2, RotateCcw, FileCode2, AlertTriangle,
  CheckCircle2, Lightbulb, ChevronDown, ChevronUp, ArrowUp, ArrowDown,
  Eye, EyeOff, Sparkles, Info,
} from 'lucide-react';
import {
  blankFixtureState, EXAMPLE_FIXTURE,
  serializeFixtureYaml, validateFixture,
  FIXTURE_TABS, renderFixtureTab, fixtureCounts,
} from './fixtures.jsx';

/* ============================================================================
   FONTS + THEME
   ============================================================================ */
const FONTS_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Work+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
`;

export const T = {
  bg:          '#FAF7F2',
  paper:       '#FFFFFF',
  ink:         '#1A1612',
  muted:       '#6B5F52',
  subtle:      '#938676',
  border:      '#E8E1D4',
  borderStr:   '#D4CBB8',
  accent:      '#B45309',
  accentSoft:  '#F3E5C7',
  accentBg:    '#FDF4E2',
  danger:      '#9B2C2C',
  dangerBg:    '#FBEDED',
  success:     '#3F6D48',
  successBg:   '#ECF3ED',
  code:        '#211C17',
  codeInk:     '#E8DFC9',
  codeAccent:  '#E0A458',
  codeString:  '#B8C48F',
  codeKey:     '#C9B48A',
  codeNum:     '#D99C6A',
  codeBool:    '#B88AB0',
  codeComment: '#6C6254',
};

export const fontDisplay = `'Fraunces', 'Georgia', serif`;
export const fontBody    = `'Work Sans', -apple-system, sans-serif`;
export const fontMono    = `'JetBrains Mono', 'Menlo', monospace`;

/* ============================================================================
   EXAMPLE / DEFAULT STATE
   ============================================================================ */
const EMPTY_WEBFLOW_STEPS_TAPE = [
  'Environment Rating', 'CCT', 'Output Level', 'Length', 'Feed Direction',
];
const EMPTY_WEBFLOW_STEPS_NEON = [
  'Environment Rating', 'CCT', 'Output Level', 'IP Rating',
  'Mounting Method', 'Finish', 'Length', 'Feed Direction',
];

const blankState = (productType) => ({
  productType,
  mode: 'new-family',
  seriesName: '',
  seriesCode: '',
  supplier: '',
  brand: 'ilLumenate Lighting',
  warrantyDays: '1825',
  tapeSpecs: [],
  tapeOfferings: [],
  tapeNeonTemplates: [],
  neonSubmittalMapping: { cloneFromTemplate: '' },
  tapeNeonWebflow: {
    productCategory: productType === 'neon' ? 'led-neon' : 'led-tape',
    sublabel: '',
    beamAngle: '110.0',
    operatingTempMinC: '-40',
    operatingTempMaxC: '60',
    l70LifeHours: '50000',
    warrantyYears: '5',
    configuratorSteps: productType === 'neon'
      ? [...EMPTY_WEBFLOW_STEPS_NEON]
      : [...EMPTY_WEBFLOW_STEPS_TAPE],
  },
  ...blankFixtureState(),
});

const EXAMPLE_TAPE = {
  productType: 'tape',
  mode: 'new-family',
  seriesName: 'Flex',
  seriesCode: 'FX',
  supplier: 'Linea Lighting Co., Limited',
  brand: 'ilLumenate Lighting',
  warrantyDays: '1825',
  tapeSpecs: [
    {
      itemCode: 'TAPE-FS-24V-4.4W', ledPackage: 'FS', productCategory: 'LED Tape',
      inputVoltage: '24V DC', wattsPerFoot: '4.4', lumensPerFoot: '400',
      criTypical: '97', ledPitchMm: '11.1', pcbMounting: 'Adhesive Backed',
      pcbFinish: 'White', cutIncrementMm: '55.55', isFreeCutting: false,
      leaderCableItem: '', dimmingProtocols: ['TRIAC', '0-10V', 'DALI'],
    },
    {
      itemCode: 'TAPE-SW-24V-2.2W', ledPackage: 'SW', productCategory: 'LED Tape',
      inputVoltage: '24V DC', wattsPerFoot: '2.2', lumensPerFoot: '200',
      criTypical: '90', ledPitchMm: '22.2', pcbMounting: 'Adhesive Backed',
      pcbFinish: 'White', cutIncrementMm: '66.66', isFreeCutting: false,
      leaderCableItem: '', dimmingProtocols: ['TRIAC', '0-10V'],
    },
  ],
  tapeOfferings: [
    { tapeSpec: 'TAPE-FS-24V-4.4W', cct: '2700K', cri: '97', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'TAPE-FS-24V-4.4W', cct: '3000K', cri: '97', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'TAPE-FS-24V-4.4W', cct: '3500K', cri: '97', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'TAPE-FS-24V-4.4W', cct: '4000K', cri: '97', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'TAPE-SW-24V-2.2W', cct: '3000K', cri: '90', sdcm: '3', ledPackage: 'SW', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'TAPE-SW-24V-2.2W', cct: '4000K', cri: '90', sdcm: '3', ledPackage: 'SW', outputLevel: 'Standard', wattsPerFtOverride: '' },
  ],
  tapeNeonTemplates: [
    {
      templateCode: 'ILL-FX-FS', templateName: 'Flex Full Spectrum',
      productCategory: 'LED Tape', series: 'Flex',
      defaultTapeSpec: 'TAPE-FS-24V-4.4W',
      basePriceMsrp: '25.00', pricePerFtMsrp: '8.50',
      pricingLengthBasis: 'L_tape_cut', leaderAllowanceMm: '15',
      allowedTapeSpecs: [{ tapeSpec: 'TAPE-FS-24V-4.4W', isDefault: true, environmentRating: 'Dry' }],
      allowedOptions: [
        { optionType: 'CCT', value: '2700K', isDefault: true, msrpAdder: '0' },
        { optionType: 'CCT', value: '3000K', isDefault: false, msrpAdder: '0' },
        { optionType: 'CCT', value: '3500K', isDefault: false, msrpAdder: '0' },
        { optionType: 'CCT', value: '4000K', isDefault: false, msrpAdder: '0' },
        { optionType: 'Output Level', value: 'Standard', isDefault: true, msrpAdder: '0' },
        { optionType: 'Environment Rating', value: 'Dry', isDefault: true, msrpAdder: '0' },
        { optionType: 'Feed Direction', value: 'Single Feed', isDefault: true, msrpAdder: '0' },
        { optionType: 'Feed Direction', value: 'Dual Feed', isDefault: false, msrpAdder: '5.00' },
      ],
    },
    {
      templateCode: 'ILL-FX-SW', templateName: 'Flex Static White',
      productCategory: 'LED Tape', series: 'Flex',
      defaultTapeSpec: 'TAPE-SW-24V-2.2W',
      basePriceMsrp: '20.00', pricePerFtMsrp: '6.00',
      pricingLengthBasis: 'L_tape_cut', leaderAllowanceMm: '15',
      allowedTapeSpecs: [{ tapeSpec: 'TAPE-SW-24V-2.2W', isDefault: true, environmentRating: 'Dry' }],
      allowedOptions: [
        { optionType: 'CCT', value: '3000K', isDefault: true, msrpAdder: '0' },
        { optionType: 'CCT', value: '4000K', isDefault: false, msrpAdder: '0' },
        { optionType: 'Output Level', value: 'Standard', isDefault: true, msrpAdder: '0' },
        { optionType: 'Environment Rating', value: 'Dry', isDefault: true, msrpAdder: '0' },
        { optionType: 'Feed Direction', value: 'Single Feed', isDefault: true, msrpAdder: '0' },
      ],
    },
  ],
  neonSubmittalMapping: { cloneFromTemplate: '' },
  tapeNeonWebflow: {
    productCategory: 'led-tape', sublabel: '', beamAngle: '110.0',
    operatingTempMinC: '-40', operatingTempMaxC: '60',
    l70LifeHours: '50000', warrantyYears: '5',
    configuratorSteps: [...EMPTY_WEBFLOW_STEPS_TAPE],
  },
};

const EXAMPLE_NEON = {
  productType: 'neon',
  mode: 'new-family',
  seriesName: 'NeonFlex',
  seriesCode: 'NF',
  supplier: 'Linea Lighting Co., Limited',
  brand: 'ilLumenate Lighting',
  warrantyDays: '1825',
  tapeSpecs: [
    {
      itemCode: 'NEON-FS-24V-6W', ledPackage: 'FS', productCategory: 'LED Neon',
      inputVoltage: '24V DC', wattsPerFoot: '6.0', lumensPerFoot: '500',
      criTypical: '95', ledPitchMm: '8.3', pcbMounting: 'Channel Mounted',
      pcbFinish: 'White', cutIncrementMm: '50.0', isFreeCutting: false,
      leaderCableItem: '', dimmingProtocols: ['TRIAC', '0-10V', 'DALI'],
    },
  ],
  tapeOfferings: [
    { tapeSpec: 'NEON-FS-24V-6W', cct: '2700K', cri: '95', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'NEON-FS-24V-6W', cct: '3000K', cri: '95', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'NEON-FS-24V-6W', cct: '4000K', cri: '95', sdcm: '3', ledPackage: 'FS', outputLevel: 'Standard', wattsPerFtOverride: '' },
    { tapeSpec: 'NEON-FS-24V-6W', cct: '2700K', cri: '95', sdcm: '3', ledPackage: 'FS', outputLevel: 'High', wattsPerFtOverride: '9.0' },
  ],
  tapeNeonTemplates: [
    {
      templateCode: 'ILL-NF-FS', templateName: 'NeonFlex Full Spectrum',
      productCategory: 'LED Neon', series: 'NeonFlex',
      defaultTapeSpec: 'NEON-FS-24V-6W',
      basePriceMsrp: '50.00', pricePerFtMsrp: '15.00',
      pricingLengthBasis: 'L_tape_cut', leaderAllowanceMm: '20',
      allowedTapeSpecs: [{ tapeSpec: 'NEON-FS-24V-6W', isDefault: true, environmentRating: 'Wet' }],
      allowedOptions: [
        { optionType: 'CCT', value: '2700K', isDefault: true, msrpAdder: '0' },
        { optionType: 'CCT', value: '3000K', isDefault: false, msrpAdder: '0' },
        { optionType: 'CCT', value: '4000K', isDefault: false, msrpAdder: '0' },
        { optionType: 'Output Level', value: 'Standard', isDefault: true, msrpAdder: '0' },
        { optionType: 'Output Level', value: 'High', isDefault: false, msrpAdder: '3.00' },
        { optionType: 'Environment Rating', value: 'Wet', isDefault: true, msrpAdder: '0' },
        { optionType: 'Environment Rating', value: 'Dry', isDefault: false, msrpAdder: '0' },
        { optionType: 'IP Rating', value: 'IP67', isDefault: true, msrpAdder: '0' },
        { optionType: 'IP Rating', value: 'IP68', isDefault: false, msrpAdder: '5.00' },
        { optionType: 'Feed Direction', value: 'Single Feed', isDefault: true, msrpAdder: '0' },
        { optionType: 'Feed Direction', value: 'Dual Feed', isDefault: false, msrpAdder: '10.00' },
        { optionType: 'Mounting Method', value: 'Surface Mount', isDefault: true, msrpAdder: '0' },
        { optionType: 'Mounting Method', value: 'Channel Mount', isDefault: false, msrpAdder: '2.50' },
        { optionType: 'Finish', value: 'White', isDefault: true, msrpAdder: '0' },
        { optionType: 'Finish', value: 'Black', isDefault: false, msrpAdder: '0' },
        { optionType: 'Endcap Style', value: 'Solid', isDefault: true, msrpAdder: '0' },
        { optionType: 'Endcap Style', value: 'Feed Through', isDefault: false, msrpAdder: '2.00' },
      ],
    },
  ],
  neonSubmittalMapping: { cloneFromTemplate: '' },
  tapeNeonWebflow: {
    productCategory: 'led-neon', sublabel: '', beamAngle: '110.0',
    operatingTempMinC: '-40', operatingTempMaxC: '60',
    l70LifeHours: '50000', warrantyYears: '5',
    configuratorSteps: [...EMPTY_WEBFLOW_STEPS_NEON],
  },
};

/* ============================================================================
   CHOICES / ENUMS
   ============================================================================ */
const VOLTAGE_CHOICES = ['12V DC', '24V DC', '36V DC', '48V DC', '120V AC', '277V AC'];
const PCB_MOUNTING_CHOICES = ['Adhesive Backed', 'Channel Mounted', 'Free Standing', 'None'];
const PCB_FINISH_CHOICES = ['White', 'Black', 'Copper', 'Aluminum'];
const DIMMING_PROTOCOL_CHOICES = ['TRIAC', '0-10V', 'DALI', 'ELV', 'PWM', 'Forward Phase', 'Reverse Phase'];
const LED_PACKAGE_CHOICES = ['FS', 'SW', 'TW', 'RGBW', 'RGB', 'RGBWW', 'Pixel'];
const OUTPUT_LEVEL_CHOICES = [
  '100 lm/ft', '150 lm/ft', '200 lm/ft', '250 lm/ft', '300 lm/ft',
  '400 lm/ft', '500 lm/ft', '750 lm/ft', '1000 lm/ft', '1250 lm/ft', '1500 lm/ft'
];
const PRICING_BASIS_CHOICES = ['L_tape_cut', 'L_fixture_cut', 'L_fixture_total'];
const ENV_RATING_CHOICES = ['Dry', 'Damp', 'Wet'];

const OPTION_TYPE_SUGGESTIONS_TAPE = [
  'CCT', 'Output Level', 'Environment Rating', 'Feed Direction', 'CRI',
];
const OPTION_TYPE_SUGGESTIONS_NEON = [
  'CCT', 'Output Level', 'Environment Rating', 'IP Rating',
  'Mounting Method', 'Finish', 'Endcap Style', 'Feed Direction', 'CRI',
];

const OPTION_VALUE_SUGGESTIONS = {
  'CCT': ['1800K', '2200K', '2700K', '3000K', '3500K', '4000K', '5000K', '6500K', 'RGBW', 'Tunable White'],
  'Output Level': OUTPUT_LEVEL_CHOICES,
  'Environment Rating': ENV_RATING_CHOICES,
  'IP Rating': ['IP20', 'IP54', 'IP65', 'IP66', 'IP67', 'IP68'],
  'Mounting Method': ['Surface Mount', 'Channel Mount', 'Recessed', 'Pendant', 'Wall Mount'],
  'Finish': ['White', 'Black', 'Silver', 'Bronze', 'Natural Aluminum'],
  'Endcap Style': ['Solid', 'Feed Through', 'Open', 'Custom'],
  'Feed Direction': ['Single Feed', 'Dual Feed', 'Center Feed'],
  'CRI': ['80', '90', '95', '97'],
};

/* ============================================================================
   YAML SERIALIZER
   ============================================================================ */
const YAML_SPECIAL_BOOLS = new Set([
  'true', 'false', 'True', 'False', 'TRUE', 'FALSE',
  'yes', 'no', 'Yes', 'No', 'YES', 'NO',
  'null', 'Null', 'NULL', '~', 'on', 'off', 'On', 'Off',
]);

export function isNumericString(s) {
  return typeof s === 'string' && s.length > 0 && /^-?\d+(\.\d+)?$/.test(s);
}

function needsQuoting(s) {
  if (s === '') return true;
  if (YAML_SPECIAL_BOOLS.has(s)) return true;
  if (/^\s|\s$/.test(s)) return true;
  // starts with a character that has YAML meaning
  if (/^[-?:,\[\]{}#&*!|>'"%@`]/.test(s)) return true;
  // starts with digit → would parse as number
  if (/^[0-9]/.test(s)) return true;
  // contains YAML structural chars
  if (/[:#]/.test(s) && /(:\s|\s#)/.test(' ' + s + ' ')) return true;
  if (/[,\[\]{}]/.test(s)) return true;
  return false;
}

export function yamlScalar(v) {
  if (v === null || v === undefined) return '""';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string') {
    if (v === '') return '""';
    if (isNumericString(v)) return v; // output as number-like, unquoted
    if (needsQuoting(v)) return JSON.stringify(v);
    return v;
  }
  return JSON.stringify(String(v));
}

export function indent(n) { return '  '.repeat(n); }

// Render a sequence of objects as a YAML list with per-object block.
export function yamlListOfObjects(items, level, renderItem) {
  if (!items || items.length === 0) return `${indent(level)}[]\n`;
  return items.map((it) => {
    // Render the item's fields at level+1, then replace the first line's
    // leading indent with a `- ` bullet at the list's own level.
    const body = renderItem(it, level + 1);
    const lines = body.split('\n');
    const firstIdx = lines.findIndex(l => l.trim().length > 0);
    if (firstIdx === -1) return '';
    const stripCount = (level + 1) * 2;
    const dashPrefix = indent(level) + '- ';
    lines[firstIdx] = dashPrefix + lines[firstIdx].substring(stripCount);
    return lines.join('\n');
  }).join('');
}

export function yamlSimpleList(items, level) {
  if (!items || items.length === 0) return `${indent(level)}[]\n`;
  return items.map((v) => `${indent(level)}- ${yamlScalar(v)}\n`).join('');
}

function renderTapeSpec(spec, level) {
  let out = '';
  out += `${indent(level)}item_code: ${yamlScalar(spec.itemCode)}\n`;
  out += `${indent(level)}led_package: ${yamlScalar(spec.ledPackage)}\n`;
  out += `${indent(level)}product_category: ${yamlScalar(spec.productCategory)}\n`;
  out += `${indent(level)}input_voltage: ${yamlScalar(spec.inputVoltage)}\n`;
  out += `${indent(level)}watts_per_foot: ${yamlScalar(spec.wattsPerFoot)}\n`;
  out += `${indent(level)}lumens_per_foot: ${yamlScalar(spec.lumensPerFoot)}\n`;
  out += `${indent(level)}cri_typical: ${yamlScalar(spec.criTypical)}\n`;
  out += `${indent(level)}led_pitch_mm: ${yamlScalar(spec.ledPitchMm)}\n`;
  out += `${indent(level)}pcb_mounting: ${yamlScalar(spec.pcbMounting)}\n`;
  out += `${indent(level)}pcb_finish: ${yamlScalar(spec.pcbFinish)}\n`;
  out += `${indent(level)}cut_increment_mm: ${yamlScalar(spec.cutIncrementMm)}\n`;
  out += `${indent(level)}is_free_cutting: ${yamlScalar(!!spec.isFreeCutting)}\n`;
  out += `${indent(level)}leader_cable_item: ${yamlScalar(spec.leaderCableItem || '')}\n`;
  out += `${indent(level)}dimming_protocols:\n`;
  out += yamlSimpleList(spec.dimmingProtocols || [], level + 1);
  return out;
}

function renderOffering(off, level) {
  let out = '';
  out += `${indent(level)}tape_spec: ${yamlScalar(off.tapeSpec)}\n`;
  out += `${indent(level)}cct: ${yamlScalar(off.cct)}\n`;
  out += `${indent(level)}cri: ${yamlScalar(off.cri)}\n`;
  out += `${indent(level)}sdcm: ${yamlScalar(off.sdcm)}\n`;
  out += `${indent(level)}led_package: ${yamlScalar(off.ledPackage)}\n`;
  out += `${indent(level)}output_level: ${yamlScalar(off.outputLevel)}\n`;
  if (off.wattsPerFtOverride && String(off.wattsPerFtOverride).trim() !== '') {
    out += `${indent(level)}watts_per_ft_override: ${yamlScalar(off.wattsPerFtOverride)}\n`;
  }
  return out;
}

function renderAllowedTapeSpec(a, level) {
  let out = '';
  out += `${indent(level)}tape_spec: ${yamlScalar(a.tapeSpec)}\n`;
  if (a.isDefault) out += `${indent(level)}is_default: true\n`;
  out += `${indent(level)}environment_rating: ${yamlScalar(a.environmentRating)}\n`;
  return out;
}

function renderAllowedOption(o, level) {
  let out = '';
  out += `${indent(level)}option_type: ${yamlScalar(o.optionType)}\n`;
  out += `${indent(level)}value: ${yamlScalar(o.value)}\n`;
  if (o.isDefault) out += `${indent(level)}is_default: true\n`;
  out += `${indent(level)}msrp_adder: ${yamlScalar(o.msrpAdder)}\n`;
  return out;
}

function renderTemplate(tpl, level) {
  let out = '';
  out += `${indent(level)}template_code: ${yamlScalar(tpl.templateCode)}\n`;
  out += `${indent(level)}template_name: ${yamlScalar(tpl.templateName)}\n`;
  out += `${indent(level)}product_category: ${yamlScalar(tpl.productCategory)}\n`;
  out += `${indent(level)}series: ${yamlScalar(tpl.series)}\n`;
  out += `${indent(level)}default_tape_spec: ${yamlScalar(tpl.defaultTapeSpec)}\n`;
  out += `${indent(level)}base_price_msrp: ${yamlScalar(tpl.basePriceMsrp)}\n`;
  out += `${indent(level)}price_per_ft_msrp: ${yamlScalar(tpl.pricePerFtMsrp)}\n`;
  out += `${indent(level)}pricing_length_basis: ${yamlScalar(tpl.pricingLengthBasis)}\n`;
  out += `${indent(level)}leader_allowance_mm: ${yamlScalar(tpl.leaderAllowanceMm)}\n`;

  out += `${indent(level)}allowed_tape_specs:\n`;
  out += yamlListOfObjects(tpl.allowedTapeSpecs || [], level + 1, renderAllowedTapeSpec);

  out += `${indent(level)}allowed_options:\n`;
  // Group options by type for visual readability (match example format)
  const groups = groupOptionsByType(tpl.allowedOptions || []);
  let optionsBody = '';
  for (const { type, items } of groups) {
    optionsBody += `${indent(level + 1)}# ${type}\n`;
    optionsBody += yamlListOfObjects(items, level + 1, renderAllowedOption);
  }
  out += optionsBody;
  return out;
}

function groupOptionsByType(options) {
  const order = [];
  const byType = new Map();
  for (const o of options) {
    const t = o.optionType || '(unset)';
    if (!byType.has(t)) { byType.set(t, []); order.push(t); }
    byType.get(t).push(o);
  }
  return order.map(type => ({ type, items: byType.get(type) }));
}

function serializeYaml(s) {
  if (s.productType === 'fixture') return serializeFixtureYaml(s);
  const isNeon = s.productType === 'neon';
  let out = '';

  out += `# ${isNeon ? 'LED Neon' : 'LED Tape'} Configuration — generated by ilLumenate YAML Builder\n`;
  out += `# Usage: python -m tools.fixture_builder --product-type ${s.productType} --config <path-to-this-file> --output ./output/${(s.seriesCode || 'series').toLowerCase()}/\n`;
  out += `\n`;
  out += `product_type: ${yamlScalar(s.productType)}\n`;
  out += `mode: ${yamlScalar(s.mode || 'new-family')}\n`;
  out += `series_name: ${yamlScalar(s.seriesName)}\n`;
  out += `series_code: ${yamlScalar(s.seriesCode)}\n`;
  out += `\n`;
  out += `supplier: ${yamlScalar(s.supplier)}\n`;
  out += `brand: ${yamlScalar(s.brand)}\n`;
  out += `warranty_days: ${yamlScalar(s.warrantyDays)}\n`;
  out += `\n`;

  out += `# ── Tape Spec Definitions ─────────────────────────────────────────────\n`;
  out += `tape_specs:\n`;
  out += yamlListOfObjects(s.tapeSpecs, 1, renderTapeSpec);
  out += `\n`;

  out += `# ── Tape Offerings ────────────────────────────────────────────────────\n`;
  out += `tape_offerings:\n`;
  out += yamlListOfObjects(s.tapeOfferings, 1, renderOffering);
  out += `\n`;

  out += `# ── Tape/Neon Templates ──────────────────────────────────────────────\n`;
  out += `tape_neon_templates:\n`;
  out += yamlListOfObjects(s.tapeNeonTemplates, 1, renderTemplate);
  out += `\n`;

  out += `# ── Neon Submittal Mapping ───────────────────────────────────────────\n`;
  out += `neon_submittal_mapping:\n`;
  out += `  clone_from_template: ${yamlScalar(s.neonSubmittalMapping.cloneFromTemplate || '')}\n`;
  out += `\n`;

  out += `# ── Webflow ──────────────────────────────────────────────────────────\n`;
  const w = s.tapeNeonWebflow;
  out += `tape_neon_webflow:\n`;
  out += `  product_category: ${yamlScalar(w.productCategory)}\n`;
  out += `  sublabel: ${yamlScalar(w.sublabel || '')}\n`;
  out += `  beam_angle: ${yamlScalar(w.beamAngle)}\n`;
  out += `  operating_temp_min_c: ${yamlScalar(w.operatingTempMinC)}\n`;
  out += `  operating_temp_max_c: ${yamlScalar(w.operatingTempMaxC)}\n`;
  out += `  l70_life_hours: ${yamlScalar(w.l70LifeHours)}\n`;
  out += `  warranty_years: ${yamlScalar(w.warrantyYears)}\n`;
  out += `  configurator_steps:\n`;
  out += yamlSimpleList(w.configuratorSteps || [], 2);

  return out;
}

/* ============================================================================
   VALIDATION
   ============================================================================ */
function validate(s) {
  if (s.productType === 'fixture') return validateFixture(s);
  const issues = [];
  const specCodes = new Set();
  const dupSpecCodes = new Set();

  if (!s.seriesName?.trim()) issues.push({ level: 'warn', text: 'Series name is empty.' });
  if (!s.seriesCode?.trim()) issues.push({ level: 'warn', text: 'Series code is empty.' });
  if (!s.supplier?.trim()) issues.push({ level: 'warn', text: 'Supplier is empty.' });
  if (!s.brand?.trim()) issues.push({ level: 'warn', text: 'Brand is empty.' });
  if (!isNumericString(String(s.warrantyDays)) || Number(s.warrantyDays) <= 0) {
    issues.push({ level: 'warn', text: 'Warranty days should be a positive number.' });
  }

  if (!s.tapeSpecs?.length) issues.push({ level: 'error', text: 'At least one tape spec is required.' });

  s.tapeSpecs?.forEach((spec, i) => {
    if (!spec.itemCode?.trim()) issues.push({ level: 'error', text: `Tape spec #${i + 1}: item_code is required.` });
    else if (specCodes.has(spec.itemCode)) dupSpecCodes.add(spec.itemCode);
    else specCodes.add(spec.itemCode);

    if (!spec.ledPackage?.trim()) issues.push({ level: 'warn', text: `Tape spec "${spec.itemCode || `#${i + 1}`}": led_package is empty.` });
    if (!spec.inputVoltage?.trim()) issues.push({ level: 'warn', text: `Tape spec "${spec.itemCode || `#${i + 1}`}": input_voltage is empty.` });
    if (!(spec.dimmingProtocols?.length > 0)) {
      issues.push({ level: 'warn', text: `Tape spec "${spec.itemCode || `#${i + 1}`}": no dimming protocols selected.` });
    }
  });
  dupSpecCodes.forEach(c => issues.push({ level: 'error', text: `Duplicate tape spec item_code: "${c}".` }));

  s.tapeOfferings?.forEach((off, i) => {
    if (!off.tapeSpec) issues.push({ level: 'error', text: `Offering #${i + 1}: tape_spec is not selected.` });
    else if (!specCodes.has(off.tapeSpec)) {
      issues.push({ level: 'error', text: `Offering #${i + 1}: references undefined spec "${off.tapeSpec}".` });
    }
    if (!off.cct?.trim()) issues.push({ level: 'warn', text: `Offering #${i + 1}: CCT is empty.` });
  });

  const tplCodes = new Set();
  const dupTpl = new Set();
  s.tapeNeonTemplates?.forEach((tpl, i) => {
    if (!tpl.templateCode?.trim()) issues.push({ level: 'error', text: `Template #${i + 1}: template_code is required.` });
    else if (tplCodes.has(tpl.templateCode)) dupTpl.add(tpl.templateCode);
    else tplCodes.add(tpl.templateCode);

    if (!tpl.templateName?.trim()) issues.push({ level: 'warn', text: `Template "${tpl.templateCode || `#${i + 1}`}": name is empty.` });
    if (tpl.defaultTapeSpec && !specCodes.has(tpl.defaultTapeSpec)) {
      issues.push({ level: 'error', text: `Template "${tpl.templateCode}": default_tape_spec references undefined "${tpl.defaultTapeSpec}".` });
    }
    if (!tpl.allowedTapeSpecs?.length) {
      issues.push({ level: 'error', text: `Template "${tpl.templateCode}": at least one allowed_tape_specs entry required.` });
    }
    tpl.allowedTapeSpecs?.forEach((a, ai) => {
      if (a.tapeSpec && !specCodes.has(a.tapeSpec)) {
        issues.push({ level: 'error', text: `Template "${tpl.templateCode}" allowed_tape_specs #${ai + 1}: references undefined "${a.tapeSpec}".` });
      }
    });
    const atsDefaults = (tpl.allowedTapeSpecs || []).filter(a => a.isDefault).length;
    if ((tpl.allowedTapeSpecs?.length || 0) > 0 && atsDefaults !== 1) {
      issues.push({ level: 'warn', text: `Template "${tpl.templateCode}": exactly one allowed_tape_specs should be default (found ${atsDefaults}).` });
    }
    // exactly one default per option_type
    const byType = new Map();
    (tpl.allowedOptions || []).forEach(o => {
      if (!o.optionType) return;
      if (!byType.has(o.optionType)) byType.set(o.optionType, 0);
      if (o.isDefault) byType.set(o.optionType, byType.get(o.optionType) + 1);
    });
    byType.forEach((count, type) => {
      if (count !== 1) {
        issues.push({ level: 'warn', text: `Template "${tpl.templateCode}" option "${type}": expected exactly one default (found ${count}).` });
      }
    });
  });
  dupTpl.forEach(c => issues.push({ level: 'error', text: `Duplicate template_code: "${c}".` }));

  if (s.neonSubmittalMapping?.cloneFromTemplate &&
      !tplCodes.has(s.neonSubmittalMapping.cloneFromTemplate)) {
    issues.push({ level: 'warn', text: `Submittal mapping clones unknown template "${s.neonSubmittalMapping.cloneFromTemplate}".` });
  }

  return issues;
}

/* ============================================================================
   SMALL UI PRIMITIVES
   ============================================================================ */
export function Field({ label, hint, children, required, wide }) {
  return (
    <label className={`flex flex-col gap-1.5 ${wide ? 'col-span-2' : ''}`}>
      <span className="flex items-baseline gap-1.5" style={{ fontFamily: fontBody, fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', color: T.muted, textTransform: 'uppercase' }}>
        {label}
        {required && <span style={{ color: T.accent }}>*</span>}
        {hint && <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: 'none', color: T.subtle, fontSize: 11 }}>— {hint}</span>}
      </span>
      {children}
    </label>
  );
}

export function TextInput({ value, onChange, placeholder, monospace, list, ...rest }) {
  return (
    <input
      type="text"
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      list={list}
      style={{
        fontFamily: monospace ? fontMono : fontBody,
        fontSize: monospace ? 13 : 14,
        color: T.ink,
        background: T.paper,
        border: `1px solid ${T.border}`,
        borderRadius: 6,
        padding: '9px 12px',
        outline: 'none',
        transition: 'border-color 0.15s',
      }}
      onFocus={e => e.target.style.borderColor = T.accent}
      onBlur={e => e.target.style.borderColor = T.border}
      {...rest}
    />
  );
}

export function NumInput({ value, onChange, placeholder, step }) {
  return (
    <input
      type="text"
      inputMode="decimal"
      value={value ?? ''}
      onChange={e => {
        const v = e.target.value;
        // allow empty, digits, one minus sign, one dot
        if (v === '' || /^-?\d*\.?\d*$/.test(v)) onChange(v);
      }}
      placeholder={placeholder}
      style={{
        fontFamily: fontMono,
        fontSize: 13,
        color: T.ink,
        background: T.paper,
        border: `1px solid ${T.border}`,
        borderRadius: 6,
        padding: '9px 12px',
        outline: 'none',
        transition: 'border-color 0.15s',
      }}
      onFocus={e => e.target.style.borderColor = T.accent}
      onBlur={e => e.target.style.borderColor = T.border}
    />
  );
}

export function Select({ value, onChange, options, placeholder, allowEmpty }) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      style={{
        fontFamily: fontBody,
        fontSize: 14,
        color: value ? T.ink : T.subtle,
        background: T.paper,
        border: `1px solid ${T.border}`,
        borderRadius: 6,
        padding: '9px 12px',
        outline: 'none',
        appearance: 'none',
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B5F52' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'right 10px center',
        paddingRight: 30,
      }}
    >
      {allowEmpty && <option value="">{placeholder || '— Select —'}</option>}
      {options.map(opt => {
        const v = typeof opt === 'string' ? opt : opt.value;
        const l = typeof opt === 'string' ? opt : opt.label;
        return <option key={v} value={v}>{l}</option>;
      })}
    </select>
  );
}

export function Checkbox({ checked, onChange, label }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2"
      style={{
        fontFamily: fontBody,
        fontSize: 13,
        color: T.ink,
        background: 'transparent',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
      }}
    >
      <span style={{
        width: 18, height: 18, borderRadius: 4,
        border: `1.5px solid ${checked ? T.accent : T.borderStr}`,
        background: checked ? T.accent : T.paper,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s',
      }}>
        {checked && <CheckCircle2 size={12} style={{ color: T.paper }} strokeWidth={3} />}
      </span>
      {label}
    </button>
  );
}

export function MultiSelect({ value, onChange, options }) {
  const set = new Set(value || []);
  const toggle = (opt) => {
    const next = new Set(set);
    if (next.has(opt)) next.delete(opt); else next.add(opt);
    onChange(Array.from(next));
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => {
        const on = set.has(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            style={{
              fontFamily: fontBody,
              fontSize: 12,
              fontWeight: 500,
              padding: '6px 11px',
              borderRadius: 999,
              border: `1px solid ${on ? T.accent : T.border}`,
              background: on ? T.accentBg : T.paper,
              color: on ? T.accent : T.muted,
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}

export function Button({ children, onClick, variant = 'default', size = 'md', icon: Icon, disabled, title }) {
  const sizes = {
    sm: { pad: '6px 10px', fs: 12, icon: 14 },
    md: { pad: '9px 14px', fs: 13, icon: 15 },
    lg: { pad: '11px 18px', fs: 14, icon: 16 },
  };
  const z = sizes[size];
  const variants = {
    default: { bg: T.paper, bd: T.borderStr, fg: T.ink, hoverBg: T.accentBg },
    primary: { bg: T.ink, bd: T.ink, fg: T.bg, hoverBg: T.accent },
    accent:  { bg: T.accent, bd: T.accent, fg: T.paper, hoverBg: '#8B4008' },
    ghost:   { bg: 'transparent', bd: 'transparent', fg: T.muted, hoverBg: T.accentBg },
    danger:  { bg: 'transparent', bd: 'transparent', fg: T.danger, hoverBg: T.dangerBg },
  };
  const v = variants[variant];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        fontFamily: fontBody, fontSize: z.fs, fontWeight: 500,
        padding: z.pad, borderRadius: 6,
        border: `1px solid ${v.bd}`, background: v.bg, color: v.fg,
        display: 'inline-flex', alignItems: 'center', gap: 6,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => !disabled && (e.currentTarget.style.background = v.hoverBg)}
      onMouseLeave={e => !disabled && (e.currentTarget.style.background = v.bg)}
    >
      {Icon && <Icon size={z.icon} />}
      {children}
    </button>
  );
}

/* ============================================================================
   SECTION CARD
   ============================================================================ */
export function Section({ title, subtitle, count, children, right }) {
  return (
    <section style={{
      background: T.paper,
      border: `1px solid ${T.border}`,
      borderRadius: 12,
      padding: 24,
      marginBottom: 16,
    }}>
      <header className="flex items-start justify-between mb-5">
        <div>
          <h2 style={{
            fontFamily: fontDisplay,
            fontSize: 22,
            fontWeight: 500,
            color: T.ink,
            letterSpacing: '-0.01em',
            margin: 0,
            display: 'flex',
            alignItems: 'baseline',
            gap: 10,
          }}>
            {title}
            {typeof count === 'number' && (
              <span style={{
                fontFamily: fontMono, fontSize: 12, fontWeight: 400,
                color: T.subtle, letterSpacing: 0,
              }}>
                {count}
              </span>
            )}
          </h2>
          {subtitle && (
            <p style={{
              fontFamily: fontBody, fontSize: 13, color: T.muted,
              margin: '4px 0 0 0', maxWidth: 540, lineHeight: 1.5,
            }}>{subtitle}</p>
          )}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

export function Card({ children, accent = false }) {
  return (
    <div style={{
      background: accent ? T.accentBg : T.bg,
      border: `1px solid ${accent ? T.accentSoft : T.border}`,
      borderRadius: 10,
      padding: 18,
      marginBottom: 12,
    }}>
      {children}
    </div>
  );
}

/* ============================================================================
   PRODUCT INFO SECTION
   ============================================================================ */
function ProductInfoSection({ s, upd }) {
  return (
    <Section
      title="Product Info"
      subtitle="Top-level metadata about the series. The series code becomes part of item codes and the output folder name."
    >
      <div className="grid grid-cols-2 gap-4">
        <Field label="Series Name" required hint="e.g. Flex, NeonFlex, Pinnacle">
          <TextInput value={s.seriesName} onChange={v => upd({ seriesName: v })} placeholder="Flex" />
        </Field>
        <Field label="Series Code" required hint="Short code used in SKUs, e.g. FX, NF">
          <TextInput value={s.seriesCode} onChange={v => upd({ seriesCode: v })} placeholder="FX" />
        </Field>
        <Field label="Supplier" required>
          <TextInput value={s.supplier} onChange={v => upd({ supplier: v })} placeholder="Linea Lighting Co., Limited" />
        </Field>
        <Field label="Brand" required>
          <TextInput value={s.brand} onChange={v => upd({ brand: v })} />
        </Field>
        <Field label="Warranty Days" required hint="1825 = 5 years">
          <NumInput value={s.warrantyDays} onChange={v => upd({ warrantyDays: v })} />
        </Field>
        <Field label="Mode" hint="Used by the fixture_builder CLI">
          <Select
            value={s.mode}
            onChange={v => upd({ mode: v })}
            options={['new-family', 'append', 'update']}
          />
        </Field>
      </div>
    </Section>
  );
}

/* ============================================================================
   TAPE SPECS SECTION
   ============================================================================ */
function TapeSpecsSection({ s, setS }) {
  const add = () => {
    const isNeon = s.productType === 'neon';
    setS({
      ...s,
      tapeSpecs: [...s.tapeSpecs, {
        itemCode: '', ledPackage: 'FS',
        productCategory: isNeon ? 'LED Neon' : 'LED Tape',
        inputVoltage: '24V DC', wattsPerFoot: '', lumensPerFoot: '',
        criTypical: '', ledPitchMm: '',
        pcbMounting: isNeon ? 'Channel Mounted' : 'Adhesive Backed',
        pcbFinish: 'White', cutIncrementMm: '', isFreeCutting: false,
        leaderCableItem: '', dimmingProtocols: ['TRIAC', '0-10V', 'DALI'],
      }],
    });
  };
  const update = (i, patch) => {
    const copy = [...s.tapeSpecs];
    copy[i] = { ...copy[i], ...patch };
    setS({ ...s, tapeSpecs: copy });
  };
  const remove = (i) => {
    setS({ ...s, tapeSpecs: s.tapeSpecs.filter((_, idx) => idx !== i) });
  };
  const duplicate = (i) => {
    const copy = [...s.tapeSpecs];
    const dup = { ...copy[i], itemCode: copy[i].itemCode + '-COPY' };
    copy.splice(i + 1, 0, dup);
    setS({ ...s, tapeSpecs: copy });
  };

  return (
    <Section
      title="Tape Specs"
      subtitle="Each entry becomes one ilL-Spec-LED Tape row. Define the underlying PCB/LED specification; the product_category differentiates Tape from Neon."
      count={s.tapeSpecs.length}
      right={<Button onClick={add} variant="primary" icon={Plus}>Add Spec</Button>}
    >
      {s.tapeSpecs.length === 0 && (
        <EmptyHint label="No tape specs yet. Add one to get started." />
      )}
      {s.tapeSpecs.map((spec, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>spec #{i + 1}</span>
              {spec.itemCode && <span style={{ color: T.ink, marginLeft: 10 }}>{spec.itemCode}</span>}
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" icon={Copy} onClick={() => duplicate(i)}>Duplicate</Button>
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => remove(i)}>Remove</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Item Code" required>
              <TextInput monospace value={spec.itemCode} onChange={v => update(i, { itemCode: v })} placeholder="TAPE-FS-24V-4.4W" />
            </Field>
            <Field label="LED Package">
              <TextInput list={`led-pkg-${i}`} value={spec.ledPackage} onChange={v => update(i, { ledPackage: v })} placeholder="FS" />
              <datalist id={`led-pkg-${i}`}>{LED_PACKAGE_CHOICES.map(x => <option key={x} value={x} />)}</datalist>
            </Field>
            <Field label="Product Category">
              <Select value={spec.productCategory} onChange={v => update(i, { productCategory: v })}
                options={['LED Tape', 'LED Neon']} />
            </Field>
            <Field label="Input Voltage">
              <Select value={spec.inputVoltage} onChange={v => update(i, { inputVoltage: v })} options={VOLTAGE_CHOICES} />
            </Field>
            <Field label="Watts / ft">
              <NumInput value={spec.wattsPerFoot} onChange={v => update(i, { wattsPerFoot: v })} placeholder="4.4" />
            </Field>
            <Field label="Lumens / ft">
              <NumInput value={spec.lumensPerFoot} onChange={v => update(i, { lumensPerFoot: v })} placeholder="400" />
            </Field>
            <Field label="CRI (typical)">
              <NumInput value={spec.criTypical} onChange={v => update(i, { criTypical: v })} placeholder="97" />
            </Field>
            <Field label="LED Pitch (mm)">
              <NumInput value={spec.ledPitchMm} onChange={v => update(i, { ledPitchMm: v })} placeholder="11.1" />
            </Field>
            <Field label="PCB Mounting">
              <Select value={spec.pcbMounting} onChange={v => update(i, { pcbMounting: v })} options={PCB_MOUNTING_CHOICES} />
            </Field>
            <Field label="PCB Finish">
              <Select value={spec.pcbFinish} onChange={v => update(i, { pcbFinish: v })} options={PCB_FINISH_CHOICES} />
            </Field>
            <Field label="Cut Increment (mm)">
              <NumInput value={spec.cutIncrementMm} onChange={v => update(i, { cutIncrementMm: v })} placeholder="55.55" />
            </Field>
            <Field label="Leader Cable Item" hint="Optional">
              <TextInput monospace value={spec.leaderCableItem} onChange={v => update(i, { leaderCableItem: v })} placeholder="(optional)" />
            </Field>
            <Field label="Free Cutting?">
              <Checkbox checked={!!spec.isFreeCutting} onChange={v => update(i, { isFreeCutting: v })} label={spec.isFreeCutting ? 'Yes — can cut anywhere' : 'No — cut only at increment'} />
            </Field>
            <Field label="Dimming Protocols" wide>
              <MultiSelect value={spec.dimmingProtocols} onChange={v => update(i, { dimmingProtocols: v })} options={DIMMING_PROTOCOL_CHOICES} />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

/* ============================================================================
   TAPE OFFERINGS SECTION
   ============================================================================ */
function TapeOfferingsSection({ s, setS }) {
  const specCodes = s.tapeSpecs.map(x => x.itemCode).filter(Boolean);
  const add = () => {
    const firstSpec = s.tapeSpecs[0];
    setS({
      ...s,
      tapeOfferings: [...s.tapeOfferings, {
        tapeSpec: firstSpec?.itemCode || '',
        cct: '3000K', cri: firstSpec?.criTypical || '',
        sdcm: '3', ledPackage: firstSpec?.ledPackage || 'FS',
        outputLevel: 'Standard', wattsPerFtOverride: '',
      }],
    });
  };
  const update = (i, patch) => {
    const copy = [...s.tapeOfferings];
    copy[i] = { ...copy[i], ...patch };
    setS({ ...s, tapeOfferings: copy });
  };
  const remove = (i) => setS({ ...s, tapeOfferings: s.tapeOfferings.filter((_, idx) => idx !== i) });
  const duplicate = (i) => {
    const copy = [...s.tapeOfferings];
    copy.splice(i + 1, 0, { ...copy[i] });
    setS({ ...s, tapeOfferings: copy });
  };

  return (
    <Section
      title="Tape Offerings"
      subtitle="Each offering is a CCT × Output Level combination of a tape spec. These represent the orderable variants before template/options apply."
      count={s.tapeOfferings.length}
      right={<Button onClick={add} variant="primary" icon={Plus} disabled={!specCodes.length}>Add Offering</Button>}
    >
      {!specCodes.length && <EmptyHint label="Define at least one tape spec before adding offerings." />}
      {s.tapeOfferings.length === 0 && specCodes.length > 0 && (
        <EmptyHint label="No offerings yet. Add one." />
      )}
      {s.tapeOfferings.map((off, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>offering #{i + 1}</span>
              {off.tapeSpec && <span style={{ color: T.ink, marginLeft: 10 }}>{off.tapeSpec} · {off.cct} · {off.outputLevel}</span>}
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" icon={Copy} onClick={() => duplicate(i)}>Duplicate</Button>
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => remove(i)}>Remove</Button>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <Field label="Tape Spec" required>
              <Select value={off.tapeSpec} onChange={v => update(i, { tapeSpec: v })}
                options={specCodes} allowEmpty placeholder="— Select spec —" />
            </Field>
            <Field label="CCT" required>
              <TextInput list={`cct-${i}`} value={off.cct} onChange={v => update(i, { cct: v })} placeholder="3000K" />
              <datalist id={`cct-${i}`}>{OPTION_VALUE_SUGGESTIONS.CCT.map(x => <option key={x} value={x} />)}</datalist>
            </Field>
            <Field label="Output Level">
              <Select value={off.outputLevel} onChange={v => update(i, { outputLevel: v })} options={OUTPUT_LEVEL_CHOICES} />
            </Field>
            <Field label="CRI">
              <NumInput value={off.cri} onChange={v => update(i, { cri: v })} placeholder="97" />
            </Field>
            <Field label="SDCM">
              <NumInput value={off.sdcm} onChange={v => update(i, { sdcm: v })} placeholder="3" />
            </Field>
            <Field label="LED Package">
              <TextInput value={off.ledPackage} onChange={v => update(i, { ledPackage: v })} placeholder="FS" />
            </Field>
            <Field label="Watts/ft Override" hint="Only when differs from spec">
              <NumInput value={off.wattsPerFtOverride} onChange={v => update(i, { wattsPerFtOverride: v })} placeholder="(optional)" />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

/* ============================================================================
   TEMPLATES SECTION (most complex)
   ============================================================================ */
function TemplatesSection({ s, setS }) {
  const specCodes = s.tapeSpecs.map(x => x.itemCode).filter(Boolean);
  const isNeon = s.productType === 'neon';

  const add = () => {
    const firstSpec = s.tapeSpecs[0];
    setS({
      ...s,
      tapeNeonTemplates: [...s.tapeNeonTemplates, {
        templateCode: '', templateName: '',
        productCategory: isNeon ? 'LED Neon' : 'LED Tape',
        series: s.seriesName || '',
        defaultTapeSpec: firstSpec?.itemCode || '',
        basePriceMsrp: '0.00', pricePerFtMsrp: '0.00',
        pricingLengthBasis: 'L_tape_cut', leaderAllowanceMm: '15',
        allowedTapeSpecs: firstSpec ? [{ tapeSpec: firstSpec.itemCode, isDefault: true, environmentRating: isNeon ? 'Wet' : 'Dry' }] : [],
        allowedOptions: [
          { optionType: 'CCT', value: '3000K', isDefault: true, msrpAdder: '0' },
          { optionType: 'Output Level', value: 'Standard', isDefault: true, msrpAdder: '0' },
          { optionType: 'Environment Rating', value: isNeon ? 'Wet' : 'Dry', isDefault: true, msrpAdder: '0' },
          { optionType: 'Feed Direction', value: 'Single Feed', isDefault: true, msrpAdder: '0' },
        ],
      }],
    });
  };
  const update = (i, patch) => {
    const copy = [...s.tapeNeonTemplates];
    copy[i] = { ...copy[i], ...patch };
    setS({ ...s, tapeNeonTemplates: copy });
  };
  const remove = (i) => setS({ ...s, tapeNeonTemplates: s.tapeNeonTemplates.filter((_, idx) => idx !== i) });
  const duplicate = (i) => {
    const copy = [...s.tapeNeonTemplates];
    const dup = JSON.parse(JSON.stringify(copy[i]));
    dup.templateCode = dup.templateCode + '-COPY';
    copy.splice(i + 1, 0, dup);
    setS({ ...s, tapeNeonTemplates: copy });
  };

  return (
    <Section
      title="Templates"
      subtitle="A template bundles a default spec + pricing + allowed options. This is what maps to a Webflow product. Most families have one template per LED package."
      count={s.tapeNeonTemplates.length}
      right={<Button onClick={add} variant="primary" icon={Plus} disabled={!specCodes.length}>Add Template</Button>}
    >
      {!specCodes.length && <EmptyHint label="Define at least one tape spec before adding templates." />}
      {s.tapeNeonTemplates.length === 0 && specCodes.length > 0 && (
        <EmptyHint label="No templates yet. Add one." />
      )}
      {s.tapeNeonTemplates.map((tpl, i) => (
        <TemplateCard
          key={i} tpl={tpl} index={i} specCodes={specCodes} isNeon={isNeon}
          onUpdate={(patch) => update(i, patch)}
          onRemove={() => remove(i)}
          onDuplicate={() => duplicate(i)}
        />
      ))}
    </Section>
  );
}

function TemplateCard({ tpl, index, specCodes, isNeon, onUpdate, onRemove, onDuplicate }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div style={{
      background: T.bg,
      border: `1px solid ${T.border}`,
      borderRadius: 10,
      marginBottom: 14,
      overflow: 'hidden',
    }}>
      <div className="flex items-center justify-between" style={{ padding: '14px 18px', borderBottom: expanded ? `1px solid ${T.border}` : 'none' }}>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2.5"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          {expanded ? <ChevronDown size={16} style={{ color: T.muted }} /> : <ChevronUp size={16} style={{ color: T.muted, transform: 'rotate(180deg)' }} />}
          <span style={{ fontFamily: fontMono, fontSize: 13, color: T.subtle }}>template #{index + 1}</span>
          {tpl.templateCode && (
            <span style={{ fontFamily: fontMono, fontSize: 13, fontWeight: 500, color: T.ink }}>{tpl.templateCode}</span>
          )}
          {tpl.templateName && (
            <span style={{ fontFamily: fontBody, fontSize: 13, color: T.muted }}>· {tpl.templateName}</span>
          )}
        </button>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" icon={Copy} onClick={onDuplicate}>Duplicate</Button>
          <Button size="sm" variant="danger" icon={Trash2} onClick={onRemove}>Remove</Button>
        </div>
      </div>

      {expanded && (
        <div style={{ padding: 18 }}>
          <div className="grid grid-cols-2 gap-4 mb-5">
            <Field label="Template Code" required>
              <TextInput monospace value={tpl.templateCode} onChange={v => onUpdate({ templateCode: v })} placeholder="ILL-FX-FS" />
            </Field>
            <Field label="Template Name" required>
              <TextInput value={tpl.templateName} onChange={v => onUpdate({ templateName: v })} placeholder="Flex Full Spectrum" />
            </Field>
            <Field label="Product Category">
              <Select value={tpl.productCategory} onChange={v => onUpdate({ productCategory: v })} options={['LED Tape', 'LED Neon']} />
            </Field>
            <Field label="Series">
              <TextInput value={tpl.series} onChange={v => onUpdate({ series: v })} />
            </Field>
            <Field label="Default Tape Spec">
              <Select value={tpl.defaultTapeSpec} onChange={v => onUpdate({ defaultTapeSpec: v })} options={specCodes} allowEmpty placeholder="— Select —" />
            </Field>
            <Field label="Pricing Length Basis">
              <Select value={tpl.pricingLengthBasis} onChange={v => onUpdate({ pricingLengthBasis: v })} options={PRICING_BASIS_CHOICES} />
            </Field>
            <Field label="Base Price MSRP ($)" required>
              <NumInput value={tpl.basePriceMsrp} onChange={v => onUpdate({ basePriceMsrp: v })} placeholder="25.00" />
            </Field>
            <Field label="Price / ft MSRP ($)" required>
              <NumInput value={tpl.pricePerFtMsrp} onChange={v => onUpdate({ pricePerFtMsrp: v })} placeholder="8.50" />
            </Field>
            <Field label="Leader Allowance (mm)">
              <NumInput value={tpl.leaderAllowanceMm} onChange={v => onUpdate({ leaderAllowanceMm: v })} placeholder="15" />
            </Field>
          </div>

          <AllowedTapeSpecsEditor
            items={tpl.allowedTapeSpecs || []}
            specCodes={specCodes}
            isNeon={isNeon}
            onChange={(v) => onUpdate({ allowedTapeSpecs: v })}
          />

          <AllowedOptionsEditor
            items={tpl.allowedOptions || []}
            isNeon={isNeon}
            onChange={(v) => onUpdate({ allowedOptions: v })}
          />
        </div>
      )}
    </div>
  );
}

function AllowedTapeSpecsEditor({ items, specCodes, isNeon, onChange }) {
  const add = () => onChange([...items, {
    tapeSpec: specCodes[0] || '', isDefault: items.length === 0,
    environmentRating: isNeon ? 'Wet' : 'Dry',
  }]);
  const update = (i, patch) => {
    const copy = [...items];
    copy[i] = { ...copy[i], ...patch };
    // enforce only one default
    if (patch.isDefault) copy.forEach((x, idx) => { if (idx !== i) x.isDefault = false; });
    onChange(copy);
  };
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <div style={{ marginBottom: 20 }}>
      <div className="flex items-center justify-between mb-2">
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: 0 }}>
          Allowed Tape Specs <span style={{ fontFamily: fontMono, fontSize: 12, color: T.subtle, fontWeight: 400 }}>{items.length}</span>
        </h3>
        <Button size="sm" icon={Plus} onClick={add}>Add</Button>
      </div>
      {items.length === 0 && <EmptyHint small label="None yet." />}
      <div className="flex flex-col gap-2">
        {items.map((a, i) => (
          <div key={i} className="grid gap-3 items-end" style={{
            gridTemplateColumns: '1fr 1fr auto auto',
            padding: '10px 12px',
            background: T.paper,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
          }}>
            <Field label="Tape Spec">
              <Select value={a.tapeSpec} onChange={v => update(i, { tapeSpec: v })} options={specCodes} allowEmpty placeholder="— Select —" />
            </Field>
            <Field label="Environment Rating">
              <Select value={a.environmentRating} onChange={v => update(i, { environmentRating: v })} options={ENV_RATING_CHOICES} />
            </Field>
            <div style={{ paddingBottom: 9 }}>
              <Checkbox checked={!!a.isDefault} onChange={v => update(i, { isDefault: v })} label="Default" />
            </div>
            <div style={{ paddingBottom: 4 }}>
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => remove(i)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AllowedOptionsEditor({ items, isNeon, onChange }) {
  const typeSuggestions = isNeon ? OPTION_TYPE_SUGGESTIONS_NEON : OPTION_TYPE_SUGGESTIONS_TAPE;

  const add = (optionType = '') => onChange([...items, {
    optionType: optionType || 'CCT', value: '', isDefault: false, msrpAdder: '0',
  }]);
  const update = (i, patch) => {
    const copy = [...items];
    copy[i] = { ...copy[i], ...patch };
    // enforce only one default per option_type
    if (patch.isDefault) {
      copy.forEach((x, idx) => {
        if (idx !== i && x.optionType === copy[i].optionType) x.isDefault = false;
      });
    }
    onChange(copy);
  };
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i));
  const move = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= items.length) return;
    const copy = [...items];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    onChange(copy);
  };

  // group for display
  const grouped = useMemo(() => {
    const order = [];
    const byType = new Map();
    items.forEach((o, idx) => {
      const t = o.optionType || '(unset)';
      if (!byType.has(t)) { byType.set(t, []); order.push(t); }
      byType.get(t).push({ ...o, _idx: idx });
    });
    return order.map(t => ({ type: t, items: byType.get(t) }));
  }, [items]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: 0 }}>
          Allowed Options <span style={{ fontFamily: fontMono, fontSize: 12, color: T.subtle, fontWeight: 400 }}>{items.length}</span>
        </h3>
        <div className="flex flex-wrap gap-1">
          {typeSuggestions.map(t => (
            <Button key={t} size="sm" variant="ghost" icon={Plus} onClick={() => add(t)}>{t}</Button>
          ))}
        </div>
      </div>
      {items.length === 0 && <EmptyHint small label="No options. Click a suggestion above to add by type." />}

      {grouped.map(g => (
        <div key={g.type} style={{ marginBottom: 10 }}>
          <div style={{
            fontFamily: fontMono, fontSize: 11, fontWeight: 500, textTransform: 'uppercase',
            letterSpacing: '0.08em', color: T.subtle, padding: '8px 4px 6px',
          }}>
            {g.type}
          </div>
          <div className="flex flex-col gap-1.5">
            {g.items.map((o) => (
              <OptionRow
                key={o._idx}
                o={o}
                typeSuggestions={typeSuggestions}
                onUpdate={(patch) => update(o._idx, patch)}
                onRemove={() => remove(o._idx)}
                onMove={(dir) => move(o._idx, dir)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function OptionRow({ o, typeSuggestions, onUpdate, onRemove, onMove }) {
  const valueSuggestions = OPTION_VALUE_SUGGESTIONS[o.optionType] || [];
  const listId = `optval-${o._idx}`;
  const typeListId = `opttype-${o._idx}`;
  return (
    <div className="grid gap-2 items-center" style={{
      gridTemplateColumns: '1.2fr 1.2fr 90px auto auto',
      padding: '8px 10px',
      background: T.paper,
      border: `1px solid ${T.border}`,
      borderRadius: 8,
    }}>
      <div>
        <TextInput list={typeListId} value={o.optionType} onChange={v => onUpdate({ optionType: v })} placeholder="Option Type" />
        <datalist id={typeListId}>{typeSuggestions.map(x => <option key={x} value={x} />)}</datalist>
      </div>
      <div>
        <TextInput list={listId} value={o.value} onChange={v => onUpdate({ value: v })} placeholder="Value" />
        <datalist id={listId}>{valueSuggestions.map(x => <option key={x} value={x} />)}</datalist>
      </div>
      <div>
        <NumInput value={o.msrpAdder} onChange={v => onUpdate({ msrpAdder: v })} placeholder="$0" />
      </div>
      <div>
        <Checkbox checked={!!o.isDefault} onChange={v => onUpdate({ isDefault: v })} label="Default" />
      </div>
      <div className="flex gap-0.5">
        <Button size="sm" variant="ghost" icon={ArrowUp} onClick={() => onMove(-1)} />
        <Button size="sm" variant="ghost" icon={ArrowDown} onClick={() => onMove(1)} />
        <Button size="sm" variant="danger" icon={Trash2} onClick={onRemove} />
      </div>
    </div>
  );
}

/* ============================================================================
   SUBMITTAL + WEBFLOW
   ============================================================================ */
function SubmittalSection({ s, setS }) {
  const tplCodes = s.tapeNeonTemplates.map(x => x.templateCode).filter(Boolean);
  return (
    <Section
      title="Submittal Mapping"
      subtitle="Controls how the fixture's submittal document is generated. Leave blank to use category defaults; specify a template code to clone its submittal layout."
    >
      <div className="grid grid-cols-2 gap-4">
        <Field label="Clone From Template" hint="Leave blank for defaults">
          <Select
            value={s.neonSubmittalMapping.cloneFromTemplate}
            onChange={v => setS({ ...s, neonSubmittalMapping: { cloneFromTemplate: v } })}
            options={tplCodes}
            allowEmpty
            placeholder="— Use category defaults —"
          />
        </Field>
      </div>
    </Section>
  );
}

function WebflowSection({ s, setS }) {
  const w = s.tapeNeonWebflow;
  const updW = (patch) => setS({ ...s, tapeNeonWebflow: { ...w, ...patch } });

  const isNeon = s.productType === 'neon';
  const stepOptions = isNeon ? OPTION_TYPE_SUGGESTIONS_NEON.concat('Length') : OPTION_TYPE_SUGGESTIONS_TAPE.concat('Length');
  const [newStep, setNewStep] = useState('');

  const addStep = () => {
    if (!newStep.trim()) return;
    updW({ configuratorSteps: [...(w.configuratorSteps || []), newStep.trim()] });
    setNewStep('');
  };
  const removeStep = (i) => updW({ configuratorSteps: w.configuratorSteps.filter((_, idx) => idx !== i) });
  const moveStep = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= w.configuratorSteps.length) return;
    const copy = [...w.configuratorSteps];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    updW({ configuratorSteps: copy });
  };

  return (
    <Section
      title="Webflow"
      subtitle="Catalog + configurator metadata for the online product listing."
    >
      <div className="grid grid-cols-2 gap-4 mb-5">
        <Field label="Product Category">
          <Select value={w.productCategory} onChange={v => updW({ productCategory: v })}
            options={['led-tape', 'led-neon']} />
        </Field>
        <Field label="Sublabel" hint="Optional tagline">
          <TextInput value={w.sublabel} onChange={v => updW({ sublabel: v })} />
        </Field>
        <Field label="Beam Angle (°)">
          <NumInput value={w.beamAngle} onChange={v => updW({ beamAngle: v })} />
        </Field>
        <Field label="L70 Life (hrs)">
          <NumInput value={w.l70LifeHours} onChange={v => updW({ l70LifeHours: v })} />
        </Field>
        <Field label="Operating Temp Min (°C)">
          <NumInput value={w.operatingTempMinC} onChange={v => updW({ operatingTempMinC: v })} />
        </Field>
        <Field label="Operating Temp Max (°C)">
          <NumInput value={w.operatingTempMaxC} onChange={v => updW({ operatingTempMaxC: v })} />
        </Field>
        <Field label="Warranty Years">
          <NumInput value={w.warrantyYears} onChange={v => updW({ warrantyYears: v })} />
        </Field>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: 0 }}>
            Configurator Steps <span style={{ fontFamily: fontMono, fontSize: 12, color: T.subtle, fontWeight: 400 }}>{w.configuratorSteps?.length || 0}</span>
          </h3>
        </div>
        <p style={{ fontFamily: fontBody, fontSize: 12, color: T.muted, margin: '0 0 10px' }}>
          Order of steps the customer sees on the online configurator. Use the arrows to reorder.
        </p>
        <div className="flex flex-col gap-1.5 mb-3">
          {(w.configuratorSteps || []).map((st, i) => (
            <div key={i} className="flex items-center gap-2" style={{
              padding: '8px 12px', background: T.paper, border: `1px solid ${T.border}`, borderRadius: 8,
            }}>
              <span style={{ fontFamily: fontMono, fontSize: 12, color: T.subtle, width: 20 }}>{i + 1}.</span>
              <span style={{ fontFamily: fontBody, fontSize: 14, color: T.ink, flex: 1 }}>{st}</span>
              <Button size="sm" variant="ghost" icon={ArrowUp} onClick={() => moveStep(i, -1)} />
              <Button size="sm" variant="ghost" icon={ArrowDown} onClick={() => moveStep(i, 1)} />
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => removeStep(i)} />
            </div>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          <input
            type="text"
            list="webflow-step-sugg"
            value={newStep}
            onChange={e => setNewStep(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addStep(); } }}
            placeholder="Add step (e.g. CCT, Length, Finish)"
            style={{
              flex: 1, fontFamily: fontBody, fontSize: 14, color: T.ink,
              background: T.paper, border: `1px solid ${T.border}`, borderRadius: 6,
              padding: '9px 12px', outline: 'none',
            }}
          />
          <datalist id="webflow-step-sugg">{stepOptions.map(x => <option key={x} value={x} />)}</datalist>
          <Button icon={Plus} onClick={addStep}>Add Step</Button>
        </div>
      </div>
    </Section>
  );
}

/* ============================================================================
   HELPERS
   ============================================================================ */
export function EmptyHint({ label, small }) {
  return (
    <div style={{
      fontFamily: fontBody, fontSize: small ? 12 : 13,
      color: T.subtle, fontStyle: 'italic',
      padding: small ? '8px 4px' : '20px 4px',
    }}>
      {label}
    </div>
  );
}

/* ============================================================================
   YAML PREVIEW (with simple syntax highlighting)
   ============================================================================ */
function highlight(yaml) {
  const lines = yaml.split('\n');
  return lines.map((line, i) => {
    // comment
    if (/^\s*#/.test(line)) {
      return <div key={i} style={{ color: T.codeComment }}>{line || '\u00A0'}</div>;
    }
    // list item with key:value on same line: "- key: value"
    const kvMatch = line.match(/^(\s*)(-\s*)?([a-zA-Z_][\w]*)(:)(.*)$/);
    if (kvMatch) {
      const [, lead, dash, key, colon, rest] = kvMatch;
      return (
        <div key={i}>
          <span>{lead}</span>
          {dash && <span style={{ color: T.codeAccent }}>{dash}</span>}
          <span style={{ color: T.codeKey }}>{key}</span>
          <span style={{ color: T.codeInk }}>{colon}</span>
          <span>{renderYamlValue(rest)}</span>
        </div>
      );
    }
    const listMatch = line.match(/^(\s*)(-\s+)(.*)$/);
    if (listMatch) {
      const [, lead, dash, rest] = listMatch;
      return (
        <div key={i}>
          <span>{lead}</span>
          <span style={{ color: T.codeAccent }}>{dash}</span>
          <span>{renderYamlValue(' ' + rest)}</span>
        </div>
      );
    }
    return <div key={i} style={{ color: T.codeInk }}>{line || '\u00A0'}</div>;
  });
}

function renderYamlValue(text) {
  // strip leading space
  const m = text.match(/^(\s*)(.*)$/);
  const [, lead, v] = m;
  if (v === '') return <span>{lead || '\u00A0'}</span>;
  let color = T.codeInk;
  if (/^".*"$/.test(v)) color = T.codeString;
  else if (/^(true|false)$/.test(v)) color = T.codeBool;
  else if (/^-?\d+(\.\d+)?$/.test(v)) color = T.codeNum;
  return <><span>{lead}</span><span style={{ color }}>{v}</span></>;
}

function YamlPreview({ yaml, issues, filename, onDownload, onCopy, copied }) {
  const errors = issues.filter(x => x.level === 'error');
  const warnings = issues.filter(x => x.level === 'warn');
  return (
    <div style={{
      background: T.code,
      borderRadius: 12,
      border: `1px solid ${T.ink}`,
      overflow: 'hidden',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div className="flex items-center justify-between" style={{
        padding: '12px 16px',
        borderBottom: `1px solid #3A3328`,
        background: '#1B1612',
      }}>
        <div className="flex items-center gap-2.5">
          <FileCode2 size={15} style={{ color: T.codeAccent }} />
          <span style={{ fontFamily: fontMono, fontSize: 12, color: T.codeInk }}>{filename}</span>
        </div>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={onCopy}
            style={{
              fontFamily: fontBody, fontSize: 12, fontWeight: 500,
              padding: '5px 10px', borderRadius: 5,
              border: `1px solid #4A4238`, background: 'transparent',
              color: copied ? T.codeString : T.codeInk,
              display: 'inline-flex', alignItems: 'center', gap: 5,
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            {copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={onDownload}
            style={{
              fontFamily: fontBody, fontSize: 12, fontWeight: 500,
              padding: '5px 10px', borderRadius: 5,
              border: 'none', background: T.codeAccent,
              color: T.code,
              display: 'inline-flex', alignItems: 'center', gap: 5,
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <Download size={13} /> Download
          </button>
        </div>
      </div>

      {issues.length > 0 && (
        <div style={{
          padding: '10px 16px',
          borderBottom: `1px solid #3A3328`,
          background: '#221A13',
          fontFamily: fontMono, fontSize: 11.5,
          maxHeight: 140, overflowY: 'auto',
        }}>
          {errors.length > 0 && (
            <div style={{ color: '#E89090', marginBottom: warnings.length ? 6 : 0 }}>
              <div className="flex items-center gap-1.5 mb-1" style={{ fontWeight: 600 }}>
                <AlertTriangle size={12} /> {errors.length} {errors.length === 1 ? 'error' : 'errors'}
              </div>
              {errors.map((x, i) => <div key={i} style={{ paddingLeft: 18, opacity: 0.9 }}>· {x.text}</div>)}
            </div>
          )}
          {warnings.length > 0 && (
            <div style={{ color: '#E0B87A' }}>
              <div className="flex items-center gap-1.5 mb-1" style={{ fontWeight: 600 }}>
                <Info size={12} /> {warnings.length} {warnings.length === 1 ? 'warning' : 'warnings'}
              </div>
              {warnings.map((x, i) => <div key={i} style={{ paddingLeft: 18, opacity: 0.9 }}>· {x.text}</div>)}
            </div>
          )}
        </div>
      )}

      <pre style={{
        flex: 1,
        margin: 0,
        padding: 16,
        fontFamily: fontMono,
        fontSize: 12.5,
        lineHeight: 1.55,
        color: T.codeInk,
        overflow: 'auto',
        whiteSpace: 'pre',
        background: T.code,
      }}>
        {highlight(yaml)}
      </pre>
    </div>
  );
}

/* ============================================================================
   TAB NAV
   ============================================================================ */
const TAPE_NEON_TABS = [
  { id: 'product',   label: 'Product Info' },
  { id: 'specs',     label: 'Tape Specs' },
  { id: 'offerings', label: 'Offerings' },
  { id: 'templates', label: 'Templates' },
  { id: 'submittal', label: 'Submittal' },
  { id: 'webflow',   label: 'Webflow' },
];

function getTabs(productType) {
  return productType === 'fixture' ? FIXTURE_TABS : TAPE_NEON_TABS;
}

function TabNav({ tabs, active, onChange, counts }) {
  return (
    <nav className="flex flex-col gap-0.5" style={{ padding: '4px 0' }}>
      {tabs.map(t => {
        const isActive = active === t.id;
        const count = counts[t.id];
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            style={{
              fontFamily: fontBody,
              fontSize: 13.5,
              fontWeight: isActive ? 600 : 500,
              color: isActive ? T.accent : T.muted,
              background: isActive ? T.accentBg : 'transparent',
              border: 'none',
              padding: '10px 14px',
              borderRadius: 8,
              textAlign: 'left',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              transition: 'all 0.15s',
              borderLeft: `2px solid ${isActive ? T.accent : 'transparent'}`,
              paddingLeft: 14,
            }}
            onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = T.bg; }}
            onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
          >
            <span>{t.label}</span>
            {typeof count === 'number' && count > 0 && (
              <span style={{
                fontFamily: fontMono,
                fontSize: 11,
                fontWeight: 500,
                color: isActive ? T.accent : T.subtle,
                background: isActive ? T.paper : T.bg,
                padding: '2px 7px',
                borderRadius: 999,
                minWidth: 20,
                textAlign: 'center',
              }}>{count}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

/* ============================================================================
   MAIN APP
   ============================================================================ */
export default function App() {
  const [s, setS] = useState(() => blankState('tape'));
  const [activeTab, setActiveTab] = useState('product');
  const [previewOpen, setPreviewOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [issuesHover, setIssuesHover] = useState(false);
  const confirmTimer = useRef(null);

  const yaml = useMemo(() => serializeYaml(s), [s]);
  const issues = useMemo(() => validate(s), [s]);

  const setProductType = (pt) => {
    if (pt === s.productType) return;
    setS({
      ...s,
      productType: pt,
      tapeNeonWebflow: {
        ...s.tapeNeonWebflow,
        productCategory: pt === 'neon' ? 'led-neon' : 'led-tape',
      },
    });
  };

  const upd = (patch) => setS({ ...s, ...patch });

  const filename = useMemo(() => {
    const code = (s.seriesCode || s.productType).toLowerCase().replace(/[^a-z0-9]/g, '_');
    return `${code || s.productType}_config.yaml`;
  }, [s.seriesCode, s.productType]);

  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(yaml);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {}
  };

  const doDownload = () => {
    const blob = new Blob([yaml], { type: 'text/yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const loadExample = () => {
    const ex = s.productType === 'fixture' ? EXAMPLE_FIXTURE
             : s.productType === 'neon'    ? EXAMPLE_NEON
                                            : EXAMPLE_TAPE;
    setS(JSON.parse(JSON.stringify({ ...blankState(s.productType), ...ex })));
  };

  const doReset = () => {
    if (confirmReset) {
      setS(blankState(s.productType));
      setConfirmReset(false);
      clearTimeout(confirmTimer.current);
    } else {
      setConfirmReset(true);
      confirmTimer.current = setTimeout(() => setConfirmReset(false), 3000);
    }
  };

  useEffect(() => () => clearTimeout(confirmTimer.current), []);

  const counts = {
    specs: s.tapeSpecs.length,
    offerings: s.tapeOfferings.length,
    templates: s.tapeNeonTemplates.length,
    ...fixtureCounts(s),
  };

  const tabs = getTabs(s.productType);
  // If activeTab is not in the current product type's tabs, fall back to 'product'
  useEffect(() => {
    if (!tabs.some(t => t.id === activeTab)) setActiveTab('product');
  }, [s.productType]); // eslint-disable-line react-hooks/exhaustive-deps

  const errCount = issues.filter(x => x.level === 'error').length;
  const warnCount = issues.filter(x => x.level === 'warn').length;

  return (
    <div style={{
      background: T.bg, minHeight: '100vh', fontFamily: fontBody, color: T.ink,
    }}>
      <style>{FONTS_CSS}</style>
      <style>{`
        ::selection { background: ${T.accentSoft}; color: ${T.ink}; }
        input::placeholder, textarea::placeholder { color: ${T.subtle}; opacity: 0.7; }
        * { box-sizing: border-box; }
      `}</style>

      {/* ── HEADER ────────────────────────────────── */}
      <header style={{
        borderBottom: `1px solid ${T.border}`,
        background: T.paper,
      }}>
        <div className="flex items-center justify-between" style={{ padding: '18px 32px' }}>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div style={{
                width: 36, height: 36, borderRadius: 8,
                background: T.ink,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Lightbulb size={18} style={{ color: T.codeAccent }} strokeWidth={1.8} />
              </div>
              <div>
                <div style={{ fontFamily: fontDisplay, fontSize: 20, fontWeight: 500, color: T.ink, letterSpacing: '-0.01em', lineHeight: 1 }}>
                  <span style={{ fontStyle: 'italic' }}>il</span>Lumenate
                </div>
                <div style={{ fontFamily: fontMono, fontSize: 10.5, color: T.subtle, letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 2 }}>
                  YAML Builder
                </div>
              </div>
            </div>

            <div style={{ width: 1, height: 28, background: T.border, margin: '0 8px' }} />

            {/* product type toggle */}
            <div style={{
              display: 'inline-flex',
              background: T.bg,
              border: `1px solid ${T.border}`,
              borderRadius: 8,
              padding: 3,
            }}>
              {['tape', 'neon', 'fixture'].map(pt => {
                const on = s.productType === pt;
                const label = pt === 'tape' ? 'LED Tape' : pt === 'neon' ? 'LED Neon' : 'Linear Fixture';
                return (
                  <button
                    key={pt}
                    type="button"
                    onClick={() => setProductType(pt)}
                    style={{
                      fontFamily: fontBody, fontSize: 13, fontWeight: 500,
                      padding: '6px 14px', borderRadius: 6,
                      border: 'none',
                      background: on ? T.paper : 'transparent',
                      color: on ? T.ink : T.muted,
                      cursor: 'pointer',
                      boxShadow: on ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {(errCount > 0 || warnCount > 0) && (
              <div
                onMouseEnter={() => setIssuesHover(true)}
                onMouseLeave={() => setIssuesHover(false)}
                style={{
                  position: 'relative',
                  fontFamily: fontBody, fontSize: 12,
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  marginRight: 4,
                  padding: '6px 10px',
                  borderRadius: 6,
                  cursor: 'help',
                  background: issuesHover ? T.paper : 'transparent',
                  border: `1px solid ${issuesHover ? T.border : 'transparent'}`,
                  transition: 'background 120ms ease, border-color 120ms ease',
                }}
              >
                {errCount > 0 && (
                  <span style={{ color: T.danger, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <AlertTriangle size={13} /> {errCount}
                  </span>
                )}
                {warnCount > 0 && (
                  <span style={{ color: T.accent, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <Info size={13} /> {warnCount}
                  </span>
                )}

                {issuesHover && (
                  <div
                    style={{
                      position: 'absolute',
                      top: 'calc(100% + 6px)',
                      right: 0,
                      width: 380,
                      maxHeight: 420,
                      overflowY: 'auto',
                      background: T.paper,
                      border: `1px solid ${T.border}`,
                      borderRadius: 8,
                      boxShadow: '0 12px 32px rgba(26, 22, 18, 0.18)',
                      padding: 12,
                      zIndex: 100,
                      cursor: 'default',
                      textAlign: 'left',
                    }}
                  >
                    <div style={{
                      fontFamily: fontDisplay, fontSize: 13, fontWeight: 600,
                      color: T.ink, marginBottom: 10,
                      paddingBottom: 8, borderBottom: `1px solid ${T.border}`,
                      letterSpacing: 0.2,
                    }}>
                      {errCount > 0 && warnCount > 0
                        ? `${errCount} error${errCount === 1 ? '' : 's'}, ${warnCount} warning${warnCount === 1 ? '' : 's'}`
                        : errCount > 0
                          ? `${errCount} error${errCount === 1 ? '' : 's'}`
                          : `${warnCount} warning${warnCount === 1 ? '' : 's'}`}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {issues
                        .slice()
                        .sort((a, b) => (a.level === 'error' ? -1 : 1) - (b.level === 'error' ? -1 : 1))
                        .map((iss, idx) => (
                          <div
                            key={idx}
                            style={{
                              display: 'flex', alignItems: 'flex-start', gap: 8,
                              padding: '6px 8px',
                              borderRadius: 4,
                              background: iss.level === 'error'
                                ? 'rgba(180, 47, 47, 0.06)'
                                : 'rgba(180, 83, 9, 0.06)',
                              borderLeft: `2px solid ${iss.level === 'error' ? T.danger : T.accent}`,
                            }}
                          >
                            <span style={{
                              flexShrink: 0, marginTop: 2,
                              color: iss.level === 'error' ? T.danger : T.accent,
                            }}>
                              {iss.level === 'error'
                                ? <AlertTriangle size={12} />
                                : <Info size={12} />}
                            </span>
                            <span style={{
                              fontFamily: fontBody, fontSize: 12,
                              color: T.ink, lineHeight: 1.45,
                            }}>
                              {iss.text}
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            <Button icon={Sparkles} variant="default" onClick={loadExample}>Load example</Button>
            <Button icon={RotateCcw} variant={confirmReset ? 'accent' : 'default'} onClick={doReset}>
              {confirmReset ? 'Click again to reset' : 'Reset'}
            </Button>
            <Button icon={previewOpen ? EyeOff : Eye} variant="default" onClick={() => setPreviewOpen(!previewOpen)}>
              {previewOpen ? 'Hide preview' : 'Show preview'}
            </Button>
            <Button icon={Download} variant="accent" onClick={doDownload}>Download YAML</Button>
          </div>
        </div>
      </header>

      {/* ── BODY ──────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: previewOpen ? '220px 1fr 520px' : '220px 1fr',
        gap: 24,
        padding: 24,
        maxWidth: 1800,
        margin: '0 auto',
        minHeight: 'calc(100vh - 80px)',
      }}>
        {/* LEFT NAV */}
        <aside style={{
          position: 'sticky', top: 24, alignSelf: 'start',
          background: T.paper, border: `1px solid ${T.border}`,
          borderRadius: 12, padding: 10,
        }}>
          <div style={{
            fontFamily: fontMono, fontSize: 10.5,
            color: T.subtle, letterSpacing: '0.12em', textTransform: 'uppercase',
            padding: '8px 14px 10px',
          }}>
            Sections
          </div>
          <TabNav tabs={tabs} active={activeTab} onChange={setActiveTab} counts={counts} />

          <div style={{ borderTop: `1px solid ${T.border}`, margin: '14px 10px 10px' }} />

          <div style={{ padding: '4px 14px 10px' }}>
            <div style={{ fontFamily: fontMono, fontSize: 10.5, color: T.subtle, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 8 }}>
              Output file
            </div>
            <div style={{ fontFamily: fontMono, fontSize: 12, color: T.ink, wordBreak: 'break-all' }}>
              {filename}
            </div>
          </div>
        </aside>

        {/* MAIN CONTENT */}
        <main>
          {s.productType === 'fixture' ? (
            <>
              {activeTab === 'product' && <ProductInfoSection s={s} upd={upd} />}
              {activeTab !== 'product' && renderFixtureTab(activeTab, s, setS)}
            </>
          ) : (
            <>
              {activeTab === 'product'   && <ProductInfoSection s={s} upd={upd} />}
              {activeTab === 'specs'     && <TapeSpecsSection s={s} setS={setS} />}
              {activeTab === 'offerings' && <TapeOfferingsSection s={s} setS={setS} />}
              {activeTab === 'templates' && <TemplatesSection s={s} setS={setS} />}
              {activeTab === 'submittal' && <SubmittalSection s={s} setS={setS} />}
              {activeTab === 'webflow'   && <WebflowSection s={s} setS={setS} />}
            </>
          )}
        </main>

        {/* YAML PREVIEW */}
        {previewOpen && (
          <aside style={{ position: 'sticky', top: 24, alignSelf: 'start', height: 'calc(100vh - 48px)' }}>
            <YamlPreview
              yaml={yaml}
              issues={issues}
              filename={filename}
              onCopy={doCopy}
              onDownload={doDownload}
              copied={copied}
            />
          </aside>
        )}
      </div>

      {/* FOOTER */}
      <footer style={{
        padding: '20px 32px',
        borderTop: `1px solid ${T.border}`,
        background: T.paper,
        fontFamily: fontBody, fontSize: 12, color: T.subtle,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span>Generates config files for <code style={{ fontFamily: fontMono, fontSize: 11, background: T.bg, padding: '2px 6px', borderRadius: 4, color: T.muted }}>tools.fixture_builder</code></span>
        <span>Run: <code style={{ fontFamily: fontMono, fontSize: 11, background: T.bg, padding: '2px 6px', borderRadius: 4, color: T.muted }}>python -m tools.fixture_builder --product-type {s.productType} --config {filename} --output ./output/{(s.seriesCode || 'series').toLowerCase()}/</code></span>
      </footer>
    </div>
  );
}
