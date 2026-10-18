(function(root){
  'use strict';
  // Power supply configurator: pick an ilL-Driver-Template, choose its options and save the
  // resolved ilL-Spec-Driver Item to a schedule line. Same layout as the kit configurator.
  var IC=root.IllConfigurator,API='illumenate_lighting.illumenate_lighting.api.driver_controller_configurator.';
  function Driver(el,context){IC.DriverController.call(this,el,context);this.kind='Driver';this.template=context.selected_template||(context.initial_request||{}).template||'';}
  Driver.prototype=Object.create(IC.DriverController.prototype);Driver.prototype.constructor=Driver;
  Driver.prototype.init=function(){
    var self=this;
    this.scheduleTarget=this.hostSaves()?null:IC.bindScheduleContext({instance:this,context:this.context,onChange:function(){self.fillFromLine();self.updateSave();}});
    var draft=this.context.draft||{};
    this.$('#familyLineId').val(draft.line_id||'');this.$('#familyLocation').val(draft.location||'');this.$('#familyQty').val(draft.qty||1);this.$('#familyNotes').val(draft.notes||'');
    this.$('#familySave').on('click',function(){self.save();});
    var select=this.$('#driverTemplateSelect');
    if(this.template)select.val(this.template);
    if(IC.renderTemplateCards)IC.renderTemplateCards({$container:this.$('#driverTemplatePicker'),$select:select,labels:{search:__('Search power supplies…'),empty:__('No power supplies match your search.'),count:function(n,total){return n===total?__('{0} power supplies',[total]):__('{0} of {1} power supplies',[n,total]);}}});
    select.on('change',function(){self.template=$(this).val();self.context.initial_request=null;self.delay(function(){self.load();},0);});
    this.load();
    return this;
  };
  Driver.prototype.load=function(){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.steps=[];this.selections={};this.reachable={};this.updateSave();
    this.renderSteps();this.renderTemplateInfo({});this.renderPlaceholder();this.setStatus('Incomplete','secondary');
    if(!this.template){this.loading=false;return;}
    this.request({method:API+'get_driver_configurator_init',args:{template:this.template},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};
      if(!data.success){self.loading=false;self.renderError(data.error||__('This power supply is unavailable.'));return;}
      self.loading=false;self.steps=data.steps||[];self.options=data.options||{};
      var requested=(self.context.initial_request||{}).selections||{};
      self.steps.forEach(function(step){var options=self.options[step.name]||[],chosen=options.find(function(o){return String(o.value)===String(requested[step.name]);})||options.find(function(o){return o.is_default;})||(options.length===1?options[0]:null);if(chosen)self.selections[step.name]=chosen.value;});
      self.renderTemplateInfo(data.template||{});self.renderSteps();self.validate();
    }});
  };
  Driver.prototype.changed=function(step){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.updateSave();this.renderSteps();
    var partial={};partial[step]=this.selections[step];
    this.request({method:API+'get_driver_cascading_options',args:{template:this.template,step_name:step,selections:JSON.stringify(partial)},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};self.loading=false;self.reachable=data.updated_options||{};
      Object.keys(self.reachable).forEach(function(key){if(!self.reachable[key].some(function(o){return String(o.value)===String(self.selections[key]);})){delete self.selections[key];if(self.reachable[key].length===1)self.selections[key]=self.reachable[key][0].value;}});
      self.renderSteps();self.validate();
    }});
  };
  Driver.prototype.validate=function(){
    var self=this,revision=this.revision;
    if(!this.template||!this.steps.length||!this.steps.every(function(step){return self.selections[step.name]!=null&&self.selections[step.name]!=='';})){this.setStatus('Incomplete','secondary');if(this.template&&this.steps.length)this.renderPlaceholder(__('Choose an option for every step to see the compatible spec ID.'));return;}
    this.request({method:API+'validate_driver_configuration',args:{template:this.template,selections:JSON.stringify(this.selections)},callback:function(r){if(revision!==self.revision)return;var data=r.message||{};self.result=data.success&&data.variant&&data.variant.item?data:null;self.renderResult(data);self.updateSave();}});
  };
  // Choosing an existing schedule line brings its fixture type, location, quantity and notes along.
  Driver.prototype.fillFromLine=function(){
    var target=this.scheduleTarget,value=target&&target.lineValue();if(value===this.filledLine)return;this.filledLine=value;
    var line=value&&value!=='__new__'&&target.lineAt?target.lineAt(parseInt(value,10)):null;if(!line)return;
    this.$('#familyLineId').val(line.line_id||'');this.$('#familyLocation').val(line.location||'');this.$('#familyQty').val(line.qty||1);this.$('#familyNotes').val(line.notes||'');
  };
  // Say what is still missing next to a disabled Add to Schedule button.
  Driver.prototype.updateSave=function(){
    IC.DriverController.prototype.updateSave.call(this);
    var target=this.scheduleTarget,hint='';
    if(this.saving)hint='';
    else if(!this.result)hint=this.template?__('Choose an option for every step.'):__('Choose a power supply.');
    else if(this.targetReady())hint='';
    else if(!target||!target.hasTarget())hint=__('Choose a project, fixture schedule and line under Schedule Target.');
    else if(!target.canSave)hint=__('You can view this schedule but not change it.');
    this.$('#driverSaveHint').text(hint).prop('hidden',!hint);
  };
  Driver.prototype._updateButtons=function(){this.result=null;this.updateSave();if(!this.loading&&this.steps.length)this.validate();};
  Driver.prototype.save=function(){
    if(!this.result||this.saving)return;
    if(this.hostSaves()){this.context.saveHandler({product_type:'Driver',template:this.template,selections:Object.assign({},this.selections)});return;}
    var selected=this.scheduleTarget.lineValue(),snapshot=this.scheduleSnapshot||{},line=(snapshot.lines||[]).find(function(l){return String(l.idx)===String(selected);});
    var meta=this.metadata();if(!String(meta.line_id||'').trim()){frappe.msgprint(__('Enter a fixture type for this power supply.'));return;}
    this.sendSave('illumenate_lighting.illumenate_lighting.portal.driver_configuration.save',{schedule_name:this.scheduleTarget.scheduleName(),template:this.template,selections:JSON.stringify(this.selections),expected_modified:snapshot.modified,line_key:line?line.line_key:null,line_idx:line?null:selected==='__new__'?null:selected,metadata:JSON.stringify(meta),finder:this.context.finder});
  };
  // Numbered option sections with pill choices; small screens get a select.
  Driver.prototype.renderSteps=function(){
    var self=this,container=this.$('#familySteps').empty();
    this.steps.forEach(function(step,index){
      var options=self.options[step.name]||[],allowed=self.reachable[step.name],chosen=self.selections[step.name];
      var section=$('<div class="config-section">').attr('data-step',step.name).append($('<h4>').append($('<span class="ill-config-step-num">').text(index+2),document.createTextNode(step.label)));
      var pills=$('<div class="pill-selector" role="radiogroup">').attr('aria-label',step.label),select=$('<select class="form-control select-fallback">').attr('aria-label',step.label).append($('<option value="">').text(__('Select...')));
      options.forEach(function(option){
        var disabled=!!allowed&&!allowed.some(function(o){return String(o.value)===String(option.value);}),selected=chosen!=null&&String(chosen)===String(option.value);
        pills.append($('<button type="button" role="radio" class="pill">').toggleClass('active',selected).toggleClass('disabled',disabled).attr('aria-checked',selected).prop('disabled',disabled).text(option.label).on('click',function(){self.choose(step.name,option.value);}));
        select.append($('<option>').val(option.value).text(option.label).prop('disabled',disabled).prop('selected',selected));
      });
      select.on('change',function(){var value=$(this).val();if(value)self.choose(step.name,value);});
      container.append(section.append(pills,select));
    });
    this.$('#driverLineStepNum').text(this.steps.length+2);
    var total=this.steps.length+1,done=(this.template?1:0)+this.steps.filter(function(step){return self.selections[step.name]!=null&&self.selections[step.name]!=='';}).length;
    this.$('#driverProgressBadge').text(Math.round(100*done/(total||1))+'%');
  };
  Driver.prototype.choose=function(name,value){this.selections[name]=value;this.changed(name);};
  Driver.prototype.setStatus=function(label,tone){this.$('#driverValidationStatus').attr('class','badge badge-'+tone).text(__(label));};
  Driver.prototype.renderPlaceholder=function(text){this.$('#familySummary').empty().append($('<div class="text-center text-muted py-3 ill-driver-placeholder">').append($('<i class="fa fa-bolt fa-2x mb-2" aria-hidden="true">'),$('<p class="mb-0">').text(text||__('Choose a power supply and its options to see its spec ID, specifications and pricing.'))));};
  Driver.prototype.renderError=function(text){this.setStatus('Invalid','danger');this.$('#familySummary').empty().append($('<div class="alert alert-danger mb-0">').text(text));};
  // Template header: series, warranty and the spec sheet link.
  Driver.prototype.renderTemplateInfo=function(t){
    var box=this.$('#driverTemplateInfo').empty();if(!t.code){box.prop('hidden',true);return;}
    box.prop('hidden',false);
    var facts=$('<dl class="ill-driver-facts">');
    if(t.series_code)facts.append($('<dt>').text(__('Series')),$('<dd>').text(t.series_code));
    if(t.warranty)facts.append($('<dt>').text(__('Warranty')),$('<dd>').text(t.warranty));
    if(this.context.show_pricing&&t.base_price_msrp)facts.append($('<dt>').text(__('Starting at')),$('<dd>').text('$'+Number(t.base_price_msrp).toFixed(2)));
    if(facts.children().length)box.append(facts);
    if(t.spec_sheet)box.append($('<a target="_blank" rel="noopener" class="btn btn-sm btn-outline-secondary">').attr('href',t.spec_sheet).append($('<i class="fa fa-file-pdf-o" aria-hidden="true">'),document.createTextNode(' '+__('View spec sheet'))));
  };
  // Validation result: part number, the resolved Item, its specifications, price and stock.
  Driver.prototype.renderResult=function(data){
    var box=this.$('#familySummary').empty();
    if(!data.success){this.renderError(data.error||__('Choose a valid configuration.'));return;}
    if(!data.variant||!data.variant.item){this.renderError(__('This configuration has no orderable item. Contact us to order it.'));return;}
    this.setStatus('Valid','success');
    box.append($('<div class="ill-driver-part">').append($('<small>').text(__('Spec ID')),$('<code>').text(data.variant.spec_name||data.part_number)));
    box.append($('<p class="ill-driver-item">').text((data.template_name?data.template_name+' · ':'')+(data.variant.item_name||data.variant.item)));
    var pricing=data.pricing||{};
    if(this.context.show_pricing&&pricing.total_msrp!=null)box.append($('<div class="ill-driver-price">').append($('<span>').text(__('MSRP each')),$('<strong>').text('$'+Number(pricing.total_msrp).toFixed(2))));
    if((data.specs||[]).length){var specs=$('<dl class="ill-driver-specs">');data.specs.forEach(function(row){specs.append($('<dt>').text(row.label),$('<dd>').text(row.value));});box.append(specs);}
    var stock=data.stock;if(stock&&stock.availability!=='unknown'){box.append($('<p class="ill-driver-stock">').addClass(stock.in_stock?'is-in-stock':'is-short').text(stock.in_stock?__('In stock'):__('Not in stock')));if(this.context.show_stock_qty&&stock.qty_available!=null)box.append($('<p class="small text-muted mb-0">').text(__('{0} available',[stock.qty_available])));}
  };
  IC.Driver=Driver;
})(window);
