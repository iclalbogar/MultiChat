
# MultiChat Project

`MultiChat` is a feature-rich chat server and client project built with Python. It started as a simple multi-user chat room and grew to include a graphical user interface (GUI), private messaging, and real-time web monitoring tools.

## Features

* **GUI Client:** A user-friendly graphical client built with `tkinter`.
* **Multi-User Chat:** A central server that broadcasts messages to all connected clients.
* **Private Messaging (PM):** Double-click a user's name to open a new window for a private conversation.
* **Live Web Monitor:** A built-in web server (HTTP + WebSocket) that serves a web page. Anyone with a browser can visit `http://127.0.0.1:8000` to see a live feed of all chat activity (joins, leaves, public messages, and PM notifications).
* **Spam Protection:** The server includes rate-limiting to automatically disconnect clients who send too many messages too quickly.
* **Relay Server (Optional):** A separate `chat_relay.py` script that acts as a proxy. It modifies the user's nickname (adds a `*`) before passing them to the main server.
* **Server Stats:** The server console prints performance statistics, such as the number of connected clients and total messages processed.

## Requirements

* Python 3 (Developed on 3.10, but any modern Python 3 version should work)
* The `websockets` Python library

To install the only dependency, open your terminal and run:

```bash
pip install websockets
```
> **Note:** If you have multiple Python versions, you might need to use `python -m pip install websockets`.

## Execution Guide (How to Run)

There are three main parts to this project. You must start the server first.

### 1. The Main Server (server.py)

This is the heart of the project. It handles all chat messages, web connections, and monitoring. You must run this file first.

1.  Open your terminal in the project folder.
2.  Run the server:
    ```bash
    python server.py
    ```
3.  The server is now running and will print status messages to the console.

The server starts three services at once:

* **Main Chat (TCP):** Listens on port `12345` for the GUI clients.
* **Web Interface (HTTP):** Listens on port `8000`.
* **Live Feed (WebSocket):** Listens on port `8765` (used by the web interface).

---

### 2. The GUI Client (gui_client.py)

This is the chat program for users. You can run many copies of this file at the same time to simulate multiple users.

1.  Make sure the `server.py` is running.
2.  In a new terminal, run the client:
    ```bash
    python gui_client.py
    ```
3.  When the program opens, fill in the connection details:
    * **Nickname:** Any name you want (e.g., `iclal`)
    * **Server:** `127.0.0.1` (to connect to your local server)
    * **Port:** `12345` (to connect to the main TCP server)
4.  Click "Connect" and start chatting!

---

### 3. The Relay Server (Optional) (chat_relay.py)

This is an optional proxy server that adds a `*` to a user's nickname. It's a fun way to show how a proxy can sit between the client and server.

To use it:

1.  Make sure `server.py` is running (the relay needs to connect to it).
2.  In a new terminal, start the relay server:
    ```bash
    python chat_relay.py
    ```
3.  (The relay will listen on port `9999`)
4.  Now, open a new `gui_client.py`.
5.  To connect through the relay, use these settings:
    * **Nickname:** `relay_user`
    * **Server:** `127.0.0.1`
    * **Port:** `9999` (This time, connect to the relay's port)

When you connect, you will appear in the chat as `*relay_user` to everyone.

---

## Configuration (Ports & IP)

This project uses constants at the top of each file instead of command-line arguments. To change the ports or host IP, you can edit the files directly.

* `server.py`: Change `TCP_PORT`, `HTTP_PORT`, or `WEBSOCKET_PORT`.
* `chat_relay.py`: Change `RELAY_PORT` (the port it listens on) or `MAIN_SERVER_PORT` (the port it connects to).
* `gui_client.py`: The default port `12345` is just pre-filled in the text box. You can type any port you want to connect to.
