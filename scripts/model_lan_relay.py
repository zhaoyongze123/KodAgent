#!/usr/bin/env python3
"""Small, local-only TCP relay for a LAN model endpoint.

Docker Desktop containers can reach the host gateway even when the LAN model
host rejects Docker's bridged source address.  This process intentionally
does not inspect or log HTTP payloads (which may contain API keys or prompts).
It only forwards bytes between a local listener and the configured target.
"""

from __future__ import annotations

import argparse
import asyncio
import logging


LOG = logging.getLogger("kodagent.model_lan_relay")


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(64 * 1024)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    peer = client_writer.get_extra_info("peername")
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except OSError as exc:
        # Do not log request data or credentials.  The peer and exception are
        # enough to diagnose a relay outage.
        LOG.warning("target connection failed peer=%s error=%s", peer, str(exc)[:160])
        client_writer.close()
        await client_writer.wait_closed()
        return

    await asyncio.gather(
        _pipe(client_reader, target_writer),
        _pipe(target_reader, client_writer),
    )


async def _serve(args: argparse.Namespace) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: _handle(reader, writer, args.target_host, args.target_port),
        host=args.listen_host,
        port=args.listen_port,
        reuse_address=True,
    )
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    LOG.info("listening=%s target=%s:%s", addresses, args.target_host, args.target_port)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=18081)
    parser.add_argument("--target-host", default="192.168.1.103")
    parser.add_argument("--target-port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[model-relay] %(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(_serve(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
