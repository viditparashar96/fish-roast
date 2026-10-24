# The bot, for Pipecat Cloud (`pipecat cloud deploy`, with pcc-deploy.toml). Built from the repo
# root, so the cast (characters.json) comes along. The base image runs bot.py's bot() for each
# session, in a Daily room Pipecat Cloud makes; no CMD needed.
FROM dailyco/pipecat-base:latest

# Compile bytecode up front; copy from uv's cache rather than link (it's a mounted volume).
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# The server's dependencies, exactly as locked.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=server/uv.lock,target=uv.lock \
    --mount=type=bind,source=server/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# The bot's modules and prompts, and the cast (the panel).
COPY server/*.py ./
COPY server/prompts ./prompts
COPY characters.json ./characters.json
