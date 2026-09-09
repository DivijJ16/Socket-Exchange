from select import kqueue, kevent, KQ_EV_ENABLE, KQ_FILTER_READ, KQ_EV_ADD, KQ_FILTER_WRITE, KQ_EV_DELETE
from socket import AF_INET, SO_REUSEADDR, SOL_SOCKET, SOCK_STREAM, socket, SHUT_RDWR
import sys

socket_list = []
clients = {} # map of client's sock to address
clients_buffer = {}
clients_role = {} 
active_traders = {} #sock -> user
all_traders = set() #all usernames
order_counts = 0
file_desc_to_socket = {}
file_desc_gen = {}
next_gen = 0

order_book = {"JNST":{"BUY":{},"SELL":{}}, "IMCT":{"BUY":{},"SELL":{}}}
curr_orders = {} #order_id -> order

market_clients = {} #instr -> set of sockets

send_buff = {}
kernel_q = None

max_value = 2147483647

def send_response(res, sock) :
  if sock not in socket_list or kernel_q is None :
    return
  
  res = res.encode('utf-8')
  res = send_buff.get(sock,b"") + res
  
  pending_before = sock in send_buff
  
  if not sock in send_buff :
    try :
      n = sock.send(res)
    except BlockingIOError :
      n = 0
    except Exception :
      disconnect(sock)
      return
    res = res[n:]
   
  if not res :
    send_buff.pop(sock,None)
    return

  send_buff[sock] = res
  
  if not pending_before :
    try :
      kernel_q.control([kevent(sock.fileno(), filter = KQ_FILTER_WRITE, flags = KQ_EV_ADD|KQ_EV_ENABLE,udata=file_desc_gen.get(sock.fileno()))],0,0)
    except Exception :
      disconnect(sock)

def pending_sends(sock) :
  if kernel_q is None :
    return
  
  res = send_buff.get(sock)
  
  if not res :
    try :
      kernel_q.control([kevent(sock.fileno(), filter = KQ_FILTER_WRITE, flags = KQ_EV_DELETE)],0,0)
    except Exception :
      pass
    send_buff.pop(sock,None)
    return
  
  try :
    n = sock.send(res)
    res = res[n:]
  except BlockingIOError :
    return
  except Exception :
    disconnect(sock)
    return
  
  if res :
    send_buff[sock] = res
  else :
    send_buff.pop(sock,None)
    try :
      kernel_q.control([kevent(sock.fileno(), filter = KQ_FILTER_WRITE, flags = KQ_EV_DELETE)],0,0)
    except Exception :
      pass
  
def disconnect(sock) :
  send_buff.pop(sock,None)
  
  if sock not in socket_list :
    try :
      sock.close()
    except Exception :
      pass
    return
  
  socket_list.remove(sock)
  clients.pop(sock,None)
  file_desc_to_socket.pop(sock.fileno(),None)
  file_desc_gen.pop(sock.fileno(),None)
  clients_buffer.pop(sock,None)
  role = clients_role.pop(sock,None)
  
  if role == 'trader' :
    user = active_traders.pop(sock,None)
    if user in all_traders :
      all_traders.remove(user)
  else :
    for instr in market_clients :
      market_clients[instr].discard(sock)
  
  try :
    sock.shutdown(SHUT_RDWR)
  except Exception :
    pass     
  try :
    sock.close()
  except Exception :
    pass  
  return  
 
def matching_eng(instr, side, price) :
  dual_side = "SELL" if side == "BUY" else "BUY"
  my_orders = order_book[instr][side].get(price,[])
  dual_orders = order_book[instr][dual_side].get(price,[])
  
  if not my_orders or not dual_orders:
    return
  
  while my_orders and dual_orders:
    my_order = my_orders[0]
    dual_order = dual_orders[0]
    qty = min(my_order["quantity"], dual_order["quantity"])
    
    my_order["quantity"] -= qty
    dual_order["quantity"] -= qty
    
    if my_order["quantity"] == 0:
      my_orders.pop(0)
      curr_orders.pop(my_order["id"],None)
      
      if not my_orders :
        order_book[instr][side].pop(price,None)
        
    if dual_order["quantity"] == 0:
      dual_orders.pop(0)
      curr_orders.pop(dual_order["id"],None)
      
      if not dual_orders :
        order_book[instr][dual_side].pop(price,None)
    
    buyer_socket = my_order["sock"] if side == "BUY" else dual_order["sock"]
    seller_socket = my_order["sock"] if side == "SELL" else dual_order["sock"]
    
    if buyer_socket in socket_list: #send notification to the traders whose order was executed
      send_response(f"BOUGHT {instr} {qty} {price}\n", buyer_socket)
    if seller_socket in socket_list:
      send_response(f"SOLD {instr} {qty} {price}\n", seller_socket)
      
    resp = f"TRADE {instr} {qty} {price}\n" 
    for sock in list(market_clients.get(instr, set())):
      send_response(resp,sock)
    
def execute_trader_req(req, sock) :
  global order_counts
  wants = req[0]
  # clients_role[sock] = 'trader'
  
  if wants == 'LOGIN' :
    if len(req) != 2 :
      send_response("ERROR Invalid LOGIN attempt\n", sock)
      return
    username = req[1]
    if sock in active_traders :
      send_response("ERROR Already Logged in\n", sock)
      return
    if username in all_traders :
      send_response("ERROR Username already taken\n", sock)
      return
    clients_role[sock] = 'trader'
    active_traders[sock] = username
    all_traders.add(username)
    send_response("OK\n", sock)
  else :
    if sock not in active_traders :
      send_response("ERROR Login before any Trading Activity\n", sock)
      return
    if wants == 'BUY' or wants == 'SELL' :
      if len(req) != 4 :
        send_response("ERROR Invalid TRADE attempt\n", sock)
        return
      instr, qty, price = req[1], req[2], req[3]
      if instr != 'JNST' and instr != 'IMCT' :
        send_response("ERROR Invalid Instrument Trading\n", sock)
        return
      try :
        qty = int(qty)
        price = int(price)
        if not (qty >= 1 and qty <= max_value and price >= 1 and price <= max_value) :
          send_response("ERROR Price and quantity for order needs to be in [1,2147483647]\n", sock)
          return
      except Exception as e :
        send_response("ERROR Price and quantity must be valid integers\n", sock)
        return
      id = order_counts
      order_counts += 1
      order = {"id" : id, "sock" : sock, "instrument" : instr, "side" : wants, "price" : price, "quantity" : qty, "user" : active_traders[sock]}
      curr_orders[id] = order
      order_book[instr][wants].setdefault(price,[]).append(order)
      
      send_response(f"ORDER_ACCEPTED {id}\n", sock)
      matching_eng(instr, wants, price)
    elif wants == 'CANCEL':
      if len(req) != 2 :
        send_response("ERROR Invalid Cancelling attempt\n", sock)
        return
      try :
        id = int(req[1])
        if not (id >= 0 and id <= max_value) :
          send_response("ERROR Invalid order id\n", sock)
          return
      except Exception as e :
        send_response("ERROR Order id must be valid integer\n", sock)
        return
      
      if id not in curr_orders :
        send_response("ERROR Order not found\n", sock)
        return
      
      order = curr_orders[id]
      if order['sock'] != sock :
        send_response("ERROR Need to be owner to cancel order\n", sock)
        return
      
      instr, side, price = order["instrument"], order["side"], order["price"]
      curr_orders.pop(id,None)
      if price in order_book[instr][side] :
        order_book[instr][side][price] = [ord for ord in order_book[instr][side][price] if ord["id"] != id]
        
        if not order_book[instr][side][price] :
          order_book[instr][side].pop(price,None)
          
      send_response(f"ORDER_CANCELLED {id}\n", sock)
    elif wants == 'QUIT' :
      disconnect(sock)
    else :
      send_response("ERROR Unknown Trader Command\n", sock)     
        
def execute_market_data_req(req, sock) :
  wants = req[0]
  # clients_role[sock] = "market_data"
  
  if wants == 'SUBSCRIBE' :
    if len(req) != 2 :
      send_response("ERROR Invalid SUBSCRIBE attempt\n", sock)
      return
    instr = req[1]
    if instr != 'JNST' and instr != 'IMCT' :
      send_response("ERROR Invalid Instrument\n", sock)
      return
    clients_role[sock] = "market_data"
    market_clients.setdefault(instr, set()).add(sock)
    send_response("OK\n", sock)
  elif wants == 'UNSUBSCRIBE' :
    if len(req) != 2 :
      send_response("ERROR Invalid UNSUBSCRIBE attempt\n", sock)
      return
    instr = req[1]
    if instr != 'JNST' and instr != 'IMCT' :
      send_response("ERROR Invalid Instrument\n", sock)
      return
    if sock in market_clients.get(instr,set()) :
      market_clients[instr].remove(sock)
    else :
      send_response("ERROR TRying to unsubscribe to subscription that doesn't exists\n", sock)
      return
    send_response("OK\n", sock)
  elif wants == 'QUIT' :
    disconnect(sock)
  else :
    send_response("ERROR Unknown Market Client Command\n", sock)     
  
def parse(req, sock) :
  req = req.strip().split()
  
  if req :
    wants = req[0]
    
    if sock not in clients_role :
      if wants == 'LOGIN' :
        execute_trader_req(req,sock)
      elif wants == 'SUBSCRIBE' or wants == 'UNSUBSCRIBE' :
        execute_market_data_req(req,sock)
      elif wants == 'QUIT' :
        disconnect(sock)
      else :
        send_response("ERROR Client not recognised\n", sock)
    else :
      role = clients_role[sock]
      if role == 'trader' :
        execute_trader_req(req,sock)
      else :
        execute_market_data_req(req,sock)
        
  return

def server(hostname, port):
  global kernel_q, next_gen
  
  welcome_socket = socket(AF_INET, SOCK_STREAM)
  welcome_socket.setsockopt(SOL_SOCKET,SO_REUSEADDR,1) #for immediate reuse of port after server restart
  welcome_socket.bind((hostname,port))
  welcome_socket.listen(8000) 
  welcome_socket.setblocking(False)
  
  socket_list.append(welcome_socket)
  file_desc_to_socket[welcome_socket.fileno()] = welcome_socket
  file_desc_gen[welcome_socket.fileno()] = 0
  
  kernel_q = kqueue()
  kernel_event = kevent(welcome_socket.fileno(), filter= KQ_FILTER_READ, flags=KQ_EV_ADD | KQ_EV_ENABLE)
  kernel_q.control([kernel_event],0,0)
  while 1:
    try :
      # print("waiting on kqueue control", flush=True)
      events = kernel_q.control(None, 10020, None)
      # print(f"woke up with {len(events)} events", flush=True)
    except Exception :
      continue
    
    for event in events:
      file_desc = event.ident
      if file_desc not in file_desc_to_socket:
        continue
      
      if event.filter != KQ_FILTER_WRITE and file_desc_gen.get(file_desc) != event.udata :
        continue
      
      sock = file_desc_to_socket[file_desc]
      
      if event.filter == KQ_FILTER_WRITE :
        pending_sends(sock)
        continue
      
      if sock == welcome_socket: # if the server sock is ready, it means a new client is connecting
        for _ in range(event.data):
          try:
            client_socket, client_addr = welcome_socket.accept()
            client_socket.setblocking(False)
            socket_list.append(client_socket)
            file_desc_to_socket[client_socket.fileno()] = client_socket
            next_gen += 1
            file_desc_gen[client_socket.fileno()] = next_gen 
            clients[client_socket] = client_addr
            clients_buffer[client_socket] = ""
            client_kev = kevent(client_socket.fileno(), filter=KQ_FILTER_READ, flags=KQ_EV_ADD | KQ_EV_ENABLE, udata=next_gen)
            kernel_q.control([client_kev], 0, 0)
          except Exception:
            pass
      else:  #an existing client sent data
        try:
            data = sock.recv(4096)
            # print(f"Received fd={sock.fileno()} bytes={len(data)}", flush=True)
            if data:
                clients_buffer[sock] += data.decode('utf-8', errors = 'ignore')
                # print(f"Server received : {data}", flush=True)
                
                while sock in clients_buffer and '\n' in clients_buffer[sock] :
                  #parse all the fully received req
                  req, clients_buffer[sock] = clients_buffer[sock].split('\n',1)
                  if req.strip() :
                    # print(f"Parsed fd={sock.fileno()} msg={req.strip()!r}", flush=True)       
                    parse(req.strip(),sock) 
            else:  # empty data means the client closed the connection gracefully
                # print(f"Received fd={sock.fileno()} bytes=0 (orderly fin)", flush=True)       
                disconnect(sock)
        except Exception :
            # print(f"Received fd={sock.fileno()} bytes=0 (abrupt reset)", flush=True)       
            disconnect(sock)
            
if __name__ == "__main__":
  server(sys.argv[1],int(sys.argv[2]))