import os, sys
from dotenv import load_dotenv
load_dotenv()
# ensure project root on path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
	sys.path.insert(0, project_root)
from backend import oauth_server
import json
print('services:', list(oauth_server.OAUTH_CONFIGS.keys()))
print(json.dumps({k:{'client_id':v.get('client_id'),'redirect_uri':v.get('redirect_uri'),'auth_url':v.get('auth_url')} for k,v in oauth_server.OAUTH_CONFIGS.items()}, indent=2))
