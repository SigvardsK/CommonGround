# Connecting Common Ground to an Obsidian MCP Server via Docker Gateway

These steps let Common Ground act as an MCP client for an Obsidian server that you run inside Docker Desktop. The same flow works for any other MCP server that exposes an HTTP endpoint.

## 0. Prerequisites
- Your Obsidian MCP container is already running and reachable (for example `http://localhost:27124` or, when crossing from WSL to Docker Desktop, `http://host.docker.internal:27124`).
- The Obsidian "Local REST API" plugin is enabled and you configured its API token.
- Quick connectivity test:
  ```bash
  curl -i http://localhost:27124
  ```
  The call should return headers instead of `connection refused`.

## 1. Configure and launch the Docker MCP Gateway
1. Create a working directory on the host:
   ```bash
   mkdir -p ~/ops/mcp-gateway
   cd ~/ops/mcp-gateway
   ```
2. Create `gateway.json` that points at your Obsidian server and exposes a new HTTP endpoint:
   ```json
   {
     "servers": [
       {
         "name": "obsidian",
         "transport": "sse",
         "url": "http://host.docker.internal:27124"
       }
     ],
     "expose": {
       "http": {
         "host": "0.0.0.0",
         "port": 8787,
         "base_path": "/mcp"
       }
     }
   }
   ```
   Use `http://localhost:27124` when everything runs on the same host; use `host.docker.internal` when the client is inside WSL or another container.
3. Start the gateway (pick either option):
   ```bash
   # Docker MCP CLI helper
   docker mcp gateway run --config ./gateway.json

   # ...or, plain docker
   docker run -d --name mcp-gateway \
     -p 8787:8787 \
     -v "$PWD/gateway.json:/etc/mcp/gateway.json:ro" \
     ghcr.io/docker/mcp-gateway:latest \
     --config /etc/mcp/gateway.json
   ```
4. Smoke test:
   ```bash
   curl -i http://localhost:8787/mcp
   docker logs mcp-gateway | tail
   ```
   Adjust the upstream URL in `gateway.json` if the gateway cannot reach Obsidian (swap `localhost`/`host.docker.internal` accordingly) and restart the container.

## 2. Point Common Ground at the gateway
- **Local dev (`uv run run_server.py`)** – `core/mcp.json` already ships with:
  ```json
  {
    "mcpServers": {
      "obsidian": {
        "transport": "http",
        "url": "http://localhost:8787/mcp",
        "enabled": true
      }
    }
  }
  ```
  Modify the URL if you exposed the gateway on a different host/port.
- **Docker compose deployment** – `deployment/mcp.json` targets the gateway service name:
  ```json
  {
    "mcpServers": {
      "obsidian": {
        "transport": "http",
        "url": "http://mcp-gateway:8787/mcp",
        "enabled": true
      }
    }
  }
  ```
  If you run the gateway separately, update the URL to match your environment.

Restart the Common Ground backend (or `docker compose up --force-recreate core`) so the new MCP settings are loaded. On startup you should see log entries like:
```
mcp_server_connection_success ... "server_name": "obsidian"
```

## 3. Verify tool access from Common Ground
Create a new run and ask the Partner to list available tools, or call `list_rag_sources`. You should see Obsidian specific MCP tools in the output. Try a small write (for example, append to a demo note) to confirm end-to-end connectivity.

## 4. Troubleshooting tips
- **`connection refused` on 8787** – Gateway container is down or port binding is incorrect (`docker ps`, `docker logs mcp-gateway`).
- **Gateway reachable but tools missing** – Gateway cannot reach the upstream Obsidian server. Adjust the URL in `gateway.json` and restart.
- **WSL networking quirks** – Use `http://host.docker.internal` from WSL clients. The Docker Desktop gateway exposes that hostname.
- **Proxies** – Avoid placing the MCP gateway behind an HTTP proxy that strips SSE headers.

With these settings Common Ground will act as the MCP client, while the gateway bridges to your Obsidian MCP server.
