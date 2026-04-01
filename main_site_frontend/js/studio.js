// main_site_frontend/js/studio.js

const API_BASE = "https://api.ivantishchenko.ru/api";
const token = localStorage.getItem('jwt_token');

// Состояние приложения
let editor = null;
let currentMode = 'quick'; // 'quick' | 'project'
let currentProjectId = null;
let currentFileId = null;
let projectFiles =[];
let splitInstance = null;
let currentBlobUrl = null; // Ссылка на скомпилированный PDF для скачивания

const TEMPLATES = {
    latex: `\\documentclass[12pt, a4paper]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T2A]{fontenc}\n\\usepackage[russian]{babel}\n\\usepackage{amsmath, amssymb, graphicx}\n\n\\begin{document}\n\\section{Введение}\nПривет, LaTeX! Формула: \\[ E = mc^2 \\]\n\\end{document}`,
    markdown: `# Live Markdown\nФормулы работают на лету: $$E = mc^2$$\n\nИзмените этот текст!`,
    mermaid: `graph TD;\n    A[Начало] --> B{Работает?};\n    B -- Да --> C[Отлично!];\n    B -- Нет --> D[Ищем баг];`
};

if (!token) {
    alert("Пожалуйста, авторизуйтесь для доступа к Студии.");
    window.location.href = '/login';
}

// === 1. ИНИЦИАЛИЗАЦИЯ ИНТЕРФЕЙСА (SPLIT.JS) ===
function setupSplit() {
    if (splitInstance) splitInstance.destroy();
    
    if (currentMode === 'project') {
        document.getElementById('sidebar-pane').classList.remove('hidden');
        splitInstance = Split(['#sidebar-pane', '#editor-pane', '#viewer-pane'], { 
            sizes: [20, 40, 40], 
            minSize:[150, 300, 300], 
            gutterSize: 6,
            cursor: 'col-resize'
        });
    } else {
        document.getElementById('sidebar-pane').classList.add('hidden');
        splitInstance = Split(['#editor-pane', '#viewer-pane'], { 
            sizes:[50, 50], 
            minSize: [300, 300], 
            gutterSize: 6,
            cursor: 'col-resize'
        });
    }
}
setupSplit();

// === 2. ИНИЦИАЛИЗАЦИЯ MONACO EDITOR И INTELLISENSE ===
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' }});
require(['vs/editor/editor.main'], function() {
    
    // Регистрируем умные сниппеты (Snippets) для LaTeX
    monaco.languages.registerCompletionItemProvider('latex', {
        provideCompletionItems: function(model, position) {
            const suggestions =[
                {
                    label: '\\begin',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: '\\begin{${1:environment}}\n\t$0\n\\end{${1:environment}}',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Вставить окружение LaTeX'
                },
                {
                    label: '\\section',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: '\\section{${1:title}}\n$0',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
                },
                {
                    label: '\\includegraphics',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: '\\includegraphics[width=${1:0.8}\\textwidth]{${2:image.png}}',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
                }
            ];
            return { suggestions: suggestions };
        }
    });

    editor = monaco.editor.create(document.getElementById('monaco-container'), {
        value: TEMPLATES.latex,
        language: 'latex',
        theme: 'vs-light',
        automaticLayout: true,
        wordWrap: 'on',
        minimap: { enabled: false },
        fontSize: 14
    });

    // Автосохранение, Live Preview и подсчет слов (Debounce)
    let timeout;
    editor.onDidChangeModelContent(() => {
        updateWordCount();
        setStatus("Unsaved", false);
        monaco.editor.setModelMarkers(editor.getModel(), 'latex',[]); // Очищаем маркеры ошибок при редактировании
        
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            if (currentMode === 'project') saveCurrentFile();
            updateLivePreview();
        }, 1000); 
    });

    // Биндим Ctrl+S
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, compileCurrent);
    
    // Инит Mermaid
    try {
        mermaid.initialize({ startOnLoad: false, theme: 'default' });
    } catch(e) {
        console.warn("Mermaid init error:", e);
    }
});

// Обновление UI Статус-бара
function setStatus(text, isSaving = false) {
    document.getElementById('status-text').innerText = text;
    document.getElementById('status-icon-saved').classList.toggle('hidden', isSaving || text !== 'Saved');
    document.getElementById('status-icon-sync').classList.toggle('hidden', !isSaving);
}

function updateWordCount() {
    if (!editor) return;
    const text = editor.getValue();
    const chars = text.length;
    const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
    document.getElementById('doc-stats').innerText = `${words} words, ${chars} chars`;
}

// === 3. ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ (QUICK / PROJECT) ===
document.getElementById('mode-quick').onclick = () => switchMode('quick');
document.getElementById('mode-project').onclick = () => switchMode('project');
document.getElementById('doc-type').addEventListener('change', (e) => setLanguage(e.target.value));

function switchMode(mode) {
    currentMode = mode;
    const btnQ = document.getElementById('mode-quick');
    const btnP = document.getElementById('mode-project');
    const typeSelect = document.getElementById('doc-type');
    const btnZip = document.getElementById('btn-download-zip');

    if (mode === 'quick') {
        btnQ.className = "px-3 py-1.5 text-sm font-medium rounded-md bg-white shadow-sm text-blue-700 transition-all";
        btnP.className = "px-3 py-1.5 text-sm font-medium rounded-md text-slate-500 hover:text-slate-800 transition-all";
        typeSelect.classList.remove('hidden');
        btnZip.classList.add('hidden');
        
        currentProjectId = null;
        currentFileId = null;
        setLanguage(typeSelect.value);
    } else {
        btnP.className = "px-3 py-1.5 text-sm font-medium rounded-md bg-white shadow-sm text-blue-700 transition-all";
        btnQ.className = "px-3 py-1.5 text-sm font-medium rounded-md text-slate-500 hover:text-slate-800 transition-all";
        typeSelect.classList.add('hidden');
        btnZip.classList.remove('hidden');
        
        loadProjects();
    }
    setupSplit();
}

function setLanguage(type) {
    if (!editor) return;
    let lang = type === 'mermaid' ? 'javascript' : type;
    monaco.editor.setModelLanguage(editor.getModel(), lang);
    
    if (currentMode === 'quick') {
        editor.setValue(TEMPLATES[type]);
    }
    
    // Скрываем PDF, если перешли на Live формат
    if (type !== 'latex') {
        document.getElementById('pdf-viewer').classList.add('hidden');
        document.getElementById('btn-download-pdf').classList.add('hidden');
    }
    updateLivePreview();
}

// === 4. LIVE PREVIEW (Markdown & Mermaid) ===
async function updateLivePreview() {
    const type = currentMode === 'quick' ? document.getElementById('doc-type').value : 'latex';
    if (type === 'latex') return; // LaTeX требует серверной сборки

    const code = editor.getValue();
    const liveDiv = document.getElementById('live-preview');
    const contentDiv = document.getElementById('live-preview-content');
    const emptyState = document.getElementById('empty-state');
    const pdfViewer = document.getElementById('pdf-viewer');

    emptyState.classList.add('hidden');
    pdfViewer.classList.add('hidden');
    liveDiv.classList.remove('hidden');

    if (type === 'markdown') {
        // Подменяем $$ формулы для KaTeX перед парсингом Markdown
        let safeCode = code.replace(/\$\$(.*?)\$\$/gs, (m, p1) => `\n<div class="math-block">${p1}</div>\n`);
        safeCode = safeCode.replace(/\$(.*?)\$/g, (m, p1) => `<span class="math-inline">${p1}</span>`);
        
        contentDiv.innerHTML = marked.parse(safeCode);
        
        // Рендерим математику
        if (typeof renderMathInElement === 'function') {
            renderMathInElement(contentDiv, {
                delimiters:[
                    {left: '<div class="math-block">', right: '</div>', display: true},
                    {left: '<span class="math-inline">', right: '</span>', display: false}
                ]
            });
        }
    } else if (type === 'mermaid') {
        try {
            const { svg } = await mermaid.render('mermaid-svg-' + Date.now(), code);
            contentDiv.innerHTML = `<div class="flex items-center justify-center h-full">${svg}</div>`;
        } catch (e) {
            contentDiv.innerHTML = `<pre class="text-red-500 text-xs p-4">${e.message}</pre>`;
        }
    }
}

// === 5. СЕРВЕРНАЯ КОМПИЛЯЦИЯ И ОШИБКИ ===
async function compileCurrent() {
    if (currentMode === 'project') await saveCurrentFile();
    
    const overlay = document.getElementById('loader-overlay');
    const errorPanel = document.getElementById('error-panel');
    const errorText = document.getElementById('error-text');
    
    if(editor) monaco.editor.setModelMarkers(editor.getModel(), 'latex',[]); // Чистим старые ошибки

    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
    errorPanel.classList.add('hidden');
    setStatus("Building...", true);

    try {
        let response;
        if (currentMode === 'quick') {
            const type = document.getElementById('doc-type').value;
            response = await fetch(`${API_BASE}/studio/compile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ type, content: editor.getValue() })
            });
        } else {
            if(!currentProjectId) throw new Error("Проект не выбран");
            response = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/compile`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
        }

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            setStatus("Saved", false);
            
            // Если вернулся PDF
            if (data.pdf) {
                document.getElementById('live-preview').classList.add('hidden');
                document.getElementById('empty-state').classList.add('hidden');
                const pdfViewer = document.getElementById('pdf-viewer');
                pdfViewer.classList.remove('hidden');

                // Конвертируем Base64 в Blob
                const byteCharacters = atob(data.pdf);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) byteNumbers[i] = byteCharacters.charCodeAt(i);
                const blob = new Blob([new Uint8Array(byteNumbers)], {type: 'application/pdf'});
                
                if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl); // Очистка старой ссылки памяти
                currentBlobUrl = URL.createObjectURL(blob);
                
                pdfViewer.src = currentBlobUrl + "#toolbar=0&view=FitH"; // Скрываем тулбар, подгоняем по ширине
                document.getElementById('btn-download-pdf').classList.remove('hidden');
            }
        } else {
            setStatus("Error", false);
            
            // Парсинг ошибок в Monaco Editor
            if (data.errors && data.errors.length > 0) {
                const markers = data.errors.map(err => ({
                    severity: monaco.MarkerSeverity.Error,
                    startLineNumber: err.line,
                    startColumn: 1,
                    endLineNumber: err.line,
                    endColumn: 1000,
                    message: err.message
                }));
                monaco.editor.setModelMarkers(editor.getModel(), 'latex', markers);
                
                errorText.innerText = data.errors.map(e => `Line ${e.line}: ${e.message}`).join('\n');
            } else {
                errorText.innerText = data.message || data.error || "Compilation failed";
            }
            errorPanel.classList.remove('hidden');
        }

    } catch (err) {
        setStatus("Error", false);
        errorText.innerText = "Server error: " + err.message;
        errorPanel.classList.remove('hidden');
    } finally {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }
}


// === 6. PROJECT CRUD & FILE SYSTEM ===
async function loadProjects() {
    const res = await fetch(`${API_BASE}/studio/projects`, { headers: { 'Authorization': `Bearer ${token}` } });
    if (!res.ok) return;
    
    const projects = await res.json();
    const selector = document.getElementById('project-selector');
    
    selector.innerHTML = '<option value="" disabled selected>-- Выберите проект --</option>';
    projects.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id; 
        opt.text = p.name; 
        selector.appendChild(opt);
    });

    if(projects.length > 0) {
        selector.value = projects[0].id;
        openProject(projects[0].id);
    }
}

async function createNewProject() {
    const name = prompt("Название нового проекта:");
    if (!name) return;
    
    const res = await fetch(`${API_BASE}/studio/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ name: name, project_type: 'latex' })
    });
    if (res.ok) await loadProjects();
}

async function openProject(id) {
    currentProjectId = id;
    document.getElementById('empty-state').classList.remove('hidden');
    document.getElementById('pdf-viewer').classList.add('hidden');
    document.getElementById('btn-download-pdf').classList.add('hidden');

    const res = await fetch(`${API_BASE}/studio/projects/${id}`, { headers: { 'Authorization': `Bearer ${token}` } });
    projectFiles = await res.json();
    
    renderFileList();

    const mainFile = projectFiles.find(f => f.is_main);
    if (mainFile) openFile(mainFile.id);
}

// Рендеринг дерева файлов (с иконками и кнопками Rename/Delete)
function renderFileList() {
    const list = document.getElementById('file-list');
    list.innerHTML = '';
    
    projectFiles.forEach(f => {
        const div = document.createElement('div');
        div.className = `file-item group px-3 py-1.5 text-sm text-slate-700 cursor-pointer hover:bg-slate-200 transition-colors flex items-center justify-between border-l-[3px] border-transparent`;
        if (f.id === currentFileId) div.classList.add('active');
        
        let icon = f.is_binary ? '🖼️' : (f.path.endsWith('.tex') ? '✍️' : '📄');
        
        const nameDiv = document.createElement('div');
        nameDiv.className = "flex items-center gap-2 truncate";
        nameDiv.innerHTML = `<span>${icon}</span> <span class="truncate" title="${f.path}">${f.path}</span>`;
        nameDiv.onclick = () => openFile(f.id);
        
        const actionsDiv = document.createElement('div');
        actionsDiv.className = "hidden group-hover:flex items-center gap-2 opacity-50 hover:opacity-100";
        
        if (!f.is_main) {
            const btnRename = document.createElement('button');
            btnRename.innerHTML = '✏️';
            btnRename.className = "hover:scale-125 transition-transform text-xs";
            btnRename.title = "Переименовать";
            btnRename.onclick = (e) => { e.stopPropagation(); renameFile(f.id, f.path); };
            
            const btnDelete = document.createElement('button');
            btnDelete.innerHTML = '❌';
            btnDelete.className = "hover:scale-125 transition-transform text-xs";
            btnDelete.title = "Удалить";
            btnDelete.onclick = (e) => { e.stopPropagation(); deleteFile(f.id, f.path); };
            
            actionsDiv.appendChild(btnRename);
            actionsDiv.appendChild(btnDelete);
        }

        div.appendChild(nameDiv);
        div.appendChild(actionsDiv);
        list.appendChild(div);
    });
}

async function openFile(id) {
    if (currentFileId !== null) await saveCurrentFile();
    
    const file = projectFiles.find(f => f.id === id);
    if (!file) return;

    currentFileId = id;
    renderFileList(); // Обновляем выделение в Sidebar

    if (file.is_binary) {
        editor.setValue(`% Это бинарный файл (${file.path}).\n% Используйте \\includegraphics{${file.path}} в коде.`);
        monaco.editor.setModelLanguage(editor.getModel(), 'plaintext');
        editor.updateOptions({ readOnly: true });
    } else {
        editor.updateOptions({ readOnly: false });
        let ext = file.path.split('.').pop().toLowerCase();
        let langMap = { 'tex': 'latex', 'md': 'markdown', 'sty': 'latex' };
        monaco.editor.setModelLanguage(editor.getModel(), langMap[ext] || 'plaintext');
        editor.setValue(file.content || "");
    }
}

async function saveCurrentFile() {
    if (!currentFileId || !currentProjectId) return;
    const file = projectFiles.find(f => f.id === currentFileId);
    
    if (file && !file.is_binary) {
        const newContent = editor.getValue();
        if (newContent !== file.content) {
            setStatus("Saving...", true);
            const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/files/${currentFileId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ content: newContent })
            });
            if(res.ok) {
                file.content = newContent;
                setStatus("Saved", false);
            }
        }
    }
}

async function renameFile(fileId, oldPath) {
    const newName = prompt(`Новое имя для файла ${oldPath}:`, oldPath);
    if (!newName || newName === oldPath) return;

    const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/files/${fileId}/rename`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ new_name: newName })
    });
    if (res.ok) await openProject(currentProjectId);
    else alert("Ошибка переименования. Возможно имя занято.");
}

async function deleteFile(fileId, path) {
    if (!confirm(`Удалить файл ${path}? Это действие необратимо.`)) return;

    const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/files/${fileId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
        if (currentFileId === fileId) currentFileId = null; // Сбрасываем если удалили открытый
        await openProject(currentProjectId);
    } else {
        alert("Ошибка удаления файла.");
    }
}


// === 7. DRAG & DROP ДЛЯ ЗАГРУЗКИ АССЕТОВ ===
const sidebar = document.getElementById('sidebar-pane');

sidebar.addEventListener('dragover', (e) => {
    e.preventDefault();
    sidebar.classList.add('bg-blue-50', 'border-blue-300');
});
sidebar.addEventListener('dragleave', (e) => {
    e.preventDefault();
    sidebar.classList.remove('bg-blue-50', 'border-blue-300');
});
sidebar.addEventListener('drop', async (e) => {
    e.preventDefault();
    sidebar.classList.remove('bg-blue-50', 'border-blue-300');
    
    if (!currentProjectId) { alert("Сначала откройте проект для загрузки файлов."); return; }
    
    const files = e.dataTransfer.files;
    for (let f of files) {
        await uploadSingleFile(f);
    }
});

// Обработчик скрытого input type="file"
async function uploadAsset(event) {
    if (!currentProjectId) return;
    const files = event.target.files;
    for (let f of files) {
        await uploadSingleFile(f);
    }
    event.target.value = ''; // Сброс
}

async function uploadSingleFile(file) {
    setStatus("Uploading...", true);
    const formData = new FormData(); 
    formData.append('file', file);
    
    const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });
    
    if (res.ok) {
        await openProject(currentProjectId); 
        setStatus("Saved", false);
    } else {
        alert(`Ошибка загрузки ${file.name}`);
        setStatus("Error", false);
    }
}


// === 8. ФУНКЦИИ ЭКСПОРТА (PDF & ZIP) ===
function downloadPDF() {
    if (!currentBlobUrl) return;
    const a = document.createElement('a');
    a.href = currentBlobUrl;
    a.download = `Document_${new Date().getTime()}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function downloadZIP() {
    if (!currentProjectId) return;
    
    setStatus("Zipping...", true);
    fetch(`${API_BASE}/studio/projects/${currentProjectId}/export/zip`, {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => {
        if(!res.ok) throw new Error("API Error");
        return res.blob();
    })
    .then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `Project_${currentProjectId}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setStatus("Saved", false);
    })
    .catch(err => {
        alert("Ошибка выгрузки ZIP архива");
        setStatus("Error", false);
    });
}