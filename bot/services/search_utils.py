# bot/services/search_utils.py
import logging
import asyncio
import matplobblib
from shared_lib.services.semantic_search import search_engine

logger = logging.getLogger(__name__)

async def index_matplobblib_library():
    """
    Проходит по библиотеке и обновляет записи в БД.
    """
    logger.info("Starting background indexing of matplobblib...")
    count = 0
    
    for submodule_name in matplobblib.submodules:
        try:
            module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
            code_dictionary = getattr(module, 'themes_list_dicts_full', {})
            
            for topic_name, codes in code_dictionary.items():
                for code_name, code_content in codes.items():
                    code_path = f"{submodule_name}.{topic_name}.{code_name}"
                    
                    # Текст для эмбеддинга: Путь + Код (docstring важен!)
                    search_text = f"{submodule_name} {topic_name} {code_name}\n{code_content}"
                    
                    metadata = {
                        'name': code_name,
                        'topic': topic_name
                    }
                    
                    # Upsert в базу
                    await search_engine.upsert_document(
                        source_type='lib',
                        path=code_path,
                        content=search_text,
                        metadata=metadata
                    )
                    count += 1
                    
        except Exception as e:
            logger.error(f"Error indexing submodule {submodule_name}: {e}")
            
    logger.info(f"Finished indexing matplobblib. Processed {count} items.")