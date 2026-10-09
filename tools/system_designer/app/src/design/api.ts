import type { Design } from '@ill/core-schemas/design';

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
}

export interface SaveResult {
  name: string;
  revision: string;
  modified: string;
  build_hash: string;
  summary: Record<string, unknown>;
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
    saveDesign(args: { schedule: string; design: Design; designName?: string; expectedModified?: string }) {
      return post<SaveResult>('save_design', {
        schedule: args.schedule,
        design_json: JSON.stringify(args.design),
        design_name: args.designName,
        expected_modified: args.expectedModified,
      });
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
