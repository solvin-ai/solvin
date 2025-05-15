
$ export OPENAI_API_KEY=''

# Go to github.com (Setting -> Developer Settings -> Personal access tokens) to generate a token

$ gh auth login
$ git config --global user.email "you@example.com"
$ git config --global user.name "Your Name"
$ git config --global credential.helper store

$ sudo apt install -y python3 python3.12-venv pipx expect tree python3-pip

$ mkdir -p ~/dev ; cd ~/dev 
$ git clone https://github.com/solvin-ai/solvin.git


$ sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 1
$ sudo update-alternatives --config python

$ cd solvin/agentic-os/backend 
$ rm -rf venv/ ; python -m venv venv && source venv/bin/activate.fish && pip install -r requirements.txt ; pipx ensurepath ; pipx install .

# python -m venv venv
# source venv/bin/activate.fish     # source venv/bin/activate
# pip install -r requirements.txt
# pip install -e . 
# pipx install .
# pipx reinstall .

## pipx install poetry






# export OPENAI_LOG=debug



# git remote set-url origin https://solvin-ai@github.com/solvin-ai/solvin.it

# command tree -n --gitignore -I '__pycache__' -I 'env' -I '.pytest_cache' --prune

# git add -A && git commit -m "v0.99 - On new computer" && git push


# sqlite3 XXX.sqlite
# PRAGMA table_list;


# brew install asdf
# brew install fisher
