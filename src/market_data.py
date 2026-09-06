from socket import AF_INET, SOCK_STREAM, socket
from select import select
import sys

def market_client(hostname, port, instr) :
    market_client = socket(AF_INET, SOCK_STREAM)
    try :
        market_client.connect((hostname,port))
    except Exception :
        return
    
    if instr :
        market_client.sendall(f"SUBSCRIBE {instr}\n".encode('utf-8'))
        
    recv_buff = ""
    
    while 1 :
        try :
          read_sockets , _, _ = select([sys.stdin, market_client], [], [])
        except Exception :
          break
        
        for sock in read_sockets :
            if sock == market_client :
                try:
                    data = market_client.recv(4096)
                    if not data: # means connection was closed by server
                        market_client.close()
                        return
                    recv_buff += data.decode('utf-8', errors='ignore')
                    while "\n" in recv_buff:
                        msg, recv_buff = recv_buff.split('\n',1)
                        print(msg.strip())

                except Exception :
                    market_client.close()
                    return
            elif sock == sys.stdin :
                user_inp = sys.stdin.readline()
                if not user_inp:
                  market_client.close()
                  return
                try:
                    market_client.sendall(user_inp.encode('utf-8'))
                except Exception:
                    return
                if user_inp.strip() == "QUIT":
                  market_client.close()
                  return
        
if __name__ == "__main__" :
    instr = None
    if len(sys.argv) > 3 :
        instr = sys.argv[3]
        
    market_client(sys.argv[1],int(sys.argv[2]),instr)