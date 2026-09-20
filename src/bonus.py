import sys
from socket import AF_INET, SOCK_STREAM, socket
import time

if __name__ == "__main__" :
    host = "127.0.0.1"
    port = 5000
    conn_aim = int(sys.argv[1])
    
    sock = []
    avail_ips = ["127.0.0.1", "127.0.0.2", "127.0.0.3"]
    curr_conn = 0
    start = time.time()
        
    while curr_conn < conn_aim :
        src_ip = avail_ips[curr_conn%3]

        try :
            s = socket(AF_INET,SOCK_STREAM)
            s.bind((src_ip,0))
            s.connect((host,port))
            sock.append(s)
            curr_conn += 1
        except Exception as e :
            print(f"Error while connection {curr_conn} : {e}")
            time.sleep(0.05)
            continue
            
        if curr_conn%10000 == 0 :
            now = time.time() - start 
            print(f"Currently {curr_conn} connections in time {now}")
            input(f">>> Paused at {curr_conn}, Enter to continue")
            
    print(f"Succesfully established {len(sock)} connections")

    time.sleep(10)
    for s in sock :
        try :
            s.close()
        except Exception :
            pass
    print("All connections closed")
        