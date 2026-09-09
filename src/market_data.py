from socket import AF_INET, SOCK_STREAM, socket, SHUT_WR
from select import select
import sys
import os

def market_client(hostname, port, instr) :
    market_client = socket(AF_INET, SOCK_STREAM)
    try :
        market_client.connect((hostname,port))
    except Exception as e :
        # print(f"MarketClient could not connect : {e}", file = sys.stderr)
        return
    
    if instr :
        market_client.sendall(f"SUBSCRIBE {instr}\n".encode('utf-8'))
        
    recv_buff = ""
    stdin_buff = ""
    stdin_actv = True
    
    while 1 :
        sockets_watch = [market_client] + ([sys.stdin] if stdin_actv else [])
        try :
          read_sockets , _, _ = select(sockets_watch, [], [])
        except Exception :
            try :
              market_client.close()
            except Exception :
              pass
            break
        
        for sock in read_sockets :
            if sock == market_client :
                try:
                    data = market_client.recv(4096)
                    if not data: # means connection was closed by server
                        try :
                          market_client.close()
                        except Exception :
                          pass
                        return
                    recv_buff += data.decode('utf-8', errors='ignore')
                    while "\n" in recv_buff:
                        msg, recv_buff = recv_buff.split('\n',1)
                        print(msg.strip(), flush=True)

                except Exception :
                    try :
                      market_client.close()
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
                    market_client.sendall((msg+'\n').encode('utf-8'))
                except Exception:
                  try :
                    market_client.close()
                  except Exception :
                    pass
                  return
              
                if msg.strip() == "QUIT":
                  try :
                    market_client.shutdown(SHUT_WR)
                  except Exception :
                    pass
                  try :
                    while 1:
                      data = market_client.recv(4096)
                      if not data :
                        break
                  except Exception:
                    pass
                  
                  try :
                    market_client.close()
                  except Exception :
                    pass
                  return
        
if __name__ == "__main__" :
    instr = None
    if len(sys.argv) > 3 :
        instr = sys.argv[3]
        
    market_client(sys.argv[1],int(sys.argv[2]),instr)