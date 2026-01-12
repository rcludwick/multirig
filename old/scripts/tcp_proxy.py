#!/usr/bin/env python3
"""
TCP Proxy for debugging rigctl connections.
Listens on a local port and forwards traffic to a target host/port, logging all data.
"""

import argparse
import asyncio
import sys
from typing import Optional


def _safe_decode(data: bytes) -> str:
    """Safely decode bytes to string for display, escaping non-printable chars."""
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return repr(data)


class TcpProxy:
    def __init__(self, local_port: int, target_host: str, target_port: int):
        self.local_port = local_port
        self.target_host = target_host
        self.target_port = target_port
        self.server: Optional[asyncio.base_events.Server] = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, "0.0.0.0", self.local_port
        )
        print(f"[*] Listening on 0.0.0.0:{self.local_port}")
        print(f"[*] Forwarding to {self.target_host}:{self.target_port}")
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
        peer_addr = client_writer.get_extra_info("peername")
        print(f"[{peer_addr}] New connection")

        try:
            target_reader, target_writer = await asyncio.open_connection(
                self.target_host, self.target_port
            )
        except Exception as e:
            print(f"[{peer_addr}] Failed to connect to target: {e}")
            client_writer.close()
            return

        async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, tag: str):
            try:
                while True:
                    data = await reader.read(4096)
                    if not data:
                        break
                    
                    # Log data
                    decoded = _safe_decode(data)
                    print(f"[{peer_addr}] {tag} {len(data)} bytes: {decoded}")
                    
                    writer.write(data)
                    await writer.drain()
            except Exception as e:
                print(f"[{peer_addr}] Connection error in {tag}: {e}")
            finally:
                writer.close()

        # Run both directions concurrently
        await asyncio.gather(
            forward(client_reader, target_writer, "C->S"),
            forward(target_reader, client_writer, "S->C"),
            return_exceptions=True
        )
        
        print(f"[{peer_addr}] Connection closed")


def main():
    parser = argparse.ArgumentParser(description="TCP Proxy for rigctl debugging")
    parser.add_argument(
        "--listen-port", "-l", type=int, default=4533, help="Local port to listen on"
    )
    parser.add_argument(
        "--target-host", "-t", type=str, default="127.0.0.1", help="Target host"
    )
    parser.add_argument(
        "--target-port", "-p", type=int, default=4532, help="Target port"
    )
    
    args = parser.parse_args()

    proxy = TcpProxy(args.listen_port, args.target_host, args.target_port)
    
    try:
        asyncio.run(proxy.start())
    except KeyboardInterrupt:
        print("\n[*] Stopping proxy")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
