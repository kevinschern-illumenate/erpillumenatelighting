import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {existsSync} from 'node:fs';
import FamilyChooser from './FamilyChooser.jsx';
import QuestionStep from './QuestionStep.jsx';
import Results from './Results.jsx';
import Wizard from './Wizard.jsx';
import {setDefinition,visibleQuestions,pruneHiddenAnswers,isAnswered} from '../lib/engine.js';
import {createClient} from '../lib/api.js';

const definition={version:1,settings:{},glossary:{},questions:[
  {id:'family',type:'family',label:'Product type',required:true,options:[{value:'Driver',label:'Driver'},{value:'Linear Fixture',label:'Linear',featured:true},{value:'accessories',label:'Accessories',routesTo:'catalog'}]},
  {id:'moisture',type:'single',label:'Moisture',required:true,families:['Linear Fixture'],options:[{value:'Dry',label:'Dry'},{value:'Wet',label:'Wet'}]},
  {id:'watts',type:'number',label:'Load',required:true,families:['Driver'],min:1,max:100},
]};
let host,root;
beforeEach(()=>{globalThis.IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement('div');document.body.append(host);root=createRoot(host);setDefinition(definition);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();localStorage.clear();});
const render=async(node)=>act(async()=>root.render(node));
const click=async(text)=>act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text).click());
const client=()=>({getDefinition:vi.fn().mockResolvedValue(definition),start:vi.fn().mockResolvedValue({token:'TOKEN'}),saveAnswers:vi.fn().mockResolvedValue({saved:true}),evaluate:vi.fn().mockResolvedValue({options:{}}),complete:vi.fn().mockResolvedValue({route:'catalog',catalog_url:'/portal/products?type=Accessory%2CComponent'}),getSession:vi.fn().mockResolvedValue({answers:{family:'Driver'},stale:true}),claim:vi.fn().mockResolvedValue({catalog_url:'/portal/products?finder=G'})});

describe('live Finder',()=>{
  it('filters family branches, prunes hidden choices, and validates numeric bounds',()=>{
    expect(visibleQuestions({family:'Driver'}).map(q=>q.id)).toEqual(['family','watts']);
    expect(pruneHiddenAnswers({family:'Driver',moisture:'Wet',obsolete:'x'})).toEqual({family:'Driver'});
    expect(isAnswered(definition.questions[2],{watts:101})).toBe(false);
    expect(isAnswered(definition.questions[2],{watts:80})).toBe(true);
  });
  it('places the featured card first in keyboard order and offers an unsure shortcut',async()=>{
    const change=vi.fn();await render(<FamilyChooser options={definition.questions[0].options} onChange={change}/>);
    expect(host.querySelector('button').textContent).toBe('Linear');
    expect(host.querySelector('button').tabIndex).toBe(0);
    await click("I'm not sure");expect(change).toHaveBeenCalledWith('Linear Fixture');
  });
  it('shows live counts and disabling reasons but keeps no-preference usable',async()=>{
    const question={id:'q',type:'single',label:'Choice',options:[{value:'x',label:'X'},{value:'any',label:'Any',noPreference:true}]};
    await render(<QuestionStep question={question} answers={{}} onChange={()=>{}} counts={{options:{x:{match:0,verify:0}},disabled:[{value:'x',reason:'No products match Wet'},{value:'any',reason:'No products'}]}}/>);
    expect(host.querySelectorAll('button')[0].disabled).toBe(true);expect(host.querySelectorAll('button')[1].disabled).toBe(false);
    expect(host.textContent).toContain('0 products · 0 need a check');
  });
  it('debounces autosave, evaluates the current question, and moves focus',async()=>{
    vi.useFakeTimers();const api=client();await render(<Wizard config={{client:api}}/>);await click('Driver');
    await act(async()=>vi.advanceTimersByTimeAsync(150));expect(api.evaluate).toHaveBeenLastCalledWith({family:'Driver'},'watts');
    expect(document.activeElement.textContent).toBe('Load');
    expect(api.saveAnswers).not.toHaveBeenCalled();await act(async()=>vi.advanceTimersByTimeAsync(350));
    expect(api.saveAnswers).toHaveBeenCalledTimes(1);expect(api.saveAnswers).toHaveBeenCalledWith('TOKEN',{family:'Driver'});
  });
  it('saves before accessories navigation and resumes existing answers',async()=>{
    const api=client(),navigate=vi.fn();await render(<Wizard config={{client:api,navigate}}/>);await click('Accessories');
    expect(api.saveAnswers).toHaveBeenCalledWith('TOKEN',{family:'accessories'});expect(navigate).toHaveBeenCalledWith('/portal/products?type=Accessory%2CComponent');
  });
  it('resumes stale sessions without creating another session',async()=>{
    const api=client();await render(<Wizard config={{client:api,sessionToken:'S'}}/>);expect(api.start).not.toHaveBeenCalled();expect(host.textContent).toContain('catalog has changed');expect(host.textContent).toContain('Load');
  });
  it('claims a saved public session once and clears local storage',async()=>{
    localStorage.setItem('ill-finder-claim','G');const api=client(),navigate=vi.fn();await render(<Wizard config={{client:api,navigate}}/>);
    expect(api.claim).toHaveBeenCalledWith('G');expect(localStorage.getItem('ill-finder-claim')).toBeNull();expect(navigate).toHaveBeenCalledWith('/portal/products?finder=G');
  });
  it('renders portal results and public website/claim links',async()=>{
    const result={counts:{match:1},matches:[{name:'P',title:'Product',slug:'p',url:'https://brand.test/p',verify:['IP67']}],catalog_url:'/portal/products?finder=T',claim_url:'https://erp.test/claim',relaxed:['Finish']};
    await render(<Results result={result} config={{}} token="T" settings={{}}/>);expect(host.innerHTML).toContain('/portal/products/p?finder=T#configure');expect(host.textContent).toContain('Finish');
    await render(<Results result={result} config={{mode:'public'}} settings={{}}/>);expect(host.querySelector('a').href).toBe('https://brand.test/p');expect(host.innerHTML).toContain('https://erp.test/claim');
    expect(existsSync(new URL('./CompareTable.jsx',import.meta.url))).toBe(false);
  });
  it('uses CSRF for portal writes and omits credentials on public calls',async()=>{
    const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({message:{}})});vi.stubGlobal('fetch',fetch);
    await createClient({csrfToken:'CSRF'}).saveAnswers('T',{});expect(fetch.mock.calls[0][1].headers['X-Frappe-CSRF-Token']).toBe('CSRF');
    await createClient({mode:'public',apiBase:'https://erp.test',brand:'brand'}).evaluate({},'family');expect(fetch.mock.calls[1][1].credentials).toBe('omit');expect(fetch.mock.calls[1][1].method).toBe('GET');
  });
});
