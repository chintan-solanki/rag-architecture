#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def main():
    
    # 1. Define the safe path under the project root
    # __file__ is scripts/setup_nltk.py, so parent.parent gets the project root
    project_root = Path(__file__).resolve().parent.parent
    custom_nltk_dir = project_root / ".nltk_data"
    
    # Enforce the environment variable for this runtime session
    os.environ["NLTK_DATA"] = str(custom_nltk_dir)
    
    # Target path for the stopwords corpus
    stopwords_path = custom_nltk_dir / "corpora" / "stopwords"

    # 2. Check if the corpus already exists
    if stopwords_path.exists():
        print(f"✅ NLTK stopwords already exist at: {stopwords_path}")
        return

    # 3. Download the corpus if missing
    print(f"📥 Downloading NLTK stopwords to project root: {custom_nltk_dir}")
    custom_nltk_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        import nltk
        nltk.download("stopwords", download_dir=str(custom_nltk_dir), quiet=False)
        print("🎉 NLTK download completed successfully.")
    except ImportError:
        print("❌ Error: 'nltk' package not found. Please activate your virtual environment.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
