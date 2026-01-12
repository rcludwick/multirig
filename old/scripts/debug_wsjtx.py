import asyncio
import sys

async def replay():
    if len(sys.argv) >= 3:
        host = sys.argv[1]
        port = int(sys.argv[2])
    else:
        host = "127.0.0.1"
        port = 9003
    
    commands = [
        b"\\get_powerstat\n",
        b"\\chk_vfo\n",
        b"\\dump_state\n"
    ]
    
    print(f"Connecting to {host}:{port}...")
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    for cmd in commands:
        print(f"\n--- Sending: {cmd.strip()} ---")
        writer.write(cmd)
        await writer.drain()
        
        # Read response.
        try:
            # Read line by line until we get a response (or timeout)
            # Some commands return multiple lines.
            # \get_powerstat -> 1 line
            # \dump_state -> many lines
            
            # We just read a chunk and print it for debugging
            # But readline is better for synchronization if we know what to expect.
            # Let's try reading lines with a short loop
            
            # Initial read
            data = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=0.5)
                    if not chunk:
                        break
                    data += chunk
                    # If we got response (heuristic), break?
                    # But dump_state is large.
                    # For dump_state, we might expect failure RPRT -1 which is short.
                except asyncio.TimeoutError:
                    break
            
            print(f"Received ({len(data)} bytes):")
            print(data.decode(errors='replace'))
            
        except Exception as e:
            print(f"Error reading response: {e}")

    print("\nClosing connection")
    writer.close()
    await writer.wait_closed()

if __name__ == "__main__":
    asyncio.run(replay())
