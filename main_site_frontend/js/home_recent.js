(() => {
    const container=document.createElement('div');container.className='ui-row home-recent';document.querySelector('a[href="#projects"][data-i18n]')?.parentElement.after(container);
    const render=()=>{container.replaceChildren();const t=window.MpbUI.t;try{
        const recent=JSON.parse(localStorage.getItem('mpb_schedule_recent_entities')||'[]')[0];
        if(recent&&['group','person','auditorium'].includes(recent.type)&&recent.id){const a=document.createElement('a');a.className='ui-button';a.href='/schedule?'+new URLSearchParams({type:recent.type,id:recent.id,name:recent.name||recent.label});a.textContent=t('recentSchedule')+': '+(recent.name||recent.label);container.append(a);}
        const token=localStorage.getItem('jwt_token');if(token){const sub=JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub;const project=JSON.parse(localStorage.getItem('mpb-last-project:'+encodeURIComponent(String(sub)))||'null');if(project&&Number.isInteger(Number(project.id))){const a=document.createElement('a');a.className='ui-button';a.href='/studio?project='+encodeURIComponent(project.id);a.textContent=t('recentProject')+': '+project.name;container.append(a);}}
    }catch{}};
    window.mpbI18n.ready.then(render);window.addEventListener('mpb-language-change',render);
})();
