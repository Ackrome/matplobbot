const API_BASE = "https://api.ivantishchenko.ru/api";
const token = localStorage.getItem('jwt_token');

let editor = null;
let currentMode = 'quick'; // 'quick' | 'project'
let currentProjectId = null;
let currentFileId = null;
let projectFiles =[];
let splitInstance = null;

const TEMPLATES = {
    latex: `\\documentclass{article}\n\\begin{document}\nПривет, LaTeX!\n\\end{document}`,
    markdown: `# Live Markdown\nФормулы работают на лету: $$E = mc^2$$\n\nИзмените этот текст!`,
    mermaid: `graph TD;\n    A-->B;`
};

if (!token) window.location.href = '/login';

// 1. Инициализация Split.js
function setupSplit() {
    if (splitInstance) splitInstance.destroy();
    if (currentMode === 'project') {
        document.getElementById('sidebar-pane').classList.remove('hidden');
        splitInstance = Split(['#sidebar-pane', '#editor-pane', '#viewer-pane'], { sizes:[20, 40, 40], minSize: [150, 300, 300], gutterSize: 6 });
    } else {
        document.getElementById('sidebar-pane').classList.add('hidden');
        splitInstance = Split(['#editor-pane', '#viewer-pane'], { sizes:[50, 50], minSize: [300, 300], gutterSize: 6 });
    }
}
setupSplit();

// 2. Инициализация Monaco
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' }});
require(['vs/editor/editor.main'], function() {
    editor = monaco.editor.create(document.getElementById('monaco-container'), {
        value: TEMPLATES.latex,
        language: 'latex',
        theme: 'vs-light',
        automaticLayout: true,
        wordWrap: 'on',
        minimap: { enabled: false }
    });

    // Дебаунс для Live Preview
    let timeout;
    editor.onDidChangeModelContent(() => {
        clearTimeout(timeout);
        timeout = setTimeout(updateLivePreview, 500); // 500ms после остановки печати
        
        // Очищаем маркеры ошибок при редактировании
        monaco.editor.setModelMarkers(editor.getModel(), 'latex',[]);
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, compileCurrent);
    
    // Инит Mermaid
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
});

// --- ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ ---
document.getElementById('mode-quick').onclick = () => switchMode('quick');
document.getElementById('mode-project').onclick = () => switchMode('project');

function switchMode(mode) {
    currentMode = mode;
    const btnQ = document.getElementById('mode-quick');
    const btnP = document.getElementById('mode-project');
    const typeSelect = document.getElementById('doc-type');

    if (mode === 'quick') {
        btnQ.className = "px-3 py-1.5 text-sm font-medium rounded-md bg-white shadow-sm text-blue-700";
        btnP.className = "px-3 py-1.5 text-sm font-medium rounded-md text-slate-500 hover:text-slate-800";
        typeSelect.classList.remove('hidden');
        
        currentProjectId = null;
        currentFileId = null;
        setLanguage(typeSelect.value);
    } else {
        btnP.className = "px-3 py-1.5 text-sm font-medium rounded-md bg-white shadow-sm text-blue-700";
        btnQ.className = "px-3 py-1.5 text-sm font-medium rounded-md text-slate-500 hover:text-slate-800";
        typeSelect.classList.add('hidden');
        
        loadProjects();
    }
    setupSplit();
}

document.getElementById('doc-type').addEventListener('change', (e) => setLanguage(e.target.value));

function setLanguage(type) {
    if (!editor) return;
    let lang = type === 'mermaid' ? 'javascript' : type;
    monaco.editor.setModelLanguage(editor.getModel(), lang);
    if (currentMode === 'quick') editor.setValue(TEMPLATES[type]);
    
    // Скрываем PDF, если перешли на Live формат
    if (type !== 'latex') {
        document.getElementById('pdf-viewer').classList.add('hidden');
    }
    updateLivePreview();
}

// --- LIVE PREVIEW (Killer Feature) ---
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
        // Подменяем $$ формулы для KaTeX
        let safeCode = code.replace(/\$\$(.*?)\$\$/gs, (m, p1) => `\n<div class="math-block">${p1}</div>\n`);
        safeCode = safeCode.replace(/\$(.*?)\$/g, (m, p1) => `<span class="math-inline">${p1}</span>`);
        
        contentDiv.innerHTML = marked.parse(safeCode);
        
        // Рендерим математику
        renderMathInElement(contentDiv, {
            delimiters:[
                {left: '<div class="math-block">', right: '</div>', display: true},
                {left: '<span class="math-inline">', right: '</span>', display: false}
            ]
        });
    } else if (type === 'mermaid') {
        try {
            const { svg } = await mermaid.render('mermaid-svg', code);
            contentDiv.innerHTML = `<div class="flex items-center justify-center h-full">${svg}</div>`;
        } catch (e) {
            contentDiv.innerHTML = `<pre class="text-red-500 text-xs p-4">${e.message}</pre>`;
        }
    }
}

// --- СЕРВЕРНАЯ КОМПИЛЯЦИЯ И ОШИБКИ (Killer Feature) ---
async function compileCurrent() {
    if (currentMode === 'project') await saveCurrentFile();
    
    const overlay = document.getElementById('loader-overlay');
    const statusText = document.getElementById('status-text');
    monaco.editor.setModelMarkers(editor.getModel(), 'latex',[]); // Чистим старые ошибки

    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
    statusText.innerText = "Building...";

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
            response = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/compile`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
        }

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            statusText.innerText = "Success";
            statusText.className = "text-xs font-bold mr-2 text-green-500";
            
            // Если это PDF
            if (data.pdf) {
                document.getElementById('live-preview').classList.add('hidden');
                document.getElementById('empty-state').classList.add('hidden');
                const pdfViewer = document.getElementById('pdf-viewer');
                pdfViewer.classList.remove('hidden');

                const byteCharacters = atob(data.pdf);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) byteNumbers[i] = byteCharacters.charCodeAt(i);
                const blob = new Blob([new Uint8Array(byteNumbers)], {type: 'application/pdf'});
                pdfViewer.src = URL.createObjectURL(blob) + "#toolbar=0&view=FitH";
            }

        } else {
            statusText.innerText = "Error";
            statusText.className = "text-xs font-bold mr-2 text-red-500";
            
            // Расставляем маркеры ошибок в Monaco Editor!
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
            } else {
                alert(data.message || data.error || "Compilation failed");
            }
        }

    } catch (err) {
        alert("Server error: " + err.message);
    } finally {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }
}

// --- PROJECT CRUD (Из Фазы 2) ---
async function loadProjects() {
    const res = await fetch(`${API_BASE}/studio/projects`, { headers: { 'Authorization': `Bearer ${token}` } });
    const projects = await res.json();
    
    const selector = document.getElementById('project-selector');
    selector.innerHTML = '<option value="" disabled selected>-- Выберите --</option>';
    projects.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id; opt.text = p.name; selector.appendChild(opt);
    });

    if(projects.length > 0) {
        selector.value = projects[0].id;
        openProject(projects[0].id);
    }
}

async function createNewProject() {
    const name = prompt("Название проекта:");
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

    const res = await fetch(`${API_BASE}/studio/projects/${id}`, { headers: { 'Authorization': `Bearer ${token}` } });
    projectFiles = await res.json();
    renderFileList();

    const mainFile = projectFiles.find(f => f.is_main);
    if (mainFile) openFile(mainFile.id);
}

function renderFileList() {
    const list = document.getElementById('file-list');
    list.innerHTML = '';
    projectFiles.forEach(f => {
        const div = document.createElement('div');
        div.className = `file-item px-4 py-2 text-sm text-slate-700 cursor-pointer hover:bg-slate-200 transition-colors flex items-center gap-2 border-l-[3px] border-transparent`;
        if (f.id === currentFileId) div.classList.add('active');
        div.innerHTML = `<span>${f.is_binary ? '🖼️' : '📄'}</span> <span class="truncate">${f.path}</span>`;
        div.onclick = () => openFile(f.id);
        list.appendChild(div);
    });
}

async function openFile(id) {
    if (currentFileId !== null) await saveCurrentFile();
    const file = projectFiles.find(f => f.id === id);
    if (!file) return;

    currentFileId = id;
    renderFileList();

    if (file.is_binary) {
        editor.setValue(`% Это бинарный файл (${file.path}).\n% Используйте \\includegraphics{${file.path}} в коде.`);
        monaco.editor.setModelLanguage(editor.getModel(), 'plaintext');
        editor.updateOptions({ readOnly: true });
    } else {
        editor.updateOptions({ readOnly: false });
        monaco.editor.setModelLanguage(editor.getModel(), 'latex');
        editor.setValue(file.content || "");
    }
}

async function saveCurrentFile() {
    if (!currentFileId || !currentProjectId) return;
    const file = projectFiles.find(f => f.id === currentFileId);
    if (file && !file.is_binary) {
        const newContent = editor.getValue();
        if (newContent !== file.content) {
            document.getElementById('status-text').innerText = "Saving...";
            await fetch(`${API_BASE}/studio/projects/${currentProjectId}/files/${currentFileId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ content: newContent })
            });
            file.content = newContent;
            document.getElementById('status-text').innerText = "Saved";
        }
    }
}

async function uploadAsset(event) {
    if (!currentProjectId) return;
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData(); formData.append('file', file);
    const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });
    if (res.ok) await openProject(currentProjectId);
}