from socket import *
from select import *
import sys

def trader(hostname, port):
    client_socket = socket(AF_INET, SOCK_STREAM)
    try:
        client_socket.connect((hostname, port))
    except Exception as e:
        return
        
    recv_buff = ""
    while 1:
      read_inp , _, _ = select([sys.stdin, client_socket], [], [])
      for inp in read_inp:
        if inp == client_socket: # server sent a response or asynch msg
          try:
            data = client_socket.recv(4096)
            if not data: # means connection was closed by server
              return
            recv_buff += data.decode('utf-8', errors='ignore')
            while "\n" in recv_buff:
              msg, recv_buff = recv_buff.split('\n',1)
              print(msg.strip())
            
          except Exception as e:
            return
        elif inp == sys.stdin:
          user_inp = sys.stdin.readline()
          if not user_inp:
            client_socket.close()
            return
          try:
              client_socket.sendall(user_inp.encode('utf-8'))
          except Exception:
              return
              

if __name__ == "__main__":
    trader(sys.argv[1], int(sys.argv[2]))
    