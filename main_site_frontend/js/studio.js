/* Studio: drafts and transport errors never silently discard the editor. */
const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : '/api';
const $ = id => document.getElementById(id);
const t = (key, params = {}) => window.mpbI18n?.t(`studio.${key}`, key, params) || key;
let token, editor, session, sessionScope, splitInstance, currentBlobUrl, activeJob;
let currentMode = 'quick', currentProjectId = null, currentFileId = null, currentProjectType = 'latex';
let projectsList = [], projectFiles = [], previewGeneration = 0, editorGeneration = 0;
let changingEditor = false, transitionBusy = false, saveTimer, transitionQueue = Promise.resolve();
let currentStatus = 'ready', statusParams = {}, lastFocus, selectedMobilePane = 'editor-pane';
let markdownConfigured = false, jobPolling = false, jobStarting = false, storageWarningShown = false;
const TEMPLATES = {
    latex: '\\documentclass[12pt,a4paper]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T2A]{fontenc}\n\\usepackage[russian]{babel}\n\\usepackage{amsmath,graphicx}\n\\begin{document}\n\\section{Introduction}\n$E=mc^2$\n\\end{document}',
    markdown: '# Document\n\n$$E=mc^2$$\n',
    mermaid: 'graph TD;\n    A[Start] --> B[Finish];',
};
const STUDIO_MARKDOWN_SANITIZE_CONFIG = Object.freeze({
    ALLOWED_TAGS: ['a','b','blockquote','br','code','del','div','em','h1','h2','h3','h4','h5','h6','hr','i','img','li','ol','p','pre','span','strong','table','tbody','td','th','thead','tr','ul'],
    ALLOWED_ATTR: ['alt','class','colspan','href','rel','rowspan','src','target','title'],
    ALLOW_DATA_ATTR: false, ALLOW_UNKNOWN_PROTOCOLS: false,
    FORBID_TAGS: ['embed','form','iframe','input','math','object','script','style','svg'],
});
function getStudioHtmlSanitizer() {
    const sanitizer = window.DOMPurify;
    if (!sanitizer?.sanitize) throw new Error(t('preview.sanitizerUnavailable'));
    return sanitizer;
}
function sanitizeStudioMarkdownPreview(markdownSource) {
    const renderedHtml = marked.parse(markdownSource);
    return getStudioHtmlSanitizer().sanitize(renderedHtml, STUDIO_MARKDOWN_SANITIZE_CONFIG);
}
function renderStudioPreviewError(container, error) {
    const errorElement = document.createElement('pre');
    errorElement.className = 'studio-preview-error';
    errorElement.textContent = error instanceof Error ? error.message : String(error);
    container.replaceChildren(errorElement);
}
function storage() { try { return window.localStorage; } catch (_) { return {getItem(){return null;},setItem(){throw new Error('Storage unavailable');},removeItem(){}}; } }
async function ensureStudioAuth() {
    token = storage().getItem('jwt_token');
    if (!token && window.mpbTelegramAuthReady) { await window.mpbTelegramAuthReady; token = storage().getItem('jwt_token'); }
    if (!token) {
        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search + window.location.hash)}`;
        throw new Error(t('authRequired'));
    }
    if (sessionScope && MpbStudioSession.accountScope(token) !== sessionScope) throw new Error(t('sessionChanged'));
    return true;
}
async function api(path, options = {}) {
    await ensureStudioAuth();
    const {timeoutMs=20000,...requestOptions}=options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(`${API_BASE}${path}`, {...requestOptions, signal: controller.signal,
            headers: {Authorization: `Bearer ${token}`, ...requestOptions.headers}});
        if (!response.ok) {
            let detail;
            try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : null; } catch (_) { /* non-JSON proxy errors */ }
            const error = new Error(detail || t(response.status === 401 ? 'authExpired' : 'requestFailed', {status: response.status}));
            error.status = response.status;
            throw error;
        }
        return response;
    } catch (error) {
        if (error.name === 'AbortError') throw new Error(t('networkTimeout'));
        throw error;
    } finally { clearTimeout(timer); }
}
function setStatus(key, params = {}) {
    currentStatus = key; statusParams = params;
    $('status-text').textContent = t(`status.${key}`, params);
    $('status-icon-saved').classList.toggle('hidden', key !== 'saved');
    $('status-icon-sync').classList.toggle('hidden', !['saving','uploading','creating'].includes(key));
}
function showError(error) {
    $('error-text').textContent = error.message || String(error);
    $('error-panel').classList.remove('hidden');
    $('retry-studio-button').classList.remove('hidden');
    setStatus('error');
    if (editor && window.innerWidth<768) switchMobileTab('editor-pane');
}
function run(action) { return Promise.resolve().then(action).catch(showError); }
function setEditorContent(value, readOnly = false) {
    changingEditor = true;
    editor.setValue(value);
    editor.updateOptions({readOnly});
    changingEditor = false;
    updateWordCount();
}
function onEditorChange() {
    if (changingEditor || !session) return;
    session.edit(editor.getValue());
    updateWordCount();
    setStatus(currentMode === 'quick' ? 'localDraft' : 'unsaved');
    $('pdf-stale').classList.toggle('hidden', !currentBlobUrl);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
        if (currentMode === 'project') run(saveCurrentFile);
        run(updateLivePreview);
    }, 900);
}
function updateWordCount() {
    if (!editor) return;
    const content = editor.getValue();
    $('doc-stats').textContent = t('wordCount', {words: content.trim().split(/\s+/).filter(Boolean).length, chars: content.length});
}
function createFallbackEditor(content = '') {
    const textarea = document.createElement('textarea');
    textarea.className = 'studio-fallback-editor';
    textarea.setAttribute('aria-label', t('editor'));
    textarea.spellcheck = false;
    textarea.value = content;
    textarea.addEventListener('input', onEditorChange);
    textarea.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); run(compileCurrent); } });
    $('monaco-container').replaceChildren(textarea);
    return {getValue:()=>textarea.value,setValue:value=>{textarea.value=value;},updateOptions:options=>{textarea.readOnly=Boolean(options.readOnly);},layout(){},getModel(){return null;},dispose(){textarea.remove();}};
}
async function upgradeEditor() {
    if(editor?.getModel())return;
    const generation = ++editorGeneration;
    const frame=document.createElement('iframe');frame.className='studio-editor-frame';frame.title=t('editor');frame.hidden=true;
    try {
        await new Promise((resolve,reject) => {
            const timeout=setTimeout(()=>reject(new Error(t('editorUnavailable'))),24000);
            frame.onload=()=>{
                const ready=frame.contentWindow.mpbStudioMonacoReady;
                if(!ready){clearTimeout(timeout);reject(new Error(t('editorUnavailable')));return;}
                ready.then(()=>{clearTimeout(timeout);resolve();},error=>{clearTimeout(timeout);reject(error);});
            };
            frame.onerror=()=>{clearTimeout(timeout);reject(new Error(t('editorUnavailable')));};
            frame.src='/studio-editor.html';$('monaco-container').appendChild(frame);
        });
        if (generation !== editorGeneration) {frame.remove();return;}
        const content = editor.getValue();
        const previousEditor=editor;
        window.monaco=frame.contentWindow.monaco;
        frame.contentDocument.documentElement.classList.toggle('dark',document.documentElement.classList.contains('dark'));
        frame.contentDocument.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();event.stopPropagation();window.mpbOpenCommandPalette?.();}},true);
        frame.hidden=false;
        const enhanced = monaco.editor.create(frame.contentDocument.getElementById('monaco-container'), {value:content,language:editorLanguage(),
            theme:document.documentElement.classList.contains('dark')?'vs-dark':'vs-light',
            automaticLayout:true,wordWrap:'on',minimap:{enabled:false},fontSize:14,readOnly:transitionBusy||Boolean(currentFile()?.is_binary),ariaLabel:t('editor')});
        previousEditor.dispose();editor=enhanced;
        monaco.languages.registerCompletionItemProvider('latex',{provideCompletionItems(){return {suggestions:[
            {label:'\\begin',kind:monaco.languages.CompletionItemKind.Snippet,insertText:'\\begin{${1:environment}}\n\t$0\n\\end{${1:environment}}',insertTextRules:monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet},
            {label:'\\section',kind:monaco.languages.CompletionItemKind.Snippet,insertText:'\\section{${1:title}}\n$0',insertTextRules:monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet},
            {label:'\\includegraphics',kind:monaco.languages.CompletionItemKind.Snippet,insertText:'\\includegraphics[width=${1:0.8}\\textwidth]{${2:image.png}}',insertTextRules:monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet}
        ]};}});
        editor.onDidChangeModelContent(onEditorChange);
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,()=>run(compileCurrent));
        $('editor-fallback-notice').classList.add('hidden');
        performance.mark?.('studio-editor-ready');
    } catch (_) {
        frame.remove();
        $('editor-fallback-notice').classList.remove('hidden');
        // The textarea remains fully editable and participates in the same durable session.
    }
}
function currentFile() { return projectFiles.find(file=>file.id===currentFileId); }
function editorLanguage() { return currentMode==='quick' ? ($('doc-type').value==='mermaid'?'plaintext':$('doc-type').value) : ({tex:'latex',sty:'latex',md:'markdown'}[currentFile()?.path.split('.').pop()]||'plaintext'); }
function setModelLanguage() { if (window.monaco && editor.getModel()) monaco.editor.setModelLanguage(editor.getModel(),editorLanguage()); }
async function saveCurrentFile() {
    clearTimeout(saveTimer);
    if (!session?.dirty()) return;
    setStatus('saving');
    await session.flush();
    setStatus('saved');
    $('retry-studio-button').classList.add('hidden');
}
function transition(action) {
    const next = transitionQueue.catch(()=>{}).then(async()=>{
        transitionBusy=true;
        editor.updateOptions({readOnly:true});
        try { await saveCurrentFile(); await action(); }
        finally { transitionBusy=false; editor.updateOptions({readOnly:Boolean(currentMode==='project'&&(!currentProjectId||currentFile()?.is_binary))});renderProjectList(); }
    });
    transitionQueue=next;
    return next;
}
function activateDocument(record) {
    let restored = session.open(record);
    if (restored.conflict) restored=session.resolveConflict(confirm(t('draftConflict')));
    setEditorContent(restored.content);
    setModelLanguage();
    setStatus(restored.recovered?'recovered':record.projectId?'saved':'ready');
    if (restored.recovered && record.projectId) saveTimer=setTimeout(()=>run(saveCurrentFile),900);
    run(updateLivePreview);
}
function activateFile(id) {
    const file=projectFiles.find(item=>item.id===id);
    if (!file) return;
    currentFileId=id;
    if (file.is_binary) {
        session.open({type:'binary',content:'',projectId:null});
        setEditorContent(t('binaryFile',{name:file.path}),true);
        setModelLanguage();
    } else activateDocument({projectId:currentProjectId,fileId:id,type:currentProjectType,content:file.content||''});
    renderFileList();
}
async function activateProject(id) {
    const files=await (await api(`/studio/projects/${id}`)).json();
    if (!Array.isArray(files)) throw new Error(t('invalidResponse'));
    const preserveId=String(currentProjectId)===String(id)?currentFileId:null;
    currentMode='project';
    currentProjectId=id;
    projectFiles=files;
    currentProjectType=projectsList.find(project=>String(project.id)===String(id))?.type||'latex';
    currentFileId=null;
    $('project-selector').value=id;
    resetPreview();
    const file=files.find(item=>item.id===preserveId)||files.find(item=>item.is_main)||files[0];
    if (file) activateFile(file.id);
    else { session.open({type:'empty',content:''});setEditorContent('',true);renderFileList(); }
}
function openProject(id) { return transition(()=>activateProject(id)); }
function openFile(id) { return transition(()=>activateFile(id)); }
async function loadProjects() {
    const projects=await (await api('/studio/projects')).json();
    if (!Array.isArray(projects)) throw new Error(t('invalidResponse'));
    projectsList=projects;
    renderProjectList();
}
function renderProjectList() {
    const select=$('project-selector');
    select.replaceChildren(new Option(t('chooseProject'),''));
    projectsList.forEach(project=>select.add(new Option(project.name,project.id)));
    select.value=currentProjectId||'';
}
function switchMode(mode) { return transition(async()=>{
    if(mode===currentMode) return;
    if(mode==='project') await loadProjects();
    if(mode==='quick') {
        currentMode=mode;
        currentProjectId=currentFileId=null;
        activateDocument({type:$('doc-type').value,content:TEMPLATES[$('doc-type').value]});
    } else if(projectsList.length) await activateProject(projectsList[0].id);
    else { currentMode=mode;currentProjectId=currentFileId=null;session.open({type:'empty',content:''});setEditorContent('',true); }
    resetPreview();updateModeUi();run(updateLivePreview);
}); }
function setLanguage(type) { return transition(()=>{ activateDocument({type,content:TEMPLATES[type]});resetPreview();run(updateLivePreview); }); }
function updateModeUi() {
    const project=currentMode==='project';
    $('mode-quick').setAttribute('aria-pressed',String(!project));
    $('mode-project').setAttribute('aria-pressed',String(project));
    $('doc-type').classList.toggle('hidden',project);
    ['btn-download-zip','btn-send-tg'].forEach(id=>$(id).classList.toggle('hidden',!project));
    $('tab-btn-sidebar').classList.toggle('hidden',!project);
    setupSplit();
}
function renderFileList() {
    const list=$('file-list');list.replaceChildren();
    projectFiles.forEach(file=>{
        const row=document.createElement('div');row.className=`file-item${file.id===currentFileId?' active':''}`;
        const open=document.createElement('button');open.type='button';open.className='studio-file-open';
        open.textContent=file.path;open.title=file.path;open.setAttribute('aria-current',file.id===currentFileId?'true':'false');
        open.addEventListener('click',()=>run(()=>openFile(file.id)));row.appendChild(open);
        if(!file.is_main) {
            for(const [key,action] of [['rename',()=>renameFile(file.id,file.path)],['delete',()=>deleteFile(file.id,file.path)]]) {
                const button=document.createElement('button');button.type='button';button.className='studio-file-action';
                button.textContent=t(key);button.setAttribute('aria-label',t(`${key}Named`,{name:file.path}));
                button.addEventListener('click',()=>run(action));row.appendChild(button);
            }
        }
        list.appendChild(row);
    });
}
function setupSplit() {
    if(splitInstance){splitInstance.destroy();splitInstance=null;}
    const mobile=window.innerWidth<768;
    $('mobile-tabs').classList.toggle('hidden',!mobile);
    $('split-container').dataset.mode=currentMode;
    if(mobile) switchMobileTab(currentMode==='quick'&&selectedMobilePane==='sidebar-pane'?'editor-pane':selectedMobilePane);
    else {
        ['editor-pane','viewer-pane'].forEach(id=>$(id).classList.remove('hidden'));
        $('sidebar-pane').classList.toggle('hidden',currentMode!=='project');
        if(window.Split) splitInstance=Split(currentMode==='project'?['#sidebar-pane','#editor-pane','#viewer-pane']:['#editor-pane','#viewer-pane'],
            {sizes:currentMode==='project'?[20,40,40]:[50,50],minSize:currentMode==='project'?[130,240,240]:[260,260],gutterSize:6});
    }
    editor?.layout();
}
function switchMobileTab(targetPaneId) {
    selectedMobilePane=targetPaneId;
    ['sidebar-pane','editor-pane','viewer-pane'].forEach(id=>{
        const active=id===targetPaneId;
        $(id).classList.toggle('hidden',!active);
        const button=$(`tab-btn-${id.split('-')[0]}`);
        button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
    });
    editor?.layout();
}
function resetPreview() {
    previewGeneration++;
    if(currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl=null;
    $('pdf-viewer').removeAttribute('src');
    ['pdf-viewer','btn-download-pdf','live-preview','pdf-stale'].forEach(id=>$(id).classList.add('hidden'));
    $('empty-state').classList.remove('hidden');
}
function configureMarkdown() {
    if(markdownConfigured)return;
    const renderer=new marked.Renderer();
    renderer.image=function(tokenOrHref,legacyTitle,legacyText){
        let href,title,text;
        if(typeof tokenOrHref === 'object')({href='',title='',text=''}=tokenOrHref);
        else {href=String(tokenOrHref||'');title=legacyTitle||'';text=legacyText||'';}
        if(currentMode==='project'&&currentProjectId&&!/^(https?:|data:)/i.test(href)) href=`${API_BASE}/studio/projects/${currentProjectId}/assets/${encodeURIComponent(href.replace(/^\/+/,''))}?token=${encodeURIComponent(token)}`;
        const image=document.createElement('img');image.src=href;image.alt=text;image.title=title;image.loading='lazy';
        return image.outerHTML;
    };
    marked.use({renderer});markdownConfigured=true;
}
async function updateLivePreview() {
    if(!editor||currentFile()?.is_binary&&currentMode==='project')return;
    const type=currentMode==='quick'?$('doc-type').value:currentProjectType;
    if(type==='latex')return;
    const generation=++previewGeneration, code=editor.getValue();
    const contentDiv=$('live-preview-content');
    $('empty-state').classList.add('hidden');$('pdf-viewer').classList.add('hidden');$('live-preview').classList.remove('hidden');
    try {
        await mpbStudioLibraries.ensure(type);
        if(generation!==previewGeneration)return;
        if(type==='markdown') {
            configureMarkdown();
            contentDiv.innerHTML=sanitizeStudioMarkdownPreview(code);
            contentDiv.querySelectorAll('a[target="_blank"]').forEach(link=>{link.rel='noopener noreferrer';});
            renderMathInElement(contentDiv,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false});
        } else {
            mermaid.initialize({startOnLoad:false,theme:document.documentElement.classList.contains('dark')?'dark':'default',securityLevel:'strict',flowchart:{htmlLabels:false}});
            const renderedDiagram=await mermaid.render(`studio-diagram-${generation}`,code);
            if(generation!==previewGeneration)return;
            const svg=typeof renderedDiagram === 'string'?renderedDiagram:renderedDiagram.svg;
            if(!svg)throw new Error(t('preview.mermaidEmpty'));
            const diagramContainer=document.createElement('div');
            diagramContainer.innerHTML=getStudioHtmlSanitizer().sanitize(svg,{USE_PROFILES:{svg:true,svgFilters:true}});
            contentDiv.replaceChildren(diagramContainer);
        }
    } catch(error) { if(generation===previewGeneration){renderStudioPreviewError(contentDiv,error);$('retry-studio-button').classList.remove('hidden');} }
}
function updateJobUi() {
    $('compile-btn').disabled=Boolean(activeJob||jobStarting);
    $('job-panel').classList.toggle('hidden',!activeJob);
    if(activeJob)$('job-status').textContent=t(`job.${activeJob.status||'queued'}`);
}
async function compileCurrent() {
    if(activeJob)return pollJob();
    if(jobStarting)return;
    jobStarting=true;updateJobUi();
    try {await transition(async()=>{
        const type=currentMode==='quick'?$('doc-type').value:currentProjectType;
        if(currentMode==='project'&&!currentProjectId)throw new Error(t('chooseProject'));
        const path=currentMode==='quick'?'/studio/jobs':`/studio/projects/${currentProjectId}/jobs`;
        const snapshot={mode:currentMode,projectId:currentProjectId,fileId:currentFileId,type,sourceContent:editor.getValue()};
        const response=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},
            ...(currentMode==='quick'?{body:JSON.stringify({type,content:snapshot.sourceContent})}:{})});
        const job=await response.json();
        activeJob={...job,...snapshot};session.storeValue('active-job',activeJob);
    });} finally {jobStarting=false;updateJobUi();}
    $('error-panel').classList.add('hidden');
    return pollJob();
}
async function pollJob() {
    if(!activeJob||jobPolling)return;
    jobPolling=true;$('job-resume-button').disabled=true;
    try {
        while(activeJob) {
            const job=await (await api(`/studio/jobs/${encodeURIComponent(activeJob.job_id)}`)).json();
            activeJob.status=job.status;updateJobUi();
            if(['success','error'].includes(job.status)) {
                const completed=activeJob;
                activeJob=null;session.removeValue('active-job');updateJobUi();
                if(job.status==='error'){
                    const errors=job.result?.errors||[];
                    if(window.monaco&&editor.getModel()&&String(completed.fileId)===String(currentFileId)) monaco.editor.setModelMarkers(editor.getModel(),'latex',errors.map(error=>({severity:monaco.MarkerSeverity.Error,startLineNumber:Math.max(1,error.line||1),startColumn:1,endLineNumber:Math.max(1,error.line||1),endColumn:1000,message:error.message||t('buildFailed')})));
                    throw new Error(errors.length?errors.map(error=>`${error.line||1}: ${error.message}`).join('\n'):job.error||t('buildFailed'));
                }
                const result=job.result;
                if(!result||result.status==='error')throw new Error(result?.error||result?.message||t('buildFailed'));
                showBuildResult(result,completed);return;
            }
            await new Promise(resolve=>setTimeout(resolve,1500));
        }
    } catch(error) {
        if(error.status===404){activeJob=null;session.removeValue('active-job');updateJobUi();throw new Error(t('job.expired'));}
        if(activeJob){activeJob.status='paused';updateJobUi();}
        throw error;
    } finally {jobPolling=false;$('job-resume-button').disabled=false;}
}
function showBuildResult(data,job) {
    const encoded=data.pdf||data.image;
    if(!encoded)throw new Error(t('invalidResponse'));
    const bytes=Uint8Array.from(atob(encoded),char=>char.charCodeAt(0));
    if(currentBlobUrl)URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl=URL.createObjectURL(new Blob([bytes],{type:data.pdf?'application/pdf':'image/png'}));
    $('pdf-viewer').src=currentBlobUrl+(data.pdf?'#toolbar=0&view=FitH':'');
    $('pdf-viewer').classList.remove('hidden');$('live-preview').classList.add('hidden');$('empty-state').classList.add('hidden');
    $('btn-download-pdf').classList.remove('hidden');$('btn-download-pdf').dataset.extension=data.pdf?'pdf':'png';
    $('pdf-stale').classList.toggle('hidden',job.mode===currentMode&&String(job.projectId)===String(currentProjectId)&&job.sourceContent===editor.getValue());
    setStatus('built');
}
function createNewProject() {
    lastFocus=document.activeElement;
    $('new-project-name').value='';$('new-project-type').value='latex';updateTemplateOptions();
    $('create-project-modal').classList.remove('hidden');$('new-project-name').focus();
}
function closeCreateProjectModal() {$('create-project-modal').classList.add('hidden');lastFocus?.focus();}
function updateTemplateOptions() {
    const type=$('new-project-type').value,select=$('new-project-template'),previous=select.value;
    select.replaceChildren();
    (type==='latex'?['latex_blank','latex_beamer','latex_report']:[type]).forEach(id=>select.add(new Option(t(`template.${id}`),id)));
    if([...select.options].some(option=>option.value===previous))select.value=previous;
}
async function submitNewProject() {
    const name=$('new-project-name').value.trim();if(!name){$('new-project-name').focus();return;}
    $('submit-create-project-button').disabled=true;
    try {
        await transition(async()=>{
            setStatus('creating');
            const created=await(await api('/studio/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,project_type:$('new-project-type').value,template_id:$('new-project-template').value})})).json();
            await loadProjects();currentMode='project';await activateProject(created.id);updateModeUi();closeCreateProjectModal();
        });
    } finally {$('submit-create-project-button').disabled=false;}
}
async function renameFile(id,path) {
    const name=prompt(t('renamePrompt',{name:path}),path);if(!name||name===path)return;
    return transition(async()=>{await api(`/studio/projects/${currentProjectId}/files/${id}/rename`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_name:name})});await activateProject(currentProjectId);});
}
async function deleteFile(id,path) {
    if(!confirm(t('deletePrompt',{name:path})))return;
    return transition(async()=>{await api(`/studio/projects/${currentProjectId}/files/${id}`,{method:'DELETE'});await activateProject(currentProjectId);});
}
async function uploadFiles(files) {
    if(!currentProjectId)throw new Error(t('chooseProject'));
    return transition(async()=>{
        for(const file of files){setStatus('uploading');const body=new FormData();body.append('file',file);await api(`/studio/projects/${currentProjectId}/upload`,{method:'POST',body});}
        await activateProject(currentProjectId);setStatus('saved');
    });
}
function downloadBlob(blob,name) {
    const url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function downloadZIP() {return transition(async()=>{if(!currentProjectId)throw new Error(t('chooseProject'));downloadBlob(await(await api(`/studio/projects/${currentProjectId}/export/zip`)).blob(),`Project_${currentProjectId}.zip`);});}
function downloadPDF() {if(!currentBlobUrl)return;const anchor=document.createElement('a');anchor.href=currentBlobUrl;anchor.download=`Document.${$('btn-download-pdf').dataset.extension||'pdf'}`;anchor.click();}
async function sendToTelegram() {
    $('btn-send-tg').disabled=true;
    try {await transition(async()=>{if(!currentProjectId)throw new Error(t('chooseProject'));await api(`/studio/projects/${currentProjectId}/send_telegram`,{method:'POST',timeoutMs:65000});window.mpbPopup?.(t('sent'));});}
    finally {$('btn-send-tg').disabled=false;}
}
function translateStudio() {
    setStatus(currentStatus,statusParams);updateWordCount();renderProjectList();renderFileList();updateTemplateOptions();updateJobUi();
    $('monaco-container').querySelector('textarea')?.setAttribute('aria-label',t('editor'));
    $('monaco-container').querySelector('iframe')?.setAttribute('title',t('editor'));
    if(currentMode==='project'&&currentFile()?.is_binary)setEditorContent(t('binaryFile',{name:currentFile().path}),true);
}
function bind() {
    const actions={'mode-quick':()=>switchMode('quick'),'mode-project':()=>switchMode('project'),'compile-btn':compileCurrent,
        'btn-download-zip':downloadZIP,'btn-download-pdf':downloadPDF,'btn-send-tg':sendToTelegram,
        'create-project-button':createNewProject,'cancel-create-project-button':closeCreateProjectModal,
        'submit-create-project-button':submitNewProject,'close-error-panel-button':()=>$('error-panel').classList.add('hidden'),
        'job-resume-button':pollJob,'retry-editor-button':upgradeEditor,'upload-file-button':()=>$('file-uploader').click(),'retry-studio-button':async()=>{await saveCurrentFile();await updateLivePreview();if(activeJob)await pollJob();}};
    Object.entries(actions).forEach(([id,action])=>$(id).addEventListener('click',()=>run(action)));
    $('doc-type').addEventListener('change',event=>run(()=>setLanguage(event.target.value)));
    $('project-selector').addEventListener('change',event=>run(()=>event.target.value&&openProject(event.target.value)));
    $('new-project-type').addEventListener('change',updateTemplateOptions);
    $('file-uploader').addEventListener('change',event=>run(async()=>{const files=[...event.target.files];event.target.value='';await uploadFiles(files);}));
    ['sidebar','editor','viewer'].forEach(name=>$(`tab-btn-${name}`).addEventListener('click',()=>switchMobileTab(`${name}-pane`)));
    $('mobile-tabs').addEventListener('keydown',event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        const buttons=[...$('mobile-tabs').querySelectorAll('button')].filter(button=>!button.classList.contains('hidden'));
        let index=buttons.indexOf(document.activeElement);if(index<0)return;
        event.preventDefault();index=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
        buttons[index].click();buttons[index].focus();
    });
    $('create-project-modal').addEventListener('keydown',event=>{
        if(event.key==='Escape'){event.preventDefault();closeCreateProjectModal();}
        if(event.key==='Tab'){
            const controls=[...$('create-project-modal').querySelectorAll('input,select,button')].filter(el=>!el.disabled);
            const first=controls[0],last=controls[controls.length-1];
            if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
            else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
        }
    });
    $('create-project-modal').addEventListener('click',event=>{if(event.target===$('create-project-modal'))closeCreateProjectModal();});
    const sidebar=$('sidebar-pane');
    sidebar.addEventListener('dragover',event=>event.preventDefault());
    sidebar.addEventListener('drop',event=>{event.preventDefault();run(()=>uploadFiles([...event.dataTransfer.files]));});
    window.addEventListener('resize',setupSplit);
    window.addEventListener('beforeunload',event=>{if(session?.dirty()){event.preventDefault();event.returnValue='';}});
    window.addEventListener('online',()=>run(async()=>{await saveCurrentFile();if(activeJob)await pollJob();}));
    window.addEventListener('mpb-theme-change',event=>{if(window.monaco){monaco.editor.setTheme(event.detail.isDark?'vs-dark':'vs-light');editor.getDomNode?.()?.ownerDocument.documentElement.classList.toggle('dark',event.detail.isDark);}run(updateLivePreview);});
}
async function initStudio() {
    await window.mpbI18n?.ready;
    await ensureStudioAuth();
    sessionScope=MpbStudioSession.accountScope(token);
    session=MpbStudioSession.create({storage:storage(),scope:sessionScope,
        save:async record=>{await api(`/studio/projects/${record.projectId}/files/${record.fileId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:record.content})});
            const file=projectFiles.find(item=>item.id===record.fileId);if(file)file.content=record.content;},
        onStorageError:()=>{if(!storageWarningShown){storageWarningShown=true;window.mpbPopup?.(t('storageUnavailable'),{type:'warning'});}}});
    editor=createFallbackEditor();bind();activateDocument({type:'latex',content:TEMPLATES.latex});updateModeUi();
    window.mpbI18n?.registerTranslator(translateStudio);
    activeJob=session.readValue('active-job');
    if(activeJob?.job_id){updateJobUi();run(pollJob);}
    run(upgradeEditor);
    mpbStudioLibraries.ensure('layout').then(setupSplit).catch(()=>{});
}
run(initStudio);
