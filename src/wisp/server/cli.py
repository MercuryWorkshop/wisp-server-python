import asyncio
import argparse
import pathlib
import sys
import logging
import multiprocessing

try:
  import uvloop
  use_uvloop = True
except ImportError:
  use_uvloop = False

import wisp
from wisp.server import http 
from wisp.server import net

def run_async(func, *args, **kwargs):
  try:
    if use_uvloop:
      uvloop.run(func(*args, **kwargs))
    else:
      #uvloop doesn't support windows at all so we don't need to print the error
      if not sys.platform in ("win32", "cygwin"):
        logging.error("Importing uvloop failed. Falling back to asyncio, which is slower.")
      asyncio.run(func(*args, **kwargs))
  except KeyboardInterrupt:
    pass

def run_http(args):
  run_async(http.main, args)

def main():
  parser = argparse.ArgumentParser(
    prog="wisp-server-python",
    description=f"A Wisp server implementation, written in Python (v{wisp.version})"
  )

  parser.add_argument("--host", default="127.0.0.1", help="The hostname the server will listen on.")
  parser.add_argument("--port", default=6001, help="The TCP port the server will listen on.")
  parser.add_argument("--static", help="Where static files are served from.")
  parser.add_argument("--limits", action="store_true", help="Enable rate limits.")
  parser.add_argument("--bandwidth", default=1000, help="Bandwidth limit per IP, in kilobytes per second.")
  parser.add_argument("--connections", default=30, help="New connections limit per IP.")
  parser.add_argument("--window", default=60, help="Fixed window length for rate limits, in seconds.")
  parser.add_argument("--allow-loopback", action="store_true", help="Allow connections to loopback IP addresses.")
  parser.add_argument("--allow-private", action="store_true", help="Allow connections to private IP addresses.")
  parser.add_argument("--log-level", default="info", help="The log level (either debug, info, warning, error, or critical).")
  parser.add_argument("--threads", default=0, help="The number of threads to run the server on. By default it uses all CPU cores.")
  args = parser.parse_args()

  logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=getattr(logging, args.log_level.upper()),
    datefmt="%Y/%m/%d - %H:%M:%S"
  )

  logging.info(f"running wisp-server-python v{wisp.version} (async)")
  if args.static:
    static_path = pathlib.Path(args.static).resolve()
    logging.info(f"serving static files from {static_path}")
  if args.limits:
    logging.info("enabled rate limits")
  logging.info(f"listening on {args.host}:{args.port}")

  threads = int(args.threads)
  if net.reuse_port_supported():
    if threads == 0:
      threads = multiprocessing.cpu_count()
    logging.info(f"running using {threads} threads")

    processes = []
    for i in range(0, int(threads)):
      process = multiprocessing.Process(target=run_http, args=(args,), daemon=True)
      processes.append(process)
      process.start()
    try:
      for process in processes:
        process.join()
    except KeyboardInterrupt:
      pass
  
  else:
    if threads != 0:
      logging.warn("the --threads option is not supported on this platform")
    run_http(args)