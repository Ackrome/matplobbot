const API_BASE = "https://api.ivantishchenko.ru/api";
let editor = null;

// Дефолтные шаблоны для типов документов
const TEMPLATES = {
    latex: `\\documentclass[12pt, a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[T2A]{fontenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath, amssymb}

\\title{Мой первый документ}
\\author{Matplobbot Studio}
\\date{\\today}

\\begin{document}
\\maketitle

\\section{Введение}
Здесь начинается ваш текст. Вы можете писать формулы:
\\[ E = mc^2 \\]

\\section{Заключение}
Всё работает отлично!
\\end{document}`,

    markdown: `# Привет, Markdown!

Это тестовый документ.

## Списки
* Пункт 1
* Пункт 2

## Формулы (LaTeX)
$$
\\int_{0}^{\\infty} e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}
$$`,

    mermaid: `graph TD;
    A[Начало] --> B{Есть идея?};
    B -- Да --> C[Пишем код];
    B -- Нет --> D[Идем пить кофе];
    C --> E[Profit!];`
};

// 1. Инициализация Split.js
Split(['#editor-pane', '#viewer-pane'], {
    sizes:[50, 50],
    minSize: [300, 300],
    gutterSize: 8,
    cursor: 'col-resize'
});

// 2. Инициализация Monaco Editor
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' }});

require(['vs/editor/editor.main'], function() {
    editor = monaco.editor.create(document.getElementById('monaco-container'), {
        value: TEMPLATES.latex,
        language: 'latex',
        theme: 'vs-light', // Можно 'vs-dark'
        automaticLayout: true,
        wordWrap: 'on',
        minimap: { enabled: false },
        fontSize: 14
    });

    // Биндим Ctrl+S
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function() {
        compileDocument();
    });
});

// 3. Обработка смены типа документа
document.getElementById('doc-type').addEventListener('change', (e) => {
    const type = e.target.value;
    if (editor) {
        // Меняем синтаксис
        let lang = type;
        if (type === 'mermaid') lang = 'javascript'; // mermaid подсветка ставится отдельно, юзаем базовую
        monaco.editor.setModelLanguage(editor.getModel(), lang);
        
        // Вставляем темплейт, если редактор пустой или был дефолтным
        editor.setValue(TEMPLATES[type]);
    }
});

// 4. Логика компиляции
document.getElementById('compile-btn').addEventListener('click', compileDocument);

async function compileDocument() {
    const token = localStorage.getItem('jwt_token');
    if (!token) {
        alert("Для компиляции необходимо авторизоваться.");
        window.location.href = '/login';
        return;
    }

    const type = document.getElementById('doc-type').value;
    const content = editor.getValue();
    
    const overlay = document.getElementById('loader-overlay');
    const statusText = document.getElementById('status-text');
    const errorPanel = document.getElementById('error-panel');
    const errorText = document.getElementById('error-text');

    // UI Feedback
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
    errorPanel.classList.add('hidden');
    statusText.innerText = "Compiling...";
    statusText.className = "text-xs font-medium mr-2 text-blue-500 animate-pulse";

    try {
        const response = await fetch(`${API_BASE}/studio/compile`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ type, content })
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            statusText.innerText = "Success";
            statusText.className = "text-xs font-bold mr-2 text-green-500";
            renderOutput(type, data);
        } else {
            throw new Error(data.detail || data.error || "Compilation failed");
        }

    } catch (err) {
        statusText.innerText = "Error";
        statusText.className = "text-xs font-bold mr-2 text-red-500";
        errorText.innerText = err.message;
        errorPanel.classList.remove('hidden');
    } finally {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }
}

// 5. Рендеринг результата (Base64 -> Blob -> Iframe / Image)
function renderOutput(type, data) {
    const pdfViewer = document.getElementById('pdf-viewer');
    const imageViewer = document.getElementById('image-viewer');
    const emptyState = document.getElementById('empty-state');

    emptyState.classList.add('hidden');

    if (type === 'latex' || type === 'markdown') {
        // Работаем с PDF
        imageViewer.classList.add('hidden');
        pdfViewer.classList.remove('hidden');

        // Конвертируем base64 PDF в Blob для правильного отображения в браузере
        const byteCharacters = atob(data.pdf);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], {type: 'application/pdf'});
        
        // Создаем локальный URL и вставляем в Iframe
        const blobUrl = URL.createObjectURL(blob);
        pdfViewer.src = blobUrl + "#toolbar=0&view=FitH"; // Скрываем верхнюю панель PDF и подгоняем по ширине
        
    } else if (type === 'mermaid') {
        // Работаем с PNG
        pdfViewer.classList.add('hidden');
        imageViewer.classList.remove('hidden');
        
        imageViewer.src = "data:image/png;base64," + data.image;
    }
}