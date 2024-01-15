# Python Wisp Server

This is an implementation of a [Wisp](https://github.com/MercuryWorkshop/wisp-protocol) server, written in Python. It follows the Wisp spec completely, except that it lacks the optional UDP support.

## Running the Server:
Clone this repository and cd into it, then run the following commands to install the needed dependencies.
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

To start the server, run the `main.py` file. You can use the `HOST` and `PORT` environment variables to specify which port and hostname the server listens on.
```
source .venv/bin/activate
PORT=5000 python3 main.py 
```

## Copyright:
This repository is licensed under the GNU AGPL v3.

### Copyright Notice:
```
wisp-server-python: a Wisp server implementation written in Python
Copyright (C) 2024 Mercury Workshop

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