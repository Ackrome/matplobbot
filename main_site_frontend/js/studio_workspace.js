/* Studio workflow UI; uses the authenticated transport/session owned by studio.js. */
window.MpbStudioUX = (() => {
    const tr=(key,params={})=>window.MpbUI.t(key,params);
    const button=(text,action,kind='')=>{const el=document.createElement('button');el.type='button';el.className=`ui-button ${kind}`;if(typeof text==='object'){el.dataset.i18n='ux.'+text.key;el.textContent=tr(text.key);}else el.textContent=text;el.addEventListener('click',()=>run(async()=>{el.disabled=true;try{await action();}catch(error){const dialog=[...document.querySelectorAll('dialog[open]')].at(-1);if(!dialog)throw error;let status=dialog.querySelector('.dialog-error');if(!status){status=document.createElement('p');status.className='dialog-error plan-field-error';status.setAttribute('role','alert');dialog.querySelector('h2').after(status);}status.textContent=error.message||t('requestFailed');}finally{el.disabled=false;}}));return el;};
    function modalButton(id, key, action) {
        const trigger = document.createElement('button');
        trigger.id = id;
        trigger.type = 'button';
        trigger.className = 'ui-button';
        trigger.dataset.i18n = `ux.${key}`;
        trigger.textContent = tr(key);
        let open = false;
        trigger.addEventListener('click', () => run(async () => {
            if (open) return;
            open = true;
            try { await action(); }
            finally { open = false; }
        }));
        return trigger;
    }
    let importDraft=null,uploadQueue=[],uploadBusy=false,uploadProjectId=null;
    function filename(){return (projectsList.find(p=>String(p.id)===String(currentProjectId))?.name||editor.getValue().match(/(?:^# |\\(?:title|section)\{)([^\n}]+)/)?.[1]||tr('document')).replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').trim().slice(0,100)||'document';}
    function init(){
        const toolbar=document.createElement('div');toolbar.className='studio-workflow-toolbar';toolbar.id='studio-workflow-toolbar';
        const autosave=document.createElement('span');autosave.className='ui-muted';autosave.dataset.i18n='ux.autosave';autosave.textContent=tr('autosave');toolbar.append(autosave);
        const save=button({key:'saveAsProject'},()=>{const draft={content:editor.getValue(),type:$('doc-type').value};createNewProject();importDraft=draft;$('new-project-type').value=importDraft.type;$('new-project-type').disabled=true;$('template-container').hidden=true;updateTemplateOptions();});save.id='save-as-project';toolbar.append(save);
        toolbar.append(button({key:'manageProjects'},manageProjects),button({key:'buildHistory'},history));
        toolbar.insertBefore(modalButton('project-versions-button', 'projectVersions', manageVersions), toolbar.lastElementChild);
        toolbar.append(modalButton('import-studio-zip', 'studioZipImport', importZIP));
        for(const id of ['btn-download-pdf','btn-download-zip','btn-send-tg']){const el=$(id);el.classList.add('ui-button');el.replaceChildren();const label=document.createElement('span');label.dataset.i18n=id==='btn-download-pdf'?'studio.downloadResult':id==='btn-download-zip'?'studio.downloadZip':'studio.send';label.textContent=window.mpbI18n.t(label.dataset.i18n);el.append(label);toolbar.append(el);}
        $('navbar').after(toolbar);

        const hint=document.createElement('p');hint.className='ui-muted studio-upload-hint';hint.dataset.i18n='ux.uploadHint';hint.textContent=tr('uploadHint');$('file-list').before(hint);const queue=document.createElement('div');queue.id='studio-upload-list';queue.setAttribute('aria-live','polite');$('file-list').before(queue);
        $('job-panel').append(button({key:'cancelBuild'},cancelJob));
        const preview=document.createElement('div');preview.id='template-preview';$('new-project-template').after(preview);$('new-project-template').addEventListener('change',templatePreview);
        $('empty-state').querySelector('p').dataset.i18n='ux.previewHint';$('empty-state').querySelector('p').textContent=tr('previewHint');$('empty-state').append(button({key:'buildNow'},compileCurrent,'primary'));
        $('create-project-button').textContent=tr('newProject');
        $('error-text').before(Object.assign(document.createElement('div'),{id:'studio-error-links'}));
    }
    function mode(){
        if ($('save-as-project')) $('save-as-project').hidden = currentMode !== 'quick';
        const versions = $('project-versions-button');
        if (versions) {
            versions.hidden = currentMode !== 'project';
            versions.disabled = !currentProjectId;
        }
    }
    function resetCreate(){importDraft=null;$('new-project-type').disabled=false;$('template-container').hidden=false;}
    function draft(){return importDraft;}
    function importZIP() {
        const content = document.createElement('div');
        content.className = 'ui-stack';
        const pick = document.createElement('input');
        pick.type = 'file';
        pick.accept = '.zip,application/zip';
        pick.hidden = true;
        const choose = document.createElement('button');
        choose.type = 'button';
        choose.className = 'ui-button';
        choose.textContent = tr('studioZipFile');
        choose.addEventListener('click', () => pick.click());
        const filename = document.createElement('span');
        filename.className = 'ui-muted';
        filename.setAttribute('role', 'status');
        filename.textContent = tr('studioZipNoFile');
        const picker = document.createElement('div');
        picker.className = 'studio-archive-picker';
        picker.append(pick, choose, filename);
        const inspect = document.createElement('button');
        inspect.className = 'ui-button';
        inspect.type = 'button';
        inspect.textContent = tr('studioZipPreview');
        inspect.disabled = true;
        const status = document.createElement('p');
        status.setAttribute('role', 'status');
        status.hidden = true;
        const form = document.createElement('form');
        form.className = 'ui-stack';
        form.hidden = true;
        const name = document.createElement('input');
        name.required = true;
        name.maxLength = 160;
        const projectType = document.createElement('select');
        projectType.required = true;
        projectType.replaceChildren(new Option(tr('studioZipChooseType'), ''), ...['LaTeX','Markdown','Mermaid'].map(label=>new Option(label,label.toLowerCase())));
        const main = document.createElement('select');
        main.required = true;
        const inventory = document.createElement('ul');
        inventory.className = 'studio-archive-inventory ui-muted';
        inventory.tabIndex = 0;
        const commit = document.createElement('button');
        commit.type = 'submit';
        commit.className = 'ui-button primary';
        commit.textContent = tr('studioZipCreateCopy');
        const legacy = document.createElement('p');
        legacy.className = 'ui-muted';
        legacy.textContent = tr('studioZipLegacy');
        let loaded, saving = false;

        function field(input, labelText) {
            input.className = 'ui-input';
            const label = document.createElement('label');
            label.append(labelText, input);
            return label;
        }
        function showStatus(message, error = false) {
            status.className = error ? 'plan-field-error' : 'ui-muted';
            status.textContent = message;
            status.hidden = !message;
        }
        function archiveMessage(error) {
            if (/^archive_(?:invalid|bad_files|manifest_invalid|too_large|no_main|preview_required|bad_name|quota)$/.test(error.code || '')) return tr(`studioZipError.${error.code}`);
            if (error.status === 413) return tr('studioZipError.archive_too_large');
            return error.message;
        }
        form.append(field(name, t('projectName')), field(projectType, t('projectType')), field(main, tr('studioZipMain')), legacy, inventory, commit);
        content.append(picker, inspect, status, form);

        pick.addEventListener('change', () => {
            loaded = null;
            form.hidden = true;
            inspect.disabled = !pick.files.length;
            filename.textContent = pick.files[0]?.name || tr('studioZipNoFile');
            showStatus('');
        });
        inspect.addEventListener('click', async () => {
            const file = pick.files[0];
            if (!file) return;
            inspect.disabled = true;
            loaded = null;
            form.hidden = true;
            showStatus('');
            try {
                const body = new FormData();
                body.append('file', file);
                const preview = await (await api('/studio/projects/import/preview', {method:'POST',body,timeoutMs:60000})).json();
                if (pick.files[0] !== file) return;
                loaded = {file, preview};
                name.value = preview.name;
                projectType.value = preview.type || '';
                projectType.disabled = preview.manifest;
                main.replaceChildren(new Option(tr('studioZipChooseMain'), ''), ...preview.files.filter(entry=>!entry.is_binary).map(entry=>new Option(entry.path,entry.path)));
                main.value = preview.main || '';
                main.disabled = Boolean(preview.manifest && preview.main);
                legacy.hidden = preview.manifest;
                inventory.replaceChildren(...preview.files.map(entry => {
                    const row = document.createElement('li');
                    row.textContent = entry.is_binary ? `${entry.path} · ${tr('projectVersionBinaryFile')}` : entry.path;
                    return row;
                }));
                form.hidden = false;
                name.focus();
            } catch (error) {
                if (pick.files[0] === file) showStatus(archiveMessage(error), true);
            } finally { inspect.disabled = !pick.files.length; }
        });
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (!loaded || saving || !name.value.trim()) return;
            const body = new FormData();
            body.append('file', loaded.file);
            body.append('preview_token', loaded.preview.preview_token);
            body.append('name', name.value.trim());
            body.append('project_type', projectType.value);
            body.append('main', main.value);
            saving = commit.disabled = pick.disabled = choose.disabled = inspect.disabled = true;
            showStatus('');
            try {
                await transition(async () => {
                    const created = await (await api('/studio/projects/import', {method:'POST',body,timeoutMs:60000})).json();
                    content.closest('dialog')?.close();
                    window.mpbPopup?.(tr('studioZipCreated'));
                    await loadProjects();
                    await activateProject(created.id);
                    updateModeUi();
                });
            } catch (error) { showStatus(archiveMessage(error), true); }
            finally { saving = commit.disabled = pick.disabled = choose.disabled = inspect.disabled = false; }
        });
        const closed = MpbUI.dialog({title:tr('studioZipImport'),content,actions:[{label:tr('close'),value:'close',validate:()=>!saving}]});
        content.closest('dialog')?.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
        return closed;
    }
    function templatePreview(){const el=$('template-preview');if(!el)return;const id=$('new-project-template').value;el.replaceChildren();el.className='template-preview '+(id==='latex_beamer'?'template-slide':'');const page=document.createElement('div');page.className='template-paper';const h=document.createElement('h3');h.textContent=tr('templateTitle.'+id);const p=document.createElement('p');p.textContent=tr('templateDescription.'+id);const lines=document.createElement('div');lines.className='template-lines';lines.setAttribute('aria-hidden','true');page.append(h,lines);el.append(page,p);}
    async function manageProjects(){
        await transition(loadProjects);const content=document.createElement('div');content.className='ui-stack';const search=document.createElement('input');search.type='search';search.className='ui-input';search.placeholder=tr('projectSearch');search.setAttribute('aria-label',tr('projectSearch'));const list=document.createElement('div');list.className='project-manager-list';content.append(search,button({key:'newProject'},()=>{document.querySelector('dialog[open]')?.close();createNewProject();},'primary'),list);
        const render=()=>{list.replaceChildren();const matches=projectsList.filter(p=>p.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));if(!matches.length){const p=document.createElement('p');p.className='ui-muted';p.textContent=tr('noProjects');list.append(p);}for(const project of matches){const row=document.createElement('section');row.className='project-manager-row';const open=button(project.name,async()=>{await openProject(project.id);updateModeUi();document.querySelector('dialog[open]')?.close();});open.classList.add('project-open');const meta=document.createElement('p');meta.className='ui-muted';meta.textContent=project.type;const actions=document.createElement('div');actions.className='ui-row';
            actions.append(button({key:'rename'},async()=>{const name=await MpbUI.prompt(tr('renameProject'),project.name);if(!name)return;await api(`/studio/projects/${project.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});await loadProjects();render();}),button({key:'duplicate'},async()=>{const name=await MpbUI.prompt(tr('duplicateProject'),`${project.name} — ${tr('copyName')}`);if(!name)return;await transition(async()=>{await api(`/studio/projects/${project.id}/duplicate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});await loadProjects();});render();}),button({key:'delete'},async()=>{if(!await MpbUI.confirm(tr('deleteProject'),tr('deleteProjectMessage',{name:project.name})))return;await transition(async()=>{await api(`/studio/projects/${project.id}`,{method:'DELETE'});await loadProjects();if(String(currentProjectId)===String(project.id)){currentProjectId=currentFileId=null;projectFiles=[];session.open({type:'empty',content:''});setEditorContent('',true);resetPreview();renderFileList();}});render();},'danger'));row.append(open,meta,actions);list.append(row);}};search.addEventListener('input',render);render();await MpbUI.dialog({title:tr('manageProjects'),content,actions:[{label:tr('close'),value:'close'}]});
    }
    function versionMutation(path, method, name) {
        return api(path, {
            method, headers:{'Content-Type':'application/json'}, body:JSON.stringify({name}),
        }).catch(error => {
            if (/^version_(?:name_taken|project_too_large|quota|restore_quota)$/.test(error.code || '')) {
                error.message = tr(`projectVersionError.${error.code}`);
            }
            throw error;
        });
    }
    async function manageVersions() {
        const projectId = currentProjectId;
        if (!projectId) throw new Error(t('chooseProject'));
        const base = `/studio/projects/${projectId}/versions`;
        const content = document.createElement('div');
        content.className = 'ui-stack';
        const hint = document.createElement('p');
        hint.className = 'ui-muted';
        hint.textContent = tr('projectVersionsHint');
        const form = document.createElement('form');
        form.className = 'studio-version-form';
        const name = document.createElement('input');
        name.className = 'ui-input';
        name.required = true;
        name.maxLength = 120;
        name.placeholder = tr('projectVersionName');
        name.setAttribute('aria-label', name.placeholder);
        const save = document.createElement('button');
        save.className = 'ui-button primary';
        save.type = 'submit';
        save.textContent = tr('saveProjectVersion');
        const status = document.createElement('p');
        status.setAttribute('role', 'status');
        status.hidden = true;
        const list = document.createElement('div');
        list.className = 'project-manager-list';
        form.append(name, save);
        content.append(hint, form, status, list);

        async function renderVersions() {
            const versions = await (await api(base, {cache:'no-store'})).json();
            list.replaceChildren();
            if (!versions.length) {
                const empty = document.createElement('p');
                empty.className = 'ui-muted';
                empty.textContent = tr('noProjectVersions');
                list.append(empty);
            }
            for (const version of versions) {
                const path = `${base}/${version.id}`;
                const row = document.createElement('section');
                row.className = 'project-manager-row break-words';
                const title = document.createElement('strong');
                title.textContent = version.name;
                const info = document.createElement('p');
                info.className = 'ui-muted';
                const created = document.createElement('time');
                created.dateTime = version.created_at;
                created.textContent = new Intl.DateTimeFormat(window.mpbI18n.getLanguage(), {
                    dateStyle:'medium',timeStyle:'short',
                }).format(new Date(version.created_at));
                info.append(created, ` · ${tr('projectVersionFiles', {count:version.file_count})}`);
                const files = document.createElement('details');
                const fileLabel = document.createElement('summary');
                fileLabel.textContent = tr('projectVersionFileList');
                const names = document.createElement('ul');
                names.className = 'ui-muted';
                files.append(fileLabel, names);
                files.addEventListener('toggle', async () => {
                    if (!files.open || files.dataset.loading) return;
                    files.dataset.loading = 'true';
                    try {
                        const detail = await (await api(path, {cache:'no-store'})).json();
                        names.replaceChildren(...detail.files.map(file => {
                            const entry = document.createElement('li');
                            entry.textContent = [file.path, file.is_main && tr('projectVersionMainFile'), file.is_binary && tr('projectVersionBinaryFile')].filter(Boolean).join(' · ');
                            return entry;
                        }));
                    } catch (error) {
                        delete files.dataset.loading;
                        updateVersionStatus(error.message, true);
                    }
                });
                const actions = document.createElement('div');
                actions.className = 'ui-row';
                actions.append(button({key:'restoreProjectVersion'}, async () => {
                    const copyName = await MpbUI.prompt(tr('restoreProjectVersionName'), `${version.project_name} — ${version.name}`.slice(0,160));
                    if (!copyName) return;
                    await transition(async () => {
                        const restored = await (await versionMutation(`${path}/restore`, 'POST', copyName)).json();
                        content.closest('dialog')?.close();
                        window.mpbPopup?.(tr('projectVersionRestored'));
                        await loadProjects();
                        await activateProject(restored.id);
                        updateModeUi();
                    });
                }), button({key:'deleteProjectVersion'}, async () => {
                    if (!await MpbUI.confirm(tr('deleteProjectVersion'), tr('deleteProjectVersionMessage', {name:version.name}))) return;
                    await api(path, {method:'DELETE'});
                    await renderVersions();
                    name.focus();
                }, 'danger'));
                row.append(title, info, files, actions);
                list.append(row);
            }
        }

        function updateVersionStatus(message, error = false) {
            status.textContent = message;
            status.className = error ? 'plan-field-error' : 'ui-muted';
            status.hidden = false;
        }
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const value = name.value.trim();
            if (!value || save.disabled) return;
            save.disabled = true;
            try {
                await transition(async () => {
                    await versionMutation(base, 'POST', value);
                    name.value = '';
                    updateVersionStatus(tr('projectVersionSaved'));
                    await renderVersions();
                });
            } catch (error) { updateVersionStatus(error.message, true); }
            finally { save.disabled = false; }
        });
        await renderVersions();
        await MpbUI.dialog({title:tr('projectVersions'),content,actions:[{label:tr('close'),value:'close'}]});
    }
    function draftPreview({content, baseContent}) {
        const base = typeof baseContent === 'string' ? baseContent : '';
        let start = 0;
        while (start < content.length && content[start] === base[start]) start++;
        start = Math.max(0, start - 30);
        const end = start + 240;
        return content ? `${start ? '…' : ''}${content.slice(start, end)}${end < content.length ? '…' : ''}` : tr('emptyDraftPreview');
    }
    async function chooseDraft(drafts) {
        const content = document.createElement('div');
        content.className = 'ui-stack';
        const hint = document.createElement('p');
        hint.className = 'ui-muted';
        hint.textContent = tr('restoreDraftsHint');
        const choices = document.createElement('div');
        choices.className = 'studio-draft-options';
        choices.setAttribute('role', 'radiogroup');
        choices.setAttribute('aria-label', tr('restoreDraftsTitle'));
        for (const [index, draft] of drafts.entries()) {
            const option = document.createElement('label');
            option.className = 'studio-draft-option';
            const input = document.createElement('input');
            input.type = 'radio';
            input.name = 'studio-draft';
            input.value = String(index);
            input.checked = index === 0;
            const body = document.createElement('span');
            body.className = 'studio-draft-summary';
            const heading = document.createElement('strong');
            heading.textContent = tr('draftLabel', {number:index + 1});
            body.append(heading);
            const updated = new Date(draft.updatedAt);
            if (draft.updatedAt && Number.isFinite(updated.valueOf())) {
                const time = document.createElement('time');
                time.dateTime = updated.toISOString();
                time.textContent = new Intl.DateTimeFormat(window.mpbI18n.getLanguage(), {
                    dateStyle:'medium', timeStyle:'medium',
                }).format(updated);
                body.append(time);
            }
            const preview = document.createElement('span');
            preview.className = 'studio-draft-preview';
            preview.textContent = draftPreview(draft);
            body.append(preview);
            option.append(input, body);
            choices.append(option);
        }
        content.append(hint, choices);
        const answer = await MpbUI.dialog({title:tr('restoreDraftsTitle'), content, actions:[
            {label:tr('openWithoutDraft'), value:'server'},
            {label:tr('restoreDraft'), value:'restore', primary:true},
        ]});
        return answer === 'restore' ? Number(choices.querySelector(':checked').value) : -1;
    }
    async function conflict(record) {
        const content = document.createElement('div');
        content.className = 'ui-stack';
        const hint = document.createElement('p');
        hint.className = 'ui-muted';
        hint.textContent = tr('conflictHint') + (record.draftUpdatedAt
            ? ' ' + new Date(record.draftUpdatedAt).toLocaleString(window.mpbI18n.getLanguage()) : '');
        content.append(hint);
        const grid = document.createElement('div');
        grid.className = 'conflict-grid';
        const localLines = record.draftContent.split('\n');
        const serverLines = record.serverContent.split('\n');
        for (const [label, lines, other] of [
            [tr('localVersion'), localLines, serverLines],
            [tr('serverVersion'), serverLines, localLines],
        ]) {
            const section = document.createElement('section');
            const title = document.createElement('h3');
            const pre = document.createElement('pre');
            title.textContent = label;
            pre.tabIndex = 0;
            pre.setAttribute('aria-label', label);
            for (const [i, text] of lines.entries()) {
                const line = document.createElement('span');
                line.className = 'diff-line' + (text !== other[i] ? ' diff-changed' : '');
                line.textContent = `${i + 1}  ${text}`;
                pre.append(line);
            }
            section.append(title, pre);
            grid.append(section);
        }
        content.append(grid, button({key:'downloadBoth'}, () => MpbArchive.download(MpbArchive.zip([
            {name:'local.txt', text:record.draftContent}, {name:'server.txt', text:record.serverContent},
        ]), 'document-versions.zip')));
        const choice = await MpbUI.dialog({title:tr('conflictTitle'), content, actions:[
            {label:tr('decideLater'), value:'later'},
            {label:tr('useServer'), value:'server'},
            {label:tr('useLocal'), value:'local', primary:true},
        ]});
        if (choice !== 'server' && choice !== 'local') throw new Error(tr('resolveConflict'));
        return choice === 'local';
    }
    async function hash(content){const value=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(content));return Array.from(new Uint8Array(value),b=>b.toString(16).padStart(2,'0')).join('');}
    function remember(job){const entries=session.readValue('job-history')||[];const item={job_id:job.job_id,status:job.status,created_at:job.created_at||new Date().toISOString(),expires_at:job.expires_at,projectId:job.projectId,name:job.name||filename(),fingerprint:job.fingerprint||job.source_fingerprint};const next=[item,...entries.filter(i=>i.job_id!==job.job_id&&Date.parse(i.expires_at)>Date.now())].slice(0,20);session.storeValue('job-history',next);}
    async function history(){const content=document.createElement('div');content.className='ui-stack';const hint=document.createElement('p');hint.className='ui-muted';hint.textContent=tr('historyHint');content.append(hint);const entries=(session.readValue('job-history')||[]).filter(i=>Date.parse(i.expires_at)>Date.now());if(!entries.length){const p=document.createElement('p');p.textContent=tr('noBuilds');content.append(p);}for(const job of entries){const row=document.createElement('section');row.className='project-manager-row';const title=document.createElement('strong');title.textContent=job.name;const info=document.createElement('p');info.className='ui-muted';info.textContent=`${new Date(job.created_at).toLocaleString(window.mpbI18n.getLanguage())} · ${t('job.'+job.status)} · ${tr('version')} ${(job.fingerprint||'').slice(0,10)}`;const result=button({key:'getBuild'},async()=>{const data=await(await api('/studio/jobs/'+job.job_id)).json();info.textContent=`${new Date(job.created_at).toLocaleString(window.mpbI18n.getLanguage())} · ${t('job.'+data.status)} · ${tr('version')} ${(job.fingerprint||'').slice(0,10)}`;remember({...job,status:data.status});if(data.status==='success'){const artifact=data.result.pdf||data.result.image;if(!artifact)throw new Error(t('invalidResponse'));MpbArchive.download(new Blob([Uint8Array.from(atob(artifact),c=>c.charCodeAt(0))],{type:data.result.pdf?'application/pdf':'image/png'}),`${MpbArchive.safePath(job.name).replaceAll('/','_')}-${job.created_at.slice(0,10)}.${data.result.pdf?'pdf':'png'}`);}else if(data.status==='error'){info.textContent+=' · '+(data.error||t('buildFailed'));}});row.append(title,info,result);content.append(row);}await MpbUI.dialog({title:tr('buildHistory'),content,actions:[{label:tr('close'),value:'close'}]});}
    async function cancelJob(){if(!activeJob)return;const id=activeJob.job_id;const response=await(await api(`/studio/jobs/${id}/cancel`,{method:'POST'})).json();if(activeJob?.job_id===id){activeJob.status=response.status;session.storeValue('active-job',activeJob);updateJobUi();if(!jobPolling)await pollJob();}}
    function errorLinks(errors,job){const list=$('studio-error-links');list.replaceChildren();for(const error of errors){const path=error.file||error.filename||error.path;const file=projectFiles.find(f=>f.path===path)||(String(job.fileId)===String(currentFileId)?currentFile():null);const line=Math.max(1,Number(error.line)||1);list.append(button(`${file?.path||path||tr('document')}:${line} — ${error.message||t('buildFailed')}`,async()=>{if(job.projectId&&String(job.projectId)!==String(currentProjectId)){await openProject(job.projectId);updateModeUi();}const target=projectFiles.find(f=>f.path===path)||projectFiles.find(f=>f.id===job.fileId)||projectFiles.find(f=>f.is_main);if(target)await openFile(target.id);if(innerWidth<768)switchMobileTab('editor-pane');if(editor.revealLineInCenter){editor.revealLineInCenter(line);editor.setPosition({lineNumber:line,column:1});editor.focus();}else{const area=$('monaco-container').querySelector('textarea');if(area){const pos=area.value.split('\n').slice(0,line-1).join('\n').length+(line>1?1:0);area.focus();area.setSelectionRange(pos,pos);}}}));}}
    function renderUploads(){const list=$('studio-upload-list');list.replaceChildren();const target=document.createElement('p');target.className='ui-muted studio-upload-hint';target.textContent=tr('uploadProject',{name:projectsList.find(p=>String(p.id)===String(uploadProjectId))?.name||String(uploadProjectId)});list.append(target);const done=uploadQueue.filter(x=>x.state==='success').length;const progress=document.createElement('progress');progress.max=uploadQueue.length||1;progress.value=done;progress.setAttribute('aria-label',tr('uploadProgress',{done,total:uploadQueue.length}));list.append(progress);for(const item of uploadQueue){const row=document.createElement('div');row.className='upload-row';const span=document.createElement('span');span.textContent=`${item.file.name} · ${tr('upload.'+item.state)}`;row.append(span);if(item.state==='error')row.append(button({key:'retry'},()=>performUploads()));list.append(row);}}
    async function performUploads(){if(uploadBusy)return;uploadBusy=true;try{await transition(async()=>{const projectId=uploadProjectId;for(const item of uploadQueue.filter(i=>i.state==='queued'||i.state==='error')){if(item.file.size>5*1024*1024){item.state='large';renderUploads();continue;}item.state='uploading';renderUploads();try{const body=new FormData();body.append('file',item.file);await api(`/studio/projects/${projectId}/upload`,{method:'POST',body});item.state='success';}catch{item.state='error';}renderUploads();}if(String(currentProjectId)===String(projectId))await activateProject(projectId);setStatus('saved');});}finally{uploadBusy=false;}}
    async function upload(files){if(!currentProjectId)throw new Error(t('chooseProject'));if(uploadBusy)throw new Error(tr('uploadWait'));uploadProjectId=currentProjectId;uploadQueue=files.map(file=>({file,state:'queued'}));renderUploads();await performUploads();}
    return {init,mode,filename,resetCreate,draft,templatePreview,manageProjects,chooseDraft,conflict,hash,remember,errorLinks,upload};
})();
