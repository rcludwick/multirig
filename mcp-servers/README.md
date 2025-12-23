# MCP Servers Configuration for MultiRig

This directory contains converted MCP server configurations from gemini settings.json.
Each .json file represents a single MCP server in FastMCP format.

## Generating Configs for AI Assistants

You can generate a consolidated configuration file for Gemini Code Assist, Windsurf, or other MCP clients using the helper script:

```bash
python3 generate_ai_config.py
```

This will create `gemini_mcp_config.json` which you can use in your AI assistant settings.

### Options

- **Copy to clipboard:**
  ```bash
  python3 generate_ai_config.py --clipboard
  ```
- **Print to stdout:**
  ```bash
  python3 generate_ai_config.py --stdout
  ```
- **Save to specific file:**
  ```bash
  python3 generate_ai_config.py --output /path/to/config.json
  ```
- **Replace variables:**
  Replace `${VAR_NAME}` placeholders with actual values.
  ```bash
  python3 generate_ai_config.py --set-var GITHUB_PERSONAL_ACCESS_TOKEN=my_token
  ```
- **Generate Windsurf Config:**
  ```bash
  python3 generate_ai_config.py --windsurf
  ```
  This will create `windsurf_mcp_config.json`.
- **Generate Gemini Config (Default):**
  ```bash
  python3 generate_ai_config.py --gemini
  ```
  This will create `gemini_mcp_config.json`.
- **Update Gemini CLI Settings:**
  Updates `~/.gemini/settings.json` with the generated configuration.
  ```bash
  python3 generate_ai_config.py --gemini-cli
  ```

## Running Individual Servers

To run individual servers:
```bash
fastmcp run <server_name>.json
```

## Available Servers

1. **deepwiki** - URL-based server at https://mcp.deepwiki.com/sse
2. **playwright** - npx @playwright/mcp@latest
3. **puppeteer** - npx -y @modelcontextprotocol/server-puppeteer
4. **chrome-devtools** - npx -y chrome-devtools-mcp@latest
5. **github** - npx -y @modelcontextprotocol/server-github with token
6. **netmind** - uv run netmind-mcp (already part of this project)

Note: Some of these configurations require the referenced Python files to exist with the appropriate entrypoint functions. You may need to create wrapper scripts to call the npx commands within the FastMCP framework.
