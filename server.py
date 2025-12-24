import socket
import threading
import logging
import time
import http.server
import socketserver
import asyncio
import websockets
import json

#Server Ports
TCP_PORT = 12345        # Main port for the chat application (TCP)
HTTP_PORT = 8000        # Port for the web interface (serves index.html)
WEBSOCKET_PORT = 8765   # Port for the WebSocket (provides the live feed)

# Set up the loggger to write to a file
logging.basicConfig(filename='chat.log', level=logging.INFO, 
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

#Global Settings
HOST = '127.0.0.1'

# Rate Limiting: 10 messages every 5 seconds
RATE_LIMIT_MESSAGES = 10
RATE_LIMIT_SECONDS = 5

#Global State

# Stores active TCP clients. Format: { socket: "nickname" }
clients = {}

# Tracks message timestamps for each client for rate limiting.
# Format: { socket: [timestamp1, timestamp2, ...] }
client_message_times = {}

# Performance counters
total_messages_processed = 0
stats_lock = threading.Lock() # A lock to make counter changes thread-safe
server_running = True         # A flag to signal background threads to stop

# This set holds all connected web (browser) clients.
WEB_CLIENTS = set()
# We need to store the asyncio event loop for the WebSocket server.
WS_LOOP = None


def broadcast_to_web(message_data_dict):
    """
    Sends a message (as a dict) to all connected web clients (browsers).
    This function must be thread-safe.
    """
    global WS_LOOP, WEB_CLIENTS
    
    # If the WebSocket server isn't ready or has no clients, do nothing.
    if not WS_LOOP or not WEB_CLIENTS:
        return

    # Convert the Python dict to a JSON string.
    message_json = json.dumps(message_data_dict)
    
    # We are in a TCP thread, but we need to send data on the
    # asyncio loop (which is in another thread).
    # 'run_coroutine_threadsafe' is the correct way to do this.
    
    disconnected_clients = set()
    
    # We send to a copy of the set, so we can remove clients
    # if they disconnect while we are looping.
    for client in WEB_CLIENTS.copy():
        try:
            # Schedule the send task for each client.
            coro = client.send(message_json)
            asyncio.run_coroutine_threadsafe(coro, WS_LOOP)
        except Exception:
            # If sending fails that client is probably disconnected.
            disconnected_clients.add(client)
    
    # Remove any clients that failed from the main list.
    if disconnected_clients:
        for client in disconnected_clients:
            WEB_CLIENTS.discard(client)

def start_http_server():
    #Starts a simple HTTP server in a new thread to serve index.html
    try:
        # Use the built-in simple HTTP handler.
        Handler = http.server.SimpleHTTPRequestHandler
        
        # This allows the server to reuse the port quickly after a restart
        socketserver.TCPServer.allow_reuse_address = True
        
        httpd = socketserver.TCPServer((HOST, HTTP_PORT), Handler)
        
        print(f"HTTP server started -> http://{HOST}:{HTTP_PORT} (Web Interface)")
        httpd.serve_forever()
    except Exception as e:
        print(f"Could not start HTTP server: {e}")
        logging.error(f"HTTP server error: {e}")

async def web_client_handler(websocket, path):
    """Handles a new connection from a web (browser) client."""
    global WEB_CLIENTS
    try:
        # Add the new client to our set of web clients.
        WEB_CLIENTS.add(websocket)
        print(f"Web Monitor: New viewer connected. (Total: {len(WEB_CLIENTS)})")
        
        # Wait until the client disconnects.
        await websocket.wait_closed()
    except Exception as e:
        logging.warning(f"WebSocket client error: {e}")
    finally:
        # Remove the client from the set when they disconnect.
        WEB_CLIENTS.discard(websocket)
        print(f"Web Monitor: A viewer disconnected. (Remaining: {len(WEB_CLIENTS)})")

def start_websocket_server():
    """Starts the WebSocket server in its own thread and asyncio loop."""
    global WS_LOOP
    try:
        # Create a new event loop for this thread.
        WS_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(WS_LOOP)
        
        # Set up the WebSocket server.
        start_server = websockets.serve(web_client_handler, HOST, WEBSOCKET_PORT)
        
        # Run the server forever.
        print(f"WebSocket server started -> ws://{HOST}:{WEBSOCKET_PORT} (Live Feed)")
        WS_LOOP.run_until_complete(start_server)
        WS_LOOP.run_forever()
    except Exception as e:
        print(f"Could not start WebSocket server: {e}")
        logging.error(f"WebSocket server error: {e}")


# --- TCP Chat Server Functions ---

def print_stats():
    """Prints the current server status to the console."""
    with stats_lock:
        current_messages = total_messages_processed
    
    # Getting the length of a dict is thread-safe.
    current_clients = len(clients)
    
    print(f"\n--- STATUS: [Connected TCP Clients: {current_clients}] - [Total Messages Processed: {current_messages}] ---")

def periodic_stats_printer():
    """A thread function that prints stats every 30 seconds."""
    global server_running
    wait_time = 30

    while server_running:
        # We sleep in 1-second chunks
        # so we can check 'server_running' flag often.
        # This allows for a fast shutdown.
        for _ in range(wait_time):
            if not server_running:
                return # Exit the thread
            time.sleep(1)
        
        if server_running:
            print_stats()

def get_user_list_string():
    #Returns a comma-separated string of all nicknames
    if not clients:
        return ""
    return ",".join(list(clients.values()))

def broadcast(message, current_client=None):
    #Sends a message to all connected clients except the sender
    # We iterate over a list copy, in case 'clients' changes.
    for client_socket in list(clients.keys()):
        if client_socket != current_client:
            try:
                client_socket.send(message)
            except Exception as e:
                # The client probably disconnected unexpectedly.
                print(f"Broadcast error: {e}. Removing client.")
                logging.warning(f"Broadcast error: {e}. Removing client.")
                remove_client(client_socket)

def broadcast_user_list():
    """Sends the updated user list to all clients."""
    user_list_str = get_user_list_string()
    message = f"USERLIST_UPDATE:{user_list_str}".encode('utf-8')
    print(f"Broadcasting user list: {user_list_str}")
    broadcast(message)

def remove_client(client_socket):
    """Safely removes a client from the server."""
    if client_socket in clients:
        # Remove from all our tracking dictionaries
        nickname = clients.pop(client_socket)
        client_message_times.pop(client_socket, None)
        client_socket.close()
        
        leave_message = f"{nickname} has left the chat."
        print(leave_message)
        logging.info(leave_message)
        
        # Tell everyone the user has left
        broadcast(leave_message.encode('utf-8'))
        broadcast_user_list()
        
        # Print updated stats
        print("\nClient disconnected, updating stats:")
        print_stats()
        
        # Also update the web monitor
        broadcast_to_web({"type": "system", "content": leave_message})

def handle_client(client):
    """
    This function runs in a new thread for each connected TCP client.
    It manages the client's entire session.
    """
    nickname = None
    try:
        # The first message from a client must be their nickname.
        nickname = client.recv(1024).decode('utf-8')
        
        # Check if the nickname is valid or already taken.
        if not nickname or nickname in clients.values():
            client.send("ERROR: This nickname is already in use or is invalid. Please reconnect with a different name.".encode('utf-8'))
            client.close()
            return
            
        # Add the new client to our lists
        clients[client] = nickname
        client_message_times[client] = []
        
        join_message = f"{nickname} has joined the chat."
        print(join_message)
        logging.info(join_message)
        
        # Send confirmation to the client and notify others
        client.send("You are connected to the server!".encode('utf-8'))
        broadcast(join_message.encode('utf-8'), current_client=client)
        broadcast_user_list()

        # Update stats and web monitor
        print("\nNew client connected, updating stats:")
        print_stats()
        broadcast_to_web({"type": "system", "content": join_message})

        # Main loop for listening to this client's messages
        while True:
            message = client.recv(1024)
            if not message:
                # Empty message means the client disconnected.
                break 

            # --- RATE LIMITING CHECK ---
            now = time.time()
            timestamps = client_message_times.get(client, [])
            
            # Keep only timestamps from the last 5 seconds.
            recent_timestamps = [t for t in timestamps if (now - t) <= RATE_LIMIT_SECONDS]
            
            # Check if they exceeded the 10-message limit.
            if len(recent_timestamps) >= RATE_LIMIT_MESSAGES:
                print(f"--- WARNING: {nickname} exceeded the rate limit. Disconnecting. ---")
                logging.warning(f"RATE LIMIT: {nickname} disconnected for spamming.")
                try:
                    client.send("[System] You have exceeded the rate limit. Disconnecting.".encode('utf-8'))
                except Exception as e:
                    logging.warning(f"Could not send rate limit message to {nickname}: {e}")
                
                break # Break loop to disconnect the client.
            
            # Add this message's timestamp to the list.
            recent_timestamps.append(now)
            client_message_times[client] = recent_timestamps
            # --- END OF RATE LIMITING ---
            
            # Count this message (it was not spam).
            with stats_lock:
                global total_messages_processed
                total_messages_processed += 1
            
            decoded_message = message.decode('utf-8').strip()

            # Handle the 'EXIT' command.
            if decoded_message.upper() == 'EXIT':
                print(f"{nickname} sent 'Exit' command. Closing connection.")
                logging.info(f"{nickname} sent 'Exit' command.")
                break 
            
            # Handle private messages (PM).
            elif decoded_message.upper().startswith('PM '):
                try:
                    # Expected format: "PM <target_user> <message>"
                    parts = decoded_message.split(' ', 2)
                    
                    if len(parts) < 3:
                        client.send("[System] Invalid PM format. Use: PM <username> <message>".encode('utf-8'))
                        continue
                    
                    target_nickname = parts[1]
                    message_text = parts[2]
                    sender_nickname = clients[client]

                    if target_nickname == sender_nickname:
                        client.send("[System] You cannot send a private message to yourself.".encode('utf-8'))
                        continue

                    # Find the target user's socket.
                    target_socket = None
                    for sock, nick in clients.items():
                        if nick == target_nickname:
                            target_socket = sock
                            break
                    
                    if target_socket:
                        # Send the PM to the target.
                        pm_to_send = f"[Private Message] {sender_nickname}: {message_text}".encode('utf-8')
                        target_socket.send(pm_to_send)
                        
                        # Send confirmation back to the sender.
                        client.send(f"[System] Your message was sent to {target_nickname}.".encode('utf-8'))
                        logging.info(f"Private Message: {sender_nickname} -> {target_nickname}")
                        
                        # Notify the web monitor that a PM happened (but not the content).
                        broadcast_to_web({"type": "private", "sender": sender_nickname, "receiver": target_nickname})
                    else:
                        # Target user was not found.
                        client.send(f"[System] Error: User '{target_nickname}' not found.".encode('utf-8'))

                except Exception as e:
                    print(f"Error processing PM: {e}")
                    client.send("[System] An error occurred while sending your PM.".encode('utf-8'))
            
            # Handle regular public messages.
            else:
                full_message = f"{nickname}: {decoded_message}"
                print(f"Received: {full_message}")
                logging.info(f"Message: {full_message}")
                
                # Broadcast to all other TCP clients.
                broadcast(full_message.encode('utf-8'), current_client=client)
                
                # Broadcast to all web monitor clients.
                broadcast_to_web({"type": "public", "content": full_message})

    except Exception as e:
        # Handle unexpected disconnects (e.g., "Connection reset by peer")
        if "Connection reset by peer" not in str(e) and "forcibly closed" not in str(e):
             print(f"Error: {e}")
             logging.error(f"Client {nickname} error: {e}")
    finally:
        # This code runs whether the client exits, errors, or is kicked.
        remove_client(client)

def main():
    """
    Main function to start all three servers (TCP, HTTP, WebSocket)
    and manage the main application loop.
    """
    global server_running
    server_running = True
    
    # Start the HTTP server in a background thread.
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Start the WebSocket server in a background thread.
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()
    
    # Start the statistics printer in a background thread.
    stats_thread = threading.Thread(target=periodic_stats_printer, daemon=True)
    stats_thread.start()
    print("Stats monitor started (updates every 30s).")
    
    # Set up the main TCP chat server.
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.bind((HOST, TCP_PORT))
    tcp_server.listen()
    print(f"Main TCP Chat Server listening on {HOST}:{TCP_PORT}...")
    
    try:
        # This is the main loop, it just accepts new clients.
        while True:
            client, address = tcp_server.accept()
            print(f"New TCP connection accepted from {address}.")
            logging.info(f"New TCP connection accepted from {address}.")
            
            # Start a new thread to handle this client's session.
            thread = threading.Thread(target=handle_client, args=(client,))
            thread.daemon = True
            thread.start()
            
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        logging.info("Server shutting down (KeyboardInterrupt).")
        server_running = False # Signal background threads to stop
    except Exception as e:
        logging.error(f"Main TCP server loop error: {e}")
    finally:
        # Clean up all client connections when the server stops.
        for client_socket in list(clients.keys()):
            try:
                client_socket.send("Server is shutting down. Disconnecting.".encode('utf-8'))
                client_socket.close()
            except Exception as e:
                logging.warning(f"Error closing client socket: {e}")
        
        tcp_server.close()
        print("Server shut down complete.")

if __name__ == "__main__":
    main()