import logging
import os
import socket
import threading

IDLE_TIMEOUT = int(os.environ.get('CHAT_IDLE_TIMEOUT', '60'))

lock = threading.Lock()
clients = {}  # conn -> nickname


def broadcast(message, exclude_conn=None):
    with lock:
        targets = list(clients.items())

    dead = []
    for conn, nickname in targets:
        if conn is exclude_conn:
            continue
        try:
            conn.sendall(message.encode())
        except OSError as e:
            logging.warning(f'[브로드캐스트 실패] {nickname} - {type(e).__name__}: {e}')
            dead.append(conn)

    for conn in dead:
        remove_client(conn)


def add_client(conn, nickname):
    with lock:
        clients[conn] = nickname


def remove_client(conn):
    with lock:
        nickname = clients.pop(conn, None)
    return nickname


def handle_client(conn, addr):
    nickname = None
    try:
        conn.settimeout(IDLE_TIMEOUT)
        data = conn.recv(1024)
        if not data:
            return
        nickname = data.decode().strip() or f'Guest-{addr[1]}'
        add_client(conn, nickname)

        logging.info(f'[접속] {nickname} ({addr[0]}:{addr[1]})')
        broadcast(f'[알림] {nickname}님이 입장하셨습니다.\n', exclude_conn=conn)

        while True:
            data = conn.recv(1024)
            if not data:
                logging.info(f'[FIN 수신] {nickname} - recv()가 빈 바이트 반환 (정상 종료)')
                break

            message = data.decode().strip()
            if message == 'exit':
                logging.info(f'[정상 종료] {nickname} - exit 메시지 수신')
                break

            broadcast(f'{nickname}> {message}\n', exclude_conn=conn)

    except socket.timeout:
        logging.error(f'[Timeout] {nickname or addr} - {IDLE_TIMEOUT}초간 데이터 없음 (idle timeout)')
    except ConnectionResetError as e:
        logging.error(f'[ConnectionReset] {nickname or addr} - {type(e).__name__}: {e}')
    except OSError as e:
        logging.error(f'[OSError] {nickname or addr} - {type(e).__name__}: {e}')
    finally:
        removed_nickname = remove_client(conn)
        display_name = removed_nickname or nickname
        if display_name:
            logging.info(f'[퇴장] {display_name} ({addr[0]}:{addr[1]})')
            broadcast(f'[알림] {display_name}님이 퇴장하셨습니다.\n', exclude_conn=conn)
        conn.close()
