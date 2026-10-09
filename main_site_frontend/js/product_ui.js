/* Accessible shared dialogs and content-free, bounded journey measurements. */
(() => {
    'use strict';
    const t=(key,params={})=>window.mpbI18n?.t(`ux.${key}`,key,params)||key;
    const journeys=new Map();
    const allowed=new Set(['schedule_first','studio_first','calendar_connected','error_recovered']);
    function start(name){if(allowed.has(name)&&!journeys.has(name))journeys.set(name,performance.now());}
    function finish(name){
        if(!journeys.has(name))return;
        const duration=Math.min(3600000,Math.max(0,Math.round(performance.now()-journeys.get(name))));journeys.delete(name);
        const token=localStorage.getItem('jwt_token');if(!token)return;
        fetch(`${window.getMpbApiBase?.()||'/api'}/ux/events`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({journey:name,duration_ms:duration}),signal:AbortSignal.timeout(3000)}).catch(()=>{});
    }
    function dialog({title,content,actions}){
        return new Promise(resolve=>{
            const previous=document.activeElement,el=document.createElement('dialog');el.className='ui-dialog';
            const heading=document.createElement('h2');heading.id=`ui-dialog-${crypto.randomUUID()}`;heading.textContent=title;el.setAttribute('aria-labelledby',heading.id);el.append(heading,content);
            const footer=document.createElement('div');footer.className='dialog-actions';
            for(const action of actions){const button=document.createElement('button');button.type='button';button.className=`ui-button ${action.primary?'primary':''} ${action.danger?'danger':''}`;button.textContent=action.label;button.addEventListener('click',()=>{if(action.validate&&!action.validate())return;el.close(action.value);});footer.append(button);}
            el.append(footer);document.body.append(el);el.addEventListener('close',()=>{const value=el.returnValue;el.remove();previous?.focus();resolve(value);},{once:true});el.showModal();
        });
    }
    async function prompt(title,value=''){
        const input=document.createElement('input');input.className='ui-input';input.value=value;input.maxLength=160;input.setAttribute('aria-label',title);
        const result=await dialog({title,content:input,actions:[{label:t('cancel'),value:'cancel'},{label:t('save'),value:'save',primary:true,validate:()=>{if(!input.value.trim()){input.focus();return false;}return true;}}]});return result==='save'?input.value.trim():null;
    }
    async function confirm(title,message){const p=document.createElement('p');p.textContent=message;return(await dialog({title,content:p,actions:[{label:t('cancel'),value:'cancel'},{label:t('confirm'),value:'yes',danger:true}]}))==='yes';}
    window.MpbUI={t,dialog,prompt,confirm,start,finish};
    if(location.pathname.startsWith('/schedule'))start('schedule_first');
    if(location.pathname.startsWith('/studio'))start('studio_first');
})();
