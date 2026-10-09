/* GitHub is content, never executable instructions. Sanitize before DOM insertion. */
(() => {
    const repo='Ackrome/matplobbot',key='mpb-readme-v1',article=document.getElementById('readme-content'),status=document.getElementById('readme-status');
    const narrow=matchMedia('(max-width:640px)'),navigation=document.querySelector('.readme-navigation');const fitContents=()=>navigation.open=!narrow.matches;fitContents();narrow.addEventListener('change',fitContents);
    let state='readmeLoading';const t=key=>window.mpbI18n.t(`ux.${key}`,key);
    function render(data){
        if(!window.marked||!window.DOMPurify)throw new Error('renderer');
        article.innerHTML=DOMPurify.sanitize(marked.parse(data.markdown),{USE_PROFILES:{html:true},FORBID_TAGS:['style','form','input','button','iframe','object','embed'],FORBID_ATTR:['style','srcset','id','name'],ALLOW_DATA_ATTR:false});
        const base=data.html_url.replace(/[^/]+$/,''),raw=base.replace('github.com/','raw.githubusercontent.com/').replace('/blob/','/');
        const toc=document.getElementById('readme-toc');toc.replaceChildren();const ids=new Map();
        article.querySelectorAll('h1,h2,h3').forEach(node=>{const slug=node.textContent.toLowerCase().trim().replace(/[^\p{L}\p{N}\s_-]/gu,'').replace(/\s+/g,'-')||'section';const n=ids.get(slug)||0;ids.set(slug,n+1);node.id=slug+(n?`-${n}`:'');if(node.tagName!=='H3'){const a=document.createElement('a');a.href=`#${node.id}`;a.textContent=node.textContent;toc.append(a);}});
        article.querySelectorAll('a[href],img[src]').forEach(node=>{const attr=node.tagName==='IMG'?'src':'href',value=node.getAttribute(attr);if(value.startsWith('#'))return;try{const url=new URL(value,node.tagName==='IMG'?raw:base);if(!['https:','http:'].includes(url.protocol)){node.removeAttribute(attr);return;}node.setAttribute(attr,url.href);if(node.tagName==='A'){node.target='_blank';node.rel='noopener noreferrer';}else{node.loading='lazy';node.referrerPolicy='no-referrer';node.addEventListener('error',()=>{const label=document.createElement('span');label.className='readme-image-fallback';label.textContent=node.alt||t('imageUnavailable');node.replaceWith(label);},{once:true});}}catch{node.removeAttribute(attr);}});
        article.querySelectorAll('pre').forEach(pre=>{const button=document.createElement('button');button.className='ui-button';button.dataset.i18n='ux.copy';button.textContent=t('copy');const text=pre.textContent;button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(text);button.textContent=t('copied');}catch{button.textContent=t('copyFailed');}});pre.after(button);});
    }
    async function load(force=false){
        await window.mpbI18n.ready;const button=document.getElementById('readme-retry');button.disabled=true;article.setAttribute('aria-busy','true');let cached;
        try{cached=JSON.parse(localStorage.getItem(key));}catch{}
        try{
            if(cached&&typeof cached.markdown==='string'&&cached.html_url?.startsWith(`https://github.com/${repo}/blob/`)){render(cached);state='readmeCached';status.textContent=t(state);if(!force&&Date.now()-cached.savedAt<600000)return;}
            const response=await fetch(`https://api.github.com/repos/${repo}/readme`,{headers:{Accept:'application/vnd.github+json'},signal:AbortSignal.timeout(12000)});
            if(!response.ok)throw new Error('github');const body=await response.json();if(body.encoding!=='base64'||body.size>1500000||!body.html_url?.startsWith(`https://github.com/${repo}/blob/`))throw new Error('format');
            const markdown=new TextDecoder().decode(Uint8Array.from(atob(body.content.replace(/\s/g,'')),x=>x.charCodeAt(0)));const data={markdown,html_url:body.html_url,savedAt:Date.now()};render(data);try{localStorage.setItem(key,JSON.stringify(data));}catch{}state='readmeReady';
        }catch{state=article.textContent?'readmeCached':'readmeFailed';}finally{status.textContent=t(state);button.disabled=false;article.setAttribute('aria-busy','false');}
    }
    document.getElementById('readme-retry').addEventListener('click',()=>load(true));window.addEventListener('mpb-language-change',()=>{status.textContent=t(state);});load();
})();
