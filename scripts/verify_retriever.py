import asyncio
import os
import sys

# Ensure backend module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.config.settings import get_settings
from backend.database.postgres import init_tiger_schema
from backend.memory.embedder import embed_text
from backend.memory.tiger_client import CodeChunk, get_tiger_memory
from backend.memory.context_retriever import retrieve_context_for_diff

async def run_sanity_check():
    print("1. Loading settings...")
    cfg = get_settings()
    
    if not cfg.tiger_database_url or "tsdbadmin" in cfg.tiger_database_url:
        print("\n[!] WARNING: TIGER_DATABASE_URL looks like it's missing or still the default example.")
        print("You must complete Task 1.2 (Tiger Cloud Setup) and update your .env before this will pass.\n")
    
    if not cfg.google_api_key or cfg.google_api_key.startswith("<"):
        print("\n[!] WARNING: GOOGLE_API_KEY is missing or invalid.")
        print("You must complete Task 1.3 and update your .env before this will pass.\n")

    print("2. Initializing Tiger schema and connection pool...")
    # This connects to Tiger Cloud and creates the pool, setting up the memory singleton
    await init_tiger_schema()
    
    print("3. Generating embedding for test chunk using Gemini...")
    test_content = "def hello_world():\n    print('hello from mira')"
    try:
        embedding = await embed_text(test_content)
    except Exception as e:
        print(f"❌ FAILED to generate embedding: {e}")
        return
        
    print("4. Upserting test chunk into Tiger...")
    client = get_tiger_memory()
    chunk = CodeChunk(
        repo="async-ar15/mira-test-repo",
        path="test_file.py",
        content=test_content,
        embedding=embedding,
        symbol="hello_world",
        token_count=10
    )
    await client.upsert_chunks([chunk])
    
    print("5. Running context_retriever.py on a fake PR diff...")
    fake_diff = "--- a/test_file.py\n+++ b/test_file.py\n+def hello_world():\n+    print('hello from mira')"
    
    # Retrieve context
    context = await retrieve_context_for_diff(
        diff=fake_diff,
        repo_full_name="async-ar15/mira-test-repo"
    )
    
    print("\n--- RETRIEVED CONTEXT ---")
    print(context)
    print("-------------------------\n")
    
    if test_content in context:
        print("✅ SUCCESS: The retriever successfully found the inserted chunk using Tiger Cloud DiskANN!")
    else:
        print("❌ FAILED: The chunk was not found in the context.")

if __name__ == "__main__":
    asyncio.run(run_sanity_check())
