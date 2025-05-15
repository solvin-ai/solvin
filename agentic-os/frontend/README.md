$ sudo apt install -y npm sqlite3

brew upgrade node
npm install
npm run dev



curl -sf 'http://localhost:3000/api/models?withProviders=1&model_id=4' | jq
curl -sf 'http://localhost:3000/api/model-providers' | jq
curl -sf 'http://localhost:3000/api/agent-roles?agent_role=root' | jq

