import argparse
import uvloop

import wisp
import wisp.server.http

if __name__ == "__main__":
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
  args = parser.parse_args()

  uvloop.run(wisp.server.http.main(args))
