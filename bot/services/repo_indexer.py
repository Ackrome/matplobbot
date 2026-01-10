# bot/services/repo_indexer.py
import logging
import asyncio
import aiohttp
from bot.config import GITHUB_TOKEN, MD_SEARCH_BRANCH
from bot.services.text_utils import chunk_markdown
from shared_lib.services.semantic_search import search_engine

logger = logging.getLogger(__name__)

async def index_github_repository(repo_path: str):
    """
    Downloads MD files and indexes them with Hybrid Search (Keyword + Vector).
    """
    source_type_key = f"repo:{repo_path}"
    
    # 1. Clear old data
    await search_engine.clear_index(source_type=source_type_key)
    logger.info(f"Started indexing repo: {repo_path}")
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            url = f"https://api.github.com/repos/{repo_path}/git/trees/{MD_SEARCH_BRANCH}?recursive=1"
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch file list for {repo_path}: {response.status}")
                    return
                data = await response.json()
                
            files = [item for item in data.get('tree', []) if item['path'].endswith('.md')]
            logger.info(f"Found {len(files)} markdown files in {repo_path}")

            indexed_count = 0
            for file_info in files:
                file_path = file_info['path']
                raw_url = f"https://raw.githubusercontent.com/{repo_path}/{MD_SEARCH_BRANCH}/{file_path}"
                
                try:
                    async with session.get(raw_url) as file_resp:
                        if file_resp.status == 200:
                            text = await file_resp.text()
                            chunks = chunk_markdown(text)
                            
                            for i, chunk in enumerate(chunks):
                                chunk_path = f"{file_path}#chunk_{i}"
                                
                                # --- HYBRID SEARCH OPTIMIZATION ---
                                # We inject the filename and header into the content.
                                # This ensures 'Gini.md' is found by keyword search 'Gini'.
                                filename = file_path.split('/')[-1]
                                header_text = chunk['header']
                                body = chunk['content']
                                
                                # This format helps both the Embedding Model (context) and TSVECTOR (keywords)
                                optimized_content = (
                                    f"File: {filename}\n"
                                    f"Section: {header_text}\n"
                                    f"----------------\n"
                                    f"{body}"
                                )

                                await search_engine.upsert_document(
                                    source_type=source_type_key,
                                    path=chunk_path,
                                    content=optimized_content,
                                    metadata={
                                        'file_path': file_path,
                                        'header': header_text,
                                        'repo': repo_path
                                    }
                                )
                            indexed_count += 1
                        else:
                            logger.warning(f"Failed to download {file_path}")
                            
                    await asyncio.sleep(0.1) # Rate limit protection
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")

            logger.info(f"Successfully indexed {indexed_count} files for {repo_path}")

    except Exception as e:
        logger.error(f"Critical error indexing {repo_path}: {e}", exc_info=True)