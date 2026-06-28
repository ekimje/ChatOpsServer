import socket
import threading
import keyboard
import sys

server_host = '127.0.0.1'
server_port = 8080

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((server_host, server_port))
print(f'Connected to server at {server_host}:{server_port}')

# 상대방의 답이 없어도 여러번 보낼 수 있도록 송수신 스레드를 각각 생성.
def send_messages():
    while True:
        message = input()
        client_socket.sendall(message.encode())
        
        if message == 'exit':
            print('채팅 종료')
            client_socket.close()
            break

def receive_messages():
    while True:
        try:
            message = client_socket.recv(1024).decode()
            print(f'Server >> {message}')
            
        except:
            break

send_thread = threading.Thread(target=send_messages)
receive_thread = threading.Thread(target=receive_messages)
send_thread.start()
receive_thread.start()

send_thread.join()
receive_thread.join()