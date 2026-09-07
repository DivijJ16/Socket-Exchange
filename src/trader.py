from select import select
from socket import socket, AF_INET, SOCK_STREAM, SHUT_WR
import sys

def trader(host, port, user):
    client_socket = socket(AF_INET, SOCK_STREAM)
    try:
        client_socket.connect((host, port))
    except Exception as e:
        # print(f"Trader could not connect : {e}", file = sys.stderr)
        return
        
    if user :
      client_socket.sendall(f"LOGIN {user}\n".encode('utf-8'))
      
    recv_buff = ""
    
    while 1:
      try :
        read_sockets, _, _ = select([sys.stdin, client_socket], [], [])
      except Exception :
        try :
          client_socket.close()
        except Exception :
          pass
        break
      
      for sock in read_sockets:
        if sock == client_socket: # server sent a response or asynch msg
          try:
            data = client_socket.recv(4096)
            if not data: # means connection was closed by server
              try :
                client_socket.close()
              except Exception :
                pass
              return
            recv_buff += data.decode('utf-8', errors='ignore')
            while "\n" in recv_buff:
              msg, recv_buff = recv_buff.split('\n',1)
              print(msg.strip())
            
          except Exception:
            try :
              client_socket.close()
            except Exception :
              pass
            return
          
        elif sock == sys.stdin:
          user_inp = sys.stdin.readline()
          
          if not user_inp:
            try :
              client_socket.close()
            except Exception :
              pass
            return
          
          try:
              client_socket.sendall(user_inp.encode('utf-8'))
          except Exception:
            try :
              client_socket.close()
            except Exception :
              pass
            return
          
          if user_inp.strip() == "QUIT":
            try :
              client_socket.shutdown(SHUT_WR)
            except Exception :
              pass
            try :
              while 1:
                data = client_socket.recv(4096)
                if not data :
                  break
            except Exception:
              pass
            
            try :
              client_socket.close()
            except Exception :
              pass
            return
              

if __name__ == "__main__":
    user = None
    if len(sys.argv) > 3 :
      user = sys.argv[3]
    trader(sys.argv[1], int(sys.argv[2]), user)
    