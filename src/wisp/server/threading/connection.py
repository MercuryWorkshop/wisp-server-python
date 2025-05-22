import struct
import os
import logging
import queue
import threading

from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from wisp.server import ratelimit
from wisp.server.threading import netsync

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

  def setup_connection(self):
    addr_str = self.path.split("/")[-1]
    self.tcp_host, self.tcp_port = addr_str.split(":")
    self.tcp_port = int(self.tcp_port)

    try:
      self.conn = netsync.TCPConnection(self.tcp_host, self.tcp_port)
      self.conn.connect()
    except Exception as e:
      logging.info(f"Creating a WSProxy stream to {self.tcp_host}:{self.tcp_port} failed: {e}")
      self.ws.close()

  def handle_ws(self):
    while True:
      try:
        data = self.ws.recv()
      except (ConnectionClosed, ConnectionClosedError) as e:
        break

      ratelimit.limit_client_bandwidth_sync(self.client_ip, len(data), "ws")
      self.conn.send(data)
    
    self.conn.close()
  
  def handle_tcp(self):
    while True:
      data = self.conn.recv()
      if len(data) == 0:
        break #socket closed

      ratelimit.limit_client_bandwidth_sync(self.client_ip, len(data), "tcp")
      self.ws.send(data)
    
    self.ws.close()

class WispConnection:
  def __init__(self, ws, path, client_ip, id=None):
    self.ws = ws
    self.path = path
    self.active_streams = {}
    self.client_ip = client_ip
    self.id = id
  
  #send the initial CONTINUE packet
  def setup(self):
    continue_payload = struct.pack(continue_format, queue_size)
    continue_packet = struct.pack(packet_format, 0x03, 0) + continue_payload
    self.ws.send(continue_packet)
  
  def close(self):
    #close all active streams when the websocket disconnects
    for stream_id in list(self.active_streams.keys()):
      self.close_stream(stream_id)
    self.ws.close()

  def new_stream(self, stream_id, payload):
    stream_type, destination_port = struct.unpack(connect_format, payload[:3])
    hostname = bytes(payload[3:]).decode()
    logging.debug(f"({self.id}) Creating a new stream to {hostname}:{destination_port}")

    #rate limited
    stream_count = ratelimit.get_client_attr(self.client_ip, "streams")
    if ratelimit.enabled and stream_count > ratelimit.connections_limit:
      self.send_close_packet(stream_id, 0x49)
      self.close_stream(stream_id)
      return
    
    #info looks valid - try to open the connection now
    try:
      if stream_type == 0x01:
        connection = netsync.TCPConnection(hostname, destination_port)
      elif stream_type == 0x02: 
        connection = netsync.UDPConnection(hostname, destination_port)
      else:
        raise Exception("Invalid stream type.")
      self.active_streams[stream_id]["conn"] = connection
      connection.connect()
        
    except Exception as e:
      logging.warn(f"({self.id}) Creating a new stream to {hostname}:{destination_port} failed: {e}")
      self.send_close_packet(stream_id, 0x42)
      self.close_stream(stream_id)
      return
    
    self.active_streams[stream_id]["type"] = stream_type
    threading.Thread(target=self.stream_ws_to_tcp, args=(stream_id,), daemon=True).start()
    threading.Thread(target=self.stream_tcp_to_ws, args=(stream_id,), daemon=True).start()
    ratelimit.inc_client_attr(self.client_ip, "streams")
  
  def stream_ws_to_tcp(self, stream_id):
    while True: 
      stream = self.active_streams[stream_id]
      data = stream["queue"].get()
      if data is None:
        break
      try:
        stream["conn"].send(data)
      except:
        break

      #send a CONTINUE packet periodically
      stream["packets_sent"] += 1
      if stream["packets_sent"] % (queue_size // 4) == 0:
        buffer_remaining = stream["queue"].maxsize - stream["queue"].qsize()
        continue_payload = struct.pack(continue_format, buffer_remaining)
        continue_packet = struct.pack(packet_format, 0x03, stream_id) + continue_payload
        self.ws.send(continue_packet)
  
  def stream_tcp_to_ws(self, stream_id):
    while True:
      stream = self.active_streams[stream_id]
      try:
        data = stream["conn"].recv()
      except Exception as e:
        logging.warn(f"({self.id}) Receiving data from stream failed: {e}")
        self.send_close_packet(stream_id, 0x03)
        self.close_stream(stream_id)
        return
        
      if len(data) == 0: #connection closed
        break
      data_header = struct.pack(packet_format, 0x02, stream_id)

      ratelimit.limit_client_bandwidth_sync(self.client_ip, len(data_header)+len(data), "tcp")
      try:
        self.ws.send(data_header + data)
      except (ConnectionClosed, ConnectionClosedError) as e:
        return

    self.send_close_packet(stream_id, 0x02)
    self.close_stream(stream_id)
  
  def send_close_packet(self, stream_id, reason):
    if not stream_id in self.active_streams:
      return
    close_payload = struct.pack(close_format, reason)
    close_packet = struct.pack(packet_format, 0x04, stream_id) + close_payload
    self.ws.send(close_packet)
  
  def close_stream(self, stream_id):
    if not stream_id in self.active_streams:
      return #stream already closed
    stream = self.active_streams[stream_id]
    if stream["conn"]:
      stream["conn"].close()

    #empty the queue and kill it
    while not stream["queue"].empty():
      stream["queue"].get()
    stream["queue"].put(None)
    del self.active_streams[stream_id]
  
  def handle_ws(self):
    while True:
      try:
        data = self.ws.recv()
      except (ConnectionClosed, ConnectionClosedError):
        break
      except Exception as e:
        logging.warn(f"({self.id}) Receiving data from websocket failed: {e}")
        break

      if not isinstance(data, bytes): 
        continue #ignore non binary frames
      
      #implement bandwidth limits
      ratelimit.limit_client_bandwidth_sync(self.client_ip, len(data), "ws")
      
      #get basic packet info
      payload = memoryview(data)[5:]
      packet_type, stream_id = struct.unpack(packet_format, data[:5])

      if packet_type == 0x01: #CONNECT packet
        self.active_streams[stream_id] = {
          "conn": None,
          "type": None,
          "queue": queue.Queue(queue_size),
          "packets_sent": 0
        }
        threading.Thread(target=self.new_stream, args=(stream_id, payload), daemon=True).start()
      
      elif packet_type == 0x02: #DATA packet
        stream = self.active_streams.get(stream_id)
        if not stream:
          continue
        stream["queue"].put(payload)
      
      elif packet_type == 0x04: #CLOSE packet
        reason = struct.unpack(close_format, payload)[0]
        self.close_stream(stream_id)

    self.close()