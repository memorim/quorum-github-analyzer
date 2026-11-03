// Public browser client: no private token or repository code is sent to a server.
(() => {
  const normalize = value => {
    if (typeof value !== 'string' || !/^[\w.-]+\/[\w.-]+$/.test(value) || value.split('/').some(v => v === '.' || v === '..')) throw new Error('Введите owner/repository');
    return value;
  };
  async function get(path) {
    for (let attempt=0;attempt<3;attempt++) {
      let response;
      try { response = await fetch(`https://api.github.com${path}`, {headers:{Accept:'application/vnd.github+json'},signal:AbortSignal.timeout(15000),credentials:'omit',redirect:'error'}); }
      catch(error) { if(attempt===2) throw new Error('GitHub недоступен. Повторите позже.'); await new Promise(r=>setTimeout(r,250*2**attempt)); continue; }
      if ([500,502,503,504].includes(response.status) && attempt<2) {await new Promise(r=>setTimeout(r,250*2**attempt));continue;}
      if(!response.ok) throw new Error(response.status===404?'Репозиторий не найден или закрыт':response.status===403||response.status===429?'Лимит GitHub исчерпан. Повторите позже.':`GitHub: HTTP ${response.status}`);
      return {data:await response.json(),more:(response.headers.get('link')||'').includes('rel="next"')};
    }
  }
  async function analyze(value) {
    const name=normalize(value), repo=(await get(`/repos/${name}`)).data;
    const canonical=normalize(repo.full_name), base=`/repos/${canonical}`, collection={};
    async function collect(key,path,fallback,pages=1,field) {
      let result=Array.isArray(fallback)?[]:{};
      try {
        for(let page=1;page<=pages;page++) {
          const out=await get(path+(path.includes('?')?'&':'?')+`page=${page}`);
          const data=field?out.data[field]:out.data;
          if(Array.isArray(fallback)) {if(!Array.isArray(data)||data.length>100)throw new Error('Некорректные данные GitHub');result.push(...data);} else result=data;
          collection[key]={available:true,truncated:out.more,error:null};
          if(!out.more)break;
        }
      } catch(error) {collection[key]={available:false,truncated:!!result.length,error:error.message};}
      return result;
    }
    const languages=await collect('languages',base+'/languages',{});
    const issues=(await collect('issues',base+'/issues?state=open&per_page=50&sort=updated',[],3)).filter(i=>!i.pull_request);
    const pulls=await collect('pulls',base+'/pulls?state=open&per_page=50',[],2);
    const runs=await collect('workflow_runs',base+'/actions/runs?per_page=20',[],1,'workflow_runs');
    return score({repo,languages,issues,pulls,runs,collection});
  }
  function score({repo,languages,issues,pulls,runs,collection}) {
    let points=100; const risks=[],actions=[];
    const risk=(severity,title,detail)=>risks.push({severity,title,detail});
    const action=(priority,title,why)=>actions.push({priority,title,why});
    const days=repo.pushed_at?Math.max(0,Math.floor((Date.now()-Date.parse(repo.pushed_at))/86400000)):null;
    if(days>180){points-=25;risk('high','Repository is inactive',`No push for ${days} days.`);action('high','Plan a maintenance release','Restore a visible delivery cadence.');}
    else if(days>60){points-=12;risk('medium','Delivery cadence slowed',`Last push was ${days} days ago.`);}
    if(repo.archived){points-=30;risk('high','Repository is archived','New changes and issue handling are disabled.');}
    if(!repo.description){points-=8;risk('low','Missing repository description','The project purpose is unclear in search results.');action('medium','Add a concise description','Improve discoverability and onboarding.');}
    if(!repo.license){points-=10;risk('medium','No license detected','Reuse and contribution terms are ambiguous.');action('high','Choose and add a license','Clarify legal usage and contribution terms.');}
    if(!repo.topics?.length){points-=5;action('low','Add repository topics','Make the project easier to discover.');}
    if(issues.length>60){points-=20;risk('high','Large issue backlog',`${issues.length} open issues need triage.`);}
    else if(issues.length>20){points-=10;risk('medium','Issue backlog is growing',`${issues.length} open issues need review.`);}
    if(pulls.length>10){points-=8;risk('medium','Pull request queue is congested',`${pulls.length} pull requests are open.`);}
    const concluded=runs.filter(r=>r.conclusion), rate=concluded.length?concluded.filter(r=>r.conclusion==='success').length/concluded.length:null;
    if(!runs.length&&collection.workflow_runs.available){points-=12;risk('medium','No recent CI runs found','Automated validation is missing or inactive.');action('high','Add a CI quality gate','Run tests and linting on every pull request.');}
    else if(rate!==null&&rate<.6){points-=15;risk('high','CI reliability is low',`Only ${Math.round(rate*100)}% of recent runs passed.`);action('high','Stabilize failing workflows','Reliable feedback keeps pull requests moving.');}
    const partial=Object.entries(collection).filter(([,v])=>!v.available||v.truncated).map(([k])=>k);
    if(partial.length||days===null)risk('low','Incomplete metadata snapshot','Unavailable or bounded samples: '+(partial.length?partial.join(', '):'last push date'));
    if(!risks.length)risk('low','No immediate risks detected','The repository signals look healthy.');
    if(!actions.length)action('low','Keep the current engineering cadence','No urgent corrective action is required.');
    points=Math.max(0,Math.min(100,points));
    const total=Object.values(languages).reduce((a,b)=>a+b,0)||1;
    const triaged=issues.map(i=>{const labels=(i.labels||[]).map(l=>typeof l==='string'?l.toLowerCase():String(l.name||'').toLowerCase());const age=Math.max(0,Math.floor((Date.now()-Date.parse(i.created_at||new Date().toISOString()))/86400000));let n=Math.min(Math.floor(age/7),8)+Math.min(i.comments||0,10);if(labels.some(l=>l.includes('security')))n+=30;if(labels.some(l=>['bug','type:bug'].includes(l)))n+=12;if(labels.some(l=>l.includes('high')||l.includes('urgent')))n+=15;return {number:i.number,title:i.title,url:`https://github.com/${repo.full_name}/issues/${i.number}`,priority:n>=35?'critical':n>=20?'high':n>=10?'medium':'low',priority_score:n,age_days:age,comments:i.comments||0,labels};}).sort((a,b)=>b.priority_score-a.priority_score).slice(0,8);
    let verdict=points>=85?'Strong metadata maintenance signals':points>=70?'Healthy with a few visible gaps':points>=50?'Needs focused maintenance':'Metadata indicates maintenance gaps';if(partial.length)verdict+=' (partial snapshot)';
    return {id:crypto.randomUUID(),repository:repo.full_name,repository_url:`https://github.com/${repo.full_name}`,created_at:new Date().toISOString(),score:points,verdict,summary:`${repo.full_name} scored ${points}/100. Quorum found ${risks.length} risk signal(s) and ${actions.length} recommended action(s).`,risks,actions,triaged_issues:triaged,metrics:{stars:repo.stargazers_count||0,forks:repo.forks_count||0,open_issues:issues.length,open_pulls:pulls.length,days_since_push:days,ci_success_rate:rate===null?null:Math.round(rate*1000)/10,default_branch:repo.default_branch,language_mix:Object.entries(languages).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([name,size])=>({name,share:Math.round(size/total*1000)/10})),analysis_scope:'github_metadata_only',collection,analyzed_at:new Date().toISOString()}};
  }
  globalThis.QuorumPublic = {analyze,normalize,score};
})();
