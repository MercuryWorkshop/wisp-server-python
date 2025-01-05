import socket
import ipaddress

#various network utilities and wrappers - synchronous version

from wisp.server import net

def validate_hostname(host, port, stream_type):
  addr_str = net.get_ip(host, port, stream_type)
  net.validate_ip(addr_str)
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
    return self.socket.recv(net.tcp_size)
  
  def send(self, data):
    self.socket.send(data)
  
  def close(self):
    if self.socket is None:
      return
    self.socket.shutdown(socket.SHUT_RDWR)
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
    data, addr = self.socket.recvfrom(net.tcp_size)
    return data
  
  def send(self, data):
    self.socket.sendto(data, (self.hostname, self.port))
  
  def close(self):
    if self.socket is None:
      return
    self.socket.shutdown(socket.SHUT_RDWR)
    self.socket.close()