# MCP Servers Configuration for MultiRig
# 
# This directory contains converted MCP server configurations from gemini settings.json
# Each .json file represents a single MCP server in FastMCP format
#
# To run individual servers:
#   fastmcp run <server_name>.json
#
# To manage multiple servers, you can use a process manager like pm2 or supervisor
# 
# The original gemini configuration had these servers:
# 1. deepwiki - URL-based server at https://mcp.deepwiki.com/sse
# 2. playwright - npx @playwright/mcp@latest
# 3. puppeteer - npx -y @modelcontextprotocol/server-puppeteer
# 4. chrome-devtools - npx -y chrome-devtools-mcp@latest
# 5. github - npx -y @modelcontextprotocol/server-github with token
# 6. netmind - uv run netmind-mcp (already part of this project)

# Note: Some of these configurations require the referenced Python files to exist
# with the appropriate entrypoint functions. You may need to create wrapper
# scripts to call the npx commands within the FastMCP framework.