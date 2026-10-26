const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');

test('dashboard treats repository titles as text and rejects executable links', () => {
  const nodes = new Map();
  const document = {querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {style:{setProperty(){}}, addEventListener(){},querySelectorAll(){return []}});
    return nodes.get(selector);
  }};
  const attack = '<img src=x onerror="globalThis.exploited=true">';
  const report = {id:'abc',repository:attack,score:100,repository_url:'javascript:alert(1)',verdict:attack,summary:attack,created_at:'2026-01-01T00:00:00Z',metrics:{stars:1,forks:0,open_issues:1,days_since_push:0,language_mix:[{name:attack,share:100}]},risks:[],actions:[],triaged_issues:[{url:'javascript:alert(1)',title:attack,priority:'low',number:1,age_days:0,comments:0}]};
  const source = readFileSync('app/static/app.js','utf8').replace(/refresh\(\)\.catch\([^\n]+\);\s*$/, '');
  runInNewContext(source + '\nrenderReport(report); state.analyses=[report]; renderHistory();', {document,URL,report});
  assert.equal(nodes.get('#repository-link').href,'#');
  for (const node of nodes.values()) {
    if (!node.innerHTML) continue;
    assert.ok(!node.innerHTML.includes('<img'), node.innerHTML);
    assert.ok(!node.innerHTML.includes('javascript:'), node.innerHTML);
  }
  assert.ok(nodes.get('#triage-list').innerHTML.includes('&lt;img'));
  assert.ok(nodes.get('#language-list').innerHTML.includes('&lt;img'));
  assert.equal(nodes.get('#repository-name').textContent,attack);
});
