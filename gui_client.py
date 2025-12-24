import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog
import socket
import threading
import sys
import re # Used for parsing private message strings

class ChatClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MultiChat Client")
        self.root.geometry("600x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.nickname = None
        self.client_socket = None
        self.running = False
        self.receive_thread = None
        
        # This dictionary keeps track of any open Private Message (PM) windows.
        # Format: { 'username': {'window': Toplevel, 'chat_area': ScrolledText} }
        self.pm_windows = {}

        # --- Connection Frame ---
        self.connection_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        self.connection_frame.pack(fill=tk.X, padx=5, pady=5)
        
        server_frame = ttk.Frame(self.connection_frame)
        server_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(server_frame, text="Server:").pack(side=tk.LEFT, padx=(0,5))
        self.host_entry = ttk.Entry(server_frame)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,10))
        ttk.Label(server_frame, text="Port:").pack(side=tk.LEFT, padx=(0,5))
        self.port_entry = ttk.Entry(server_frame, width=10)
        self.port_entry.insert(0, "12345") # Default TCP port
        self.port_entry.pack(side=tk.LEFT, padx=(0,5))
        
        nickname_frame = ttk.Frame(self.connection_frame)
        nickname_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(nickname_frame, text="Nickname:").pack(side=tk.LEFT, padx=(0,5))
        self.nickname_entry = ttk.Entry(nickname_frame)
        self.nickname_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
        self.connect_button = ttk.Button(nickname_frame, text="Connect", command=self.connect_to_server)
        self.connect_button.pack(side=tk.RIGHT, padx=(5,0))
        
        # --- Chat Frame ---
        self.chat_frame = ttk.LabelFrame(self.root, text="Chat", padding=10)
        self.chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # The main text area where messages appear
        self.messages_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=20)
        self.messages_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.messages_area.config(state=tk.DISABLED)
        
        # The listbox for showing who is online
        self.users_frame = ttk.LabelFrame(self.chat_frame, text="Online Users")
        self.users_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        self.users_list = tk.Listbox(self.users_frame, height=6)
        self.users_list.pack(fill=tk.BOTH, expand=True)
        # Bind the double-click event to open a private message
        self.users_list.bind('<Double-Button-1>', self.open_pm_from_list)
        
        # --- Message Input Frame ---
        self.input_frame = ttk.Frame(self.chat_frame)
        self.input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.message_entry = ttk.Entry(self.input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.config(state=tk.DISABLED)
        
        self.send_button = ttk.Button(self.input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)
        self.send_button.config(state=tk.DISABLED)
        
        # Bind the Enter key to the send_message function
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def connect_to_server(self):
        """This function is called when the 'Connect' button is pressed."""
        if self.running:
            return
        try:
            host = self.host_entry.get().strip()
            port_str = self.port_entry.get().strip()
            nickname = self.nickname_entry.get().strip()
            port = int(port_str)

            if not nickname:
                self.add_message("System", "Please enter a nickname!")
                return
            
            if self.client_socket:
                try: self.client_socket.close()
                except: pass
            
            # Create a new socket and try to connect
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(5) # 5 second timeout for connection
            self.client_socket.connect((host, port))
            self.client_socket.settimeout(None) # Set back to blocking mode
            
            # Send our nickname as the first message
            self.client_socket.send(nickname.encode('utf-8'))
            
            # Wait for the server's first response
            response = self.client_socket.recv(1024).decode('utf-8')
            
            # Check if the server sent an error (e.g., nickname taken)
            if response.startswith("ERROR:"):
                self.add_message("System", response.split(":", 1)[1].strip())
                self.client_socket.close()
                self.client_socket = None
                return
            
            # If the server's response is the welcome message, we are in!
            if "You are connected to the server!" in response:
                
                # Special check: if we used the relay port (9999), 
                # our server-side nickname will have a '*'. We update our local one to match.
                if port_str == "9999" and not nickname.startswith('*'):
                    self.nickname = f"*{nickname}"
                else:
                    self.nickname = nickname
                    
                self.running = True
                
                # Update the UI: disable connection fields, enable chat fields
                self.connect_button.config(text="Connected", state=tk.DISABLED)
                self.host_entry.config(state=tk.DISABLED)
                self.port_entry.config(state=tk.DISABLED)
                self.nickname_entry.config(state=tk.DISABLED)
                self.message_entry.config(state=tk.NORMAL)
                self.send_button.config(state=tk.NORMAL)
                
                # Start the thread that listens for new messages
                self.receive_thread = threading.Thread(target=self.receive_messages)
                self.receive_thread.daemon = True
                self.receive_thread.start()
                
                self.root.title(f"MultiChat Client - {self.nickname}")
                self.add_message("System", response) # Show the "You are connected..." message
            else:
                self.add_message("System", f"Unexpected response from server: {response}")
                self.client_socket.close()
                self.client_socket = None
            
        except ValueError:
            self.add_message("System", "Invalid port number!")
        except ConnectionRefusedError:
            self.add_message("System", "Connection refused! Is the server running?")
        except socket.timeout:
            self.add_message("System", "Connection timed out.")
        except Exception as e:
            self.add_message("System", f"Connection error: {str(e)}")
        
        if not self.running and self.client_socket:
            self.client_socket.close()
            self.client_socket = None
    
    def send_message(self):
        """Sends the content of the main message entry box."""
        if not self.running:
            return
            
        message = self.message_entry.get().strip()
        if message:
            try:
                # Handle the 'exit' command
                if message.lower() == 'exit':
                    self.client_socket.send('EXIT'.encode('utf-8'))
                    self.disconnect() 
                else:
                    # Send the raw message to the server
                    self.client_socket.send(message.encode('utf-8'))
                    
                    # If we're sending a PM from the main window (e.g., "PM iclal hello")
                    # we should also open/update our local PM window.
                    if message.upper().startswith("PM "):
                        try:
                            parts = message.split(' ', 2)
                            target_user = parts[1]
                            pm_text = parts[2]
                            self.root.after(0, self.handle_outgoing_pm, target_user, pm_text)
                        except IndexError:
                             # User typed "PM user" with no message.
                             # We still send it; the server will handle the error.
                             pass
                        except Exception as e:
                            print(f"Could not parse outgoing PM: {e}")
                    else:
                        # This is a public message, so add it to our own screen right away.
                        self.add_message(self.nickname, message) 
                
                self.message_entry.delete(0, tk.END)
                
            except Exception as e:
                self.add_message("System", f"Could not send message: {e}")
                self.disconnect()
                
    def receive_messages(self):
        """
        This function runs in a separate thread and continuously
        listens for all messages from the server.
        """
        while self.running:
            try:
                message = self.client_socket.recv(1024).decode('utf-8')
                if not message:
                    if self.running:
                        self.root.after(0, self.add_message, "System", "Disconnected from server.")
                    break
                
                # Check if it's a private message
                if message.startswith("[Private Message] "):
                    match = re.match(r"\[Private Message\] (.*?): (.*)", message, re.DOTALL)
                    if match:
                        sender = match.group(1)
                        pm_text = match.group(2)
                        # Pass this to the PM handler
                        self.root.after(0, self.handle_incoming_pm, sender, pm_text)
                    else:
                        # If format is wrong, just print it to the main window
                        self.root.after(0, self.add_message, "", message)
                
                # Check if it's a user list update
                elif message.startswith("USERLIST_UPDATE:"):
                    user_list_csv = message.split(":", 1)[1]
                    clients = user_list_csv.split(",") if user_list_csv else []
                    self.root.after(0, self.update_users_list, clients)
                
                # Check for a critical error message from the server
                elif message.startswith("ERROR:"):
                    error_msg = message.split(":", 1)[1].strip()
                    self.root.after(0, self.add_message, "System", f"Error: {error_msg}")
                    break # Stop the loop and disconnect
                
                # Handle all other messages
                else:
                    # This handles:
                    # "Esra has joined the chat."
                    # "Esra: hello"
                    # "[System] Your message was sent to Iclal." (PM confirmation)
                    # "[System] Error: User 'X' not found." (PM error)
                    # We just pass them to add_message to be printed as-is.
                    self.root.after(0, self.add_message, "", message)
                    
            except ConnectionError:
                if self.running:
                    self.root.after(0, self.add_message, "System", "Connection was lost.")
                break
            except Exception as e:
                if self.running:
                    self.root.after(0, self.add_message, "System", f"Client message processing error: {str(e)}")
                break # Stop loop on any processing error
        
        # This will run if the loop breaks (disconnect, error, etc.)
        self.root.after(0, self.disconnect)
    
    def update_users_list(self, users):
        """Clears and repopulates the 'Online Users' list."""
        self.users_list.delete(0, tk.END)
        for user in sorted(users):
            if user: # Avoid blank entries
                self.users_list.insert(tk.END, user)
    
    def add_message(self, sender, message):
        """
        Adds a formatted message to the main chat window.
        This function is thread-safe because it's called with root.after().
        """
        # We must enable the text area to add text, then disable it again.
        self.messages_area.config(state=tk.NORMAL)
        
        if sender == "System":
            self.messages_area.insert(tk.END, f"[System]: {message}\n")
        elif sender == self.nickname:
            self.messages_area.insert(tk.END, f"{self.nickname} (You): {message}\n")
        elif sender == "":
            # This is for raw messages from the server (e.g., "Iclal: Hi")
            self.messages_area.insert(tk.END, f"{message}\n")
        
        self.messages_area.see(tk.END) # Scroll to the bottom
        self.messages_area.config(state=tk.DISABLED)

    # --- Private Message (PM) Functions ---

    def open_pm_from_list(self, event):
        """Called when a user is double-clicked in the list."""
        try:
            selected_indices = self.users_list.curselection()
            if not selected_indices:
                return
            
            selected_user = self.users_list.get(selected_indices[0])
            
            if selected_user == self.nickname:
                self.add_message("System", "You cannot open a PM window with yourself.")
                return
            
            # If the window is already open, just focus it.
            if selected_user in self.pm_windows:
                self.pm_windows[selected_user]['window'].lift()
                self.pm_windows[selected_user]['window'].focus()
            else:
                # Otherwise, create a new PM window.
                self.create_pm_window(selected_user)
                
        except Exception as e:
            print(f"Error opening PM window: {e}")

    def create_pm_window(self, target_user):
        """Creates a new Toplevel window for a private chat."""
        
        pm_window = tk.Toplevel(self.root)
        pm_window.title(f"Private Message: {target_user}")
        pm_window.geometry("400x300")
        
        chat_area = scrolledtext.ScrolledText(pm_window, wrap=tk.WORD, height=15)
        chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        chat_area.config(state=tk.DISABLED)
        
        input_frame = ttk.Frame(pm_window)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        message_entry = ttk.Entry(input_frame)
        message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Use lambda to pass arguments to the send_pm function
        send_button = ttk.Button(input_frame, text="Send", 
                                 command=lambda: self.send_pm(target_user, message_entry))
        send_button.pack(side=tk.RIGHT)
        
        message_entry.bind('<Return>', lambda e: self.send_pm(target_user, message_entry))
        
        # When this PM window is closed, call on_pm_window_close
        pm_window.protocol("WM_DELETE_WINDOW", lambda: self.on_pm_window_close(target_user))
        
        # Keep track of this new window and its widgets.
        self.pm_windows[target_user] = {
            'window': pm_window,
            'chat_area': chat_area,
            'entry': message_entry
        }

    def on_pm_window_close(self, target_user):
        """Cleans up when a PM window is closed."""
        if target_user in self.pm_windows:
            self.pm_windows[target_user]['window'].destroy()
            del self.pm_windows[target_user]

    def send_pm(self, target_user, entry_widget):
        """Sends a message from a PM window."""
        message = entry_widget.get().strip()
        if not message or not self.running:
            return
        
        # Format the message as a PM command for the server
        formatted_message = f"PM {target_user} {message}"
        try:
            # Send the PM command to the server.
            self.client_socket.send(formatted_message.encode('utf-8'))
            entry_widget.delete(0, tk.END)
            
            # Add our own message to the PM window immediately.
            self.add_message_to_pm(target_user, self.nickname, message)
        except Exception as e:
            self.add_message("System", f"Could not send private message: {e}")

    def handle_incoming_pm(self, sender, message):
        """Processes a PM received from the server."""
        
        # If we don't have a window open for this sender, create one.
        if sender not in self.pm_windows:
            self.create_pm_window(sender)
            
        # Add the message to their window.
        self.add_message_to_pm(sender, sender, message)
        
        # Bring the window to the front to notify the user.
        self.pm_windows[sender]['window'].lift()

    def handle_outgoing_pm(self, target_user, message):
        """Processes a PM sent from the *main* input box."""
        
        # If we don't have a window for this user, create one.
        if target_user not in self.pm_windows:
            self.create_pm_window(target_user)
            
        # Add the message to that window.
        self.add_message_to_pm(target_user, self.nickname, message)
        self.pm_windows[target_user]['window'].lift()

    def add_message_to_pm(self, pm_partner, sender, message):
        """Adds a formatted message to a specific PM window."""
        if pm_partner not in self.pm_windows:
            return
            
        chat_area = self.pm_windows[pm_partner]['chat_area']
        chat_area.config(state=tk.NORMAL)
        
        if sender == self.nickname:
            sender_tag = "(You)"
        else:
            sender_tag = sender
            
        chat_area.insert(tk.END, f"{sender_tag}: {message}\n")
        chat_area.see(tk.END)
        chat_area.config(state=tk.DISABLED)

    # --- Main Disconnect Functions ---
    
    def disconnect(self):
        """Resets the client to its initial, disconnected state."""
        self.running = False 
        
        # Close all open PM windows
        for user in list(self.pm_windows.keys()):
            self.on_pm_window_close(user)
        self.pm_windows.clear()
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass # Ignore errors, we are closing anyway
            self.client_socket = None
        
        # Reset the UI to the "disconnected" state
        self.connect_button.config(text="Connect", state=tk.NORMAL)
        self.host_entry.config(state=tk.NORMAL)
        self.port_entry.config(state=tk.NORMAL)
        self.nickname_entry.config(state=tk.NORMAL)
        self.message_entry.delete(0, tk.END)
        self.message_entry.config(state=tk.DISABLED)
        self.send_button.config(state=tk.DISABLED)
        self.users_list.delete(0, tk.END)
        self.root.title("MultiChat Client")
    
    def on_closing(self):
        """Called when the user clicks the 'X' on the main window."""
        
        # Politely tell the server we are leaving.
        if self.running and self.client_socket:
            try:
                self.client_socket.send('EXIT'.encode('utf-8'))
            except Exception as e:
                print(f"Could not send EXIT message: {e}")
        
        self.disconnect()
        
        # Quit the tkinter main loop and exit the program.
        self.root.quit()
        self.root.destroy()
        sys.exit(0)
    
    def run(self):
        """Starts the tkinter main event loop."""
        self.root.mainloop()

# This part only runs if the script is executed directly.
if __name__ == "__main__":
    client = ChatClientGUI()
    client.run()