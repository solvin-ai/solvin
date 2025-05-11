$ sudo apt install uvicorn
$ python -m venv venv
$ source venv/bin/activate.fish     # source venv/bin/activate
$ pip install -r requirements.txt

$ uvicorn service_config:app --host 0.0.0.0 --port 8010
$ pytest test_configs.py
