import asyncio
import struct
import os
import logging

from websockets.exceptions import ConnectionClosed

from wisp.server import ratelimit
from wisp.server import net

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

    try:
      self.conn = net.TCPConnection(self.tcp_host, self.tcp_port)
      await self.conn.connect()
    except Exception as e:
      logging.info(f"Creating a WSProxy stream to {self.tcp_host}:{self.tcp_port} failed: {e}")
      await self.ws.close()

  async def handle_ws(self):
    while True:
      try:
        data = await self.ws.recv()
      except ConnectionClosed:
        break

      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "ws")
      await self.conn.send(data)
    
    self.conn.close()
  
  async def handle_tcp(self):
    while True:
      data = await self.conn.recv()
      if len(data) == 0:
        break #socket closed

      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "tcp")
      await self.ws.send(data)
    
    await self.ws.close()

class WispConnection:
  def __init__(self, ws, path, client_ip, id=None):
    self.ws = ws
    self.path = path
    self.active_streams = {}
    self.client_ip = client_ip
    self.id = id
  
  #send the initial CONTINUE packet
  async def setup(self):
    continue_payload = struct.pack(continue_format, queue_size)
    continue_packet = struct.pack(packet_format, 0x03, 0) + continue_payload
    await self.ws.send(continue_packet)

  async def new_stream(self, stream_id, payload):
    stream_type, destination_port = struct.unpack(connect_format, payload[:3])
    hostname = payload[3:].decode()
    logging.debug(f"({self.id}) Creating a new stream to {hostname}:{destination_port}")

    #rate limited
    stream_count = ratelimit.get_client_attr(self.client_ip, "streams")
    if ratelimit.enabled and stream_count > ratelimit.connections_limit:
      await self.send_close_packet(stream_id, 0x49)
      self.close_stream(stream_id)
      return
    
    #info looks valid - try to open the connection now
    try:
      if stream_type == 0x01:
        connection = net.TCPConnection(hostname, destination_port)
      elif stream_type == 0x02: 
        connection = net.UDPConnection(hostname, destination_port)
      else:
        raise Exception("Invalid stream type.")
      self.active_streams[stream_id]["conn"] = connection
      await connection.connect()
        
    except Exception as e:
      logging.warn(f"({self.id}) Creating a new stream to {hostname}:{destination_port} failed: {e}")
      await self.send_close_packet(stream_id, 0x42)
      self.close_stream(stream_id)
      return
    
    self.active_streams[stream_id]["type"] = stream_type
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
      try:
        await stream["conn"].send(data)
      except:
        break

      #send a CONTINUE packet periodically
      stream["packets_sent"] += 1
      if stream["packets_sent"] % (queue_size // 4) == 0:
        buffer_remaining = stream["queue"].maxsize - stream["queue"].qsize()
        continue_payload = struct.pack(continue_format, buffer_remaining)
        continue_packet = struct.pack(packet_format, 0x03, stream_id) + continue_payload
        await self.ws.send(continue_packet)
  
  async def stream_tcp_to_ws(self, stream_id):
    while True:
      stream = self.active_streams[stream_id]
      try:
        data = await stream["conn"].recv()
      except Exception as e:
        logging.warn(f"({self.id}) Receiving data from stream failed: {e}")
        await self.send_close_packet(stream_id, 0x03)
        self.close_stream(stream_id)
        return
        
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
    if stream["conn"]:
      stream["conn"].close()

    #kill the running tasks associated with this stream
    if not stream["connect_task"].done():
      stream["connect_task"].cancel() 
    if stream["ws_to_tcp_task"] is not None and not stream["ws_to_tcp_task"].done():
      stream["ws_to_tcp_task"].cancel()
    if stream["tcp_to_ws_task"] is not None and not stream["tcp_to_ws_task"].done():
      stream["tcp_to_ws_task"].cancel()
    
    del self.active_streams[stream_id]
  
  async def handle_ws(self):
    while True:
      try:
        data = await self.ws.recv()
      except ConnectionClosed:
        break
      except Exception as e:
        logging.warn(f"({self.id}) Receiving data from websocket failed: {e}")
        break

      if not isinstance(data, bytes): 
        continue #ignore non binary frames
      
      #implement bandwidth limits
      await ratelimit.limit_client_bandwidth(self.client_ip, len(data), "ws")
      
      #get basic packet info
      payload = data[5:]
      packet_type, stream_id = struct.unpack(packet_format, data[:5])

      if packet_type == 0x01: #CONNECT packet
        connect_task = asyncio.create_task(self.task_wrapper(self.new_stream, stream_id, payload))
        self.active_streams[stream_id] = {
          "conn": None,
          "type": None,
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
