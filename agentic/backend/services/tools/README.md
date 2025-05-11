$ sudo apt install uvicorn
$ python -m venv venv
$ source venv/bin/activate.fish     # source venv/bin/activate
$ pip install -r requirements.txt

$ uvicorn service_tools:app --host 0.0.0.0 --port 8001
$ pytest test_tools.py
