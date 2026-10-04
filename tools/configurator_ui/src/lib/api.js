export function createClient(config = {}) {
  const isPublic = config.mode === 'public';
  const prefix = (isPublic ? config.apiBase.replace(/\/$/, '') : '') + '/api/method/illumenate_lighting.illumenate_lighting.api.product_finder' + (isPublic ? '_public.' : '.');
  async function call(method, args = {}, verb = 'POST') {
    const params = {...args, ...(isPublic ? {brand:config.brand} : {preview:config.preview ? 1 : 0})};
    const query = new URLSearchParams(Object.entries(params).filter(([,v]) => v !== undefined && v !== null).map(([k,v]) => [k, typeof v === 'object' ? JSON.stringify(v) : v]));
    const options = {method:verb, credentials:isPublic ? 'omit' : 'same-origin', headers:{}};
    if (!isPublic) options.headers['X-Frappe-CSRF-Token'] = config.csrfToken || '';
    if (verb !== 'GET') { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(params); }
    const response = await fetch(prefix + method + (verb === 'GET' ? '?' + query : ''), options);
    const data = await response.json();
    if (!response.ok || data.exc || data.exception) {
      let message = 'Unable to contact the Product Finder. Please try again.';
      try { message = JSON.parse(data._server_messages).map(m => JSON.parse(m).message).join(' '); } catch { /* Do not expose backend tracebacks. */ }
      throw new Error(message.replace(/<[^>]*>/g, ''));
    }
    return data.message;
  }
  return {
    getDefinition:() => call('get_definition', {}, 'GET'),
    start:(answers) => isPublic ? Promise.resolve({token:null}) : call('start',{import_answers:answers}),
    getSession:(token) => call('get_session',{token},'GET'),
    saveAnswers:(token,answers) => isPublic ? Promise.resolve({saved:true}) : call('save_answers',{token,answers}),
    evaluate:(answers,question_id) => call('evaluate',{answers,question_id},isPublic ? 'GET' : 'POST'),
    complete:(token,answers) => call('complete',isPublic ? {answers} : {token}),
    claim:(token) => call('claim',{token}),
    requestVerification:(token,product_slug,message) => call('request_verification',{token,product_slug,message}),
  };
}
