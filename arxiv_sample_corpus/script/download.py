#Note: This script is for downloading locally the pdf arxiv papers listed in ingestion_metadata.csv. Only for testing.
#for actual RAG pipeline ingestion, use the ingestion script instead

from concurrent.futures import ThreadPoolExecutor
import os
import requests
import pandas as pd
from pathlib import Path

script_dir = Path(__file__).resolve().parent
df = pd.read_csv(f'{script_dir.parent}/data/ingestion_metadata.csv')

#download files from arxiv and store them in the data/arxiv_papers directory
output_dir = f'{script_dir.parent}/data/arxiv_papers'
os.makedirs(output_dir, exist_ok=True)
urls = df['open_access_url'].tolist()[:3]

#downloads and saves pdf paper in the output directory.
def download_pdf(url):
  try:
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
      file_name = os.path.join(output_dir, url.split("/")[-1] + '.pdf')
      with open(file_name, "wb") as f:
        f.write(response.content)
      print(f"Downloaded: {file_name}")
  except Exception as e:
    print(f"Failed {url}: {e}")

# Download using 10 threads..
with ThreadPoolExecutor(max_workers=10) as executor:
  executor.map(download_pdf, urls)