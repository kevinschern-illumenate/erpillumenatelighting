import type { VerifySubset } from '@ill/engine/verify';
import type { Design } from '@ill/core-schemas/design';
import type { ReconcileDiff } from '@ill/engine/reconcile';

/** The H6 error codes every System Designer endpoint can return. */
export type DesignErrorCode = 'NOT_FOUND' | 'FORBIDDEN' | 'INVALID' | 'CONFLICT' | 'LOCKED' | 'GATE' | 'INTERNAL';

export class DesignApiError extends Error {
  constructor(
    readonly code: DesignErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'DesignApiError';
  }
}

export interface DesignMeta {
  name: string;
  revision: string;
  status: string;
  modified: string;
  schedule_version: number;
  is_current: boolean;
  /** Someone accepted the terms on this revision; a save before that must send ``termsAccepted``. */
  terms_accepted: boolean;
  /** The Applications Engineer who approved this revision, when it is approved. */
  approved_by?: string | null;
}

export const DELIVERABLE_KINDS = ['Riser PDF', 'Riser DXF ZIP', 'Riser SVG'] as const;
export type DeliverableKind = (typeof DELIVERABLE_KINDS)[number];

/** A generated file stored on the design (``upload_deliverable``). */
export interface Deliverable {
  name: string;
  kind: string;
  variant: string;
  file: string;
  file_sha256: string;
  revision: string;
  build_hash: string;
  created_by: string;
  created_on: string;
}

export interface SaveResult {
  name: string;
  revision: string;
  modified: string;
  build_hash: string;
  summary: Record<string, unknown>;
}

/** One row of ``eligible_supplies``: ids and the opaque D6 rank, never a price. */
export interface VerifyResult {
  ok: boolean;
  mismatches: { code: string; entityRef: string; client: unknown; server: unknown }[];
  summary: VerifySubset;
}

export interface EligibleSupply {
  catalog_id: string;
  item_code: string | null;
  rank: number | null;
  location_rating: 'Dry' | 'Damp' | 'Wet';
}

export interface ApiOptions {
  /** e.g. /api/method/illumenate_lighting.illumenate_lighting.system_design.api */
  apiBase: string;
  csrfToken: string;
  fetch?: typeof fetch;
}

type Envelope<T> = { success: true; data: T } | { success: false; error: string; code: DesignErrorCode };

/** Thin client for the whitelisted endpoints; Frappe wraps each return value in ``message``. */
export function createDesignApi({ apiBase, csrfToken, fetch: fetchImpl = globalThis.fetch }: ApiOptions) {
  async function call<T>(method: string, init: RequestInit, query?: URLSearchParams): Promise<T> {
    const url = `${apiBase}.${method}${query ? `?${query.toString()}` : ''}`;
    const response = await fetchImpl(url, {
      credentials: 'same-origin',
      ...init,
    });
    let body: { message?: Envelope<T> } | undefined;
    try {
      body = (await response.json()) as { message?: Envelope<T> };
    } catch {
      body = undefined;
    }
    const envelope = body?.message;
    if (!envelope) throw new DesignApiError('INTERNAL', `The server answered ${response.status}; please try again`);
    if (!envelope.success) throw new DesignApiError(envelope.code, envelope.error);
    return envelope.data;
  }

  function post<T>(method: string, fields: Record<string, string | undefined>) {
    const body = new URLSearchParams();
    for (const [key, value] of Object.entries(fields)) if (value !== undefined) body.set(key, value);
    return call<T>(method, {
      method: 'POST',
      headers: {
        'X-Frappe-CSRF-Token': csrfToken,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    });
  }

  return {
    openDesign<T = unknown>(schedule: string, design?: string) {
      const query = new URLSearchParams({ schedule });
      if (design) query.set('design', design);
      return call<T>('open_design', { method: 'GET' }, query);
    },
    saveDesign(args: {
      schedule: string;
      design: Design;
      designName?: string;
      expectedModified?: string;
      /** The H8.4 diff shown on open was applied; required when the schedule changed. */
      reconciled?: boolean;
      /** The user accepted the terms in this session (H9 terms modal). */
      termsAccepted?: boolean;
    }) {
      return post<SaveResult>('save_design', {
        schedule: args.schedule,
        design_json: JSON.stringify(args.design),
        design_name: args.designName,
        expected_modified: args.expectedModified,
        reconciled: args.reconciled ? '1' : undefined,
        terms_accepted: args.termsAccepted ? '1' : undefined,
      });
    },
    getCatalog(hash: string) {
      return call<unknown>('get_catalog', { method: 'GET' }, new URLSearchParams({ hash }));
    },
    eligibleSupplies(args: { schedule: string; runKeys: string[]; locationRating?: string }) {
      return post<EligibleSupply[]>('eligible_supplies', {
        schedule: args.schedule,
        run_keys: JSON.stringify(args.runKeys),
        location_rating: args.locationRating,
      });
    },
    /** The server's re-check of the saved design's gating subset (plan §18.2). */
    verifyDesign(design: string, client: VerifySubset) {
      return post<VerifyResult>('verify_design', { design, client: JSON.stringify(client) });
    },
    /** Store a generated drawing on the saved design; the server recomputes the SHA-256 (H6). */
    uploadDeliverable(args: {
      design: string;
      kind: DeliverableKind;
      variant?: string;
      file: Blob;
      filename: string;
      sha256: string;
    }) {
      const body = new FormData();
      body.set('design', args.design);
      body.set('kind', args.kind);
      if (args.variant) body.set('variant', args.variant);
      body.set('sha256', args.sha256);
      body.set('file', args.file, args.filename);
      return call<{ file_url: string; row: Deliverable }>('upload_deliverable', {
        method: 'POST',
        headers: { 'X-Frappe-CSRF-Token': csrfToken },
        body,
      });
    },
    reconcileDesign(design: string) {
      return call<ReconcileDiff>('reconcile_design', { method: 'GET' }, new URLSearchParams({ design }));
    },
    copyDesignToVersion(design: string, targetSchedule: string) {
      return post<{ name: string }>('copy_design_to_version', { design, target_schedule: targetSchedule });
    },
    createRevision(design: string, note?: string) {
      return post<{ name: string; revision: string }>('create_revision', {
        design,
        note,
      });
    },
  };
}

export type DesignApi = ReturnType<typeof createDesignApi>;
