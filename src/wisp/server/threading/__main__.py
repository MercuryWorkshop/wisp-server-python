from wisp.server.threading import http 
from wisp.server import common 

if __name__ == "__main__":
  args = common.setup_main()
  http.main(args)