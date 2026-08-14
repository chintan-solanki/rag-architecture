import pandas as pd
from pathlib import Path

# read the openalex frontier ai works dataset (https://www.kaggle.com/datasets/afr1ste/openalex-frontier-ai-research-2020-2026). 
# Snapshot of frontier-AI scholarly works from OpenAlex, covering LLMs, RAG, foundation models, 
# multimodal LLMs, AI agents, alignment, and prompt engineering.

script_dir = Path(__file__).resolve().parent
df = pd.read_csv(f'{script_dir.parent}/data/openalex_frontier_ai_works.csv')

#retrieve the most impactful open access papers (with cited count > 100 or fwci > 50) available on arxiv 
cited_cnt_threshold = 100
fwci_threshold = 50

df = df[df['is_open_access'] == True]
imp_papers = df[(df['cited_by_count'] > cited_cnt_threshold) | (df['fwci'] > fwci_threshold)]
arxiv_papers = imp_papers[(~imp_papers['open_access_url'].isna()) & (imp_papers['open_access_url'].str.contains('arxiv.org/pdf'))]

#retrieve and store metadata
cols = ['doi', 'title', 'publication_date', 'first_author_name', 'last_author_name', 'open_access_url']
arxiv_papers[cols].to_csv(f'{script_dir.parent}/data/ingestion_metadata.csv', index=False)


