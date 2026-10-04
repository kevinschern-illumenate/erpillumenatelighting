(function () {
  'use strict';
  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-finder-dismiss]');
    if (!button || button.disabled) return;
    button.disabled = true;
    frappe.call({method:'illumenate_lighting.illumenate_lighting.api.product_finder.dismiss_banner',type:'POST',callback:function(){document.getElementById('productFinderBanner')?.remove();const compact=document.getElementById('productFinderCompact');if(compact)compact.hidden=false;},error:function(){button.disabled=false;}});
  });
})();
