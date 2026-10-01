(function(root){
  'use strict';
  var IC=root.IllConfigurator, API='illumenate_lighting.illumenate_lighting.api.driver_controller_configurator.';
  function DriverController(el,context){IC.Base.call(this,el,context);this.kind=context.kind;this.steps=[];this.options={};this.reachable={};this.result=null;this.revision=0;}
  DriverController.prototype=Object.create(IC.Base.prototype);DriverController.prototype.constructor=DriverController;
  DriverController.prototype.init=function(){
    var self=this;
    this.scheduleTarget=IC.bindScheduleContext({instance:this,context:this.context,onChange:function(){self.updateSave();}});
    var draft=this.context.draft||{};
    this.$('#familyLineId').val(draft.line_id||'');this.$('#familyLocation').val(draft.location||'');this.$('#familyQty').val(draft.qty||1);this.$('#familyNotes').val(draft.notes||'');
    this.$('#familySave').on('click',function(){self.save();});
    this.$('#familyProductSelect').val(this.context.product_slug||'').on('change',function(){self.context.product_slug=$(this).val();self.context.initial_request=null;self.loading=true;self.delay(function(){self.load();},0);});
    if(this.context.product_slug&&this.kind!=='Extrusion Kit')this.load();
    return this;
  };
  DriverController.prototype.load=function(){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.updateSave();
    if(!this.context.product_slug){this.loading=false;this.steps=[];this.$('#familySteps').empty();return;}
    this.request({method:API+'get_'+this.kind.toLowerCase()+'_configurator_init',args:{product_slug:this.context.product_slug},callback:function(r){
      if(revision!==self.revision)return;var data=r.message||{};if(!data.success){self.$('#familySummary').text(data.error||'Product unavailable');return;}
      self.loading=false;self.steps=data.steps;self.options=data.options;self.reachable={};self.selections={};
      self.steps.forEach(function(step){var options=data.options[step.name]||[],requested=(self.context.initial_request||{}).selections||{},chosen=options.find(function(o){return String(o.value)===String(requested[step.name]);})||options.find(function(o){return o.is_default;});if(chosen)self.selections[step.name]=chosen.value;});
      self.renderSteps();self.validate();
    }});
  };
  DriverController.prototype.renderSteps=function(){
    var self=this,container=this.$('#familySteps').empty();
    this.steps.forEach(function(step){var group=$('<div class="mb-3" role="radiogroup">').attr('aria-label',step.label).append($('<strong class="d-block mb-2">').text(step.label));
      (self.options[step.name]||[]).forEach(function(option){var allowed=self.reachable[step.name],disabled=allowed&&!allowed.some(function(o){return String(o.value)===String(option.value);});var selected=String(self.selections[step.name])===String(option.value);group.append($('<button type="button" role="radio" class="btn btn-sm mr-2 mb-2">').addClass(selected?'btn-primary':'btn-outline-primary').attr('aria-checked',selected).attr('title',step.name.includes('protocol')?'Control protocol: '+option.label:option.label).prop('disabled',!!disabled).text(option.label).on('click',function(){self.selections[step.name]=option.value;self.changed(step.name);}));});container.append(group);
    });
  };
  DriverController.prototype.changed=function(step){
    var self=this,revision=++this.revision;this.loading=true;this.result=null;this.updateSave();this.renderSteps();
    // Clear other axes when evaluating a new choice so a previously complete variant cannot trap the user.
    var partial={};partial[step]=this.selections[step];
    this.request({method:API+'get_'+this.kind.toLowerCase()+'_cascading_options',args:{product_slug:this.context.product_slug,step_name:step,selections:JSON.stringify(partial)},callback:function(r){if(revision!==self.revision)return;var data=r.message||{};self.reachable=data.updated_options||{};Object.keys(self.reachable).forEach(function(key){if(!self.reachable[key].some(function(o){return String(o.value)===String(self.selections[key]);}))delete self.selections[key];});self.renderSteps();self.validate();}});
  };
  DriverController.prototype.validate=function(){
    var self=this,revision=this.revision;
    if(!this.steps.every(function(step){return self.selections[step.name]!=null;})){this.$('#familySummary').text('Choose an option for every step.');return;}
    this.request({method:API+'validate_'+this.kind.toLowerCase()+'_configuration',args:{product_slug:this.context.product_slug,selections:JSON.stringify(this.selections)},callback:function(r){if(revision!==self.revision)return;self.result=r.message&&r.message.success?r.message:null;self.renderSummary(r.message||{});self.updateSave();}});
  };
  DriverController.prototype.renderSummary=function(data){var box=this.$('#familySummary').empty();if(!data.success){box.text(data.error||'Choose a valid configuration.');return;}box.append($('<strong>').text(data.part_number));if(data.variant)box.append($('<p>').text((data.variant.variant_code||'')+' · '+(data.variant.item||'')));if(this.context.show_pricing&&data.pricing)box.append($('<p>').text('MSRP: '+(data.pricing.total_msrp??data.pricing.total_price_msrp??data.pricing.msrp??'')));};
  DriverController.prototype._updateButtons=function(){this.result=null;this.updateSave();if(!this.loading&&this.steps.length)this.validate();};
  DriverController.prototype.updateSave=function(){this.$('#familySave').prop('disabled',!this.result||!this.scheduleTarget||!this.scheduleTarget.hasTarget()||!this.scheduleTarget.canSave||this.saving);};
  DriverController.prototype.metadata=function(){return {line_id:this.$('#familyLineId').val(),location:this.$('#familyLocation').val(),qty:Number(this.$('#familyQty').val()),notes:this.$('#familyNotes').val()};};
  DriverController.prototype.save=function(){
    if(!this.result||this.saving)return;
    if(this.scheduleTarget.lineValue()!=='__new__'){frappe.msgprint('Choose New Line to add this driver or controller.');return;}
    var meta=this.metadata(),args={product_slug:this.context.product_slug,selections:JSON.stringify(this.selections),schedule_name:this.scheduleTarget.scheduleName(),quantity:meta.qty,line_id:meta.line_id,location:meta.location,notes:meta.notes,expected_modified:(this.scheduleSnapshot||{}).modified,finder:this.context.finder};
    this.sendSave('illumenate_lighting.illumenate_lighting.portal.standard_products.add_configured',args);
  };
  DriverController.prototype.sendSave=function(method,args){
    var self=this,signature=JSON.stringify(args);if(!this.saveAttempt||this.saveAttempt.signature!==signature)this.saveAttempt={signature:signature,key:root.crypto.randomUUID()};args.idempotency_key=this.saveAttempt.key;this.saving=true;this.updateSave();
    this.request({method:method,type:'POST',args:args,callback:function(r){if(r.message&&r.message.success){if(self.context.draft_id)root.sessionStorage.removeItem('ill-line-draft:'+self.context.draft_id);root.location.href='/portal/schedules/'+encodeURIComponent(r.message.schedule_name);}else self.$('#familySummary').text((r.message||{}).error||'Save failed');},always:function(){self.saving=false;self.updateSave();}});
  };
  IC.DriverController=DriverController;
})(window);
