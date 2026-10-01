const {test}=require('node:test'),assert=require('node:assert/strict'),{setup}=require('./family_helpers.cjs');
for(const kind of ['Driver','Controller'])test(kind+' renders allowed axes, restores, cascades, and saves only selections',()=>{
 const {dom,requests,instance}=setup(kind);
 requests.at(-1).callback({message:{success:true,steps:[{name:'wattage',label:'Wattage'}],options:{wattage:[{value:60,label:'60 W'},{value:96,label:'96 W'}]}}});
 assert.equal(instance.selections.wattage,96);assert.equal(instance.$('button[role=radio]').length,2);
 requests.at(-1).callback({message:{success:true,part_number:'PART',variant:{item:'ITEM'},pricing:{total_msrp:42}}});
 assert.match(instance.$('#familySummary').text(),/42/);instance.$('#familyLineId').val('L');instance.$('#familyQty').val(2);instance.save();
 const save=requests.at(-1);assert.match(save.method,/add_configured$/);assert.equal(save.args.finder,'T');assert.equal(save.args.expected_modified,'old');assert.equal(save.args.quantity,2);assert.equal(save.args.item_code,undefined);assert.deepEqual(JSON.parse(save.args.selections),{wattage:96});
 save.always();instance.changed('wattage');requests.at(-1).callback({message:{updated_options:{wattage:[{value:96,label:'96 W'}]}}});assert.equal(instance.$('button[role=radio]').first().prop('disabled'),true);
 dom.window.close();
});
test('product changes discard validation from the previous product',()=>{const {dom,requests,instance}=setup('Driver');requests.at(-1).callback({message:{success:true,steps:[{name:'wattage',label:'Wattage'}],options:{wattage:[{value:96,label:'96 W'}]}}});const old=requests.at(-1);instance.context.product_slug='next';instance.load();old.callback({message:{success:true,part_number:'OLD'}});assert.equal(instance.result,null);dom.window.close();});
