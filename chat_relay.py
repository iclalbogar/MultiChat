import socket
import threading

# This is the address of the main chat server we want to connect to.
MAIN_SERVER_HOST = '127.0.0.1'
MAIN_SERVER_PORT = 12345

# This is the port this relay program will listen on.
# Our clients will connect to this port instead of the main server.
RELAY_HOST = '127.0.0.1'
RELAY_PORT = 9999 # Must be different from the main server port


def forward_data(source_socket, dest_socket, direction_name):
    """
    Reads data from one socket and sends it to the other.
    This function will run in a thread.
    """
    try:
        while True:
            # Read data from the source socket
            data = source_socket.recv(4096)
            
            if not data:
                # If we receive no data, the other side has closed the connection
                print(f"Connection closed ({direction_name}).")
                break
            
            # Send the data to the destination socket
            dest_socket.sendall(data)
            
    except OSError as e:
        # This error often happens when the other thread closes the socket first
        print(f"Socket error ({direction_name}): {e}")
    except Exception as e:
        print(f"Forwarding error ({direction_name}): {e}")
    finally:
        # When one direction (e.g., client-to-server) breaks,
        # we must close both sockets to stop the other thread as well.
        print(f"Forwarding stopped for {direction_name}. Closing sockets.")
        try:
            source_socket.close()
        except:
            pass
        try:
            dest_socket.close()
        except:
            pass

def handle_relay_session(client_socket, client_address):
    """
    Manages the entire relay session between one client and the main server.
    This runs in a new thread for each client.
    """
    print(f"Client {client_address} connected. Connecting to main server ({MAIN_SERVER_HOST}:{MAIN_SERVER_PORT})...")
    
    server_socket = None
    try:
        # 1. Connect to the main chat server (server.py)
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((MAIN_SERVER_HOST, MAIN_SERVER_PORT))
        print(f"Successfully connected to main server.")
        
        # 2. Get the first message from the client, which must be the nickname.
        nickname_data = client_socket.recv(1024)
        if not nickname_data:
            print("Client disconnected before sending a nickname.")
            return

        nickname = nickname_data.decode('utf-8')
        
        # 3. This is the relay's special job: add a '*' to the nickname.
        modified_nickname = f"*{nickname}"
        print(f"Received nickname: '{nickname}'. Sending '{modified_nickname}' to server.")

        # 4. Send the modified nickname to the main server.
        server_socket.sendall(modified_nickname.encode('utf-8'))
        
        # 5. Now, we start forwarding data in both directions.
        # We create a new thread for the Client -> Server direction.
        c_to_s_thread = threading.Thread(target=forward_data, 
                                         args=(client_socket, server_socket, "Client -> Server"),
                                         daemon=True)
        
        # We use the current thread for the Server -> Client direction.
        # This keeps the handle_relay_session function alive
        # until the server-to-client connection breaks.
        print("Starting two-way data forwarding.")
        c_to_s_thread.start()
        forward_data(server_socket, client_socket, "Server -> Client")

    except Exception as e:
        print(f"Error during relay session: {e}")
    finally:
        # When the 'forward_data' function (in this thread) ends,
        # we know the session is over, so we clean up both sockets.
        print(f"Ending relay session for {client_address}.")
        if client_socket:
            client_socket.close()
        if server_socket:
            server_socket.close()

def main():
    """
    The main function that starts the relay server.
    """
    relay_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # This setting allows the program to restart quickly
    # without waiting for the port to be free.
    relay_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        relay_server.bind((RELAY_HOST, RELAY_PORT))
        relay_server.listen()
        print(f"Chat Relay Server listening on {RELAY_HOST}:{RELAY_PORT}...")
        print(f"Clients should connect here. Relaying to {MAIN_SERVER_HOST}:{MAIN_SERVER_PORT}.")
        
        while True:
            # Wait for a new client to connect.
            client_socket, client_address = relay_server.accept()
            
            # Start a new thread to handle this client's session.
            # 'daemon=True' means the thread will close when the main program stops.
            session_thread = threading.Thread(target=handle_relay_session, 
                                              args=(client_socket, client_address),
                                              daemon=True)
            session_thread.start()
            
    except OSError as e:
        print(f"Could not start server (Is port {RELAY_PORT} already in use?): {e}")
    except KeyboardInterrupt:
        print("\nShutting down relay server...")
    finally:
        relay_server.close()
        print("Relay server shut down.")

if __name__ == "__main__":
    main()