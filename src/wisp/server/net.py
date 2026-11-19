import asyncio
import socket
import ipaddress

import asyncudp
import psutil
from python_socks.async_.asyncio import Proxy
try:
  import pymasque
except ImportError:
  pass

#various network utilities and wrappers

iface_name = None
iface_addr_ipv4 = None
iface_addr_ipv6 = None
dns_order = "verbatim"

tcp_size = 64*1024
block_loopback = False
block_private = False
block_udp = False
block_tcp = False

proxy_url = None
proxy_dns = False
warp = None

def reuse_port_supported():
  return hasattr(socket, "SO_REUSEPORT")

def parse_ip(addr_str):
  ip_addr = ipaddress.ip_address(addr_str)
  if ip_addr.version == 6 and ip_addr.ipv4_mapped:
    ip_addr = ip_addr.ipv4_mapped
  return ip_addr

def is_ip(addr_str):
  try:
    parse_ip(addr_str)
    return True
  except:
    return False

def get_ip(host, port, stream_type):
  if stream_type == 0x01:
    proto = socket.IPPROTO_TCP
  else:
    proto = socket.IPPROTO_UDP
  info = socket.getaddrinfo(host, port, proto=proto)
  if dns_order == "ipv4first":
    info.sort(key=lambda x: x[0] != socket.AF_INET)
  elif dns_order == "ipv6first":
    info.sort(key=lambda x: x[0] != socket.AF_INET6)
  return info[0][4][0]

#find the ip address of a network interface such as a vpn
def get_nic_ip(iface_name, socket_family=socket.AF_INET):
  all_addrs = psutil.net_if_addrs()
  if not iface_name in all_addrs:
    raise ValueError(f"interface {iface_name} not found. valid values: {list(all_addrs.keys())}")
  for addr in all_addrs[iface_name]:
    if addr.family == socket_family and not parse_ip(addr.address).is_link_local:
      return addr.address.split("%")[0]

def get_source_ip(addr_str):
  ip_addr = parse_ip(addr_str)
  if iface_addr_ipv4 and ip_addr.version == 4:
    return iface_addr_ipv4
  elif iface_addr_ipv6 and ip_addr.version == 6:
    return iface_addr_ipv6
  if iface_name:
    raise TypeError(f"network interface does not support ipv{ip_addr.version}")
  return None

async def get_ip_async(host, port, stream_type):
  loop = asyncio.get_running_loop()
  return await loop.run_in_executor(None, get_ip, host, port, stream_type)

def validate_ip(addr_str):  
  ip_addr = parse_ip(addr_str)
  if block_loopback and ip_addr.is_loopback:
    raise TypeError("Connection to loopback ip address blocked.")
  if block_private and ip_addr.is_private and not ip_addr.is_loopback:
    raise TypeError("Connection to private ip address blocked.")

async def validate_hostname(host, port, stream_type):
  if is_ip(host):
    validate_ip(host)
    return host
  #don't do a dns lookup when we're on a proxy and using remote dns
  elif proxy_url and proxy_dns:
    return None
  else:  
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
    if block_tcp:
      raise TypeError("TCP connection blocked.")

    addr_str = await validate_hostname(self.hostname, self.port, 0x01)
    if proxy_url == "warp":
      global warp
      if warp is None:
        warp = pymasque.WarpConnection()
      stream = await warp.open_stream(self.hostname, self.port)
      await stream.ensure_response()
      self.tcp_reader, self.tcp_writer = stream, stream
    elif proxy_url:
      proxy = Proxy.from_url(proxy_url, rdns=proxy_dns)
      proxy_dest = self.hostname if proxy_dns else addr_str
      sock = await proxy.connect(dest_host=proxy_dest, dest_port=self.port)
      self.tcp_reader, self.tcp_writer = await asyncio.open_connection(
        limit=tcp_size, 
        sock=sock
      )
    else:
      local_addr = get_source_ip(addr_str)
      self.tcp_reader, self.tcp_writer = await asyncio.open_connection(
        host=addr_str, 
        port=self.port,
        limit=tcp_size,
        local_addr=(local_addr, 0) if local_addr else None,
      )
  
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
    if block_udp:
      raise TypeError("UDP connection blocked.")
    if proxy_url:
      raise NotImplementedError("SOCKS/HTTP proxy is not supported for UDP.")

    addr_str = await validate_hostname(self.hostname, self.port, 0x02)
    local_addr = get_source_ip(addr_str)
    self.socket = await asyncudp.create_socket(
      remote_addr=(addr_str, self.port),
      local_addr=(local_addr, 0) if local_addr else None,
    )
  
  async def recv(self):
    data, addr = await self.socket.recvfrom()
    return data
  
  async def send(self, data):
    self.socket.sendto(data)
  
  def close(self):
    if self.socket is None:
      return
    self.socket.close()