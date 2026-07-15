import socket
import threading

# 자기 자신의 주소 등록.(여기서 대기하겠다.)
server_host = '127.0.0.1'
server_port = 8080

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_host, server_port))

# 서버 소켓을 통해 클라이언트의 연결 요청을 기다림.
server_socket.listen(1)
print('waiting.....')

client_socket, client_address = server_socket.accept()
print(f'Client connected: {client_address}')

def send_message():
    while True:
        message = input()
        client_socket.sendall(message.encode())

def receive_message():
    while True:
        message = client_socket.recv(1024)
    
        if not message:
            break
        
        if message == 'exit':
            print('채팅 종료')
            client_socket.close()
            break
        
        print(f'Client >> {message.decode()}')

send_thread = threading.Thread(target = send_message)
receive_thread = threading.Thread(target = receive_message)

send_thread.start()
receive_thread.start()

send_thread.join()
receive_thread.join()

server_socket.close()