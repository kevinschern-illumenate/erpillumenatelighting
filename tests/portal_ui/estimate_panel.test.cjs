// Plan 3.8: the configurator estimate panel (price, lead time) labelled as an estimate.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom'),jquery=require('jquery');
const SOURCE=fs.readFileSync(path.join(__dirname,'../../illumenate_lighting/public/js/configurator/estimate_panel.js'),'utf8');
const METHOD='illumenate_lighting.illumenate_lighting.portal.estimate.lead_time';

function setup(marker){
 const body=(marker===false?'':'<script type="application/json" id="ill-live-estimate">'+(marker||'{"enabled": true}')+'</script>')+'<div id="host"></div>';
 const dom=new JSDOM('<!doctype html><body>'+body+'</body>',{runScripts:'outside-only'}),w=dom.window,requests=[];
 w.$=w.jQuery=jquery(w);w.frappe={call:args=>requests.push(args)};
 w.eval(SOURCE);
 return {dom,w,requests,api:w.IllConfigurator,host:w.$('#host')};
}

test('without the page marker nothing is drawn and nothing is requested',()=>{
 for(const marker of [false,'{"enabled": false}','not json']){
  const {dom,api,host,requests}=setup(marker);
  host.append('<div class="ill-estimate">old</div>');
  assert.equal(api.estimateEnabled(),false);
  assert.equal(api.renderEstimate(host,{family:'driver',template:'DRV-A',show_pricing:true,price:5}),null);
  assert.equal(host.find('.ill-estimate').length,0,'a stale panel is still cleared');
  assert.equal(requests.length,0);
  dom.window.close();
 }
});

test('labels the panel as an estimate and shows price only with pricing access',()=>{
 const {dom,api,host}=setup();
 api.renderEstimate(host,{family:'tape_neon',show_pricing:true,price:123.4,lead_time:null});
 const panel=host.find('.ill-estimate');
 assert.equal(panel.length,1);assert.equal(panel.attr('role'),'note');
 assert.equal(panel.find('.ill-estimate-title').text(),'Estimate — confirmed on your quote');
 assert.equal(panel.find('.ill-estimate-price strong').text(),'$123.40');
 assert.equal(panel.find('.ill-estimate-lead strong').text(),'Confirmed on your quote');
 api.renderEstimate(host,{family:'tape_neon',show_pricing:true,price:null,lead_time:null});
 assert.equal(host.find('.ill-estimate').length,1,'a re-render replaces the panel');
 assert.equal(host.find('.ill-estimate-price strong').text(),'Confirmed on your quote','no current price');
 api.renderEstimate(host,{family:'tape_neon',show_pricing:false,price:99,lead_time:null});
 assert.equal(host.find('.ill-estimate-price').length,0,'a collaborator without pricing sees no price');
 assert.doesNotMatch(host.text(),/99/);
 api.renderEstimate(host,{family:'kit',show_pricing:true});
 assert.equal(host.find('.ill-estimate-price').length,0,'no price row when no estimate price is passed');
 assert.equal(host.find('.ill-estimate-lead strong').text(),'Confirmed on your quote','a kit has no lead-time class');
 dom.window.close();
});

test('fetches the lead time once per template and escapes its label',()=>{
 const {dom,api,host,requests}=setup();
 api.renderEstimate(host,{family:'driver',template:'DRV-A',schedule_name:'SCH-1'});
 assert.equal(host.find('.ill-estimate-lead strong').text(),'Loading…');
 assert.equal(requests.length,1);
 const call=requests[0];
 assert.equal(call.method,METHOD);assert.equal(call.type,'GET');
 assert.deepEqual(call.args,{family:'driver',template:'DRV-A',schedule_name:'SCH-1'});
 call.callback({message:{lead_time:{code:'STD',label:'<b>Standard</b>',days_min:10,days_max:15}}});
 const value=host.find('.ill-estimate-lead strong');
 assert.equal(value.text(),'<b>Standard</b> · 10–15 days');
 assert.equal(value.find('b').length,0,'the label is text, not markup');
 api.renderEstimate(host,{family:'driver',template:'DRV-A'});
 assert.equal(requests.length,1,'cached');
 assert.equal(host.find('.ill-estimate-lead strong').text(),'<b>Standard</b> · 10–15 days');
 api.renderEstimate(host,{family:'fixture',tape_offering:'OFF-1'});
 assert.deepEqual(requests[1].args,{family:'fixture',tape_offering:'OFF-1'});
 requests[1].error();
 assert.equal(host.find('.ill-estimate-lead strong').text(),'Confirmed on your quote','a failed lookup defers to the quote');
 api.renderEstimate(host,{family:'led_sheet'});
 assert.equal(requests.length,2,'no template means no request');
 dom.window.close();
});

test('a late response does not write into a replaced or removed panel',()=>{
 const {dom,api,host,requests}=setup();
 const first=api.renderEstimate(host,{family:'controller',template:'CTL-A'});
 api.renderEstimate(host,{family:'controller',template:'CTL-B'});
 requests[0].callback({message:{lead_time:{label:'Old',days_min:1,days_max:2}}});
 assert.equal(first.closest('body').length,0);
 assert.equal(host.find('.ill-estimate-lead strong').text(),'Loading…','the newer panel waits for its own answer');
 host.empty();
 requests[1].callback({message:{lead_time:{label:'New',days_min:3,days_max:3}}});
 assert.equal(host.children().length,0);
 dom.window.close();
});

test('formats every lead-time shape',()=>{
 const {dom,api}=setup();
 const f=api.estimateLeadTimeText;
 assert.equal(f(null),'Confirmed on your quote');
 assert.equal(f({label:'Stock',days_min:3,days_max:3}),'Stock · 3 days');
 assert.equal(f({label:'Build',days_max:20}),'Build · Up to 20 days');
 assert.equal(f({label:'Custom',days_min:30}),'Custom · 30+ days');
 assert.equal(f({code:'STD'}),'STD');
 assert.equal(f({days_min:0,days_max:5}),'0–5 days');
 assert.equal(f({label:'',days_min:'',days_max:null}),'Confirmed on your quote');
 dom.window.close();
});

test('the power supply configurator adds the panel under a valid result',()=>{
 const {setup:family}=require('./family_helpers.cjs');
 const {dom,w,requests,instance}=family('Driver');
 w.document.body.insertAdjacentHTML('beforeend','<script type="application/json" id="ill-live-estimate">{"enabled": true}</script>');
 w.eval(SOURCE);
 requests.at(-1).callback({message:{success:true,template:{code:'DRV-A',name:'Slim Driver'},steps:[{name:'wattage',label:'Wattage'}],options:{wattage:[{value:96,label:'96 W'}]}}});
 requests.at(-1).callback({message:{success:true,template_code:'DRV-A',part_number:'P',variant:{item:'DRV-96',item_name:'96W'},specs:[],pricing:{total_msrp:120},stock:{in_stock:true,qty_available:7}}});
 const panel=instance.$('#familySummary .ill-estimate');
 assert.equal(panel.length,1);
 const lead=requests.at(-1);assert.equal(lead.method,METHOD);assert.deepEqual(lead.args,{family:'driver',template:'DRV-A'});
 lead.callback({message:{lead_time:{label:'Standard',days_min:5,days_max:7}}});
 assert.equal(panel.find('.ill-estimate-lead strong').text(),'Standard · 5–7 days');
 dom.window.close();
});
