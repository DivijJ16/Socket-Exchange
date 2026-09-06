from select import select
from socket import AF_INET, SO_REUSEADDR, SOL_SOCKET, SOCK_STREAM, socket
import sys

socket_list = []
clients = {} # map of client's sock to adress/role
clients_buffer = {}
clients_role = {} 
active_traders = {} #sock -> user
all_traders = set() #all usernames
order_counts = 0

order_book = {"JNST":{"BUY":{},"SELL":{}}, "IMCT":{"BUY":{},"SELL":{}}}
curr_orders = {} #order_id -> order

market_clients = {} #instr -> set of sockets

max_value = 2147483647

def send_response(res, sock) :
  try :
    sock.sendall(res.encode('utf-8'))
  except Exception as e :
    return

def disconnect(sock) :
  if sock not in socket_list :
    try :
      sock.close()
    except Exception as e :
      return
    return
  
  socket_list.remove(sock)
  clients.pop(sock,None)
  clients_buffer.pop(sock,None)
  role = clients_role.pop(sock,None)
  
  if role == 'trader' :
    user = active_traders.pop(sock,None)
    if user in all_traders :
      all_traders.remove(user)
  else :
    if 'JNST' in market_clients :
      market_clients['JNST'].discard(sock)
    if 'IMCT' in market_clients :
      market_clients['IMCT'].discard(sock)
    
  try :
    sock.close()
  except Exception as e :
    return  
  return
     
def broadcast_trade(instr, qty, price):
  resp = f"TRADE {instr} {qty} {price}\n"
  unsubs = []
  subs_sockets = market_clients.get(instr, set())
  
  for sock in subs_sockets:
    try:
      sock.sendall(resp.encode('utf-8'))
    except Exception:
      unsubs.append(sock)
  
  for sock in unsubs: # these sockets are no longer connected!
    disconnect(sock)
 
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
    if dual_order["quantity"] == 0:
      dual_orders.pop(0)
      curr_orders.pop(dual_order["id"],None)
    
    buyer_socket = my_order["sock"] if side == "BUY" else dual_order["sock"]
    seller_socket = my_order["sock"] if side == "SELL" else dual_order["sock"]
    
    if buyer_socket in socket_list: #send notification to the traders whose order was executed
      send_response(f"BOUGHT {instr} {qty} {price}\n", buyer_socket)
    if seller_socket in socket_list:
      send_response(f"SOLD {instr} {qty} {price}\n", seller_socket)
      
    broadcast_trade(instr,qty,price)
    
def execute_trader_req(req, sock) :
  global order_counts
  wants = req[0]
  
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
      if order['user'] != active_traders[sock] :
        send_response("ERROR Need to be owner to cancel order\n", sock)
        return
      
      instr, side, price = order["instrument"], order["side"], order["price"]
      curr_orders.pop(id,None)
      if price in order_book[instr][side] :
        order_book[instr][side][price] = [ord for ord in order_book[instr][side][price] if ord["id"] != id]
      send_response(f"ORDER_CANCELLED {id}\n", sock)
    elif wants == 'QUIT' :
      disconnect(sock)
    else :
      send_response("ERROR Unknown Trader Command\n", sock)     
        
def execute_market_data_req(req, sock) :
  wants = req[0]
  
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
  welcome_socket = socket(AF_INET, SOCK_STREAM)
  welcome_socket.setsockopt(SOL_SOCKET,SO_REUSEADDR,1) #for immediate reuse of port after server restart
  welcome_socket.bind((hostname,port))
  welcome_socket.listen(20)
  welcome_socket.setblocking(False)
  
  socket_list.append(welcome_socket)
  
  
  while 1:
    try :
      read_sockets, _ , _ = select(socket_list, [], socket_list)
    except Exception as e :
      continue
    
    for sock in read_sockets:
      if sock == welcome_socket: # if the server sock is ready, it means a new client is connecting
        client_socket, client_addr = welcome_socket.accept()
        client_socket.setblocking(False)
        socket_list.append(client_socket)
        clients[client_socket] = client_addr
        clients_buffer[client_socket] = ""
      else:  #an existing client sent data
        try:
            data = sock.recv(1024)
            if data:
                # sock.sendall(b"OK\n")
                clients_buffer[sock] += data.decode('utf-8', errors = 'ignore')
                
                while '\n' in clients_buffer[sock] :
                  #parse all the fully received req
                  req, clients_buffer[sock] = clients_buffer[sock].split('\n',1)
                  if req.strip() :
                    parse(req.strip(),sock) 
            else:  # empty data means the client closed the connection gracefully
                disconnect(sock)
        except Exception as e:
            disconnect(sock)
            
if __name__ == "__main__":
  server(sys.argv[1],int(sys.argv[2]))