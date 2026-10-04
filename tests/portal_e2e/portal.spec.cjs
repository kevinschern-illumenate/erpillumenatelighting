const {test, expect} = require('@playwright/test');
const fs = require('node:fs');
const API='illumenate_lighting.illumenate_lighting.';

function fixture() {
    if (!process.env.B2B_E2E_URL || !process.env.B2B_E2E_FIXTURE) throw new Error('Set B2B_E2E_URL and B2B_E2E_FIXTURE to the isolated-site fixture manifest.');
    return JSON.parse(fs.readFileSync(process.env.B2B_E2E_FIXTURE,'utf8'));
}
async function actor(browser, name) {
    const data=fixture(), password=process.env[`B2B_E2E_${name.toUpperCase()}_PASSWORD`];
    if (!password) throw new Error(`Missing process secret for ${name}`);
    const context=await browser.newContext({baseURL:process.env.B2B_E2E_URL,viewport:test.info().project.use.viewport});
    // Login occurs through the API; secrets never enter browser screenshots or traces.
    const response=await context.request.post('/api/method/login',{form:{usr:data.actors[name],pwd:password}});
    expect(response.ok(),'Actor login must succeed').toBeTruthy();
    return context;
}

test('native private files isolate unrelated dealers and guests', async ({browser, request})=>{
    const data=fixture(), a=await actor(browser,'dealer_a'), b=await actor(browser,'dealer_b');
    try {
        expect((await a.request.get(data.private_files.a)).ok()).toBeTruthy();
        for (const client of [b.request,request]) {
            const response=await client.get(data.private_files.a,{maxRedirects:0});
            expect([302,401,403,404]).toContain(response.status());
        }
    } finally {await a.close(); await b.close();}
});

test('company members and VIEW collaborators read a schedule without editing it', async ({browser})=>{
    const data=fixture();
    for (const name of ['member_a','viewer']) {
        const context=await actor(browser,name), page=await context.newPage();
        try {
            await page.goto('/portal/schedules/'+encodeURIComponent(data.schedules.a));
            await expect(page.getByText('QA Manufacturer').first()).toBeVisible();
            await expect(page.getByRole('button',{name:'Add Line',exact:true})).toHaveCount(0);
        } finally {await context.close();}
    }
});

test('dealer catalog and schedule actions load with built assets and no runtime errors', async ({browser},testInfo)=>{
    const data=fixture(), context=await actor(browser,'dealer_a'), page=await context.newPage(), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    try {
        await page.setViewportSize(testInfo.project.use.viewport);
        await page.goto('/portal/products');
        await expect(page.locator('#catalogSearch')).toBeVisible();
        await page.goto('/portal/schedules/'+encodeURIComponent(data.schedules.a));
        await page.getByRole('button',{name:'Add Line',exact:true}).click();
        await expect(page.locator('#addLineModal')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#addLineModal')).not.toBeVisible();
        expect(errors).toEqual([]);
    } finally {await context.close();}
});

test('staff review queues and publication preflight deny dealers', async ({browser})=>{
    fixture(); const context=await actor(browser,'dealer_a');
    try {
        const response=await context.request.get('/api/method/'+API+'portal.queues.items',{params:{queue:'orders'}});
        expect(response.status()).toBe(403);
        expect((await response.json()).exc_type).toBe('PermissionError');
        const publication=await context.request.get('/api/method/'+API+'api.product_readiness.preview',{params:{product:'unauthorized'}});
        expect(publication.status()).toBe(403);
        expect((await publication.json()).exc_type).toBe('PermissionError');
    } finally {await context.close();}
});

test('catalog transport failure is actionable and preserves search for retry', async ({browser})=>{
    fixture(); const context=await actor(browser,'dealer_a'), page=await context.newPage();
    try {
        await page.route('**/api/method/'+API+'api.product_catalog.get_catalog_products',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
        await page.goto('/portal/products');
        await page.locator('#catalogSearch').fill('Snowfield');
        await expect(page.locator('#catalogFeedback')).toContainText('unavailable');
        await expect(page.locator('#catalogSearch')).toHaveValue('Snowfield');
        await page.unroute('**/api/method/'+API+'api.product_catalog.get_catalog_products');
        await page.locator('#catalogSearch').fill('Snow');
        await expect(page.locator('#productGrid')).toHaveAttribute('aria-busy','false');
    } finally {await context.close();}
});

async function schedule(context, name) {
    const response=await context.request.get('/api/resource/ilL-Project-Fixture-Schedule/'+encodeURIComponent(name));
    expect(response.ok()).toBeTruthy(); return (await response.json()).data;
}

test('four families save once across concurrent sessions, reopen and reject conflicting retries', async ({browser})=>{
    const data=fixture();
    expect(data.engineering_cases?.length,'Provide approved engineering cases with portal_request selections').toBeGreaterThanOrEqual(4);
    const a=await actor(browser,'dealer_a'), b=await actor(browser,'dealer_a');
    try {
        const pages=await Promise.all([a.newPage(),b.newPage()]);
        await Promise.all(pages.map(page=>page.goto('/portal/schedules/'+encodeURIComponent(data.schedules.a))));
        const tokens=await Promise.all(pages.map(page=>page.evaluate(()=>frappe.csrf_token)));
        for (const [index,entry] of data.engineering_cases.entries()) {
            expect(entry.portal_request?.selections,'Supply the saved UI request, including topology and power choices').toBeTruthy();
            const before=await schedule(a,data.schedules.a), key=require('node:crypto').randomUUID();
            const args={...entry.portal_request,schedule_name:data.schedules.a,family:entry.family,
                selections:JSON.stringify(entry.portal_request.selections),metadata:JSON.stringify({line_id:'QA-'+index+'-'+key.slice(0,8),qty:2,location:'Acceptance room',notes:'Retain across retries'}),
                expected_modified:before.modified,idempotency_key:key};
            if (args.segments) args.segments=JSON.stringify(args.segments);
            const post=(client,token,body)=>client.request.post('/api/method/'+API+'portal.configuration.save',{form:body,headers:{'X-Frappe-CSRF-Token':token}});
            const responses=await Promise.all([post(a,tokens[0],args),post(b,tokens[1],args)]);
            const results=await Promise.all(responses.map(async response=>{expect(response.ok()).toBeTruthy();return (await response.json()).message;}));
            expect(results[0].line_key).toBe(results[1].line_key);
            expect(results.map(result=>result.already_existed).sort()).toEqual([false,true]);
            const after=await schedule(a,data.schedules.a);
            expect(after.lines.length).toBe(before.lines.length+1);
            const opened=await a.request.get('/api/method/'+API+'portal.configuration_reopen.load',{params:{schedule_name:data.schedules.a,line_key:results[0].line_key}});
            const reopened=(await opened.json()).message.request;
            expect(reopened.selections).toEqual(entry.portal_request.selections);
            expect((await post(a,tokens[0],{...args,metadata:JSON.stringify({qty:3})})).ok()).toBeFalsy();
            expect((await schedule(a,data.schedules.a)).lines.length).toBe(after.lines.length);
        }
    } finally {await a.close(); await b.close();}
});

test('records page performance observations without inventing acceptance thresholds', async ({browser},testInfo)=>{
    fixture(); const context=await actor(browser,'dealer_a'), page=await context.newPage(), samples=[];
    try {
        for(let i=0;i<7;i++) {
            const start=Date.now(); await page.goto('/portal/products');
            await expect(page.locator('#productGrid')).toHaveAttribute('aria-busy','false');
            samples.push(Date.now()-start);
        }
        samples.sort((a,b)=>a-b);
        await testInfo.attach('catalog-timings',{body:JSON.stringify({samples_ms:samples,p95_ms:samples[Math.ceil(samples.length*.95)-1],viewport:testInfo.project.name,acceptance_threshold:'Record owner-approved baseline separately'}),contentType:'application/json'});
    } finally {await context.close();}
});

test('ordinary sales staff can open Desk review queues', async ({browser})=>{
    fixture(); const context=await actor(browser,'sales'), page=await context.newPage();
    try {
        await page.goto('/app/ill-portal-operations');
        await expect(page.getByRole('button',{name:/^Quote requests:/}).first()).toBeVisible();
        await expect(page.getByRole('button',{name:/^Order review:/}).first()).toBeVisible();
    } finally {await context.close();}
});

test('four family calculations match approved engineering references on the actual site', async ({browser})=>{
    const data=fixture();
    if (!data.engineering_cases?.length) throw new Error('Engineering must add approved family requests and expected build results to engineering_cases; an empty manifest is not acceptance.');
    expect(new Set(data.engineering_cases.map(row=>row.family))).toEqual(new Set(['Linear Fixture','LED Tape','LED Neon','LED Sheet']));
    const context=await actor(browser,'dealer_a');
    try {
        for (const entry of data.engineering_cases) {
            const response=await context.request.get('/api/method/'+API+'api.configured_product_builder.calculate_and_lookup',{params:{product_type:entry.family,payload_json:JSON.stringify(entry.payload),tape_neon_template:entry.template}});
            expect(response.ok()).toBeTruthy(); const result=(await response.json()).message;
            expect(result.success).toBeTruthy();
            expect(result.candidate_config_hash).toBe(entry.expected_build_hash);
            // Fresh/upgrade catalog differences require explicit engineering review.
        }
    } finally {await context.close();}
});

// The isolated fixture supplies current catalog choices and deterministic engineering inputs.
// Required Finder fields and setup are documented in B2B_CLOUD_ACCEPTANCE.md.
async function answerFinder(page, answers) {
    for (const [id,value] of Object.entries(answers)) {
        const question=page.locator('section[id="'+id+'"]');
        await expect(question).toBeVisible();
        if (typeof value==='number') await question.locator('input').fill(String(value));
        else if (typeof value==='object') {
            await question.locator('input').nth(0).fill(String(value.low));
            await question.locator('input').nth(1).fill(String(value.high));
        } else await question.getByRole('radio',{name:value,exact:false}).click();
    }
}
async function completeFinder(page, answers) {
    await page.goto('/portal/product-finder');await answerFinder(page,answers);
    await page.getByRole('button',{name:'See matching products',exact:true}).click();
    await page.getByRole('link',{name:'See matching products',exact:true}).click();
    await expect(page.locator('#finderBanner')).toBeVisible();
    return new URL(page.url()).searchParams.get('finder');
}

test('Finder dealer banner through wet Linear configuration, verification badge and quote request',async({browser})=>{
    const data=fixture(),context=await actor(browser,'dealer_a'),page=await context.newPage();
    try {
        await page.goto('/portal');await expect(page.locator('#productFinderBanner')).toBeVisible();
        expect(data.finder.linear.answers.moisture).toBe('Wet');expect(data.finder.linear.answers.ip_rating).toContain('IP67');
        const token=await completeFinder(page,data.finder.linear.answers);
        await page.locator('a.product-card-details[href*="/'+data.finder.linear.slug+'?"]').first().click();
        await expect(page.locator('#finderProductContext')).toContainText('verify');
        await page.goto('/portal/configure?category=Linear%20Fixture&template='+encodeURIComponent(data.finder.linear.template)+'&finder='+encodeURIComponent(token));
        await expect(page.locator('.ill-handoff-banner')).toContainText('pre-filled');
        const before=await schedule(context,data.schedules.a);
        const result=await page.evaluate(async({API,token,before,entry})=>{
            const r=await frappe.call({method:API+'portal.configuration.save',type:'POST',args:{...entry.portal_request,family:'Linear Fixture',finder:token,schedule_name:before.name,expected_modified:before.modified,idempotency_key:crypto.randomUUID(),metadata:{line_id:'FINDER-LINEAR',qty:1}}});return r.message;
        },{API,token,before,entry:data.finder.linear});
        expect(result.success).toBeTruthy();await page.goto('/portal/schedules/'+encodeURIComponent(data.schedules.a));
        await expect(page.getByText('Verification pending').first()).toBeVisible();
        await page.getByRole('button',{name:/Request Quote/i}).click();
        await expect(page.getByRole('dialog',{name:'Request quote / engineering review'})).toBeVisible();
        await page.getByRole('dialog',{name:'Request quote / engineering review'}).getByRole('button',{name:'Submit request'}).click();
        await expect(page).toHaveURL(/quote-requests/);
    } finally {await context.close();}
});
for (const [family,key] of [['Driver','driver'],['Extrusion Kit','kit']])test('Finder '+family+' configures and saves an authoritative schedule line',async({browser})=>{
    const data=fixture(),context=await actor(browser,'dealer_a'),page=await context.newPage();
    try {
        const entry=data.finder[key],token=await completeFinder(page,entry.answers);
        await page.goto('/portal/configure?category='+encodeURIComponent(family)+'&product_slug='+encodeURIComponent(entry.slug)+'&template='+encodeURIComponent(entry.template)+'&schedule='+encodeURIComponent(data.schedules.a)+'&finder='+encodeURIComponent(token));
        for(const [axis,label] of Object.entries(entry.choices))await page.getByRole('radiogroup',{name:axis,exact:true}).getByRole('radio',{name:label,exact:true}).click();
        await page.locator('[data-ill-original-id="lineSelect"], #lineSelect').selectOption('__new__');
        await page.locator('[data-ill-original-id="familyLineId"], #familyLineId').fill('FINDER-'+key.toUpperCase());
        await page.getByRole('button',{name:'Save to schedule',exact:true}).click();
        await expect(page).toHaveURL(/portal\/schedules\//);await expect(page.getByText('FINDER-'+key.toUpperCase(),{exact:true})).toBeVisible();
    } finally {await context.close();}
});
test('Finder accessories route and configurator chooser preserve project context',async({browser})=>{
    const data=fixture(),context=await actor(browser,'dealer_a'),page=await context.newPage();
    try {
        await page.goto('/portal/configure?schedule='+encodeURIComponent(data.schedules.a)+'&draft=QA');
        await expect(page.getByRole('heading',{name:'What would you like to configure?'})).toBeVisible();
        expect(await page.locator('a.card').first().getAttribute('href')).toContain('schedule=');
        await page.goto('/portal/product-finder');await page.getByRole('radio',{name:/Accessories & parts/}).click();
        await expect(page).toHaveURL(/type=Accessory/);
    } finally {await context.close();}
});
test('public Finder completion claims once and opens the dealer filtered catalog',async({browser,request})=>{
    const data=fixture(),response=await request.post('/api/method/'+API+'api.product_finder_public.complete',{data:{brand:data.finder.brand,answers:data.finder.public_answers}});
    expect(response.ok()).toBeTruthy();const result=(await response.json()).message;expect(result.matches.length).toBeGreaterThan(0);
    const context=await actor(browser,'dealer_a'),page=await context.newPage();
    try {await page.goto(result.claim_url);await expect(page).toHaveURL(/portal\/products\?finder=/);await expect(page.locator('#finderBanner')).toBeVisible();}
    finally {await context.close();}
});
