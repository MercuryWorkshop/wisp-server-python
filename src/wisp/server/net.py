import asyncudp
import asyncio
import socket
import ipaddress

#various network utilities and wrappers

tcp_size = 64*1024
block_loopback = False
block_private = False

def get_ip(host, port, stream_type):
  if stream_type == 0x01:
    proto = socket.IPPROTO_TCP
  else:
    proto = socket.IPPROTO_UDP
  info = socket.getaddrinfo(host, port, proto=proto)
  return info[0][4][0]

async def get_ip_async(host, port, stream_type):
  loop = asyncio.get_running_loop()
  return await loop.run_in_executor(None, get_ip, host, port, stream_type)

def validate_ip(addr_str):
  ip_addr = ipaddress.ip_address(addr_str)
  if block_loopback and ip_addr.is_loopback:
    raise TypeError("Connection to loopback ip address blocked.")
  if block_private and ip_addr.is_private and not ip_addr.is_loopback:
    raise TypeError("Connection to private ip address blocked.")

async def validate_hostname(host, port, stream_type):
  addr_str = await get_ip_async(host, port, stream_type)
  validate_ip(addr_str)
  return addr_str

class TCPConnection:
  def __init__(self, hostname, port):
    self.hostname = hostname
    self.port = port
    self.tcp_writer = None
    self.tcp_reader = None
  
  async def connect(self):
    addr_str = await validate_hostname(self.hostname, self.port, 0x01)
    self.tcp_reader, self.tcp_writer = await asyncio.open_connection(host=addr_str, port=self.port, limit=tcp_size)
  
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
    addr_str = await validate_hostname(self.hostname, self.port, 0x02)
    self.socket = await asyncudp.create_socket(remote_addr=(addr_str, self.port))
  
  async def recv(self):
    data, addr = await self.socket.recvfrom()
    return data
  
  async def send(self, data):
    self.socket.sendto(data)
  
  def close(self):
    if self.socket is None:
      return
    self.socket.close()