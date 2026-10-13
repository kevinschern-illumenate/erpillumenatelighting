const fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom'),jquery=require('jquery');
exports.setup=function(kind,overrides){
 const file=path.join(__dirname,'rendered',kind.replaceAll(' ','-')+'-coordinator.html');
 const dom=new JSDOM(fs.readFileSync(file,'utf8'),{runScripts:'outside-only',url:'https://portal.test/portal/configure?finder=T'}),w=dom.window,requests=[];
 w.$=w.jQuery=jquery(w);w.__=v=>v;w.frappe={call:args=>requests.push(args),msgprint(){}};
 for(const name of ['shared_configurator','driver_controller_steps','kit_steps','driver_steps'])w.eval(fs.readFileSync(path.join(__dirname,'../../illumenate_lighting/public/js/configurator',name+'.js'),'utf8'));
 const api=w.IllConfigurator;
 api.bindScheduleContext=()=>({hasTarget:()=>true,canSave:true,lineValue:()=>'__new__',scheduleName:()=>'S'});
 const instance=new api[{'Extrusion Kit':'Kit',Driver:'Driver'}[kind]||'DriverController'](w.$('#familyConfigurator'),Object.assign({kind,product_slug:kind==='Extrusion Kit'||kind==='Driver'?'':'p',selected_template:kind==='Extrusion Kit'?'KIT':kind==='Driver'?'DRV-A':null,show_pricing:true,show_stock_qty:true,initial_request:{selections:kind==='Extrusion Kit'?{finish:'White'}:{wattage:96}},finder:'T'},overrides||{}));
 instance.scheduleSnapshot={modified:'old',lines:[]};instance.init();
 return {dom,w,requests,instance};
};
