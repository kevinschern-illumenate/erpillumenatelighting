/* eslint-disable react/prop-types */
/* ============================================================================
   Linear Fixture support — sections, serializer, validator, example payload.
   Imports shared primitives from App.jsx via ESM (circular but safe — only
   referenced inside function bodies, not at module init time).
   ============================================================================ */
import { useState, useMemo } from 'react';
import {
  Plus, Trash2, Copy, ArrowUp, ArrowDown, ChevronDown, ChevronUp,
} from 'lucide-react';

import {
  T, fontBody, fontMono, fontDisplay,
  Field, TextInput, NumInput, Select, Checkbox, MultiSelect, Button,
  Section, Card, EmptyHint,
  yamlScalar, yamlListOfObjects, yamlSimpleList, indent,
  isNumericString,
} from './App.jsx';

/* ============================================================================
   ENUMS / CHOICES
   ============================================================================ */
export const FIXTURE_FINISH_CHOICES = ['WH', 'BK', 'SV'];
export const FINISH_DISPLAY_CHOICES = ['White', 'Black', 'Anodized Silver'];
export const ENDCAP_COLOR_CHOICES = ['WH', 'BK', 'GR'];
export const ENDCAP_STYLE_CHOICES = ['Solid', 'Feed Through'];
export const LENS_APPEARANCE_CHOICES = ['White', 'Frosted', 'Clear', 'Black'];
export const LENS_SHAPE_CHOICES = ['WH', 'RD', 'AS', 'CV'];
export const LENS_STOCK_TYPE_CHOICES = ['Stick', 'Continuous'];
export const LENS_INTERFACE_CHOICES = ['Snap-in', 'Slide-in', 'None'];
export const ACCESSORY_TYPE_CHOICES = ['Mounting', 'Joiner', 'Endcap'];
export const MOUNTING_METHOD_CHOICES = [
  'Mounting Clip', 'Pivot Clip', 'Surface Mount', 'Pendant Mount',
  'Recessed Mount', 'Wall Mount', 'Suspended Mount',
];
export const QTY_RULE_CHOICES = ['Per x mm', 'Per Fixture', 'Per Segment', 'Per Run'];
export const FIXTURE_LED_PACKAGES = ['FS', 'SW', 'TW', 'RGBW', 'RGB'];
export const POWER_FEED_CHOICES = ['Single End Feed', 'Dual End Feed', 'Mid Feed', 'Power Joiner'];
export const FIXTURE_PRICING_BASIS = ['L_tape_cut', 'L_fixture_cut', 'L_fixture_total'];
export const FIXTURE_ENV_RATINGS = ['Dry', 'Damp', 'Wet'];
export const FIXTURE_CONFIG_STEPS = [
  'Environment Rating', 'CCT', 'Lens Appearance', 'Output Level',
  'Mounting Method', 'Finish', 'Length', 'Power Feed', 'Endcap Style',
];
export const FINISH_TO_ENDCAP_COLOR = { WH: 'WH', BK: 'BK', SV: 'GR' };

export const FIXTURE_TABS = [
  { id: 'product',      label: 'Product Info' },
  { id: 'profiles',     label: 'Profiles' },
  { id: 'lenses',       label: 'Lenses' },
  { id: 'mappings',     label: 'Profile ↔ Lens' },
  { id: 'accessories',  label: 'Accessories' },
  { id: 'endcaps',      label: 'Endcaps' },
  { id: 'fxTemplates',  label: 'Fixture Templates' },
  { id: 'fxOverrides',  label: 'Overrides' },
  { id: 'drivers',      label: 'Drivers' },
  { id: 'submittal',    label: 'Submittal' },
  { id: 'webflow',      label: 'Webflow' },
];

/* ============================================================================
   BLANK / EXAMPLE STATE
   ============================================================================ */
export function blankFixtureState() {
  return {
    fixtureProfiles: [],
    fixtureLenses: [],
    fixtureProfileLensMappings: [],
    fixtureAccessories: [],
    fixtureEndcaps: [],
    fixtureTemplates: {
      ledPackages: ['FS', 'SW', 'TW'],
      allowedFinishes: [],
      allowedLenses: [],
      allowedMountings: [],
      allowedEndcapStyles: [],
      allowedPowerFeedTypes: [],
      allowedEnvironmentRatings: [],
      tapeOfferings: [],
      basePriceMsrp: '0',
      pricePerFtMsrp: '0',
      pricingLengthBasis: 'L_tape_cut',
      assembledMaxLenMm: '2500',
      leaderAllowanceMmPerFixture: '15',
      defaultProfileStockLenMm: '2000',
    },
    fixtureTemplateOverrides: [],
    fixtureDrivers: { driverSpecs: ['PS-UNIV-24V-100W-IP66'], priority: '0' },
    fixtureSubmittalMapping: { cloneFromTemplate: '' },
    fixtureWebflow: {
      productCategory: 'linear-fixtures',
      sublabel: '',
      beamAngle: '110.0',
      operatingTempMinC: '-40',
      operatingTempMaxC: '60',
      l70LifeHours: '50000',
      warrantyYears: '5',
      configuratorSteps: [
        'Environment Rating', 'CCT', 'Lens Appearance', 'Output Level',
        'Mounting Method', 'Finish', 'Length',
      ],
    },
  };
}

export const EXAMPLE_FIXTURE = {
  productType: 'fixture',
  mode: 'new-family',
  seriesName: 'Castle',
  seriesCode: 'CA',
  supplier: 'Linea Lighting Co., Limited',
  brand: 'ilLumenate Lighting',
  warrantyDays: '1825',
  // tape/neon sections (unused in fixture mode, kept empty for state consistency)
  tapeSpecs: [],
  tapeOfferings: [],
  tapeNeonTemplates: [],
  neonSubmittalMapping: { cloneFromTemplate: '' },
  tapeNeonWebflow: {
    productCategory: 'led-tape', sublabel: '', beamAngle: '110.0',
    operatingTempMinC: '-40', operatingTempMaxC: '60',
    l70LifeHours: '50000', warrantyYears: '5', configuratorSteps: [],
  },
  // fixture sections
  fixtureProfiles: [
    {
      family: 'CA02', variantLabel: '[WD]', finishes: ['WH', 'BK', 'SV'],
      widthMm: '30.5', heightMm: '12.8', stockLengthMm: '2000',
      maxAssembledLengthMm: '2500', isCuttable: true, supportsJoiners: false,
      joinerSystem: '', lensInterface: 'Snap-in', environmentRatings: ['Dry'],
    },
    {
      family: 'CA01', variantLabel: '[NR]', finishes: ['WH', 'BK', 'SV'],
      widthMm: '23.5', heightMm: '12.8', stockLengthMm: '2000',
      maxAssembledLengthMm: '2500', isCuttable: true, supportsJoiners: false,
      joinerSystem: '', lensInterface: 'Snap-in', environmentRatings: ['Dry'],
    },
  ],
  fixtureLenses: [
    {
      family: 'CAXX', appearances: ['Black', 'Clear', 'Frosted', 'White'],
      shape: 'WH', stockType: 'Stick', stockLengthMm: '2000',
      continuousMaxLengthMm: '',
    },
  ],
  fixtureProfileLensMappings: [
    { profileFamilies: ['CA01', 'CA02'], lensFamily: 'CAXX' },
  ],
  fixtureAccessories: [
    {
      itemCode: 'ACC-CA01-PV', accessoryType: 'Mounting', profileFamily: 'CA01',
      mountingMethod: 'Pivot Clip', joinerSystem: '', joinerAngle: '',
      endcapStyle: '', allowanceOverridePerSideMm: '0', leaderCable: '',
      feedType: '', qtyRuleType: 'Per x mm', qtyRuleValue: '304.8',
      environmentRating: '',
    },
    {
      itemCode: 'ACC-CAXX-MC', accessoryType: 'Mounting', profileFamily: 'CAXX',
      mountingMethod: 'Mounting Clip', joinerSystem: '', joinerAngle: '',
      endcapStyle: '', allowanceOverridePerSideMm: '0', leaderCable: '',
      feedType: '', qtyRuleType: 'Per x mm', qtyRuleValue: '304.8',
      environmentRating: '',
    },
  ],
  fixtureEndcaps: [
    { profileFamily: 'CA02', colors: ['WH', 'BK', 'GR'], styles: ['Solid', 'Feed Through'], allowanceOverridePerSideMm: '2.0' },
    { profileFamily: 'CA01', colors: ['WH', 'BK', 'GR'], styles: ['Solid', 'Feed Through'], allowanceOverridePerSideMm: '2.0' },
  ],
  fixtureTemplates: {
    ledPackages: ['FS', 'SW', 'TW'],
    allowedFinishes: ['White', 'Black', 'Anodized Silver'],
    allowedLenses: ['White', 'Frosted', 'Clear', 'Black'],
    allowedMountings: ['Mounting Clip', 'Pivot Clip'],
    allowedEndcapStyles: ['Solid', 'Feed Through'],
    allowedPowerFeedTypes: [],
    allowedEnvironmentRatings: ['Dry'],
    tapeOfferings: [],
    basePriceMsrp: '0',
    pricePerFtMsrp: '0',
    pricingLengthBasis: 'L_tape_cut',
    assembledMaxLenMm: '2500',
    leaderAllowanceMmPerFixture: '15',
    defaultProfileStockLenMm: '2000',
  },
  fixtureTemplateOverrides: [],
  fixtureDrivers: { driverSpecs: ['PS-UNIV-24V-100W-IP66'], priority: '0' },
  fixtureSubmittalMapping: { cloneFromTemplate: 'ILL-AX01-FS' },
  fixtureWebflow: {
    productCategory: 'linear-fixtures',
    sublabel: '',
    beamAngle: '110.0',
    operatingTempMinC: '-40',
    operatingTempMaxC: '60',
    l70LifeHours: '50000',
    warrantyYears: '5',
    configuratorSteps: [
      'Environment Rating', 'CCT', 'Lens Appearance', 'Output Level',
      'Mounting Method', 'Finish', 'Length',
    ],
  },
};

/* ============================================================================
   SERIALIZER
   ============================================================================ */
function renderProfile(p, level) {
  let out = '';
  out += `${indent(level)}family: ${yamlScalar(p.family)}\n`;
  if (p.variantLabel) out += `${indent(level)}variant_label: ${yamlScalar(p.variantLabel)}\n`;
  out += `${indent(level)}finishes: [${(p.finishes || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}width_mm: ${yamlScalar(p.widthMm)}\n`;
  out += `${indent(level)}height_mm: ${yamlScalar(p.heightMm)}\n`;
  out += `${indent(level)}stock_length_mm: ${yamlScalar(p.stockLengthMm)}\n`;
  out += `${indent(level)}max_assembled_length_mm: ${yamlScalar(p.maxAssembledLengthMm)}\n`;
  out += `${indent(level)}is_cuttable: ${yamlScalar(!!p.isCuttable)}\n`;
  out += `${indent(level)}supports_joiners: ${yamlScalar(!!p.supportsJoiners)}\n`;
  out += `${indent(level)}joiner_system: ${yamlScalar(p.joinerSystem || '')}\n`;
  out += `${indent(level)}lens_interface: ${yamlScalar(p.lensInterface)}\n`;
  out += `${indent(level)}environment_ratings: [${(p.environmentRatings || []).map(yamlScalar).join(', ')}]\n`;
  return out;
}

function renderLens(l, level) {
  let out = '';
  out += `${indent(level)}family: ${yamlScalar(l.family)}\n`;
  out += `${indent(level)}appearances: [${(l.appearances || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}shape: ${yamlScalar(l.shape)}\n`;
  out += `${indent(level)}stock_type: ${yamlScalar(l.stockType)}\n`;
  out += `${indent(level)}stock_length_mm: ${yamlScalar(l.stockLengthMm)}\n`;
  if (l.continuousMaxLengthMm && String(l.continuousMaxLengthMm).trim() !== '') {
    out += `${indent(level)}continuous_max_length_mm: ${yamlScalar(l.continuousMaxLengthMm)}\n`;
  }
  return out;
}

function renderMapping(m, level) {
  let out = '';
  out += `${indent(level)}profile_families: [${(m.profileFamilies || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}lens_family: ${yamlScalar(m.lensFamily)}\n`;
  return out;
}

function renderAccessory(a, level) {
  let out = '';
  out += `${indent(level)}item_code: ${yamlScalar(a.itemCode)}\n`;
  out += `${indent(level)}accessory_type: ${yamlScalar(a.accessoryType)}\n`;
  out += `${indent(level)}profile_family: ${yamlScalar(a.profileFamily)}\n`;
  if (a.mountingMethod) out += `${indent(level)}mounting_method: ${yamlScalar(a.mountingMethod)}\n`;
  if (a.joinerSystem)   out += `${indent(level)}joiner_system: ${yamlScalar(a.joinerSystem)}\n`;
  if (a.joinerAngle)    out += `${indent(level)}joiner_angle: ${yamlScalar(a.joinerAngle)}\n`;
  if (a.endcapStyle)    out += `${indent(level)}endcap_style: ${yamlScalar(a.endcapStyle)}\n`;
  if (a.allowanceOverridePerSideMm && String(a.allowanceOverridePerSideMm).trim() !== '' && String(a.allowanceOverridePerSideMm) !== '0') {
    out += `${indent(level)}allowance_override_per_side_mm: ${yamlScalar(a.allowanceOverridePerSideMm)}\n`;
  }
  if (a.leaderCable) out += `${indent(level)}leader_cable: ${yamlScalar(a.leaderCable)}\n`;
  if (a.feedType)    out += `${indent(level)}feed_type: ${yamlScalar(a.feedType)}\n`;
  if (a.qtyRuleType) out += `${indent(level)}qty_rule_type: ${yamlScalar(a.qtyRuleType)}\n`;
  if (a.qtyRuleValue !== '' && a.qtyRuleValue != null) {
    out += `${indent(level)}qty_rule_value: ${yamlScalar(a.qtyRuleValue)}\n`;
  }
  if (a.environmentRating) out += `${indent(level)}environment_rating: ${yamlScalar(a.environmentRating)}\n`;
  return out;
}

function renderEndcap(e, level) {
  let out = '';
  out += `${indent(level)}profile_family: ${yamlScalar(e.profileFamily)}\n`;
  out += `${indent(level)}colors: [${(e.colors || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}styles: [${(e.styles || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowance_override_per_side_mm: ${yamlScalar(e.allowanceOverridePerSideMm)}\n`;
  return out;
}

function renderOverride(o, level) {
  let out = '';
  out += `${indent(level)}profile_family: ${yamlScalar(o.profileFamily)}\n`;
  out += `${indent(level)}led_package: ${yamlScalar(o.ledPackage)}\n`;
  out += `${indent(level)}allowed_finishes: [${(o.allowedFinishes || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowed_lenses: [${(o.allowedLenses || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowed_mountings: [${(o.allowedMountings || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowed_endcap_styles: [${(o.allowedEndcapStyles || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowed_power_feed_types: [${(o.allowedPowerFeedTypes || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}allowed_environment_ratings: [${(o.allowedEnvironmentRatings || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}tape_offerings: [${(o.tapeOfferings || []).map(yamlScalar).join(', ')}]\n`;
  out += `${indent(level)}base_price_msrp: ${yamlScalar(o.basePriceMsrp)}\n`;
  out += `${indent(level)}price_per_ft_msrp: ${yamlScalar(o.pricePerFtMsrp)}\n`;
  return out;
}

export function serializeFixtureYaml(s) {
  let out = '';
  out += `# Linear Fixture Configuration — generated by ilLumenate YAML Builder\n`;
  out += `# Usage: python -m tools.fixture_builder --product-type fixture --config <path-to-this-file> --output ./output/${(s.seriesCode || 'series').toLowerCase()}/\n`;
  out += `\n`;
  out += `product_type: fixture\n`;
  out += `mode: ${yamlScalar(s.mode || 'new-family')}\n`;
  out += `series_name: ${yamlScalar(s.seriesName)}\n`;
  out += `series_code: ${yamlScalar(s.seriesCode)}\n`;
  out += `\n`;
  out += `supplier: ${yamlScalar(s.supplier)}\n`;
  out += `brand: ${yamlScalar(s.brand)}\n`;
  out += `warranty_days: ${yamlScalar(s.warrantyDays)}\n`;
  out += `\n`;

  out += `# ── Profile Families ─────────────────────────────────────────────────\n`;
  out += `profiles:\n`;
  out += yamlListOfObjects(s.fixtureProfiles || [], 1, renderProfile);
  out += `\n`;

  out += `# ── Lens Families ────────────────────────────────────────────────────\n`;
  out += `lenses:\n`;
  out += yamlListOfObjects(s.fixtureLenses || [], 1, renderLens);
  out += `\n`;

  out += `# ── Profile → Lens Mappings ──────────────────────────────────────────\n`;
  out += `profile_lens_mappings:\n`;
  out += yamlListOfObjects(s.fixtureProfileLensMappings || [], 1, renderMapping);
  out += `\n`;

  out += `# ── Accessories (Mounting / Joiner) ──────────────────────────────────\n`;
  out += `accessories:\n`;
  out += yamlListOfObjects(s.fixtureAccessories || [], 1, renderAccessory);
  out += `\n`;

  out += `# ── Endcaps (per profile family) ─────────────────────────────────────\n`;
  out += `endcaps:\n`;
  out += yamlListOfObjects(s.fixtureEndcaps || [], 1, renderEndcap);
  out += `\n`;

  out += `# ── Fixture Templates (global defaults) ──────────────────────────────\n`;
  const ft = s.fixtureTemplates || {};
  out += `fixture_templates:\n`;
  out += `  led_packages: [${(ft.ledPackages || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_finishes: [${(ft.allowedFinishes || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_lenses: [${(ft.allowedLenses || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_mountings: [${(ft.allowedMountings || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_endcap_styles: [${(ft.allowedEndcapStyles || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_power_feed_types: [${(ft.allowedPowerFeedTypes || []).map(yamlScalar).join(', ')}]\n`;
  out += `  allowed_environment_ratings: [${(ft.allowedEnvironmentRatings || []).map(yamlScalar).join(', ')}]\n`;
  out += `  tape_offerings: [${(ft.tapeOfferings || []).map(yamlScalar).join(', ')}]\n`;
  out += `  base_price_msrp: ${yamlScalar(ft.basePriceMsrp)}\n`;
  out += `  price_per_ft_msrp: ${yamlScalar(ft.pricePerFtMsrp)}\n`;
  out += `  pricing_length_basis: ${yamlScalar(ft.pricingLengthBasis)}\n`;
  out += `  assembled_max_len_mm: ${yamlScalar(ft.assembledMaxLenMm)}\n`;
  out += `  leader_allowance_mm_per_fixture: ${yamlScalar(ft.leaderAllowanceMmPerFixture)}\n`;
  out += `  default_profile_stock_len_mm: ${yamlScalar(ft.defaultProfileStockLenMm)}\n`;
  out += `\n`;

  if ((s.fixtureTemplateOverrides || []).length > 0) {
    out += `# ── Per-Template Overrides ───────────────────────────────────────────\n`;
    out += `template_overrides:\n`;
    out += yamlListOfObjects(s.fixtureTemplateOverrides, 1, renderOverride);
    out += `\n`;
  }

  out += `# ── Drivers ──────────────────────────────────────────────────────────\n`;
  const d = s.fixtureDrivers || {};
  out += `drivers:\n`;
  out += `  driver_specs: [${(d.driverSpecs || []).map(yamlScalar).join(', ')}]\n`;
  if (d.priority !== '' && d.priority != null) out += `  priority: ${yamlScalar(d.priority)}\n`;
  out += `\n`;

  out += `# ── Submittal Mapping ────────────────────────────────────────────────\n`;
  out += `submittal_mapping:\n`;
  out += `  clone_from_template: ${yamlScalar(s.fixtureSubmittalMapping?.cloneFromTemplate || '')}\n`;
  out += `\n`;

  out += `# ── Webflow ──────────────────────────────────────────────────────────\n`;
  const w = s.fixtureWebflow || {};
  out += `webflow:\n`;
  out += `  product_category: ${yamlScalar(w.productCategory || 'linear-fixtures')}\n`;
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
   VALIDATOR
   ============================================================================ */
export function validateFixture(s) {
  const issues = [];

  if (!s.seriesName?.trim())  issues.push({ level: 'warn', text: 'Series name is empty.' });
  if (!s.seriesCode?.trim())  issues.push({ level: 'warn', text: 'Series code is empty.' });
  if (!s.supplier?.trim())    issues.push({ level: 'warn', text: 'Supplier is empty.' });
  if (!s.brand?.trim())       issues.push({ level: 'warn', text: 'Brand is empty.' });
  if (!isNumericString(String(s.warrantyDays)) || Number(s.warrantyDays) <= 0) {
    issues.push({ level: 'warn', text: 'Warranty days should be a positive number.' });
  }

  const profileFamilies = new Set();
  const dupProfile = new Set();
  if (!s.fixtureProfiles?.length) {
    issues.push({ level: 'error', text: 'At least one profile family is required.' });
  }
  s.fixtureProfiles?.forEach((p, i) => {
    if (!p.family?.trim()) issues.push({ level: 'error', text: `Profile #${i + 1}: family code is required.` });
    else if (profileFamilies.has(p.family)) dupProfile.add(p.family);
    else profileFamilies.add(p.family);
    if (!isNumericString(String(p.widthMm)) || Number(p.widthMm) <= 0) {
      issues.push({ level: 'warn', text: `Profile "${p.family || `#${i + 1}`}": width_mm should be positive.` });
    }
    if (!isNumericString(String(p.heightMm)) || Number(p.heightMm) <= 0) {
      issues.push({ level: 'warn', text: `Profile "${p.family || `#${i + 1}`}": height_mm should be positive.` });
    }
    if (!(p.finishes?.length > 0)) {
      issues.push({ level: 'warn', text: `Profile "${p.family || `#${i + 1}`}": no finishes selected.` });
    }
    if (!(p.environmentRatings?.length > 0)) {
      issues.push({ level: 'warn', text: `Profile "${p.family || `#${i + 1}`}": no environment ratings selected.` });
    }
  });
  dupProfile.forEach(c => issues.push({ level: 'error', text: `Duplicate profile family: "${c}".` }));

  const lensFamilies = new Set();
  const dupLens = new Set();
  if (!s.fixtureLenses?.length) {
    issues.push({ level: 'error', text: 'At least one lens family is required.' });
  }
  s.fixtureLenses?.forEach((l, i) => {
    if (!l.family?.trim()) issues.push({ level: 'error', text: `Lens #${i + 1}: family code is required.` });
    else if (lensFamilies.has(l.family)) dupLens.add(l.family);
    else lensFamilies.add(l.family);
    if (!(l.appearances?.length > 0)) {
      issues.push({ level: 'warn', text: `Lens "${l.family || `#${i + 1}`}": no appearances selected.` });
    }
  });
  dupLens.forEach(c => issues.push({ level: 'error', text: `Duplicate lens family: "${c}".` }));

  s.fixtureProfileLensMappings?.forEach((m, i) => {
    (m.profileFamilies || []).forEach(pf => {
      if (!profileFamilies.has(pf) && pf !== profileFamily(pf)) {
        // allow "CAXX"-style shared codes that aren't a profile family
        if (!profileFamilies.has(pf)) {
          issues.push({ level: 'warn', text: `Profile↔Lens mapping #${i + 1}: profile_family "${pf}" not defined in profiles.` });
        }
      }
    });
    if (m.lensFamily && !lensFamilies.has(m.lensFamily)) {
      issues.push({ level: 'warn', text: `Profile↔Lens mapping #${i + 1}: lens_family "${m.lensFamily}" not defined in lenses.` });
    }
  });

  const accCodes = new Set();
  const dupAcc = new Set();
  s.fixtureAccessories?.forEach((a, i) => {
    if (!a.itemCode?.trim()) issues.push({ level: 'error', text: `Accessory #${i + 1}: item_code is required.` });
    else if (accCodes.has(a.itemCode)) dupAcc.add(a.itemCode);
    else accCodes.add(a.itemCode);
    if (!a.accessoryType) issues.push({ level: 'warn', text: `Accessory "${a.itemCode || `#${i + 1}`}": accessory_type is empty.` });
  });
  dupAcc.forEach(c => issues.push({ level: 'error', text: `Duplicate accessory item_code: "${c}".` }));

  s.fixtureEndcaps?.forEach((e, i) => {
    if (!e.profileFamily?.trim()) issues.push({ level: 'error', text: `Endcap row #${i + 1}: profile_family is required.` });
    else if (!profileFamilies.has(e.profileFamily)) {
      issues.push({ level: 'warn', text: `Endcap row #${i + 1}: profile_family "${e.profileFamily}" not defined in profiles.` });
    }
    if (!(e.colors?.length > 0)) issues.push({ level: 'warn', text: `Endcap row #${i + 1}: no colors selected.` });
    if (!(e.styles?.length > 0)) issues.push({ level: 'warn', text: `Endcap row #${i + 1}: no styles selected.` });
  });

  const ft = s.fixtureTemplates || {};
  if (!(ft.ledPackages?.length > 0)) {
    issues.push({ level: 'error', text: 'Fixture Templates: at least one LED package is required.' });
  }

  s.fixtureTemplateOverrides?.forEach((o, i) => {
    if (o.profileFamily && !profileFamilies.has(o.profileFamily)) {
      issues.push({ level: 'warn', text: `Override #${i + 1}: profile_family "${o.profileFamily}" not defined.` });
    }
    if (o.ledPackage && !(ft.ledPackages || []).includes(o.ledPackage)) {
      issues.push({ level: 'warn', text: `Override #${i + 1}: led_package "${o.ledPackage}" not in fixture_templates.led_packages.` });
    }
  });

  if (!(s.fixtureDrivers?.driverSpecs?.length > 0)) {
    issues.push({ level: 'warn', text: 'No driver specs defined.' });
  }

  if ((s.fixtureWebflow?.productCategory || '') !== 'linear-fixtures') {
    issues.push({ level: 'warn', text: 'Webflow product_category should be "linear-fixtures" for linear fixtures.' });
  }

  return issues;
}

function profileFamily(pf) { return pf; }

/* ============================================================================
   SECTION COMPONENTS
   ============================================================================ */

function ProfilesSection({ s, setS }) {
  const add = () => setS({
    ...s,
    fixtureProfiles: [...s.fixtureProfiles, {
      family: '', variantLabel: '', finishes: ['WH', 'BK', 'SV'],
      widthMm: '', heightMm: '', stockLengthMm: '2000',
      maxAssembledLengthMm: '2500', isCuttable: true, supportsJoiners: false,
      joinerSystem: '', lensInterface: 'Snap-in', environmentRatings: ['Dry'],
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureProfiles]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureProfiles: c });
  };
  const rm = (i) => setS({ ...s, fixtureProfiles: s.fixtureProfiles.filter((_, idx) => idx !== i) });
  const dup = (i) => {
    const c = [...s.fixtureProfiles];
    c.splice(i + 1, 0, { ...c[i], family: c[i].family + '-COPY' });
    setS({ ...s, fixtureProfiles: c });
  };
  return (
    <Section
      title="Profiles"
      subtitle="Each entry becomes one ilL-Spec-Profile family. The family code (e.g. CA01) appears in item codes like CH-CA01-WH-2000."
      count={s.fixtureProfiles.length}
      right={<Button onClick={add} variant="primary" icon={Plus}>Add Profile</Button>}
    >
      {s.fixtureProfiles.length === 0 && <EmptyHint label="No profiles yet. Add one to get started." />}
      {s.fixtureProfiles.map((p, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>profile #{i + 1}</span>
              {p.family && <span style={{ color: T.ink, marginLeft: 10 }}>{p.family}</span>}
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" icon={Copy} onClick={() => dup(i)}>Duplicate</Button>
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Family" required hint="e.g. CA01">
              <TextInput monospace value={p.family} onChange={v => upd(i, { family: v })} placeholder="CA01" />
            </Field>
            <Field label="Variant Label" hint='e.g. "[NR]" or "[WD]"'>
              <TextInput value={p.variantLabel} onChange={v => upd(i, { variantLabel: v })} placeholder="[NR]" />
            </Field>
            <Field label="Width (mm)" required>
              <NumInput value={p.widthMm} onChange={v => upd(i, { widthMm: v })} placeholder="23.5" />
            </Field>
            <Field label="Height (mm)" required>
              <NumInput value={p.heightMm} onChange={v => upd(i, { heightMm: v })} placeholder="12.8" />
            </Field>
            <Field label="Stock Length (mm)">
              <NumInput value={p.stockLengthMm} onChange={v => upd(i, { stockLengthMm: v })} placeholder="2000" />
            </Field>
            <Field label="Max Assembled Length (mm)">
              <NumInput value={p.maxAssembledLengthMm} onChange={v => upd(i, { maxAssembledLengthMm: v })} placeholder="2500" />
            </Field>
            <Field label="Lens Interface">
              <Select value={p.lensInterface} onChange={v => upd(i, { lensInterface: v })} options={LENS_INTERFACE_CHOICES} />
            </Field>
            <Field label="Joiner System" hint="Blank if no joiners">
              <TextInput value={p.joinerSystem} onChange={v => upd(i, { joinerSystem: v })} placeholder="Eldorado-Single" />
            </Field>
            <Field label="Cuttable?">
              <Checkbox checked={!!p.isCuttable} onChange={v => upd(i, { isCuttable: v })} label={p.isCuttable ? 'Yes' : 'No'} />
            </Field>
            <Field label="Supports Joiners?">
              <Checkbox checked={!!p.supportsJoiners} onChange={v => upd(i, { supportsJoiners: v })} label={p.supportsJoiners ? 'Yes' : 'No'} />
            </Field>
            <Field label="Finishes" wide>
              <MultiSelect value={p.finishes} onChange={v => upd(i, { finishes: v })} options={FIXTURE_FINISH_CHOICES} />
            </Field>
            <Field label="Environment Ratings" wide>
              <MultiSelect value={p.environmentRatings} onChange={v => upd(i, { environmentRatings: v })} options={FIXTURE_ENV_RATINGS} />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function LensesSection({ s, setS }) {
  const add = () => setS({
    ...s,
    fixtureLenses: [...s.fixtureLenses, {
      family: '', appearances: ['White'], shape: 'WH',
      stockType: 'Stick', stockLengthMm: '2000', continuousMaxLengthMm: '',
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureLenses]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureLenses: c });
  };
  const rm = (i) => setS({ ...s, fixtureLenses: s.fixtureLenses.filter((_, idx) => idx !== i) });
  return (
    <Section
      title="Lenses"
      subtitle="Lens families. Use the XX-suffix convention (e.g. CAXX) when one lens family is shared across multiple profiles."
      count={s.fixtureLenses.length}
      right={<Button onClick={add} variant="primary" icon={Plus}>Add Lens</Button>}
    >
      {s.fixtureLenses.length === 0 && <EmptyHint label="No lens families yet." />}
      {s.fixtureLenses.map((l, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>lens #{i + 1}</span>
              {l.family && <span style={{ color: T.ink, marginLeft: 10 }}>{l.family}</span>}
            </div>
            <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Family" required>
              <TextInput monospace value={l.family} onChange={v => upd(i, { family: v })} placeholder="CAXX" />
            </Field>
            <Field label="Shape">
              <Select value={l.shape} onChange={v => upd(i, { shape: v })} options={LENS_SHAPE_CHOICES} />
            </Field>
            <Field label="Stock Type">
              <Select value={l.stockType} onChange={v => upd(i, { stockType: v })} options={LENS_STOCK_TYPE_CHOICES} />
            </Field>
            <Field label="Stock Length (mm)">
              <NumInput value={l.stockLengthMm} onChange={v => upd(i, { stockLengthMm: v })} placeholder="2000" />
            </Field>
            <Field label="Continuous Max Length (mm)" hint="Optional, for Continuous stock_type">
              <NumInput value={l.continuousMaxLengthMm} onChange={v => upd(i, { continuousMaxLengthMm: v })} placeholder="(optional)" />
            </Field>
            <Field label="Appearances" wide>
              <MultiSelect value={l.appearances} onChange={v => upd(i, { appearances: v })} options={LENS_APPEARANCE_CHOICES} />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function ProfileLensMappingsSection({ s, setS }) {
  const profileCodes = s.fixtureProfiles.map(p => p.family).filter(Boolean);
  const lensCodes = s.fixtureLenses.map(l => l.family).filter(Boolean);
  const add = () => setS({
    ...s,
    fixtureProfileLensMappings: [...s.fixtureProfileLensMappings, {
      profileFamilies: [], lensFamily: lensCodes[0] || '',
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureProfileLensMappings]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureProfileLensMappings: c });
  };
  const rm = (i) => setS({ ...s, fixtureProfileLensMappings: s.fixtureProfileLensMappings.filter((_, idx) => idx !== i) });
  return (
    <Section
      title="Profile ↔ Lens"
      subtitle="Which lens families are compatible with which profile families. One mapping row per lens family is typical."
      count={s.fixtureProfileLensMappings.length}
      right={<Button onClick={add} variant="primary" icon={Plus} disabled={!profileCodes.length || !lensCodes.length}>Add Mapping</Button>}
    >
      {(!profileCodes.length || !lensCodes.length) && (
        <EmptyHint label="Define at least one profile and one lens before mapping." />
      )}
      {s.fixtureProfileLensMappings.map((m, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>mapping #{i + 1}</span>
            </div>
            <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Profile Families" wide>
              <MultiSelect value={m.profileFamilies} onChange={v => upd(i, { profileFamilies: v })} options={profileCodes} />
            </Field>
            <Field label="Lens Family">
              <Select value={m.lensFamily} onChange={v => upd(i, { lensFamily: v })} options={lensCodes} allowEmpty placeholder="— Select —" />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function AccessoriesSection({ s, setS }) {
  const profileCodes = s.fixtureProfiles.map(p => p.family).filter(Boolean);
  const allProfileChoices = Array.from(new Set([...profileCodes, ...profileCodes.map(p => p.replace(/\d+$/, 'XX'))])); // include XX variants
  const add = () => setS({
    ...s,
    fixtureAccessories: [...s.fixtureAccessories, {
      itemCode: '', accessoryType: 'Mounting',
      profileFamily: profileCodes[0] || '',
      mountingMethod: 'Mounting Clip', joinerSystem: '', joinerAngle: '',
      endcapStyle: '', allowanceOverridePerSideMm: '0',
      leaderCable: '', feedType: '',
      qtyRuleType: 'Per x mm', qtyRuleValue: '304.8',
      environmentRating: '',
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureAccessories]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureAccessories: c });
  };
  const rm = (i) => setS({ ...s, fixtureAccessories: s.fixtureAccessories.filter((_, idx) => idx !== i) });
  const dup = (i) => {
    const c = [...s.fixtureAccessories];
    c.splice(i + 1, 0, { ...c[i], itemCode: c[i].itemCode + '-COPY' });
    setS({ ...s, fixtureAccessories: c });
  };
  return (
    <Section
      title="Accessories"
      subtitle="Mounting clips, joiners, etc. Use the XX-suffix profile family (e.g. CAXX) for accessories shared across the whole series. Endcaps live on the next tab."
      count={s.fixtureAccessories.length}
      right={<Button onClick={add} variant="primary" icon={Plus}>Add Accessory</Button>}
    >
      {s.fixtureAccessories.length === 0 && <EmptyHint label="No accessories yet." />}
      {s.fixtureAccessories.map((a, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>accessory #{i + 1}</span>
              {a.itemCode && <span style={{ color: T.ink, marginLeft: 10 }}>{a.itemCode}</span>}
            </div>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" icon={Copy} onClick={() => dup(i)}>Duplicate</Button>
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Item Code" required>
              <TextInput monospace value={a.itemCode} onChange={v => upd(i, { itemCode: v })} placeholder="ACC-CAXX-MC" />
            </Field>
            <Field label="Accessory Type">
              <Select value={a.accessoryType} onChange={v => upd(i, { accessoryType: v })} options={ACCESSORY_TYPE_CHOICES} />
            </Field>
            <Field label="Profile Family">
              <TextInput list={`acc-pf-${i}`} value={a.profileFamily} onChange={v => upd(i, { profileFamily: v })} placeholder="CAXX or CA01" />
              <datalist id={`acc-pf-${i}`}>{allProfileChoices.map(x => <option key={x} value={x} />)}</datalist>
            </Field>
            {a.accessoryType === 'Mounting' && (
              <Field label="Mounting Method">
                <TextInput list={`acc-mm-${i}`} value={a.mountingMethod} onChange={v => upd(i, { mountingMethod: v })} placeholder="Mounting Clip" />
                <datalist id={`acc-mm-${i}`}>{MOUNTING_METHOD_CHOICES.map(x => <option key={x} value={x} />)}</datalist>
              </Field>
            )}
            {a.accessoryType === 'Joiner' && (
              <>
                <Field label="Joiner System">
                  <TextInput value={a.joinerSystem} onChange={v => upd(i, { joinerSystem: v })} placeholder="Eldorado-Single" />
                </Field>
                <Field label="Joiner Angle">
                  <TextInput value={a.joinerAngle} onChange={v => upd(i, { joinerAngle: v })} placeholder="90°" />
                </Field>
              </>
            )}
            <Field label="Qty Rule Type">
              <Select value={a.qtyRuleType} onChange={v => upd(i, { qtyRuleType: v })} options={QTY_RULE_CHOICES} />
            </Field>
            <Field label="Qty Rule Value" hint="e.g. 304.8 = 1 per ft">
              <NumInput value={a.qtyRuleValue} onChange={v => upd(i, { qtyRuleValue: v })} placeholder="304.8" />
            </Field>
            <Field label="Environment Rating" hint="Optional filter">
              <Select value={a.environmentRating} onChange={v => upd(i, { environmentRating: v })} options={FIXTURE_ENV_RATINGS} allowEmpty placeholder="— Any —" />
            </Field>
            <Field label="Allowance / Side (mm)" hint="Override; blank = use default">
              <NumInput value={a.allowanceOverridePerSideMm} onChange={v => upd(i, { allowanceOverridePerSideMm: v })} placeholder="0" />
            </Field>
            <Field label="Leader Cable" hint="Optional">
              <TextInput value={a.leaderCable} onChange={v => upd(i, { leaderCable: v })} placeholder="(optional)" />
            </Field>
            <Field label="Feed Type" hint="Optional">
              <TextInput value={a.feedType} onChange={v => upd(i, { feedType: v })} placeholder="(optional)" />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function EndcapsSection({ s, setS }) {
  const profileCodes = s.fixtureProfiles.map(p => p.family).filter(Boolean);
  const add = () => setS({
    ...s,
    fixtureEndcaps: [...s.fixtureEndcaps, {
      profileFamily: profileCodes[0] || '',
      colors: ['WH', 'BK', 'GR'],
      styles: ['Solid', 'Feed Through'],
      allowanceOverridePerSideMm: '2.0',
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureEndcaps]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureEndcaps: c });
  };
  const rm = (i) => setS({ ...s, fixtureEndcaps: s.fixtureEndcaps.filter((_, idx) => idx !== i) });

  return (
    <Section
      title="Endcaps"
      subtitle="Define one row per profile family. Each row expands into ColorsxStyles individual endcap accessories (e.g. EC-CA01-WH-NO, EC-CA01-WH-HO, ...)."
      count={s.fixtureEndcaps.length}
      right={<Button onClick={add} variant="primary" icon={Plus} disabled={!profileCodes.length}>Add Endcap Row</Button>}
    >
      {!profileCodes.length && <EmptyHint label="Define at least one profile family first." />}
      {s.fixtureEndcaps.map((e, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>endcap row #{i + 1}</span>
              {e.profileFamily && <span style={{ color: T.ink, marginLeft: 10 }}>{e.profileFamily}</span>}
              <span style={{ color: T.subtle, marginLeft: 10 }}>
                → {(e.colors?.length || 0) * (e.styles?.length || 0)} items
              </span>
            </div>
            <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Profile Family">
              <Select value={e.profileFamily} onChange={v => upd(i, { profileFamily: v })} options={profileCodes} allowEmpty placeholder="— Select —" />
            </Field>
            <Field label="Allowance / Side (mm)">
              <NumInput value={e.allowanceOverridePerSideMm} onChange={v => upd(i, { allowanceOverridePerSideMm: v })} placeholder="2.0" />
            </Field>
            <Field label="Colors" wide>
              <MultiSelect value={e.colors} onChange={v => upd(i, { colors: v })} options={ENDCAP_COLOR_CHOICES} />
            </Field>
            <Field label="Styles" wide>
              <MultiSelect value={e.styles} onChange={v => upd(i, { styles: v })} options={ENDCAP_STYLE_CHOICES} />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function FixtureTemplatesSection({ s, setS }) {
  const ft = s.fixtureTemplates;
  const upd = (patch) => setS({ ...s, fixtureTemplates: { ...ft, ...patch } });
  return (
    <Section
      title="Fixture Templates"
      subtitle="Global default options applied to all templates (one template per profile family x LED package). Per-template overrides live on the next tab."
    >
      <Card>
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: '0 0 12px 0' }}>LED Packages</h3>
        <MultiSelect value={ft.ledPackages} onChange={v => upd({ ledPackages: v })} options={FIXTURE_LED_PACKAGES} />
      </Card>

      <Card>
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: '0 0 12px 0' }}>Allowed Options (defaults)</h3>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Allowed Finishes" wide>
            <MultiSelect value={ft.allowedFinishes} onChange={v => upd({ allowedFinishes: v })} options={FINISH_DISPLAY_CHOICES} />
          </Field>
          <Field label="Allowed Lens Appearances" wide>
            <MultiSelect value={ft.allowedLenses} onChange={v => upd({ allowedLenses: v })} options={LENS_APPEARANCE_CHOICES} />
          </Field>
          <Field label="Allowed Mountings" wide>
            <MultiSelect value={ft.allowedMountings} onChange={v => upd({ allowedMountings: v })} options={MOUNTING_METHOD_CHOICES} />
          </Field>
          <Field label="Allowed Endcap Styles" wide>
            <MultiSelect value={ft.allowedEndcapStyles} onChange={v => upd({ allowedEndcapStyles: v })} options={ENDCAP_STYLE_CHOICES} />
          </Field>
          <Field label="Allowed Power Feed Types" wide>
            <MultiSelect value={ft.allowedPowerFeedTypes} onChange={v => upd({ allowedPowerFeedTypes: v })} options={POWER_FEED_CHOICES} />
          </Field>
          <Field label="Allowed Environment Ratings" wide>
            <MultiSelect value={ft.allowedEnvironmentRatings} onChange={v => upd({ allowedEnvironmentRatings: v })} options={FIXTURE_ENV_RATINGS} />
          </Field>
        </div>
      </Card>

      <Card>
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: '0 0 12px 0' }}>Pricing & Assembly</h3>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Base Price MSRP ($)">
            <NumInput value={ft.basePriceMsrp} onChange={v => upd({ basePriceMsrp: v })} placeholder="0.00" />
          </Field>
          <Field label="Price / ft MSRP ($)">
            <NumInput value={ft.pricePerFtMsrp} onChange={v => upd({ pricePerFtMsrp: v })} placeholder="0.00" />
          </Field>
          <Field label="Pricing Length Basis">
            <Select value={ft.pricingLengthBasis} onChange={v => upd({ pricingLengthBasis: v })} options={FIXTURE_PRICING_BASIS} />
          </Field>
          <Field label="Assembled Max Length (mm)">
            <NumInput value={ft.assembledMaxLenMm} onChange={v => upd({ assembledMaxLenMm: v })} placeholder="2500" />
          </Field>
          <Field label="Leader Allowance / Fixture (mm)">
            <NumInput value={ft.leaderAllowanceMmPerFixture} onChange={v => upd({ leaderAllowanceMmPerFixture: v })} placeholder="15" />
          </Field>
          <Field label="Default Profile Stock Length (mm)">
            <NumInput value={ft.defaultProfileStockLenMm} onChange={v => upd({ defaultProfileStockLenMm: v })} placeholder="2000" />
          </Field>
        </div>
      </Card>

      <Card>
        <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: '0 0 12px 0' }}>Tape Offerings (references)</h3>
        <p style={{ fontFamily: fontBody, fontSize: 12, color: T.muted, margin: '0 0 10px 0' }}>
          Pre-existing ilL-Rel-Tape Offering names to link. Comma-separated list of offering codes.
        </p>
        <CsvList value={ft.tapeOfferings} onChange={v => upd({ tapeOfferings: v })} placeholder="ILL-OFR-FS-2700K-STD" />
      </Card>
    </Section>
  );
}

function CsvList({ value, onChange, placeholder }) {
  const txt = (value || []).join(', ');
  return (
    <TextInput
      monospace
      value={txt}
      onChange={v => onChange(v.split(',').map(x => x.trim()).filter(Boolean))}
      placeholder={placeholder}
    />
  );
}

function TemplateOverridesSection({ s, setS }) {
  const profileCodes = s.fixtureProfiles.map(p => p.family).filter(Boolean);
  const ledPackages = s.fixtureTemplates.ledPackages || [];
  const add = () => setS({
    ...s,
    fixtureTemplateOverrides: [...s.fixtureTemplateOverrides, {
      profileFamily: profileCodes[0] || '', ledPackage: ledPackages[0] || '',
      allowedFinishes: [], allowedLenses: [], allowedMountings: [],
      allowedEndcapStyles: [], allowedPowerFeedTypes: [],
      allowedEnvironmentRatings: [], tapeOfferings: [],
      basePriceMsrp: '0', pricePerFtMsrp: '0',
    }],
  });
  const upd = (i, patch) => {
    const c = [...s.fixtureTemplateOverrides]; c[i] = { ...c[i], ...patch };
    setS({ ...s, fixtureTemplateOverrides: c });
  };
  const rm = (i) => setS({ ...s, fixtureTemplateOverrides: s.fixtureTemplateOverrides.filter((_, idx) => idx !== i) });

  return (
    <Section
      title="Per-Template Overrides"
      subtitle="Override allowed options or pricing for a specific profile family x LED package combination. Leave empty to inherit defaults from the previous tab."
      count={s.fixtureTemplateOverrides.length}
      right={<Button onClick={add} variant="primary" icon={Plus} disabled={!profileCodes.length || !ledPackages.length}>Add Override</Button>}
    >
      {(!profileCodes.length || !ledPackages.length) && (
        <EmptyHint label="Define at least one profile and one LED package first." />
      )}
      {s.fixtureTemplateOverrides.length === 0 && profileCodes.length > 0 && ledPackages.length > 0 && (
        <EmptyHint label="No overrides. Templates will use the global defaults from the previous tab." />
      )}
      {s.fixtureTemplateOverrides.map((o, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between mb-4">
            <div style={{ fontFamily: fontMono, fontSize: 13, color: T.muted }}>
              <span style={{ color: T.subtle }}>override #{i + 1}</span>
              {o.profileFamily && o.ledPackage && (
                <span style={{ color: T.ink, marginLeft: 10 }}>ILL-{o.profileFamily}-{o.ledPackage}</span>
              )}
            </div>
            <Button size="sm" variant="danger" icon={Trash2} onClick={() => rm(i)}>Remove</Button>
          </div>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <Field label="Profile Family" required>
              <Select value={o.profileFamily} onChange={v => upd(i, { profileFamily: v })} options={profileCodes} allowEmpty placeholder="— Select —" />
            </Field>
            <Field label="LED Package" required>
              <Select value={o.ledPackage} onChange={v => upd(i, { ledPackage: v })} options={ledPackages} allowEmpty placeholder="— Select —" />
            </Field>
            <Field label="Allowed Finishes" wide>
              <MultiSelect value={o.allowedFinishes} onChange={v => upd(i, { allowedFinishes: v })} options={FINISH_DISPLAY_CHOICES} />
            </Field>
            <Field label="Allowed Lens Appearances" wide>
              <MultiSelect value={o.allowedLenses} onChange={v => upd(i, { allowedLenses: v })} options={LENS_APPEARANCE_CHOICES} />
            </Field>
            <Field label="Allowed Mountings" wide>
              <MultiSelect value={o.allowedMountings} onChange={v => upd(i, { allowedMountings: v })} options={MOUNTING_METHOD_CHOICES} />
            </Field>
            <Field label="Allowed Endcap Styles" wide>
              <MultiSelect value={o.allowedEndcapStyles} onChange={v => upd(i, { allowedEndcapStyles: v })} options={ENDCAP_STYLE_CHOICES} />
            </Field>
            <Field label="Allowed Power Feed Types" wide>
              <MultiSelect value={o.allowedPowerFeedTypes} onChange={v => upd(i, { allowedPowerFeedTypes: v })} options={POWER_FEED_CHOICES} />
            </Field>
            <Field label="Allowed Environment Ratings" wide>
              <MultiSelect value={o.allowedEnvironmentRatings} onChange={v => upd(i, { allowedEnvironmentRatings: v })} options={FIXTURE_ENV_RATINGS} />
            </Field>
            <Field label="Base Price MSRP ($)">
              <NumInput value={o.basePriceMsrp} onChange={v => upd(i, { basePriceMsrp: v })} placeholder="0.00" />
            </Field>
            <Field label="Price / ft MSRP ($)">
              <NumInput value={o.pricePerFtMsrp} onChange={v => upd(i, { pricePerFtMsrp: v })} placeholder="0.00" />
            </Field>
            <Field label="Tape Offerings" wide hint="Comma-separated">
              <CsvList value={o.tapeOfferings} onChange={v => upd(i, { tapeOfferings: v })} placeholder="ILL-OFR-FS-2700K-STD" />
            </Field>
          </div>
        </Card>
      ))}
    </Section>
  );
}

function DriversSection({ s, setS }) {
  const d = s.fixtureDrivers;
  const upd = (patch) => setS({ ...s, fixtureDrivers: { ...d, ...patch } });
  return (
    <Section
      title="Drivers"
      subtitle="Driver-spec item codes eligible for this fixture series. The CLI generates ilL-Rel-Driver-Eligibility rows for each."
    >
      <Card>
        <Field label="Driver Specs" hint="Comma-separated item codes" wide>
          <CsvList value={d.driverSpecs} onChange={v => upd({ driverSpecs: v })} placeholder="PS-UNIV-24V-100W-IP66" />
        </Field>
        <div style={{ marginTop: 12 }}>
          <Field label="Priority" hint="Lower = preferred (default 0)">
            <NumInput value={d.priority} onChange={v => upd({ priority: v })} placeholder="0" />
          </Field>
        </div>
      </Card>
    </Section>
  );
}

function FixtureSubmittalSection({ s, setS }) {
  return (
    <Section
      title="Submittal Mapping"
      subtitle={`Clone an existing template's submittal layout. Use a template code like "ILL-AX01-FS".`}
    >
      <Card>
        <Field label="Clone From Template" hint="e.g. ILL-AX01-FS">
          <TextInput
            monospace
            value={s.fixtureSubmittalMapping?.cloneFromTemplate || ''}
            onChange={v => setS({ ...s, fixtureSubmittalMapping: { cloneFromTemplate: v } })}
            placeholder="ILL-AX01-FS"
          />
        </Field>
      </Card>
    </Section>
  );
}

function FixtureWebflowSection({ s, setS }) {
  const w = s.fixtureWebflow;
  const upd = (patch) => setS({ ...s, fixtureWebflow: { ...w, ...patch } });
  const [newStep, setNewStep] = useState('');

  const addStep = () => {
    if (!newStep.trim()) return;
    upd({ configuratorSteps: [...(w.configuratorSteps || []), newStep.trim()] });
    setNewStep('');
  };
  const removeStep = (i) => upd({ configuratorSteps: w.configuratorSteps.filter((_, idx) => idx !== i) });
  const moveStep = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= w.configuratorSteps.length) return;
    const c = [...w.configuratorSteps];
    [c[i], c[j]] = [c[j], c[i]];
    upd({ configuratorSteps: c });
  };

  return (
    <Section
      title="Webflow"
      subtitle='Catalog metadata for the online product listing. product_category is locked to "linear-fixtures".'
    >
      <div className="grid grid-cols-2 gap-4 mb-5">
        <Field label="Product Category" hint="Locked for linear fixtures">
          <TextInput value="linear-fixtures" onChange={() => {}} disabled />
        </Field>
        <Field label="Sublabel" hint="Optional tagline">
          <TextInput value={w.sublabel} onChange={v => upd({ sublabel: v })} />
        </Field>
        <Field label="Beam Angle (°)">
          <NumInput value={w.beamAngle} onChange={v => upd({ beamAngle: v })} />
        </Field>
        <Field label="L70 Life (hrs)">
          <NumInput value={w.l70LifeHours} onChange={v => upd({ l70LifeHours: v })} />
        </Field>
        <Field label="Operating Temp Min (°C)">
          <NumInput value={w.operatingTempMinC} onChange={v => upd({ operatingTempMinC: v })} />
        </Field>
        <Field label="Operating Temp Max (°C)">
          <NumInput value={w.operatingTempMaxC} onChange={v => upd({ operatingTempMaxC: v })} />
        </Field>
        <Field label="Warranty Years">
          <NumInput value={w.warrantyYears} onChange={v => upd({ warrantyYears: v })} />
        </Field>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 style={{ fontFamily: fontDisplay, fontSize: 16, fontWeight: 500, color: T.ink, margin: 0 }}>
            Configurator Steps <span style={{ fontFamily: fontMono, fontSize: 12, color: T.subtle, fontWeight: 400 }}>{w.configuratorSteps?.length || 0}</span>
          </h3>
        </div>
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
            list="fx-webflow-step-sugg"
            value={newStep}
            onChange={e => setNewStep(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addStep(); } }}
            placeholder="Add step"
            style={{
              flex: 1, fontFamily: fontBody, fontSize: 14, color: T.ink,
              background: T.paper, border: `1px solid ${T.border}`, borderRadius: 6,
              padding: '9px 12px', outline: 'none',
            }}
          />
          <datalist id="fx-webflow-step-sugg">{FIXTURE_CONFIG_STEPS.map(x => <option key={x} value={x} />)}</datalist>
          <Button icon={Plus} onClick={addStep}>Add Step</Button>
        </div>
      </div>
    </Section>
  );
}

/* ============================================================================
   TAB DISPATCH
   ============================================================================ */
export function renderFixtureTab(tabId, s, setS) {
  switch (tabId) {
    case 'profiles':    return <ProfilesSection s={s} setS={setS} />;
    case 'lenses':      return <LensesSection s={s} setS={setS} />;
    case 'mappings':    return <ProfileLensMappingsSection s={s} setS={setS} />;
    case 'accessories': return <AccessoriesSection s={s} setS={setS} />;
    case 'endcaps':     return <EndcapsSection s={s} setS={setS} />;
    case 'fxTemplates': return <FixtureTemplatesSection s={s} setS={setS} />;
    case 'fxOverrides': return <TemplateOverridesSection s={s} setS={setS} />;
    case 'drivers':     return <DriversSection s={s} setS={setS} />;
    case 'submittal':   return <FixtureSubmittalSection s={s} setS={setS} />;
    case 'webflow':     return <FixtureWebflowSection s={s} setS={setS} />;
    default:            return null;
  }
}

export function fixtureCounts(s) {
  return {
    profiles:    s.fixtureProfiles?.length || 0,
    lenses:      s.fixtureLenses?.length || 0,
    mappings:    s.fixtureProfileLensMappings?.length || 0,
    accessories: s.fixtureAccessories?.length || 0,
    endcaps:     s.fixtureEndcaps?.length || 0,
    fxOverrides: s.fixtureTemplateOverrides?.length || 0,
  };
}
