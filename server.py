from socket import *
from select import *
import sys

def f(hostname, port):
  welcome_socket = socket(AF_INET, SOCK_STREAM)
  welcome_socket.setsockopt(SOL_SOCKET,SO_REUSEADDR,1)
  welcome_socket.bind((hostname,port))
  welcome_socket.listen(20)
  
  socket_list = [welcome_socket]
  clients = {} # map of clients socket to adress/role
  
  while 1:
    read_sockets, _, exception_sockets = select.select(socket_list, [], socket_list)
    
    for sock in read_sockets:
      if sock == welcome_socket: # if the server socket is ready, it means a new client is connecting
        client_socket, client_addr = welcome_socket.accept()
        socket_list.append(client_socket)
        clients[client_socket] = client_addr
      else:  #an existing client sent data
        try:
            data = sock.recv(1024)
            if data:
                sock.sendall(b"OK\n")
            else:  # empty data means the client closed the connection gracefully
                socket_list.remove(sock)
                del clients[sock]
        except Exception as e:
            socket_list.remove(sock)
            del clients[sock]
            
if __name__ == "main":
  f(sys.argv[1],int(sys.argv[2]))