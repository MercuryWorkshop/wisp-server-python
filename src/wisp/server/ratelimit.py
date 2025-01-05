import asyncio
import time

#this file contains some helper functions for rate limiting
#rate limiting uses a fixed window strategy for simplicity

active_clients = {}
enabled = False

#max new streams per ip per minute
connections_limit = 30
#bandwidth limits per ip in kilobytes per second
bandwidth_limit = 100
#fixed window size, in seconds
window_size = 60

#rate limiting helper functions
def init_client(client_ip):
  if not client_ip in active_clients:
    active_clients[client_ip] = {
      "streams": 0, #number of newly created streams
      "tcp": 0, #total tcp to ws traffic
      "ws": 0, #total ws to tcp traffic
      "start": time.time()
    }

def get_client_attr(client_ip, attr):
  init_client(client_ip)
  return active_clients[client_ip][attr]

def set_client_attr(client_ip, attr, value):
  init_client(client_ip)
  active_clients[client_ip][attr] = value

def inc_client_attr(client_ip, attr, amount=1):
  set_client_attr(client_ip, attr, get_client_attr(client_ip, attr) + amount)

def calculate_client_bandwidth(client_ip, attr):
  start_time = get_client_attr(client_ip, "start")
  total_data = get_client_attr(client_ip, attr)
  now = time.time()
  return total_data / (now - start_time) / 1000

async def limit_client_bandwidth(client_ip, length, attr):
  if not enabled: return
  inc_client_attr(client_ip, attr, length)
  while calculate_client_bandwidth(client_ip, attr) > bandwidth_limit:
    await asyncio.sleep(0.01)

async def reset_limits_timer():
  global active_clients
  while True:
    active_clients = {}
    await asyncio.sleep(window_size)

def limit_client_bandwidth_sync(client_ip, length, attr):
  if not enabled: return
  inc_client_attr(client_ip, attr, length)
  while calculate_client_bandwidth(client_ip, attr) > bandwidth_limit:
    time.sleep(0.01)

def reset_limits_timer_sync():
  global active_clients
  while True:
    active_clients = {}
    time.sleep(window_size)
