import threading
import multiprocessing
import pathlib
import mimetypes
import logging
import random
import sys

from websockets.sync.server import serve
from websockets.http11 import Response, Headers

import wisp
from wisp.server import ratelimit
from wisp.server import net
from wisp.server.threading import connection

static_path = None
connections = {}

def connection_handler(websocket):
  path = websocket.request.path
  client_ip = websocket.remote_address[0]
  if client_ip == "127.0.0.1" and "X-Real-IP" in websocket.request.headers:
    client_ip = websocket.request.headers["X-Real-IP"]
  origin = websocket.request.headers.get("Origin")

  conn_id = "".join(random.choices("1234567890abcdef", k=8))
  logging.info(f"({conn_id}) incoming connection on {path} from {client_ip} (origin: {origin})")
  ratelimit.inc_client_attr(client_ip, "streams")

  if path.endswith("/"):
    wisp_conn = connection.WispConnection(websocket, path, client_ip, conn_id)
    connections[websocket] = wisp_conn
    wisp_conn.setup()
    wisp_conn.handle_ws()
    del connections[websocket]

  else:
    stream_count = ratelimit.get_client_attr(client_ip, "streams")
    if ratelimit.enabled and stream_count > ratelimit.connections_limit:
      return
    wsproxy_conn = connection.WSProxyConnection(websocket, path, client_ip)
    wsproxy_conn.setup_connection()
    t1 = threading.Thread(target=wsproxy_conn.handle_ws, daemon=True)
    t2 = threading.Thread(target=wsproxy_conn.handle_tcp, daemon=True)
    t1.start(); t2.start()
    t1.join(); t2.join()

def static_handler(connection, request):
  if "Upgrade" in request.headers:
    return
    
  response_headers = Headers()
  response_headers["Server"] = f"wisp-server-python v{wisp.version}"
  if static_path is None:
    return Response(204, None, response_headers, body=b"")

  target_path = static_path / request.path[1:]

  if target_path.is_dir():
    target_path = target_path / "index.html"
  if not target_path.is_relative_to(static_path):
    return Response(403, None, response_headers, body="403 forbidden".encode())
  if not target_path.exists():
    return Response(404, None, response_headers, body="404 not found".encode())
  
  mimetype = mimetypes.guess_type(target_path.name)[0]
  response_headers["Content-Type"] = mimetype

  static_data = target_path.read_bytes()
  return Response(200, None, response_headers, body=static_data)

def main(args):
  global static_path
  logging.info(f"running wisp-server-python v{wisp.version} (threading)")

  if args.static:
    static_path = pathlib.Path(args.static).resolve()
    mimetypes.init()
    logging.info(f"serving static files from {static_path}")
  
  if args.limits:
    logging.info("enabled rate limits")
    ratelimit.enabled = True
    ratelimit.connections_limit = int(args.connections)
    ratelimit.bandwidth_limit = float(args.bandwidth)
    ratelimit.window_size = float(args.window)

  net.block_loopback = not args.allow_loopback
  net.block_private = not args.allow_private
      
  threading.Thread(target=ratelimit.reset_limits_timer_sync, daemon=True).start()
  logging.info(f"listening on {args.host}:{args.port}")

  ws_logger = logging.getLogger("websockets")
  ws_logger.setLevel(logging.WARN)

  with serve(connection_handler, args.host, int(args.port), process_request=static_handler, compression=None) as server:
    try:
      server.serve_forever()
    except KeyboardInterrupt:
      for connection in connections.values():
        connection.close()
      server.shutdown()