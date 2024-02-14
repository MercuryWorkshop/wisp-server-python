import asyncio
import struct
import os
import pathlib
import mimetypes
import argparse

from websockets.server import serve
from websockets.exceptions import ConnectionClosed

import ratelimit
import json

version = "0.1.1"
tcp_size = 64*1024
queue_size = 128
static_path = None

#wisp packet format definitions
#see https://docs.python.org/3/library/struct.html for what these characters mean
packet_format = "<BI"
connect_format = "<BH"
continue_format = "<I"
close_format = "<B"

class WSProxyConnection:
  def __init__(self, ws, path, client_ip):
    self.ws = ws
    self.path = path
    self.client_ip = client_ip

  async def setup_connection(self):
    addr_str = self.path.split("/")[-1]
    self.tcp_host, self.tcp_port = addr_str.split(":")
    self.tcp_port = int(self.tcp_port)

    self.tcp_reader, self.tcp_writer = await asyncio.open_connection(host=self.tcp_host, port=self.tcp_port, limit=tcp_size)

  async def handle_ws(self):
    while True:
      try:
        data = await self.ws.recv()
      except ConnectionClosed:
        break

      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "ws")
      self.tcp_writer.write(data)
      await self.tcp_writer.drain()
    
    self.tcp_writer.close()
  
  async def handle_tcp(self):
    while True:
      data = await self.tcp_reader.read(tcp_size)
      if len(data) == 0:
        break #socket closed

      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "tcp")
      await self.ws.send(data)
    
    await self.ws.close()

class WispConnection:
  def __init__(self, ws, path, client_ip):
    self.ws = ws
    self.path = path
    self.active_streams = {}
    self.client_ip = client_ip
  
  #send the initial CONTINUE packet
  async def setup(self):
    continue_payload = struct.pack(continue_format, queue_size)
    continue_packet = struct.pack(packet_format, 0x03, 0) + continue_payload
    await self.ws.send(continue_packet)

  async def new_stream(self, stream_id, payload):
    stream_type, destination_port = struct.unpack(connect_format, payload[:3])
    hostname = payload[3:].decode()

    #rate limited
    stream_count = ratelimit.get_client_attr(self.client_ip, "streams")
    if ratelimit.enabled and stream_count > ratelimit.connections_limit:
      await self.send_close_packet(stream_id, 0x49)
      self.close_stream(stream_id)
      return
    
    #udp not supported yet
    if stream_type != 1: 
      await self.send_close_packet(stream_id, 0x41)
      self.close_stream(stream_id)
      return
    
    #info looks valid - try to open the connection now
    try:
      tcp_reader, tcp_writer = await asyncio.open_connection(host=hostname, port=destination_port, limit=tcp_size)
    except:
      await self.send_close_packet(stream_id, 0x42)
      self.close_stream(stream_id)
      return
    
    self.active_streams[stream_id]["reader"] = tcp_reader
    self.active_streams[stream_id]["writer"] = tcp_writer
    ws_to_tcp_task = asyncio.create_task(self.task_wrapper(self.stream_ws_to_tcp, stream_id))
    tcp_to_ws_task = asyncio.create_task(self.task_wrapper(self.stream_tcp_to_ws, stream_id))
    self.active_streams[stream_id]["ws_to_tcp_task"] = ws_to_tcp_task
    self.active_streams[stream_id]["tcp_to_ws_task"] = tcp_to_ws_task

    ratelimit.inc_client_attr(self.client_ip, "streams")
  
  async def task_wrapper(self, target_func, *args, **kwargs):
    try:
      await target_func(*args, **kwargs)
    except asyncio.CancelledError as e:
      raise e
  
  async def stream_ws_to_tcp(self, stream_id):
    #this infinite loop should get killed by the task.cancel call later on
    while True: 
      stream = self.active_streams[stream_id]
      data = await stream["queue"].get()
      stream["writer"].write(data)
      try:
        await stream["writer"].drain()
      except:
        break

      #send a CONTINUE packet periodically
      stream["packets_sent"] += 1
      if stream["packets_sent"] % queue_size / 4 == 0:
        buffer_remaining = stream["queue"].maxsize - stream["queue"].qsize()
        continue_payload = struct.pack(continue_format, buffer_remaining)
        continue_packet = struct.pack(packet_format, 0x03, stream_id) + continue_payload
        await self.ws.send(continue_packet)
  
  async def stream_tcp_to_ws(self, stream_id):
    while True:
      stream = self.active_streams[stream_id]
      data = await stream["reader"].read(tcp_size)
      if len(data) == 0: #connection closed
        break
      data_packet = struct.pack(packet_format, 0x02, stream_id) + data

      await ratelimit.limit_client_bandwidth(self.client_ip, len(data_packet), "tcp")
      await self.ws.send(data_packet)

    await self.send_close_packet(stream_id, 0x02)
    self.close_stream(stream_id)
  
  async def send_close_packet(self, stream_id, reason):
    if not stream_id in self.active_streams:
      return
    close_payload = struct.pack(close_format, reason)
    close_packet = struct.pack(packet_format, 0x04, stream_id) + close_payload
    await self.ws.send(close_packet)
  
  def close_stream(self, stream_id):
    if not stream_id in self.active_streams:
      return #stream already closed
    stream = self.active_streams[stream_id]
    self.close_tcp(stream["writer"])

    #kill the running tasks associated with this stream
    if not stream["connect_task"].done():
      stream["connect_task"].cancel() 
    if stream["ws_to_tcp_task"] is not None and not stream["ws_to_tcp_task"].done():
      stream["ws_to_tcp_task"].cancel()
    if stream["tcp_to_ws_task"] is not None and not stream["tcp_to_ws_task"].done():
      stream["tcp_to_ws_task"].cancel()
    
    del self.active_streams[stream_id]
  
  def close_tcp(self, tcp_writer):
    if tcp_writer is None:
      return
    if tcp_writer.is_closing():
      return
    tcp_writer.close()
  
  async def handle_ws(self):
    while True:
      try:
        data = await self.ws.recv()
      except ConnectionClosed:
        break
      
      #implement bandwidth limits
      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "ws")
      
      #get basic packet info
      payload = data[5:]
      packet_type, stream_id = struct.unpack(packet_format, data[:5])

      if packet_type == 0x01: #CONNECT packet
        connect_task = asyncio.create_task(self.task_wrapper(self.new_stream, stream_id, payload))
        self.active_streams[stream_id] = {
          "reader": None,
          "writer": None,
          "queue": asyncio.Queue(queue_size),
          "connect_task": connect_task,
          "ws_to_tcp_task": None,
          "tcp_to_ws_task": None,
          "packets_sent": 0
        }
      
      elif packet_type == 0x02: #DATA packet
        stream = self.active_streams.get(stream_id)
        if not stream:
          continue
        await stream["queue"].put(payload)
      
      elif packet_type == 0x04: #CLOSE packet
        reason = struct.unpack(close_format, payload)[0]
        self.close_stream(stream_id)
  
    #close all active streams when the websocket disconnects
    for stream_id in list(self.active_streams.keys()):
      self.close_stream(stream_id)

async def connection_handler(websocket, path):
  client_ip = websocket.remote_address[0]
  if client_ip == "127.0.0.1" and "X-Real-IP" in websocket.request_headers:
    client_ip = websocket.request_headers["X-Real-IP"]

  print(f"incoming connection on {path} from {client_ip}")
  ratelimit.inc_client_attr(client_ip, "streams")

  if path.endswith("/"):
    connection = WispConnection(websocket, path, client_ip)
    await connection.setup()
    ws_handler = asyncio.create_task(connection.handle_ws())  
    await asyncio.gather(ws_handler)

  else:
    stream_count = ratelimit.get_client_attr(client_ip, "streams")
    if ratelimit.enabled and stream_count > ratelimit.connections_limit:
      return
    connection = WSProxyConnection(websocket, path, client_ip)
    await connection.setup_connection()
    ws_handler = asyncio.create_task(connection.handle_ws())
    tcp_handler = asyncio.create_task(connection.handle_tcp())
    await asyncio.gather(ws_handler, tcp_handler)

async def static_handler(path, request_headers):
  if "Upgrade" in request_headers:
    return
    
  response_headers = [
    ("Server", f"wisp-server-python v{version}")
  ]
  target_path = static_path / path[1:]

  if target_path.is_dir():
    target_path = target_path / "index.html"
  if not target_path.is_relative_to(static_path):
    return 403, response_headers, "403 forbidden".encode()
  if not target_path.exists():
    return 404, response_headers, "404 not found".encode()
  
  mimetype = mimetypes.guess_type(target_path.name)[0]
  response_headers.append(("Content-Type", mimetype))

  static_data = await asyncio.to_thread(target_path.read_bytes)
  return 200, response_headers, static_data

async def main(args):
  global static_path
  print(f"running wisp-server-python v{version}")

  if args.static:
    static_path = pathlib.Path(args.static).resolve()
    request_handler = static_handler
    mimetypes.init()
    print(f"serving static files from {static_path}")
  else:
    request_handler = None
  
  if args.limits:
    print("enabled rate limits")
    ratelimit.enabled = True
    ratelimit.connections_limit = int(args.connections)
    ratelimit.bandwidth_limit = float(args.bandwidth)
    ratelimit.window_size = float(args.window)
    
  limit_task = asyncio.create_task(ratelimit.reset_limits_timer())
  print(f"listening on {args.host}:{args.port}")
  async with serve(connection_handler, args.host, int(args.port), subprotocols=["wisp-v1"], process_request=request_handler):
    await asyncio.Future()

if __name__ == "__main__":

  parser = argparse.ArgumentParser(
    prog="wisp-server-python",
    description="A Wisp server implementation, written in Python."
  )

  parser.add_argument("--config", required=True, help="The config file to use")
  args = parser.parse_args()

  def load_config():
    with open(args.config) as f:
      config = json.load(f)
    return config

  config = load_config()

  progargs = argparse.Namespace(
    host=config["host"],
    port=config["port"],
    static=config["static"],
    limits=config["limits"],
    bandwidth=config["bandwidth"],
    connections=config["connections"],
    window=config["window"]
  )

  asyncio.run(main(progargs))
