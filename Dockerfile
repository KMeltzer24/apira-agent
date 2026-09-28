FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

# Supervisor image: no specialist packages or their MCP tool trees.
FROM base AS supervisor
RUN rm -rf agents/portfolio_sub_agent agents/research_sub_agent
EXPOSE 8100

# Portfolio image: no research tools/package and no supervisor HTTP app.
FROM base AS portfolio
RUN rm -rf agents/research_sub_agent agents/supervisor agents/graph.py server.py agent.py
EXPOSE 8110

# Research image: no portfolio tools/package and no supervisor HTTP app.
FROM base AS research
RUN rm -rf agents/portfolio_sub_agent agents/supervisor agents/graph.py server.py agent.py
EXPOSE 8120

FROM supervisor
