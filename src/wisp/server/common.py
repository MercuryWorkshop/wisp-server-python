import argparse
import logging

import wisp

def setup_main():
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
  parser.add_argument("--allow-loopback", action="store_true",help="Allow connections to loopback IP addresses.")
  parser.add_argument("--allow-private", action="store_true", help="Allow connections to private IP addresses.")
  parser.add_argument("--log-level", default="info", help="The log level (either debug, info, warning, error, or critical).")
  args = parser.parse_args()

  logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=getattr(logging, args.log_level.upper()),
    datefmt="%Y/%m/%d - %H:%M:%S"
  )

  return args