from socket import *
import sys

def f(hostname, port):
    client_socket = socket(AF_INET, SOCK_STREAM)
    client_socket.connect((hostname, port))

    message = "LOGIN divij\n"
    client_socket.sendall(message.encode('utf-8'))

    response = client_socket.recv(1024)
    print(f"Server response: {response.decode('utf-8').strip()}")
    client_socket.close()

if __name__ == "__main__":
    f(sys.argv[1], int(sys.argv[2]))