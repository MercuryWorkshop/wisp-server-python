# Python Wisp Server

This is an implementation of a [Wisp](https://github.com/MercuryWorkshop/wisp-protocol) server, written in Python. It follows the Wisp v1 spec completely, including support for UDP connections.

## Installation:
### Install From Source:
Clone this repository and cd into it, then run the following commands:
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -e .
```

### Install From PyPI:
Run the following command to install this program:
```
pip3 install wisp-python
```

## Running the Server:
For the best performance use [CPython](https://github.com/python/cpython) 3.11 or newer. [PyPy](https://github.com/pypy/pypy) is not recommended as it is a lot slower than CPython here. 

If you are running this server publicly, you should start it with the `--limits` flag to enable rate limits and other anti abuse protections. The `--blacklist` option can also be used to block specific destinations.

To start the server, run `python3 -m wisp.server`. The program accepts the following arguments:
```
usage: wisp-server-python [-h] [--host HOST] [--port PORT] [--static STATIC] [--limits] [--bandwidth BANDWIDTH] [--connections CONNECTIONS] [--max-connections MAX_CONNECTIONS]
                          [--total-connections TOTAL_CONNECTIONS] [--window WINDOW] [--allow-loopback] [--allow-private] [--log-level LOG_LEVEL] [--threads THREADS] [--proxy PROXY] [--block-udp]
                          [--block-tcp] [--blacklist BLACKLIST]

A Wisp server implementation, written in Python (v0.9.0)

options:
  -h, --help            show this help message and exit
  --host HOST           The hostname the server will listen on.
  --port PORT           The TCP port the server will listen on.
  --static STATIC       Where static files are served from.
  --limits              Enable rate limits.
  --bandwidth BANDWIDTH
                        Bandwidth limit per IP, in kilobytes per second.
  --connections CONNECTIONS
                        New connections limit per IP.
  --max-connections MAX_CONNECTIONS
                        Concurrent open connections limit per IP.
  --total-connections TOTAL_CONNECTIONS
                        Concurrent open connections limit across all IPs.
  --window WINDOW       Fixed window length for rate limits, in seconds.
  --allow-loopback      Allow connections to loopback IP addresses.
  --allow-private       Allow connections to private IP addresses.
  --log-level LOG_LEVEL
                        The log level (either debug, info, warning, error, or critical).
  --threads THREADS     The number of threads to run the server on. By default it uses all CPU cores. (Linux only)
  --proxy PROXY         The url of the socks5h, socks5, sock4a, socks4 or http proxy to use.
  --block-udp           Block UDP streams.
  --block-tcp           Block TCP streams.
  --blacklist BLACKLIST
                        The path of a blacklist file with blacklisted destinations. One destination per line, and it can be a hostname, an ip address, or an ip range in cidr notation. Lines starting
                        with # are ignored.
```

## Roadmap:
- ~~Rate limits~~
- JSON based config files
- ~~UDP support~~
- ~~Ability to block local addresses~~
- Wisp v2 support

## Copyright:
This repository is licensed under the GNU AGPL v3.

A few third party libraries are used. See [`LICENSE_third_party.md`](https://github.com/MercuryWorkshop/wisp-server-python/blob/main/LICENSE_third_party.md).

### Copyright Notice:
```
wisp-server-python: a Wisp server implementation written in Python
Copyright (C) 2025 Mercury Workshop

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
