import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {webcrypto} from 'node:crypto';
function browser(storage=new Map(), failure=false) {
 let network=0;
 const scope={DEMO_SEED:JSON.parse(readFileSync(new URL('./seed.json',import.meta.url))),structuredClone,Response,Headers,URL,DOMException,Date,crypto:webcrypto,AbortSignal,setTimeout,location:new URL('https://example.test/project/'),localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},fetch:async input=>{
 network++;const url=new URL(input);assert.equal(url.origin,'https://api.github.com');
 if(failure)return new Response('{}',{status:404});
 const data=url.pathname.endsWith('/languages')?{JavaScript:100}:url.pathname.endsWith('/issues')||url.pathname.endsWith('/pulls')?[]:url.pathname.endsWith('/actions/runs')?{workflow_runs:[{conclusion:'success'}]}:{full_name:'owner/new-repo',description:'New repository',license:{spdx_id:'MIT'},topics:['test'],pushed_at:new Date().toISOString(),stargazers_count:7,forks_count:1};
 return new Response(JSON.stringify(data),{status:200});
 }};
 for(const file of ['../app/static/public-analysis.js','browser.js'])runInNewContext(readFileSync(new URL(file,import.meta.url),'utf8'),scope);
 return {call:async(path,method='GET',body)=>{const r=await scope.fetch(path,{method,...(body?{body:JSON.stringify(body)}:{})});return {status:r.status,body:await r.json()};},network:()=>network};
}
test('new GitHub analysis deduplicates concurrent requests and persists history',async()=>{
 const storage=new Map(),b=browser(storage),before=(await b.call('/api/analyses')).body.length;
 const [a,c]=await Promise.all([b.call('/api/analyses','POST',{repository:'owner/new-repo'}),b.call('/api/analyses','POST',{repository:'owner/new-repo'})]);
 assert.equal(a.status,201);assert.equal(c.body.id,a.body.id);assert.equal(a.body.repository,'owner/new-repo');assert.equal(a.body.score,100);assert.equal(a.body.metrics.stars,7);assert.equal(b.network(),5);
 assert.equal((await b.call('/api/analyses')).body.length,before+1);
 const reloaded=browser(storage);assert.equal((await reloaded.call('/api/analyses')).body[0].id,a.body.id);
 assert.equal((await reloaded.call('/api/analyses/'+a.body.id)).body.id,a.body.id);
});
test('invalid names never reach GitHub and failed analyses do not fabricate reports',async()=>{
 const b=browser(new Map(),true),before=(await b.call('/api/analyses')).body.length;
 assert.equal((await b.call('/api/analyses','POST',{repository:'../bad'})).status,400);assert.equal(b.network(),0);
 assert.equal((await b.call('/api/analyses','POST',{repository:'owner/missing'})).status,400);
 assert.equal((await b.call('/api/analyses')).body.length,before);
});
