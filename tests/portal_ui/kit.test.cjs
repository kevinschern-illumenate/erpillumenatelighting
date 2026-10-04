const {test}=require('node:test'),assert=require('node:assert/strict'),{setup}=require('./family_helpers.cjs');
test('kit restores allowed choices, shows components and stock, and saves to a stable target',()=>{
 const {dom,requests,instance}=setup('Extrusion Kit');const values={finish:'White',lens_appearance:'Frosted',mounting_method:'Clip',endcap_style:'Flat',endcap_color:'White'};
 requests.at(-1).callback({message:{success:true,options:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,[{value,label:value}]])),defaults:values}});
 requests.at(-1).callback({message:{available_lens_appearances:[{value:'Frosted'}],available_endcap_colors:[{value:'White'}]}});
 requests.at(-1).callback({message:{success:true,is_valid:true,part_number:'KIT-W',kit_composition:{profile:{qty:1,item:'PROFILE'}},pricing:{total_price_msrp:70},stock_availability:{all_in_stock:true,items:[{item_name:'Profile',qty_available:8}]}}});
 assert.equal(instance.$('button[role=radio]').length,5);assert.match(instance.$('#familySummary').text(),/KIT-W/);assert.match(instance.$('#familySummary').text(),/70/);assert.match(instance.$('#familySummary').text(),/8 available/);
 instance.scheduleTarget.lineValue=()=>2;instance.scheduleSnapshot.lines=[{idx:2,line_key:'STABLE'}];instance.$('#familyLineId').val('K1');instance.save();
 const save=requests.at(-1);assert.match(save.method,/kit_configuration.save$/);assert.equal(save.args.line_key,'STABLE');assert.equal(save.args.finder,'T');assert.equal(JSON.parse(save.args.selections).kit_template,'KIT');assert.equal(save.args.part_number,undefined);
 dom.window.close();
});
