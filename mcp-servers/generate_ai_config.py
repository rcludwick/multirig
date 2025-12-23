import json
import os
import sys

def generate_gemini_config():
    """
    Generates a configuration file for Gemini CLI or Gemini Code Assist.
    Reads all .json files in the current directory (excluding the output file)
    and aggregates them into a single JSON structure compatible with MCP clients.
    """
    
    mcp_dir = os.path.dirname(os.path.abspath(__file__))
    output_filename = "gemini_mcp_config.json"
    
    config = {
        "mcpServers": {}
    }
    
    print(f"Scanning {mcp_dir} for MCP server configurations...")
    
    # Iterate over all files in the directory
    for filename in os.listdir(mcp_dir):
        if not filename.endswith(".json"):
            continue
            
        if filename == output_filename:
            continue
            
        file_path = os.path.join(mcp_dir, filename)
        server_name = os.path.splitext(filename)[0]
        
        try:
            with open(file_path, 'r') as f:
                server_config = json.load(f)
            
            # Check if it's a FastMCP config (has "deployment") or pre-formatted MCP config
            if "mcpServers" in server_config:
                # Merge existing MCP servers config
                for name, srv_conf in server_config["mcpServers"].items():
                    config["mcpServers"][name] = srv_conf
                    print(f"  Loaded {name} from {filename}")
            elif "deployment" in server_config:
                # Convert FastMCP deployment to MCP config
                mcp_entry = {}
                deployment = server_config["deployment"]
                transport = deployment.get("transport")
                
                if transport == "stdio":
                    args = deployment.get("args", [])
                    if args:
                        mcp_entry["command"] = args[0]
                        mcp_entry["args"] = args[1:]
                    
                    if "env" in deployment:
                        mcp_entry["env"] = deployment["env"]
                        
                elif transport == "sse":
                    host = deployment.get("host", "localhost")
                    port = deployment.get("port", 8000)
                    path = deployment.get("path", "/sse")
                    mcp_entry["url"] = f"http://{host}:{port}{path}"
                
                if mcp_entry:
                    config["mcpServers"][server_name] = mcp_entry
                    print(f"  Converted {server_name} from {filename}")
            else:
                # Not a recognized format, skip
                pass
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    # Write the output file
    output_path = os.path.join(mcp_dir, output_filename)
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Generated Gemini config at {output_path}")

if __name__ == "__main__":
    generate_gemini_config()
