import socket
import threading

from client_handler import handle_client

HOST = '0.0.0.0'
PORT = 9000


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()
    print(f'[서버 시작] {HOST}:{PORT}')

    try:
        while True:
            conn, addr = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print('\n[서버 종료]')
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()
