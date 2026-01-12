
import re
import sys

def fix_file(path):
    with open(path, 'r') as f:
        content = f.read()

    # 1. Remove debug prints
    # Remove lines like: # print(f"DEBUG: ...")
    content = re.sub(r'^\s*#\s*print\(f"DEBUG:.*$\n', '', content, flags=re.MULTILINE)
    # Remove lines like: print(f"DEBUG: ...")
    content = re.sub(r'^\s*print\(f"DEBUG:.*$\n', '', content, flags=re.MULTILINE)

    # 2. Replace chk_vfo implementation
    # We'll match the method signature and indentation block.
    # It's a bit risky with regex for large blocks, but the structure is consistent.
    # Let's verify the exact existing block from read_file output.
    
    old_chk_vfo = r'''    async def chk_vfo\(self\) -> Optional\[str\]:
        async def _do\(\) -> Optional\[str\]:
            code, lines = await self\._send_erp\("chk_vfo"\)
            if code != 0:
                return None
            # Standard extended response: "chk_vfo: 0", "RPRT 0"
            # We just want the value "0" or "1" or "CHKVFO 0"
            # Ideally we reconstruct the standard response "CHKVFO 0"
            # Or just return "0" and let caller format it\?
            # Let's return the full text minus key echo\?
            # If line is "chk_vfo: 0", value is "0"\.
            for ln in lines:
                if ln\.startswith\("chk_vfo:"\):
                    return ln\.split\(":", 1\)\[1\]\.strip\(\)
            return "0" # Default\?
        return await self\._exec\.run\(_do\)'''

    new_chk_vfo = r'''    async def chk_vfo(self) -> Optional[str]:
        # chk_vfo via ERP (+chk_vfo) is not reliably supported (e.g. dummy rig interprets it as +c).
        # Use raw mode '\chk_vfo'.
        async def _do() -> Optional[str]:
            cmd = "\\chk_vfo"
            if self._debug is not None:
                with contextlib.suppress(Exception):
                    self._debug.add("rigctld_tx", cmd=cmd)
            try:
                reader, writer = await self._ensure_connection(1.5)
                writer.write((cmd + "\n").encode())
                await writer.drain()
                
                # Expect single line response like "0" or "1"
                data = await asyncio.wait_for(reader.readline(), timeout=1.5)
                if not data:
                    raise ConnectionError("Connection closed by peer")
                s = data.decode(errors="ignore").strip("\r\n")
                
                if self._debug is not None:
                    with contextlib.suppress(Exception):
                        self._debug.add("rigctld_rx", cmd=cmd, lines=[s])
                
                if s.startswith("RPRT"):
                    return None
                return s
            except Exception:
                await self._close_connection()
                return None
        return await self._exec.run(_do)'''

    # Perform replacement
    # Using simple string replace if regex is too hard, but indentation matters.
    # The file content uses 4 spaces.
    
    # We need to be careful with regex escaping.
    # Let's try to locate the start and end of the function.
    
    start_marker = "    async def chk_vfo(self) -> Optional[str]:"
    end_marker = "        return await self._exec.run(_do)"
    
    # Simple state machine to replace the block
    lines = content.split('\n')
    new_lines = []
    in_chk_vfo = False
    replaced = False
    
    for line in lines:
        if line.startswith(start_marker):
            in_chk_vfo = True
            # Insert new block
            new_lines.append(new_chk_vfo)
            replaced = True
            continue
        
        if in_chk_vfo:
            if line.strip() == "return await self._exec.run(_do)":
                in_chk_vfo = False
            continue
        
        new_lines.append(line)
        
    content = '\n'.join(new_lines)
    
    if not replaced:
        print("Could not find chk_vfo block to replace")
        # sys.exit(1) # Don't exit, just save the debug print removal
        
    with open(path, 'w') as f:
        f.write(content)
    print("File updated")

fix_file("multirig/rig.py")
