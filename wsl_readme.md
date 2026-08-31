Uv sync
-------

Run uv sync --link-mode=copy instead of uv sync.
This is to bypass security error thrown by ntkl inside llamaindex

Run the project in WSL.
-------------------------------

1. install WSL
2. clone the repo in wsl(e.g under /<distribution>/home/<user>/git directory) 
3. install WSL extension (and python + jupyter extension) in vs code.
4. Launch vs code from wsl by first moving to rag-architecture directory and then running
    code .
    This will open vs code instance connected to wsl (bottom left corner should read WSL:<distribution>)
5. install uv in wsl by running
    curl -LsSf https://astral.sh/uv/install.sh | sh
6. cd into rag-architecture directory and sync to fetch all the depedencies
    uv sync
7. activate python environment from .venv
    source .venv/bin/activate

Install docker-engine in WSL (without docker desktop on windows)
----------------------------------------------------------------

1. open wsl window and install docker engine