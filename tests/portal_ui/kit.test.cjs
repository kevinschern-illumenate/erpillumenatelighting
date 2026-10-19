const {test}=require('node:test'),assert=require('node:assert/strict'),{setup}=require('./family_helpers.cjs');
test('kit restores allowed choices, shows components and stock, and saves to a stable target',()=>{
 const {dom,requests,instance}=setup('Extrusion Kit');const values={finish:'White',lens_appearance:'Frosted',mounting_method:'Clip'};
 requests.at(-1).callback({message:{success:true,kit_template:{name:'KIT',template_name:'Slim Kit',image:'/files/slim.jpg',profile_stock_length_mm:2000,mounting_accessory_qty:6,solid_endcap_qty:2,feed_through_endcap_qty:2,spec_sheet_data:[{label:'Beam angle',value:'120°'}],spec_sheet:'/files/kit.pdf'},options:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,[{value,label:value}]])),defaults:{...values,endcap_style:'Flat',endcap_color:'Red'}}});
 assert.equal(requests.at(-1).args.endcap_style,undefined);
 requests.at(-1).callback({message:{available_lens_appearances:[{value:'Frosted'}]}});
 const validation=JSON.parse(requests.at(-1).args.selections);assert.equal(validation.endcap_style,undefined);assert.equal(validation.endcap_color,undefined);
 requests.at(-1).callback({message:{success:true,is_valid:true,part_number:'KIT-W',kit_composition:{profile:{qty:1,item:'PROFILE'}},pricing:{total_price_msrp:70},stock_availability:{all_in_stock:true,items:[{item_name:'Profile',qty_available:8}]}}});
 assert.equal(instance.$('button[role=radio]').length,3);assert.equal(instance.$('[data-step=endcap_style],[data-step=endcap_color]').length,0);const info=instance.$('#kitTemplateInfo');assert.equal(info.prop('hidden'),false);assert.match(info.text(),/Slim Kit/);assert.match(info.text(),/2000 mm profile, 6 mounting accessories, 2 solid endcaps, 2 feed-through endcaps\. Endcaps come in the color that matches the finish\./);assert.match(info.text(),/Beam angle120°/);assert.equal(info.find('a').attr('href'),'/files/kit.pdf');assert.equal(info.find('img').attr('src'),'/files/slim.jpg');assert.match(instance.$('#familySummary table').text(),/Profile.*PROFILE/);assert.match(instance.$('#familySummary').text(),/KIT-W/);assert.match(instance.$('#familySummary').text(),/70/);assert.match(instance.$('#familySummary').text(),/8 available/);
 instance.scheduleTarget.lineValue=()=>2;instance.scheduleSnapshot.lines=[{idx:2,line_key:'STABLE'}];instance.$('#familyLineId').val('K1');instance.save();
 const save=requests.at(-1);assert.match(save.method,/kit_configuration.save$/);assert.equal(save.args.line_key,'STABLE');assert.equal(save.args.finder,'T');assert.equal(JSON.parse(save.args.selections).kit_template,'KIT');assert.equal(save.args.part_number,undefined);
 dom.window.close();
});

function readyKit() {
 const state=setup('Extrusion Kit'),{requests}=state;
 const values={finish:'White',lens_appearance:'Frosted',mounting_method:'Clip'};
 requests.at(-1).callback({message:{success:true,kit_template:{name:'KIT'},options:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,[{value,label:value}]])),defaults:values}});
 requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
 requests.at(-1).callback({message:{success:true,is_valid:true,part_number:'KIT-SH01-FR-MC-WH'}});
 return state;
}

test('kit line detail edits keep the validated build and Add to Schedule sends the edited metadata',()=>{
 const {dom,w,requests,instance}=readyKit();
 try {
  assert.equal(instance.loading,false);
  const count=requests.length;
  for(const [id,value] of Object.entries({familyLineId:'K1',familyLocation:'Lobby',familyQty:3,familyNotes:'Install above door'})) {
   instance.$('#'+id).val(value).trigger(w.$.Event('input',{originalEvent:{}})).trigger('change');
  }
  assert.equal(requests.length,count);
  assert.equal(instance.$('#familySave').prop('disabled'),false);
  instance.$('#familySave').trigger('click');
  const save=requests.at(-1);
  assert.match(save.method,/kit_configuration.save$/);
  assert.deepEqual(JSON.parse(save.args.metadata),{line_id:'K1',location:'Lobby',qty:3,notes:'Install above door'});
  assert.equal(save.args.expected_modified,'old');
  assert.equal(instance.$('#familySave').prop('disabled'),true);
  assert.match(instance.$('#kitSaveStatus').text(),/Saving/);
 } finally {dom.window.close();}
});

test('kit option changes disable save until the latest validation completes, including after editing line details',()=>{
 const {dom,requests,instance}=readyKit();
 try {
  instance.choose('finish','Black');
  assert.equal(instance.result,null);
  assert.equal(instance.$('#familySave').prop('disabled'),true);
  instance.$('#familyLocation').val('Lobby').trigger('input');
  assert.equal(instance.result,null);
  requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
  const old=requests.at(-1);
  instance.choose('finish','White');
  old.callback({message:{is_valid:true,part_number:'STALE'}});
  assert.equal(instance.result,null);
  requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
  requests.at(-1).callback({message:{is_valid:true,part_number:'KIT-SH01-FR-MC-WH'}});
  assert.equal(instance.loading,false);
  assert.equal(instance.$('#familySave').prop('disabled'),false);
 } finally {dom.window.close();}
});

test('kit explains missing schedule targets and read-only schedules',()=>{
 const {dom,instance}=readyKit();
 try {
  instance.scheduleTarget.hasTarget=()=>false;instance.updateSave();
  assert.equal(instance.$('#familySave').prop('disabled'),true);
  assert.match(instance.$('#kitSaveStatus').text(),/Select.*schedule.*line/i);
  instance.scheduleTarget.hasTarget=()=>true;instance.scheduleTarget.canSave=false;instance.updateSave();
  assert.equal(instance.$('#familySave').prop('disabled'),true);
  assert.match(instance.$('#kitSaveStatus').text(),/cannot.*save|read.only/i);
 } finally {dom.window.close();}
});

test('kit save errors are visible and retries keep the same save key',()=>{
 const {dom,requests,instance}=readyKit();
 try {
  instance.$('#familySave').trigger('click');
  const failed=requests.at(-1);
  failed.error({responseJSON:{_server_messages:JSON.stringify([JSON.stringify({message:'The schedule changed. Reload before saving this kit.'})])}});
  failed.always();
  assert.match(instance.$('#familySummary').text(),/schedule changed.*Reload/);
  assert.equal(instance.$('#familySave').prop('disabled'),false);
  instance.$('#familySave').trigger('click');
  assert.equal(requests.at(-1).args.idempotency_key,failed.args.idempotency_key);
  requests.at(-1).error({});requests.at(-1).always();
  assert.match(instance.$('#familySummary').text(),/Unable to save.*try again/i);
 } finally {dom.window.close();}
});

test('kit failed option checks and validation clear loading and show the failure',()=>{
 for(const stage of ['cascade','validation']) {
  const {dom,requests,instance}=readyKit();
  try {
   instance.choose('finish','Black');
   if(stage==='validation')requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
   requests.at(-1).error({});
   assert.equal(instance.loading,false);
   assert.equal(instance.result,null);
   assert.equal(instance.$('#familySave').prop('disabled'),true);
   assert.match(instance.$('#familySummary').text(),/try again/i);
   instance.choose('finish','White');
   requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
   requests.at(-1).callback({message:{is_valid:false,error:'No profile mapping found'}});
   assert.equal(instance.loading,false);
   assert.match(instance.$('#familySummary').text(),/No profile mapping/);
  } finally {dom.window.close();}
 }
});
