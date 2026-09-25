const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const source = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_conversation.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup(messages = []) {
  const dom = new JSDOM('<body><div id="a" data-parent-type="Issue" data-parent-name="I1"></div><div id="b" data-parent-type="Issue" data-parent-name="I2"></div></body>', {runScripts:'outside-only', url:'https://portal.test/'});
  const w = dom.window;
  w.__ = value => value;
  w.frappe = {call: async () => ({message:{messages, status:'Open', next_action_by:'Staff', is_staff:false, can_reply:true, total:messages.length, page:1, page_size:20}})};
  w.PortalUploads = {uploadAll: async () => [], call: async () => ({success:true})};
  w.eval(source);
  return {dom, w, a:w.document.getElementById('a'), b:w.document.getElementById('b')};
}

test('thread renders message text safely, only private links, and scoped label targets', async () => {
  const {dom,w,a,b} = setup([{actor:'<img onerror=bad()>', creation:'today', visibility:'Customer', body:'<script>bad()</script>', files:[{file_name:'unsafe',file_url:'javascript:bad()'},{file_name:'drawing.pdf',file_url:'/private/files/drawing.pdf'}]}]);
  w.PortalConversation(a); w.PortalConversation(b); w.PortalConversation(a); await tick();
  assert.equal(a.querySelectorAll('textarea').length,1);
  assert.notEqual(a.querySelector('textarea').id,b.querySelector('textarea').id);
  assert.equal(a.querySelector('label').htmlFor,a.querySelector('textarea').id);
  assert.equal(a.querySelectorAll('script,img').length,0);
  assert.equal(a.querySelectorAll('a').length,1);
  assert.match(a.textContent, /<script>/);
  dom.window.close();
});

test('failed reply preserves draft and retries same message key', async () => {
  const {dom,w,a} = setup(); const calls=[];
  w.PortalUploads.call = async (method,args) => { calls.push(args); if(calls.length===1) throw new Error('Network interrupted'); return {success:true}; };
  w.PortalConversation(a); await tick();
  const text=a.querySelector('textarea'),form=a.querySelector('form'); text.value='Customer response';
  form.dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(text.value,'Customer response');
  assert.equal(a.querySelector('[type=submit]').disabled,false);
  form.dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls[0].idempotency_key,calls[1].idempotency_key);
  assert.equal(text.value,'');
  dom.window.close();
});
