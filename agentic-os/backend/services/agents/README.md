$ sudo apt install uvicorn
$ python -m venv venv
$ source venv/bin/activate.fish     # source venv/bin/activate
$ pip install -r requirements.txt

# rm -rf venv/ ; python -m venv venv && source venv/bin/activate.fish && pip install -r requirements.txt

$ uvicorn service_agents:app --host 0.0.0.0 --port 8000
$ pytest test_agents.py
