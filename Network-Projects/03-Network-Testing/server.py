import logging
import os
import socket
import threading

from client_handler import handle_client

HOST = '0.0.0.0'
PORT = 9001

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'server.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ],
)


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()
    logging.info(f'[서버 시작] {HOST}:{PORT}')

    try:
        while True:
            conn, addr = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        logging.info('[서버 종료] KeyboardInterrupt')
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()
