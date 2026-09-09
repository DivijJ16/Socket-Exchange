from select import select
from socket import socket, AF_INET, SOCK_STREAM, SHUT_WR
import sys
import os

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
    stdin_buff = ""
    stdin_actv = True
    
    while 1:
      sockets_watch = [client_socket] + ([sys.stdin] if stdin_actv else [])
      try :
        read_sockets, _, _ = select(sockets_watch, [], [])
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
              print(msg.strip(), flush=True)
            
          except Exception:
            try :
              client_socket.close()
            except Exception :
              pass
            return
          
        elif sock == sys.stdin:
          user_inp = os.read(0,4096)
          
          if not user_inp:
            stdin_actv = False
            continue
          
          stdin_buff += user_inp.decode('utf-8',errors='ignore')
          while '\n' in stdin_buff:
            msg, stdin_buff = stdin_buff.split('\n',1)
            try:
                client_socket.sendall((msg+'\n').encode('utf-8'))
            except Exception:
              try :
                client_socket.close()
              except Exception :
                pass
              return
          
            if msg.strip() == "QUIT":
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
    