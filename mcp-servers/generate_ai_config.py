#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import re

def copy_to_clipboard(text):
    """Copies the given text to the system clipboard (macOS only)."""
    try:
        if sys.platform == 'darwin':
            process = subprocess.Popen('pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            print("Config copied to clipboard.")
        else:
            print("Clipboard support is currently only implemented for macOS (pbcopy).")
    except Exception as e:
        print(f"Failed to copy to clipboard: {e}")

def replace_env_vars(obj, replacements):
    """Recursively replace environment variable placeholders in the config object."""
    if isinstance(obj, dict):
        return {k: replace_env_vars(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_env_vars(i, replacements) for i in obj]
    elif isinstance(obj, str):
        # Look for ${VAR_NAME} pattern
        matches = re.findall(r'\$\{([^}]+)\}', obj)
        result = obj
        for var_name in matches:
            if var_name in replacements:
                result = result.replace(f"${{{var_name}}}", replacements[var_name])
            elif var_name in os.environ:
                result = result.replace(f"${{{var_name}}}", os.environ[var_name])
        return result
    else:
        return obj

def update_gemini_cli_settings(new_config):
    """Updates the .gemini/settings.json file with the new MCP configuration."""
    home_dir = os.path.expanduser("~")
    settings_path = os.path.join(home_dir, ".gemini", "settings.json")
    
    if not os.path.exists(settings_path):
        print(f"Gemini settings file not found at {settings_path}")
        return

    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        
        # Update or add mcpServers section
        # We assume new_config has "mcpServers" key
        if "mcpServers" in new_config:
            settings["mcpServers"] = new_config["mcpServers"]
        
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
            
        print(f"Updated Gemini CLI settings at {settings_path}")
        
    except Exception as e:
        print(f"Failed to update Gemini CLI settings: {e}")

def generate_config():
    """
    Generates a configuration file for Gemini CLI, Gemini Code Assist, or Windsurf.
    Reads all .json files in the current directory (excluding the output file)
    and aggregates them into a single JSON structure compatible with MCP clients.
    """
    
    parser = argparse.ArgumentParser(description="Generate MCP config for AI assistants.")
    parser.add_argument("-c", "--clipboard", action="store_true", help="Copy config to clipboard")
    parser.add_argument("-s", "--stdout", action="store_true", help="Print config to stdout")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--set-var", action="append", help="Set a variable value (format: VAR=VALUE). Can be used multiple times.")
    parser.add_argument("--windsurf", action="store_true", help="Generate Windsurf configuration format")
    parser.add_argument("--gemini", action="store_true", help="Generate Gemini configuration format (default)")
    parser.add_argument("--gemini-cli", action="store_true", help="Update ~/.gemini/settings.json with the generated config")
    
    args = parser.parse_args()
    
    # Parse variable replacements
    replacements = {}
    if args.set_var:
        for var_def in args.set_var:
            if '=' in var_def:
                key, value = var_def.split('=', 1)
                replacements[key] = value
    
    mcp_dir = os.path.dirname(os.path.abspath(__file__))
    
    config = {
        "mcpServers": {}
    }
    
    if not args.stdout:
        print(f"Scanning {mcp_dir} for MCP server configurations...")
    
    # Iterate over all files in the directory
    for filename in os.listdir(mcp_dir):
        if not filename.endswith(".json"):
            continue
            
        # Skip the default output file name to avoid recursion if it exists
        if filename in ["gemini_mcp_config.json", "windsurf_mcp_config.json"]:
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
                    if not args.stdout:
                        print(f"  Loaded {name} from {filename}")
            elif "deployment" in server_config:
                # Convert FastMCP deployment to MCP config
                mcp_entry = {}
                deployment = server_config["deployment"]
                transport = deployment.get("transport")
                
                if transport == "stdio":
                    cmd_args = deployment.get("args", [])
                    if cmd_args:
                        mcp_entry["command"] = cmd_args[0]
                        mcp_entry["args"] = cmd_args[1:]
                    
                    if "env" in deployment:
                        mcp_entry["env"] = deployment["env"]
                        
                elif transport == "sse":
                    host = deployment.get("host", "localhost")
                    port = deployment.get("port", 8000)
                    path = deployment.get("path", "/sse")
                    mcp_entry["url"] = f"http://{host}:{port}{path}"
                
                if mcp_entry:
                    config["mcpServers"][server_name] = mcp_entry
                    if not args.stdout:
                        print(f"  Converted {server_name} from {filename}")
            else:
                # Not a recognized format, skip
                pass
                
        except Exception as e:
            if not args.stdout:
                print(f"Error processing {filename}: {e}")

    # Apply variable replacements
    config = replace_env_vars(config, replacements)

    # Handle --gemini-cli option
    if args.gemini_cli:
        update_gemini_cli_settings(config)
        return

    json_output = json.dumps(config, indent=2)

    if args.stdout:
        print(json_output)
        return

    if args.clipboard:
        copy_to_clipboard(json_output)
        return

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        if args.windsurf:
            output_path = os.path.join(mcp_dir, "windsurf_mcp_config.json")
        else:
            # Default to Gemini config
            output_path = os.path.join(mcp_dir, "gemini_mcp_config.json")
        
    try:
        # Create directory if it doesn't exist (for custom paths)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_path, 'w') as f:
            f.write(json_output)
        print(f"Generated config at {output_path}")
    except Exception as e:
        print(f"Error writing to {output_path}: {e}")

if __name__ == "__main__":
    generate_config()
