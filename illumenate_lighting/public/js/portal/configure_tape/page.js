// Tape/neon configurator page boot (plan 2.2). Server values come from #configure-tape-context.
$(function() {
    var context = JSON.parse(document.getElementById('configure-tape-context').textContent || '{}');
    var rootEl = document.querySelector('.ill-configurator-tape-neon') || document;
    var inst = new IllConfigurator.TapeNeon(rootEl, {
        product_category: context.product_category,
        is_neon: context.is_neon,
        schedule_name: context.schedule_name,
        project_name: context.project_name,
        line_idx: context.line_idx,
        can_save: context.can_save
    });
    IllConfigurator.registerDefaultTapeNeon(inst);
    inst.init();
});
