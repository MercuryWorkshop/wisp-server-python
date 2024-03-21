import asyncudp
import asyncio

tcp_size = 64*1024

class TCPConnection:
  def __init__(self, hostname, port):
    self.hostname = hostname
    self.port = port
    self.tcp_writer = None
    self.tcp_reader = None
  
  async def connect(self):
    self.tcp_reader, self.tcp_writer = await asyncio.open_connection(host=self.hostname, port=self.port, limit=tcp_size)
  
  async def recv(self):
    return await self.tcp_reader.read(tcp_size)
  
  async def send(self, data):
    self.tcp_writer.write(data)
    await self.tcp_writer.drain() 
  
  def close(self):
    if self.tcp_writer is None:
      return
    if self.tcp_writer.is_closing():
      return
    self.tcp_writer.close()

class UDPConnection:
  def __init__(self, hostname, port):
    self.hostname = hostname
    self.port = port
    self.socket = None
  
  async def connect(self):
    self.socket = await asyncudp.create_socket(remote_addr=(self.hostname, self.port))
  
  async def recv(self):
    data, addr = await self.socket.recvfrom()
    return data
  
  async def send(self, data):
    self.socket.sendto(data)
  
  def close(self):
    if self.socket is None:
      return
    self.socket.close()