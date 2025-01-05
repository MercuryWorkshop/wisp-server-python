import argparse
import asyncio
import sys

try:
  import uvloop
  use_uvloop = True
except ImportError:
  use_uvloop = False

from wisp.server import http 
from wisp.server import common 

if __name__ == "__main__":
  args = common.setup_main()

  try:
    if use_uvloop:
      uvloop.run(http.main(args))
    else:
      #uvloop doesn't support windows at all so we don't need to print the error
      if not sys.platform in ("win32", "cygwin"):
        logging.error("Importing uvloop failed. Falling back to asyncio, which is slower.")
      asyncio.run(http.main(args))
  except KeyboardInterrupt:
    pass