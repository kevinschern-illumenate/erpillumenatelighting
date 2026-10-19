const {test}=require('node:test'),assert=require('node:assert/strict'),{setup}=require('./family_helpers.cjs');
// Embedded in the desk Quotation / Sales Order dialog: no schedule target, the host saves.
function desk(kind){const saved=[];const state=setup(kind,{saveHandler:payload=>saved.push(payload)});return {...state,saved};}

test('desk kit enables Add without a schedule target and hands the host its selections',()=>{
 const {dom,requests,instance,saved}=desk('Extrusion Kit');
 try {
  const values={finish:'White',lens_appearance:'Frosted',mounting_method:'Clip'};
  requests.at(-1).callback({message:{success:true,kit_template:{name:'KIT'},options:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,[{value,label:value}]])),defaults:values}});
  requests.at(-1).callback({message:{success:true,available_lens_appearances:[{value:'Frosted'}]}});
  requests.at(-1).callback({message:{success:true,is_valid:true,part_number:'KIT-W'}});
  assert.equal(instance.scheduleTarget,null);
  assert.equal(instance.$('#familySave').prop('disabled'),false);
  assert.equal(instance.$('#kitSaveStatus').text(),'');
  const count=requests.length;instance.$('#familySave').trigger('click');
  assert.equal(requests.length,count,'the host owns the save request');
  assert.equal(saved.length,1);assert.equal(saved[0].product_type,'Extrusion Kit');assert.equal(saved[0].template,'KIT');assert.equal(saved[0].selections.kit_template,'KIT');assert.equal(saved[0].selections.finish,'White');
 } finally {dom.window.close();}
});

test('desk power supply saves its template and selections without a fixture type',()=>{
 const {dom,requests,instance,saved}=desk('Driver');
 try {
  requests.at(-1).callback({message:{success:true,template:{code:'DRV-A'},steps:[{name:'wattage',label:'Wattage'}],options:{wattage:[{value:96,label:'96 W'}]}}});
  requests.at(-1).callback({message:{success:true,template_code:'DRV-A',part_number:'DRV-96',variant:{item:'DRV-96',spec_name:'DRV-96'}}});
  assert.equal(instance.$('#familySave').prop('disabled'),false);
  assert.equal(instance.$('#driverSaveHint').prop('hidden'),true);
  instance.$('#familySave').trigger('click');
  assert.deepEqual(JSON.parse(JSON.stringify(saved)),[{product_type:'Driver',template:'DRV-A',selections:{wattage:96}}]);
 } finally {dom.window.close();}
});

test('desk controller saves the chosen product and selections',()=>{
 const {dom,requests,instance,saved}=desk('Controller');
 try {
  requests.at(-1).callback({message:{success:true,steps:[{name:'channels',label:'Channels'}],options:{channels:[{value:4,label:'4',is_default:true}]}}});
  requests.at(-1).callback({message:{success:true,part_number:'CTRL-4',variant:{item:'CTRL-4'}}});
  assert.equal(instance.$('#familySave').prop('disabled'),false);
  instance.save();
  assert.deepEqual(JSON.parse(JSON.stringify(saved)),[{product_type:'Controller',product_slug:'p',selections:{channels:4}}]);
 } finally {dom.window.close();}
});
