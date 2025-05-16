$ sudo apt install expect

solvin repos admit --team 1 --url https://github.com/solvin-ai/demo

nats stream ls
nats consumer ls STREAM_TOOLS
nats consumer info STREAM_TOOLS TOOLS_EXEC_REQ
nats consumer delete STREAM_TOOLS TOOLS_EXEC_REQ
nats stream delete STREAM_TOOLS
nats --server nats://localhost:4222 consumer delete STREAM_TOOLS TOOLS_EXEC_REQ
nats --server nats://localhost:4222 stream delete STREAM_TOOLS

export COMPOSE_BAKE=true ; docker compose down ; docker compose up --build -d ; docker compose logs -f

#rm ../data/dbs/*; env SOLVIN_EXCEPTION_HALT=1 ./backend.sh

# docker system prune -af
# docker compose exec configs sh

❯ solvin tools execute echo https://github.com/solvin-ai/demo --input-args '{"input_text": "hello"}' --repo-owner solvin-ai
