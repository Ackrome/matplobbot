# bot/services/text_utils.py
import re

def chunk_markdown(text: str, max_chunk_size: int = 1000) -> list[dict]:
    """
    Разбивает Markdown на куски, стараясь сохранять контекст заголовков.
    Возвращает список словарей {'content': str, 'header': str}.
    """
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_header = "No Header"
    current_size = 0
    
    # Регулярка для заголовков (# Header)
    header_pattern = re.compile(r'^(#{1,6})\s+(.*)')

    for line in lines:
        header_match = header_pattern.match(line)
        
        # Если встретили заголовок или чанк переполнился
        if header_match or (current_size + len(line) > max_chunk_size and current_chunk):
            if current_chunk:
                content = '\n'.join(current_chunk).strip()
                if content:
                    chunks.append({
                        'content': f"Context: {current_header}\n\n{content}", # Добавляем заголовок в текст для контекста поиска
                        'header': current_header
                    })
                current_chunk = []
                current_size = 0
            
            if header_match:
                current_header = header_match.group(2) # Текст заголовка
                # Сам заголовок тоже добавляем в новый чанк
                current_chunk.append(line)
                current_size += len(line)
        else:
            current_chunk.append(line)
            current_size += len(line)

    # Добавляем остаток
    if current_chunk:
        content = '\n'.join(current_chunk).strip()
        if content:
            chunks.append({
                'content': f"Context: {current_header}\n\n{content}",
                'header': current_header
            })
            
    return chunks