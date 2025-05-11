$ sudo apt install expect

solvin repos admit --url https://github.com/yt-dlp/yt-dlp --team 1

nats stream ls
nats consumer ls STREAM_TOOLS
nats consumer info STREAM_TOOLS TOOLS_EXEC_REQ
nats consumer delete STREAM_TOOLS TOOLS_EXEC_REQ
nats stream delete STREAM_TOOLS
nats --server nats://localhost:4222 consumer delete STREAM_TOOLS TOOLS_EXEC_REQ
nats --server nats://localhost:4222 stream delete STREAM_TOOLS
