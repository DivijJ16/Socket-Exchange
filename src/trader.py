from select import select
from socket import socket, AF_INET, SOCK_STREAM
import sys

def trader(hostname, port, user):
    client_socket = socket(AF_INET, SOCK_STREAM)
    try:
        client_socket.connect((hostname, port))
    except Exception as e:
        return
        
    if user :
      client_socket.sendall(f"LOGIN {user}\n".encode('utf-8'))
      
    recv_buff = ""
    
    while 1:
      try :
        read_sockets , _, _ = select([sys.stdin, client_socket], [], [])
      except Exception :
        break
      
      for sock in read_sockets:
        if sock == client_socket: # server sent a response or asynch msg
          try:
            data = client_socket.recv(4096)
            if not data: # means connection was closed by server
              client_socket.close()
              return
            recv_buff += data.decode('utf-8', errors='ignore')
            while "\n" in recv_buff:
              msg, recv_buff = recv_buff.split('\n',1)
              print(msg.strip())
            
          except Exception as e:
            return
        elif sock == sys.stdin:
          user_inp = sys.stdin.readline()
          if not user_inp:
            client_socket.close()
            return
          try:
              client_socket.sendall(user_inp.encode('utf-8'))
          except Exception:
              return
          if user_inp.strip() == "QUIT":
            client_socket.close()
            return
              

if __name__ == "__main__":
    user = None
    if len(sys.argv) > 3 :
      user = sys.argv[3]
    trader(sys.argv[1], int(sys.argv[2]), user)
    