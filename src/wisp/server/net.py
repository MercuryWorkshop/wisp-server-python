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

def validate_ip(addr_str):
  ip_addr = ipaddress.ip_address(addr_str)
  if block_loopback and ip_addr.is_loopback:
    raise TypeError("Connection to loopback ip address blocked.")
  if block_private and ip_addr.is_private and not ip_addr.is_loopback:
    raise TypeError("Connection to private ip address blocked.")

def validate_hostname(host, port, stream_type):
  addr_str = get_ip(host, port, stream_type)
  validate_ip(addr_str)
  return addr_str

class TCPConnection:
  def __init__(self, hostname, port):
    self.hostname = hostname
    self.port = port
    self.socket = None
  
  def connect(self):
    addr_str = validate_hostname(self.hostname, self.port, 0x01)
    self.socket = socket.socket()
    self.socket.connect((self.hostname, self.port))
  
  def recv(self):
    return self.socket.recv(tcp_size)
  
  def send(self, data):
    self.socket.send(data)
  
  def close(self):
    if self.socket is None:
      return
    self.socket.close()

class UDPConnection:
  def __init__(self, hostname, port):
    self.hostname = hostname
    self.port = port
    self.socket = None
  
  def connect(self):
    addr_str = validate_hostname(self.hostname, self.port, 0x02)
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.bind((self.hostname, self.port))
  
  def recv(self):
    data, addr = self.socket.recvfrom(tcp_size)
    return data
  
  def send(self, data):
    self.socket.sendto(data, (self.hostname, self.port))
  
  def close(self):
    if self.socket is None:
      return
    self.socket.close()