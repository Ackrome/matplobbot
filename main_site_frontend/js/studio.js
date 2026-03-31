const API_BASE = "https://api.ivantishchenko.ru/api";
let editor = null;
const token = localStorage.getItem('jwt_token');

// Состояние приложения
let currentProjectId = null;
let currentFileId = null;
let projectFiles = [];

// 1. Инициализация UI
Split(['#sidebar-pane', '#editor-pane', '#viewer-pane'], {
    sizes: [20, 40, 40],
    minSize: [200, 300, 300],
    gutterSize: 6,
    cursor: 'col-resize'
});

if (!token) {
    alert("Пожалуйста, авторизуйтесь.");
    window.location.href = '/login';
}

// 2. Инициализация Monaco Editor
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' }});
require(['vs/editor/editor.main'], function() {
    editor = monaco.editor.create(document.getElementById('monaco-container'), {
        value: "% Выберите проект слева",
        language: 'latex',
        theme: 'vs-light',
        automaticLayout: true,
        wordWrap: 'on',
        minimap: { enabled: false },
        fontSize: 14
    });

    // Биндим Ctrl+S
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, async function() {
        await saveCurrentFile();
        compileProject();
    });

    // Запускаем загрузку проектов
    loadProjects();
});

// --- API ФУНКЦИИ ---

async function loadProjects() {
    const res = await fetch(`${API_BASE}/studio/projects`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
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
    const name = prompt("Введите название нового проекта:");
    if (!name) return;

    const res = await fetch(`${API_BASE}/studio/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ name: name, project_type: 'latex' })
    });
    
    if (res.ok) {
        await loadProjects(); // Перезагружаем список
    }
}

async function openProject(id) {
    currentProjectId = id;
    document.getElementById('empty-state').classList.remove('hidden');
    document.getElementById('pdf-viewer').classList.add('hidden');

    const res = await fetch(`${API_BASE}/studio/projects/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    projectFiles = await res.json();
    
    renderFileList();

    // Открываем main.tex по умолчанию
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
        
        let icon = f.is_binary ? '🖼️' : '📄';
        div.innerHTML = `<span>${icon}</span> <span class="truncate">${f.path}</span>`;
        
        div.onclick = () => openFile(f.id);
        list.appendChild(div);
    });
}

async function openFile(id) {
    if (currentFileId !== null) {
        await saveCurrentFile(); // Сохраняем предыдущий открытый файл
    }

    const file = projectFiles.find(f => f.id === id);
    if (!file) return;

    currentFileId = id;
    renderFileList(); // Обновляем выделение в UI

    if (file.is_binary) {
        editor.setValue(`% Это бинарный файл (${file.path}).\n% Используйте \\includegraphics{${file.path}} в main.tex, чтобы вставить его.`);
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
    if (!currentProjectId) { alert("Сначала откройте проект."); return; }
    
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });

    if (res.ok) {
        await openProject(currentProjectId); // Перезагружаем файлы проекта
    } else {
        alert("Ошибка загрузки файла.");
    }
}

async function compileProject() {
    if (!currentProjectId) return;
    
    await saveCurrentFile(); // Убеждаемся, что всё сохранено

    const overlay = document.getElementById('loader-overlay');
    const errorPanel = document.getElementById('error-panel');
    
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
    errorPanel.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/studio/projects/${currentProjectId}/compile`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            const pdfViewer = document.getElementById('pdf-viewer');
            document.getElementById('empty-state').classList.add('hidden');
            pdfViewer.classList.remove('hidden');

            const byteCharacters = atob(data.pdf);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) { byteNumbers[i] = byteCharacters.charCodeAt(i); }
            const blob = new Blob([new Uint8Array(byteNumbers)], {type: 'application/pdf'});
            
            pdfViewer.src = URL.createObjectURL(blob) + "#toolbar=0&view=FitH";
        } else {
            throw new Error(data.detail || data.error || "Compilation failed");
        }

    } catch (err) {
        document.getElementById('error-text').innerText = err.message;
        errorPanel.classList.remove('hidden');
    } finally {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }
}