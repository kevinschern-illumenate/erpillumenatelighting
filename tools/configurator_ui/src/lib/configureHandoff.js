// Builds the handoff URL from quiz answers + top recommendation.
// All answer values are the exact strings from questions.json.

const runtimePortalBaseUrl = globalThis.window?.ILL_CONFIGURATOR_CONFIG?.portalBaseUrl;
const PORTAL_BASE_URL = runtimePortalBaseUrl || import.meta.env.VITE_PORTAL_BASE_URL || 'https://app.illumenate.lighting';
const AUTH_CHECK_URL = `${PORTAL_BASE_URL}/api/method/illumenate_lighting.illumenate_lighting.api.webflow_auth.get_user_context`;
const SAVE_SESSION_URL = `${PORTAL_BASE_URL}/api/method/illumenate_lighting.illumenate_lighting.api.configurator_session.save_session`;

const CATEGORY_ROUTE = {
  'Linear Fixture': 'Linear Fixture',
  'LED Tape': 'LED Tape',
  'LED Neon': 'LED Neon',
};

export function buildConfigureUrl(topRec, answers = {}) {
  const category = topRec?.attributes?.product_category ?? 'Linear Fixture';
  const template = topRec?.attributes?.fixture_template_code ?? '';

  const p = new URLSearchParams();
  p.set('category', CATEGORY_ROUTE[category] ?? 'Linear Fixture');
  if (template) p.set('template', template);

  if (answers.moisture) p.set('moisture', answers.moisture);
  if (answers.ip_rating) p.set('ip_rating', answers.ip_rating);
  if (answers.light_type) p.set('light_type', answers.light_type);
  if (answers.target_cct) p.set('cct', answers.target_cct);
  if (answers.cct_range?.low) p.set('cct_low', String(answers.cct_range.low));
  if (answers.cct_range?.high) p.set('cct_high', String(answers.cct_range.high));
  if (answers.cri) p.set('cri', answers.cri);
  if (answers.dimming_protocol) p.set('dimming', answers.dimming_protocol);
  if (answers.installation_method) p.set('mounting', answers.installation_method);
  if (answers.diffuser) p.set('lens', answers.diffuser);
  if (answers.finish) p.set('finish', answers.finish);
  if (answers.fixture_purpose) p.set('lumen_class', answers.fixture_purpose);

  return `${PORTAL_BASE_URL}/portal/configure?${p.toString()}`;
}

export function buildLoginUrl(configureUrl) {
  return `${PORTAL_BASE_URL}/login?redirect-to=${encodeURIComponent(configureUrl)}`;
}

export function saveToLocalStorage(topRec, answers) {
  try {
    localStorage.setItem('ilLumenate_quiz_session', JSON.stringify({
      topRecSku: topRec?.sku,
      productCategory: topRec?.attributes?.product_category,
      fixtureTemplateCode: topRec?.attributes?.fixture_template_code,
      answers,
      savedAt: Date.now(),
    }));
  } catch (_) {}
}

export async function checkAuthState() {
  try {
    const res = await fetch(AUTH_CHECK_URL, {
      method: 'GET',
      credentials: 'include',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      isLoggedIn: data.message?.is_logged_in ?? data.message?.success ?? false,
      isDealer: data.message?.is_dealer ?? false,
    };
  } catch (_) {
    return null;
  }
}

export async function saveServerSession(topRec, answers) {
  try {
    await fetch(SAVE_SESSION_URL, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? '',
      },
      body: JSON.stringify({
        product_type: topRec?.attributes?.product_category ?? 'Linear Fixture',
        recommended_template: topRec?.attributes?.fixture_template_code ?? '',
        quiz_answers: JSON.stringify(answers),
      }),
    });
  } catch (_) {}
}
