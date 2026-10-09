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
  /** The System Design Review request for this revision, once one was filed. */
  review_request?: string | null;
}

export const DELIVERABLE_KINDS = [
  'Riser PDF',
  'Riser DXF ZIP',
  'Riser SVG',
  'Presentation PDF',
  'Presentation SVG',
] as const;
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

/** One change ``writeback_preview`` proposes; ``key`` is the ``design_line_key`` (H8.6). */
export interface WritebackLine {
  key: string;
  role?: 'Supply' | 'Controller' | 'Wire' | 'Accessory';
  item_code: string;
  item_name?: string;
  qty: number;
  from_qty?: number;
  location?: string;
  line_id?: string | null;
  unit?: 'ft' | 'spool';
  tags?: string[];
}

/** The configurator's own supplies for a build the design now powers (consolidation, plan §14.6). */
export interface WritebackReplace {
  key: string;
  for_line: string;
  line_id: string | null;
  lines: { item_code: string; item_name?: string; qty: number }[];
}

export interface WritebackPreview {
  add: WritebackLine[];
  update: WritebackLine[];
  remove: WritebackLine[];
  replaces_configurator_lines: WritebackReplace[];
  blocked: { ref: string; reason: string }[];
  error_count: number;
  can_apply: boolean;
  /** Selling prices only, and only for users with Can View Pricing. */
  price_delta?: { amount: number; price_list: string; unpriced: string[] };
}

export interface WritebackResult {
  added: number;
  updated: number;
  removed: number;
  replaced: number;
}

/** A pin on a drawing: a fraction of the sheet, an entity, or both (WP-4.3). */
export interface CommentAnchor {
  sheet?: string;
  entityRef?: string;
  x?: number;
  y?: number;
}

export const COMMENT_VIEWS = ['Riser', 'Presentation', 'Plan', '3D', 'Run', 'Supply', 'General'] as const;
export type CommentView = (typeof COMMENT_VIEWS)[number];

/** One comment on a design (``list_comments``). */
export interface DesignComment {
  comment_id: string;
  view: CommentView;
  anchor: CommentAnchor | null;
  body: string;
  author: string;
  author_name: string | null;
  created_on: string;
  resolved: boolean;
  resolved_by: string | null;
}

/** The D4 gate for a schedule (H8.5): whether ordering needs a review, and what satisfies it. */
export interface ReviewRequirement {
  required: boolean;
  reasons: { code: string; detail?: string | null }[];
  satisfied: boolean;
  approved_design?: string | null;
  override?: { by: string; reason: string; on: string } | null;
}

export type ReviewDecision = 'Approved' | 'Changes Requested';

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
    /** Pilot telemetry (WP-3.9): what only the browser sees. */
    logEvent(args: { schedule: string; event: TelemetryEvent; design?: string; details?: Record<string, unknown> }) {
      return post<{ event_key: string | null }>('log_event', {
        schedule: args.schedule,
        event: args.event,
        design: args.design,
        details: args.details ? JSON.stringify(args.details) : undefined,
      });
    },
    /** What adding the saved design to its schedule would change (H8.6). */
    writebackPreview(design: string, wireFeet: Record<string, number>) {
      return post<WritebackPreview>('writeback_preview', { design, wire_feet: JSON.stringify(wireFeet) });
    },
    writebackApply(design: string, acceptedKeys: string[], wireFeet: Record<string, number>) {
      return post<WritebackResult>('writeback_apply', {
        design,
        accepted_keys: JSON.stringify(acceptedKeys),
        wire_feet: JSON.stringify(wireFeet),
      });
    },
    /** File the System Design Review request for the saved revision (WP-4.2). */
    requestReview(args: {
      design: string;
      priority: 'Normal' | 'High' | 'Rush';
      dueDate?: string;
      note?: string;
      errorCount: number;
      warningCount: number;
    }) {
      return post<{ request: string; reviewer: string | null; design_meta: DesignMeta }>('request_review', {
        design: args.design,
        priority: args.priority,
        due_date: args.dueDate || undefined,
        note: args.note || undefined,
        error_count: String(args.errorCount),
        warning_count: String(args.warningCount),
      });
    },
    /** The assigned Applications Engineer approves the revision or asks for changes (WP-4.3). */
    reviewDecide(design: string, decision: ReviewDecision, note?: string) {
      return post<{ review: string; status: ReviewDecision; design_meta: DesignMeta }>('review_decide', {
        design,
        decision,
        note: note || undefined,
      });
    },
    /** An Applications Engineer accepts one error on a design in review; the build hash changes. */
    overrideCheck(args: { design: string; code: string; entityRef: string; reason: string }) {
      return post<{ overrides: Design['overrides']; build_hash: string; design_meta: DesignMeta }>('override_check', {
        design: args.design,
        code: args.code,
        entity_ref: args.entityRef,
        reason: args.reason,
      });
    },
    listComments(design: string) {
      return call<DesignComment[]>('list_comments', { method: 'GET' }, new URLSearchParams({ design }));
    },
    addComment(args: { design: string; body: string; view?: CommentView; anchor?: CommentAnchor }) {
      return post<DesignComment>('add_comment', {
        design: args.design,
        body: args.body,
        view: args.view,
        anchor: args.anchor ? JSON.stringify(args.anchor) : undefined,
      });
    },
    resolveComment(design: string, commentId: string, resolved = true) {
      return post<DesignComment>('resolve_comment', {
        design,
        comment_id: commentId,
        resolved: resolved ? '1' : '0',
      });
    },
    /** Order Approvers and Applications Engineers let the schedule's current lines be ordered unreviewed. */
    overrideReviewGate(schedule: string, reason: string) {
      return post<{ override_id: string; review_requirement: ReviewRequirement }>('override_review_gate', {
        schedule,
        reason,
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

export type TelemetryEvent = 'riser_exported' | 'check_fixed' | 'feedback';

/** Send a telemetry event and forget it: telemetry never interrupts the work it describes. */
export function track(api: Partial<DesignApi>, args: Parameters<DesignApi['logEvent']>[0]) {
  try {
    void api.logEvent?.(args)?.catch(() => undefined);
  } catch {
    // Ignore: an older server or a test double without the endpoint.
  }
}
