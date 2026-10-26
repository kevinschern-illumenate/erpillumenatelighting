(function(root){
  'use strict';
  var IC=root.IllConfigurator,API='illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator.';
  function Kit(el,context){IC.DriverController.call(this,el,context);this.template=context.selected_template||(context.initial_request||{}).template;}
  Kit.prototype=Object.create(IC.DriverController.prototype);Kit.prototype.constructor=Kit;
  Kit.prototype.init=function(){var self=this;IC.DriverController.prototype.init.call(this);this.$('#familyProductSelect').hide().prev('label').hide();this.$('#kitTemplateSelect').prop('hidden',false).on('change',function(){self.template=$(this).val();self.context.initial_request=null;self.loading=true;self.delay(function(){self.load();},0);});this.load();return this;};
  Kit.prototype.load=function(){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.updateSave();
    this.request({method:API+'get_kit_configurator_init',args:{kit_template_name:this.template||null},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};
      if(!data.success){self.fail(data.error||__('Unable to load this kit. Please try again.'));return;}
      self.loading=false;
      if(data.templates){
        var select=self.$('#kitTemplateSelect');select.find('option').filter(function(){return this.value;}).remove();
        data.templates.forEach(function(t){select.append($('<option>').val(t.name).text(t.template_name).attr('data-image',t.image||''));});
        if(IC.renderTemplateCards)IC.renderTemplateCards({$container:self.$('#kitTemplatePicker'),$select:select});
        self.renderTemplateInfo({});self.steps=[];self.renderSteps();self.updateSave();return;
      }
      self.$('#kitTemplateSelect').hide();self.renderTemplateInfo(data.kit_template||{});self.options=data.options||{};
      self.steps=[['finish','Finish'],['lens_appearance','Lens appearance'],['mounting_method','Mounting method']].map(function(s){return {name:s[0],label:s[1]};});
      self.selections=Object.assign({},data.defaults||{},(self.context.initial_request||{}).selections||{}, {kit_template:self.template});
      delete self.selections.endcap_style;delete self.selections.endcap_color;self.reachable={};self.renderSteps();self.changed();
    },error:function(){if(revision===self.revision)self.fail(__('Unable to load this kit. Please try again.'));}});
  };
  Kit.prototype.changed=function(){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.updateSave();this.renderSteps();
    this.request({method:API+'get_kit_cascading_options',args:{kit_template_name:this.template,finish:this.selections.finish,lens_appearance:this.selections.lens_appearance,mounting_method:this.selections.mounting_method},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};
      if(data.success===false){self.fail(data.error||__('Unable to check kit options. Please try again.'));return;}
      self.reachable={};if(data.available_lens_appearances)self.reachable.lens_appearance=data.available_lens_appearances;
      Object.keys(self.reachable).forEach(function(key){if(!self.reachable[key].some(function(o){return o.value===self.selections[key];}))delete self.selections[key];});
      self.renderSteps();self.validate();
    },error:function(){if(revision===self.revision)self.fail(__('Unable to check kit options. Please try again.'));}});
  };
  Kit.prototype.validate=function(){
    var self=this,revision=this.revision;
    if(!this.steps.every(function(step){return !!self.selections[step.name];})){
      this.loading=false;this.result=null;this.setStatus('Incomplete','secondary');this.$('#familySummary').text(__('Choose an option for every step.'));this.updateSave();return;
    }
    this.loading=true;this.result=null;this.updateSave();
    this.request({method:API+'validate_kit_configuration',args:{selections:JSON.stringify(this.selections)},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};self.loading=false;self.result=data.is_valid?data:null;self.renderResult(data);self.updateSave();
    },error:function(){if(revision===self.revision)self.fail(__('Unable to validate this kit. Please try again.'));}});
  };
  Kit.prototype.fail=function(message){this.loading=false;this.result=null;this.renderResult({is_valid:false,error:message});this.updateSave();};
  // Kit options invalidate through changed(); line metadata does not change the build.
  Kit.prototype._updateButtons=function(){this.updateSave();};
  Kit.prototype.updateSave=function(){
    IC.DriverController.prototype.updateSave.call(this);
    if(this.loading)this.$('#familySave').prop('disabled',true);
    var target=this.scheduleTarget,message='';
    if(this.saving)message=__('Saving to schedule…');
    else if(this.loading)message=__('Checking kit configuration…');
    else if(!this.result)message=__('Choose a kit template and complete its options.');
    else if(this.targetReady())message='';
    else if(!target||!target.hasTarget())message=__('Select a fixture schedule and line, or choose New Line.');
    else if(!target.canSave)message=__('You cannot save to this schedule. Choose an editable schedule.');
    this.$('#kitSaveStatus').text(message);
  };
  Kit.prototype.save=function(){if(!this.result||this.saving)return;if(this.hostSaves()){this.context.saveHandler({product_type:'Extrusion Kit',template:this.template,selections:Object.assign({},this.selections)});return;}var selected=this.scheduleTarget.lineValue(),snapshot=this.scheduleSnapshot||{},line=(snapshot.lines||[]).find(function(l){return String(l.idx)===String(selected);});this.sendSave('illumenate_lighting.illumenate_lighting.portal.kit_configuration.save',{schedule_name:this.scheduleTarget.scheduleName(),selections:JSON.stringify(this.selections),expected_modified:snapshot.modified,line_key:line?line.line_key:null,line_idx:line?null:selected==='__new__'?null:selected,metadata:JSON.stringify(this.metadata()),finder:this.context.finder});};
  // Numbered option sections with pill choices, matching the other configurators. Small screens get a select.
  Kit.prototype.renderSteps=function(){
    var self=this,container=this.$('#familySteps').empty();
    this.steps.forEach(function(step,index){
      var options=self.options[step.name]||[],allowed=self.reachable[step.name],chosen=self.selections[step.name];
      var section=$('<div class="config-section">').attr('data-step',step.name).append($('<h4>').append($('<span class="ill-config-step-num">').text(index+2),document.createTextNode(step.label)));
      var pills=$('<div class="pill-selector" role="radiogroup">').attr('aria-label',step.label),select=$('<select class="form-control select-fallback">').attr('aria-label',step.label).append($('<option value="">').text(__('Select...')));
      options.forEach(function(option){
        var disabled=!!allowed&&!allowed.some(function(o){return String(o.value)===String(option.value);}),selected=String(chosen)===String(option.value);
        pills.append($('<button type="button" role="radio" class="pill">').toggleClass('active',selected).toggleClass('disabled',disabled).attr('aria-checked',selected).prop('disabled',disabled).text(option.label).on('click',function(){self.choose(step.name,option.value);}));
        select.append($('<option>').val(option.value).text(option.label).prop('disabled',disabled).prop('selected',selected));
      });
      select.on('change',function(){var value=$(this).val();if(value)self.choose(step.name,value);});
      container.append(section.append(pills,select));
    });
    this.$('#kitLineStepNum').text(this.steps.length+2);
    var total=this.steps.length+1,done=(this.template?1:0)+this.steps.filter(function(step){return !!self.selections[step.name];}).length;
    this.$('#kitProgressBadge').text(Math.round(100*done/(total||1))+'%');
  };
  Kit.prototype.choose=function(name,value){this.selections[name]=value;this.changed(name);};
  Kit.prototype.setStatus=function(label,tone){this.$('#kitValidationStatus').attr('class','badge badge-'+tone).text(__(label));};
  var COMPONENTS=[['profile','Profile'],['lens','Lens'],['mounting','Mounting'],['solid_endcap','Solid endcap'],['feed_through_endcap','Feed-through endcap']];
  // Template header: what the kit ships and the spec sheet data its submittals carry.
  Kit.prototype.renderTemplateInfo=function(t){
    var box=this.$('#kitTemplateInfo').empty();if(!t.name){box.prop('hidden',true);return;}
    box.prop('hidden',false);
    // The card picker already shows the chosen template's image and name.
    if(!this.$('#kitTemplatePicker').children().length){
      var head=$('<div class="ill-kit-template-head">');
      if(t.image)head.append($('<img>').attr('src',t.image).attr('alt',t.template_name||t.name));
      head.append($('<div>').append($('<div class="ill-kit-template-name">').text(t.template_name||t.name),t.template_code?$('<div class="ill-kit-template-code">').text(t.template_code):null));
      box.append(head);
    }
    var ships=[];if(t.profile_stock_length_mm)ships.push(t.profile_stock_length_mm+' mm profile');if(t.lens_stock_length_mm)ships.push(t.lens_stock_length_mm+' mm lens');if(t.mounting_accessory_qty)ships.push(t.mounting_accessory_qty+' mounting accessories');if(t.solid_endcap_qty)ships.push(t.solid_endcap_qty+' solid endcaps');if(t.feed_through_endcap_qty)ships.push(t.feed_through_endcap_qty+' feed-through endcaps');var endcapNote=t.solid_endcap_qty||t.feed_through_endcap_qty?' Endcaps come in the color that matches the finish.':'';
    if(ships.length)box.append($('<p class="ill-kit-ships">').text('Each kit: '+ships.join(', ')+'.'+endcapNote));
    if((t.spec_sheet_data||[]).length){var specs=$('<dl class="ill-kit-specs">');t.spec_sheet_data.forEach(function(row){specs.append($('<dt>').text(row.label),$('<dd>').text(row.value));});box.append(specs);}
    if(t.spec_sheet)box.append($('<a target="_blank" rel="noopener" class="btn btn-sm btn-outline-secondary">').attr('href',t.spec_sheet).append($('<i class="fa fa-file-pdf-o" aria-hidden="true">'),document.createTextNode(' '+__('View spec sheet'))));
  };
  // Validation result: part number, components with quantities, price and stock.
  Kit.prototype.renderResult=function(data){
    var self=this,box=this.$('#familySummary').empty();
    if(!data.is_valid){this.setStatus('Invalid','danger');box.append($('<div class="alert alert-danger mb-0">').text(data.error||'Choose a valid configuration.'));return;}
    this.setStatus('Valid','success');
    box.append($('<div class="ill-kit-part">').append($('<small>').text(__('Part number')),$('<code>').text(data.part_number)));
    if(this.context.show_pricing&&data.pricing&&data.pricing.total_price_msrp!=null)box.append($('<div class="ill-kit-price">').append($('<span>').text(__('MSRP per kit')),$('<strong>').text('$'+Number(data.pricing.total_price_msrp).toFixed(2))));
    var table=$('<table class="table table-sm small ill-kit-components">').append($('<thead>').append($('<tr>').append($('<th>').text('Component'),$('<th>').text('Item'),$('<th class="text-right">').text('Qty per kit'))));var body=$('<tbody>').appendTo(table);
    COMPONENTS.forEach(function(c){var comp=(data.kit_composition||{})[c[0]];if(comp&&comp.not_required){body.append($('<tr class="text-muted">').append($('<td>').text(c[1]),$('<td>').text(__('None required')),$('<td class="text-right">').text('0')));return;}if(!comp||!comp.item)return;body.append($('<tr>').append($('<td>').text(c[1]+(comp.length_mm?' ('+comp.length_mm+' mm)':'')),$('<td>').text(comp.item),$('<td class="text-right">').text(comp.qty)));});
    box.append(table);
    var sa=data.stock_availability;if(sa){box.append($('<p class="ill-kit-stock">').addClass(sa.all_in_stock?'is-in-stock':'is-short').text(sa.all_in_stock?'Components in stock':'Some components need replenishment'));if(self.context.show_stock_qty)(sa.items||[]).forEach(function(item){box.append($('<p class="small text-muted mb-0">').text(item.item_name+': '+item.qty_available+' available'));});}
  };
  IC.Kit=Kit;
})(window);
