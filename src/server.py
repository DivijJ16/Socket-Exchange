from socket import *
from select import *
import sys

socket_list = []
clients = {} # map of client's socket to adress/role
clients_buffer = {}
clients_role = {} 
active_traders = {} #socket -> user
all_traders = set() #all usernames
order_counts = 0

order_book = {"JNST":{"BUY":{},"SELL":{}}, "IMCT":{"BUY":{},"SELL":{}}}
curr_orders = {} #order_id -> order

market_clients = {} #instr -> sockets

max_value = 2147483647

def send_response(res, socket) :
  try :
    socket.sendall(res.encode('utf-8'))
  except Exception as e :
    return

def disconnect(socket) :
  if socket not in socket_list :
    try :
      socket.close()
    except Exception as e :
      return
    return
  
  socket_list.remove(socket)
  clients.pop(socket,None)
  clients_buffer.pop(socket,None)
  role = clients_role.pop(socket,None)
  
  if role == 'trader' :
    user = active_traders.pop(socket,None)
    if user in all_traders :
      all_traders.remove(user)
  else :
    if 'JNST' in market_clients :
      market_clients['JNST'].discard(socket)
    if 'IMCT' in market_clients :
      market_clients['IMCT'].discard(socket)
    
  try :
    socket.close()
  except Exception as e :
    return  
  return
     
def broadcast_trade(instr, qty, price):
  msg = f"TRADE {instr} {qty} {price}\n"
  finished_sockets = []
  poss_sockets = market_clients.get(instr, set())
  
  for sock in poss_sockets:
    try:
      sock.sendall(msg.encode('utf-8'))
    except Exception:
      finished_sockets.append(sock)
  
  for sock in finished_sockets: # these sockets are no longer connected!
    disconnect(sock)
  
 
def matching_eng(instr, side, price) :
  dual_side = "SELL" if side == "BUY" else "BUY"
  my_orders = order_book[instr][side].get(price,[])
  dual_orders = order_book[instr][dual_side].get(price,[])
  
  if not (my_orders and dual_orders):
    return
  while my_orders and dual_orders:
    my_order = my_orders[0]
    dual_order = dual_orders[0]
    quant = min(my_order["quantity"], dual_order["quantity"])
    
    my_order["quantity"] -= quant
    dual_order["quantity"] -= quant
    
    if my_order["quantity"] == 0:
      my_orders.pop(0)
      curr_orders.pop(my_order["id"],None)
    if dual_order["quantity"] == 0:
      dual_orders.pop(0)
      curr_orders.pop(dual_order["id"],None)
    
    buyer_socket = my_order["socket"] if side == "BUY" else dual_order["socket"]
    seller_socket = my_order["socket"] if side == "SELL" else dual_order["socket"]
    
    if buyer_socket in socket_list: #send notification to the traders whose order was executed
      send_response(f"BOUGHT {instr} {quant} {price}\n", buyer_socket)
    if seller_socket in socket_list:
      send_response(f"SOLD {instr} {quant} {price}\n", seller_socket)
      
    broadcast_trade(instr,quant,price)
    
def execute_trader_req(req, socket) :
  global order_counts
  wants = req[0]
  
  if wants == 'LOGIN' :
    if len(req) != 2 :
      send_response("ERROR Invalid LOGIN attempt\n", socket)
      return
    username = req[1]
    if socket in active_traders :
      send_response("ERROR Already Logged in\n", socket)
      return
    if username in all_traders :
      send_response("ERROR Username already taken\n", socket)
      return
    clients_role[socket] = 'trader'
    active_traders[socket] = username
    all_traders.add(username)
    send_response("OK\n", socket)
  else :
    if socket not in active_traders :
      send_response("ERROR Login before any Trading Activity\n", socket)
      return
    if wants == 'BUY' or wants == 'SELL' :
      if len(req) != 4 :
        send_response("ERROR Invalid TRADE attempt\n", socket)
        return
      instr, qty, price = req[1], req[2], req[3]
      if instr != 'JNST' and instr != 'IMCT' :
        send_response("ERROR Invalid Instrument Trading\n", socket)
        return
      try :
        qty = int(qty)
        price = int(price)
        if not (qty >= 1 and qty <= max_value and price >= 1 and price <= max_value) :
          send_response("ERROR Price and quantity for order needs to be in [1,2,147,483,647]\n", socket)
          return
      except Exception as e :
        return
      id = order_counts
      order_counts += 1
      order = {"id" : id, "socket" : socket, "instrument" : instr, "side" : wants, "price" : price, "quantity" : qty, "user" : active_traders[socket]}
      curr_orders[id] = order
      order_book[instr][wants].setdefault(price,[]).append(order)
      
      send_response(f"ORDER_ACCEPTED {id}\n", socket)
      matching_eng(instr, wants, price)
    elif wants == 'CANCEL':
      if len(req) != 2 :
        send_response("ERROR Invalid Cancelling attempt\n", socket)
        return
      try :
        id = int(req[1])
        if not (id >= 1 and id <= max_value) :
          send_response("ERROR Invalid order id\n", socket)
          return
      except Exception as e :
        return
      
      if id not in curr_orders :
        send_response("ERROR Order not found\n", socket)
        return
      
      order = curr_orders[id]
      if order['user'] != active_traders[socket] :
        send_response("ERROR Need to be owner to cancel order\n", socket)
        return
      
      instr, side, price = order["instrument"], order["side"], order["price"]
      curr_orders.pop(id,None)
      if price in order_book[instr][side] :
        order_book[instr][side][price] = [ord for ord in order_book[instr][side][price] if ord["id"] != id]
      send_response(f"ORDER_CANCELLED {id}\n", socket)
    elif wants == 'QUIT' :
      disconnect(socket)
    else :
      send_response("ERROR Unknown Trader Command\n", socket)     
        
def execute_market_data_req(req, socket) :
  wants = req[0]
  
  if wants == 'SUBSCRIBE' :
    if len(req) != 2 :
      send_response("ERROR Invalid SUBSCRIBE attempt\n", socket)
      return
    instr = req[1]
    if instr != 'JNST' and instr != 'IMCT' :
      send_response("ERROR Invalid Instrument\n", socket)
      return
    clients_role[socket] = "market_data"
    market_clients.setdefault(instr, set()).add(socket)
    send_response("OK\n", socket)
  elif wants == 'UNSUBSCRIBE' :
    if len(req) != 2 :
      send_response("ERROR Invalid UNSUBSCRIBE attempt\n", socket)
      return
    instr = req[1]
    if instr != 'JNST' and instr != 'IMCT' :
      send_response("ERROR Invalid Instrument\n", socket)
      return
    if socket in market_clients.get(instr,set()) :
      market_clients[instr].remove(socket)
    else :
      send_response("ERROR TRying to unsubscribe to subscription that doesn't exists\n", socket)
      return
    send_response("OK\n", socket)
  elif wants == 'QUIT' :
    disconnect(socket)
  else :
    send_response("ERROR Unknown Market Client Command\n", socket)     
  
def parse(req, socket) :
  req = req.strip().split()
  
  if req :
    wants = req[0]
    
    if socket not in clients_role :
      if wants == 'LOGIN' :
        execute_trader_req(req,socket)
      elif wants == 'SUBSCRIBE' or wants == 'UNSUBSCRIBE' :
        execute_market_data_req(req,socket)
      elif wants == 'QUIT' :
        disconnect(socket)
      else :
        send_response("ERROR Client not recognised\n", socket)
    else :
      role = clients_role[socket]
      if role == 'trader' :
        execute_trader_req(req,socket)
      else :
        execute_market_data_req(req,socket)
        
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
    
    for socket in read_sockets:
      if socket == welcome_socket: # if the server socket is ready, it means a new client is connecting
        client_socket, client_addr = welcome_socket.accept()
        client_socket.setblocking(False)
        socket_list.append(client_socket)
        clients[client_socket] = client_addr
        clients_buffer[client_socket] = ""
      else:  #an existing client sent data
        try:
            data = socket.recv(1024)
            if data:
                # socket.sendall(b"OK\n")
                clients_buffer[socket] += data.decode('utf-8', errors = 'ignore')
                
                while '\n' in clients_buffer[socket] :
                  #parse all the fully received req
                  req, clients_buffer[socket] = clients_buffer[socket].split('\n',1)
                  if req.strip() :
                    parse(req.strip(),socket) 
            else:  # empty data means the client closed the connection gracefully
                disconnect(socket)
        except Exception as e:
            disconnect(socket)
            
if __name__ == "__main__":
  server(sys.argv[1],int(sys.argv[2]))