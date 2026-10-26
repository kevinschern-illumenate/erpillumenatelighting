const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom'),jquery=require('jquery');
// Desk "Configure & Add Fixture": a reconfigured row replaces its build's rows so the document keeps matching the schedule.

function load(items, opts){
 const dom=new JSDOM('<!doctype html><body></body>',{runScripts:'outside-only'}),w=dom.window,opened=[];
 w.$=w.jQuery=jquery(w);w.__=(text,args)=>String(text).replace(/\{(\d+)\}/g,(_,i)=>args[i]);
 const wrapper=()=>({$wrapper:w.$('<div></div>')});
 w.locals={'Quotation Item':{}};
 w.frappe={session:{user:'Administrator'},utils:{escape_html:v=>v,get_random:()=>'x'},msgprint(m){opened.push({msgprint:m});},show_alert(){},call(){},
  model:{clear_doc(doctype,name){delete w.locals[doctype][name];}},
  ui:{Dialog:function(){this.fields_dict={step_indicator:wrapper(),body:wrapper(),footer:wrapper()};this.$wrapper=w.$('<div></div>');this.show=()=>{};
   this.set_primary_action=()=>{};this.get_primary_btn=()=>w.$('<button></button>');this.set_secondary_action_label=()=>{};this.set_secondary_action=()=>{};}}};
 let n=0;
 const frm={doctype:'Quotation',doc:{customer:'C',ill_fixture_schedule:'S1',items:[]},fields_dict:{},is_new:()=>false,refresh_field(){},dirty(){},set_value(){},
  add_child(field,values){const row=Object.assign({doctype:'Quotation Item',name:'new-'+(++n)},values);this.doc.items.push(row);w.locals['Quotation Item'][row.name]=row;return row;}};
 items.forEach(values=>{const row=Object.assign({doctype:'Quotation Item'},values);frm.doc.items.push(row);w.locals['Quotation Item'][row.name]=row;});
 frm.doc.items.forEach((row,i)=>{row.idx=i+1;});
 w.eval(fs.readFileSync(path.join(__dirname,'../../illumenate_lighting/public/js/desk/desk_dialog.js'),'utf8'));
 return {dom,w,frm,opened,ctrl:opts===false?null:w.IllDesk.openConfiguratorDialog(frm,opts||{})};
}

const FIXTURE={name:'r1',item_code:'OLD-FX',ill_fixture_type:'A1',ill_schedule_line_id:'L1',ill_configured_product:'CF-OLD',ill_configured_fixture:'CF-OLD',ill_product_type:'Linear Fixture',ill_configurator_request:'{"family":"Linear Fixture","template":"T"}'};
const SUPPLY={name:'r2',item_code:'PS-60',ill_fixture_type:'A1',ill_schedule_line_id:'P1',ill_is_power_supply_line:1,ill_power_supply_for:'CF-OLD'};
const FREIGHT={name:'r3',item_code:'FREIGHT',qty:1};

test('reconfiguring a row replaces it and its supply rows in place, leaving other rows alone', () => {
 const {dom,frm,ctrl}=load([FIXTURE,SUPPLY,FREIGHT],{rowName:'r1'});
 try {
  assert.equal(ctrl.productType,'Linear Fixture');
  ctrl.applyRowToForm({schedule_line_name:'L1',replaced_line_names:['P1'],fixture_type:'A1',item_code:'NEW-FX',
   row_values:{item_code:'NEW-FX',ill_fixture_type:'A1',ill_schedule_line_id:'L1',ill_configured_tape_neon:'CTN-1',ill_is_power_supply_line:0},
   accessory_rows:[{item_code:'PS-96',ill_fixture_type:'A1',ill_schedule_line_id:'P2',ill_is_power_supply_line:1}]});
  assert.deepEqual(frm.doc.items.map(r=>[r.idx,r.item_code,r.ill_schedule_line_id]),[[1,'NEW-FX','L1'],[2,'PS-96','P2'],[3,'FREIGHT',undefined]]);
  assert.equal(frm.doc.items[0].name,'r1','the row keeps its name, so schedule sync sees an edit, not a new line');
  assert.equal(frm.doc.items[0].ill_configured_fixture,null,'links of the previous family are cleared');
 } finally {dom.window.close();}
});

test('picking a configured schedule line in step 2 replaces that line\'s rows instead of adding a second set', () => {
 const KIT_A={name:'k1',item_code:'EXT-1',ill_fixture_type:'K1',ill_schedule_line_id:'L5',ill_configurator_request:'{"family":"Extrusion Kit"}'};
 const KIT_B={name:'k2',item_code:'CAP-1',ill_fixture_type:'K1',ill_schedule_line_id:'L5',ill_configurator_request:'{"family":"Extrusion Kit"}'};
 const {dom,frm,ctrl}=load([FREIGHT,KIT_A,KIT_B]);
 try {
  ctrl.applyRowToForm({schedule_line_name:'L5',replaced_line_names:[],fixture_type:'K1',item_code:'KIT-2',
   row_values:{item_code:'EXT-2',ill_schedule_line_id:'L5'},accessory_rows:[{item_code:'CAP-2',ill_schedule_line_id:'L5'}]});
  assert.deepEqual(frm.doc.items.map(r=>r.item_code),['FREIGHT','EXT-2','CAP-2']);
  assert.equal(frm.doc.items[1].name,'k1');
 } finally {dom.window.close();}
});

test('a new line is added after the existing rows without touching them', () => {
 const {dom,frm,ctrl}=load([FIXTURE,SUPPLY]);
 try {
  ctrl.applyRowToForm({schedule_line_name:'L9',replaced_line_names:[],fixture_type:'A2',item_code:'FX-2',row_values:{item_code:'FX-2',ill_schedule_line_id:'L9'},accessory_rows:[]});
  assert.deepEqual(frm.doc.items.map(r=>r.item_code),['OLD-FX','PS-60','FX-2']);
 } finally {dom.window.close();}
});

test('Reconfigure Row opens the configured row a ticked supply belongs to', () => {
 const {dom,w,frm,opened}=load([FIXTURE,SUPPLY,FREIGHT],false);
 try {
  const calls=[];w.IllDesk.openConfiguratorDialog=(form,opts)=>calls.push(opts);
  let ticked=[frm.doc.items[1]];
  frm.fields_dict.items={grid:{get_selected_children:()=>ticked}};
  w.IllDesk.reconfigureSelectedRow(frm);
  assert.deepEqual(calls.map(o=>o.rowName),['r1']);
  ticked=[frm.doc.items[2]];w.IllDesk.reconfigureSelectedRow(frm);
  ticked=[];w.IllDesk.reconfigureSelectedRow(frm);
  assert.equal(calls.length,1,'a hand-added row or no selection opens nothing');
  assert.equal(opened.length,2);
 } finally {dom.window.close();}
});

test('rows linked to an earlier schedule version follow their line to the current one', () => {
 const {dom,frm,ctrl}=load([FIXTURE,SUPPLY,FREIGHT],{rowName:'r1'});
 try {
  assert.equal(ctrl.scheduleLineName,'L1');
  ctrl.relinkRows({L1:'L1-V2',P1:'P1-V2'});
  assert.deepEqual(frm.doc.items.map(r=>r.ill_schedule_line_id),['L1-V2','P1-V2',undefined]);
  assert.equal(ctrl.scheduleLineName,'L1-V2','reconfiguring now targets the current version\'s line');
  ctrl.relinkRows({});
  assert.deepEqual(frm.doc.items.map(r=>r.ill_schedule_line_id),['L1-V2','P1-V2',undefined]);
 } finally {dom.window.close();}
});
