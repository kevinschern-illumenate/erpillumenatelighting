import expectedJson from '../../../packages/core-schemas/fixtures/open-design/expected.json';
import type { OpenDesign } from './open';

/** An `open_design` payload built from the TEST records' committed expansion (tests only). */
export function openFixture(changes: Partial<OpenDesign> = {}): OpenDesign {
  const expected = structuredClone(expectedJson) as unknown as Pick<OpenDesign, 'lines' | 'builds' | 'readiness'>;
  return {
    schedule: {
      name: 'SCH-TEST',
      schedule_name: 'Test house',
      version: 2,
      is_locked: false,
      status: 'Draft',
      project: 'PRJ-TEST',
    },
    lines: expected.lines,
    builds: expected.builds,
    design: null,
    design_meta: null,
    deliverables: [],
    title_block: {
      project_name: 'Test house',
      project_number: 'PRJ-TEST',
      site_address: '1 Test Way',
      customer: 'Test Dealer',
      dealer_logo: null,
    },
    reconcile: null,
    catalog_hash: 'c'.repeat(64),
    readiness: { ...expected.readiness, missing_line_keys: expected.readiness.missing_line_keys ?? [] },
    review_requirement: { required: false, reasons: [], satisfied: true },
    permissions: { can_edit: true, can_review: false, can_view_pricing: false },
    settings: {
      vd_target_class2_pct: 3,
      vd_target_line_pct: 3,
      vd_target_landscape_pct: 5,
      wire_waste_pct: 10,
      group_threshold_qty: 4,
      default_distance_same_space_ft: 15,
      nec_edition: '2023',
      terms_text: 'Design aid. Verify against product documentation and local code.',
    },
    newer_version: null,
    ...changes,
  };
}
