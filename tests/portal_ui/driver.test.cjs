const {test}=require('node:test'),assert=require('node:assert/strict'),{setup}=require('./family_helpers.cjs');
const INIT={success:true,template:{code:'DRV-A',name:'Slim Driver',series_code:'SLM',warranty:'5 years',base_price_msrp:80,spec_sheet:'/files/drv.pdf'},steps:[{name:'wattage',label:'Wattage'},{name:'voltage_output',label:'Output Voltage'}],options:{wattage:[{value:60,label:'60 W'},{value:96,label:'96 W'}],voltage_output:[{value:'24V DC',label:'24V'}]}};
const VALID={success:true,template_code:'DRV-A',template_name:'Slim Driver',part_number:'ILL-SLM-96-24',variant:{item:'DRV-96-24',item_name:'96W 24V driver',variant_name:'row1',spec_name:'DRV-96-24'},specs:[{label:'Max wattage',value:'96 W'}],pricing:{total_msrp:120},stock:{in_stock:true,qty_available:7}};

test('power supply picks its template on cards and lays out numbered pill sections',()=>{
 const {dom,requests,instance}=setup('Driver');
 assert.equal(instance.$('#driverTemplatePicker .ill-template-card').length,2,'one card per active template');
 assert.equal(instance.$('#driverTemplateSelect').val(),'DRV-A');
 const init=requests.at(-1);assert.match(init.method,/get_driver_configurator_init$/);assert.equal(init.args.template,'DRV-A');assert.equal(Object.keys(init.args).length,1);
 init.callback({message:INIT});
 assert.equal(instance.selections.wattage,96,'restores the requested option');assert.equal(instance.selections.voltage_output,'24V DC','a single option is chosen for the dealer');
 const steps=instance.$('#familySteps .config-section');assert.equal(steps.length,2);assert.match(steps.first().find('h4').text(),/^2Wattage/);assert.equal(instance.$('#driverLineStepNum').text(),'4');
 assert.equal(instance.$('.pill.active').length,2);assert.equal(instance.$('#driverProgressBadge').text(),'100%');
 const info=instance.$('#driverTemplateInfo');assert.equal(info.prop('hidden'),false);assert.match(info.text(),/SLM/);assert.match(info.text(),/5 years/);assert.equal(info.find('a').attr('href'),'/files/drv.pdf');
 const validate=requests.at(-1);assert.match(validate.method,/validate_driver_configuration$/);assert.equal(validate.args.template,'DRV-A');
 validate.callback({message:VALID});
 const summary=instance.$('#familySummary').text();
 assert.equal(instance.$('.ill-driver-part code').text(),'DRV-96-24','the compatible spec ID, not a built part number');assert.match(instance.$('.ill-driver-part small').text(),/Spec ID/);
 for(const text of ['Slim Driver · 96W 24V driver','$120.00','Max wattage','96 W','In stock'])assert.ok(summary.includes(text),text);
 assert.equal(instance.$('#driverValidationStatus').text(),'Valid');
 dom.window.close();
});

test('power supply cascades on the template and saves selections to a stable line',()=>{
 const {dom,requests,instance}=setup('Driver');
 requests.at(-1).callback({message:INIT});requests.at(-1).callback({message:VALID});
 instance.$('.pill').first().trigger('click');
 const cascade=requests.at(-1);assert.match(cascade.method,/get_driver_cascading_options$/);assert.equal(cascade.args.template,'DRV-A');assert.deepEqual(JSON.parse(cascade.args.selections),{wattage:60});
 assert.equal(instance.result,null,'a new choice discards the previous validation');
 cascade.callback({message:{updated_options:{voltage_output:[]}}});
 assert.equal(instance.selections.voltage_output,undefined,'an unreachable choice is cleared');
 assert.equal(instance.$('#driverValidationStatus').text(),'Incomplete');
 instance.choose('voltage_output','24V DC');requests.at(-1).callback({message:{updated_options:{}}});requests.at(-1).callback({message:{...VALID,part_number:'ILL-SLM-60-24'}});
 instance.scheduleTarget.lineValue=()=>3;instance.scheduleSnapshot.lines=[{idx:3,line_key:'STABLE'}];
 instance.$('#familyLineId').val('PS1');instance.$('#familyQty').val(4);instance.save();
 const save=requests.at(-1);assert.match(save.method,/driver_configuration\.save$/);
 assert.equal(save.args.template,'DRV-A');assert.equal(save.args.line_key,'STABLE');assert.equal(save.args.line_idx,null);assert.equal(save.args.finder,'T');
 assert.deepEqual(JSON.parse(save.args.selections),{wattage:60,voltage_output:'24V DC'});assert.deepEqual(JSON.parse(save.args.metadata),{line_id:'PS1',location:'',qty:4,notes:''});
 assert.equal(save.args.item_code,undefined,'the server resolves the Item');
 dom.window.close();
});

test('power supply without a template waits for a card and refuses a save without a fixture type',()=>{
 const {dom,requests,instance}=setup('Driver',{selected_template:null,initial_request:null});
 assert.equal(requests.filter(r=>/configurator_init/.test(r.method)).length,0);
 assert.equal(instance.$('#driverTemplateInfo').prop('hidden'),true);
 instance.$('#driverTemplatePicker .ill-template-card').last().trigger('click');
 return new Promise(resolve=>setTimeout(resolve,5)).then(()=>{
  const init=requests.filter(r=>/configurator_init/.test(r.method)).at(-1);assert.equal(init.args.template,'DRV-B');
  init.callback({message:INIT});requests.at(-1).callback({message:VALID});
  const before=requests.length;instance.save();assert.equal(requests.length,before,'no fixture type, no save');
  instance.template='DRV-A';instance.load();init.callback({message:{success:false,error:'gone'}});assert.notEqual(instance.$('#driverValidationStatus').text(),'Invalid','the previous template\'s response is ignored');assert.equal(instance.result,null);
  dom.window.close();
 });
});

test('power supply enables Add to Schedule, takes the chosen line\'s fixture type, location and quantity, and says why it cannot save yet',()=>{
 const {dom,requests,instance}=setup('Driver');
 let value='__new__',target=false;const lines=[{idx:2,line_key:'K2',line_id:'PS4',location:'Electrical room',qty:6,notes:'Remote'}];
 instance.scheduleTarget={hasTarget:()=>target,canSave:true,lineValue:()=>value,scheduleName:()=>'S',lineAt:i=>lines.find(l=>l.idx===i)||null};
 instance.updateSave();assert.equal(instance.$('#driverSaveHint').prop('hidden'),false);
 requests.at(-1).callback({message:INIT});requests.at(-1).callback({message:VALID});
 assert.match(instance.$('#driverSaveHint').text(),/Schedule Target/);assert.equal(instance.$('#familySave').prop('disabled'),true);
 target=true;value='2';instance.fillFromLine();instance.updateSave();
 assert.equal(instance.$('#familyLineId').val(),'PS4');assert.equal(instance.$('#familyLocation').val(),'Electrical room');assert.equal(instance.$('#familyQty').val(),'6');assert.equal(instance.$('#familyNotes').val(),'Remote');
 assert.equal(instance.saving,undefined,'never saved yet');assert.equal(instance.$('#familySave').prop('disabled'),false,'a valid power supply on a chosen line can be added');assert.equal(instance.$('#driverSaveHint').prop('hidden'),true);
 instance.$('#familyQty').val(8);instance.fillFromLine();assert.equal(instance.$('#familyQty').val(),'8','the same line does not overwrite edits');
 dom.window.close();
});
