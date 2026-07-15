import threading

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
        except OSError:
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
        data = conn.recv(1024)
        if not data:
            return
        nickname = data.decode().strip() or f'Guest-{addr[1]}'
        add_client(conn, nickname)

        print(f'[접속] {nickname} ({addr[0]}:{addr[1]})')
        broadcast(f'[알림] {nickname}님이 입장하셨습니다.\n', exclude_conn=conn)

        while True:
            data = conn.recv(1024)
            if not data:
                break

            message = data.decode().strip()
            if message == 'exit':
                break

            broadcast(f'{nickname}> {message}\n', exclude_conn=conn)

    except (ConnectionResetError, OSError):
        pass
    finally:
        removed_nickname = remove_client(conn)
        display_name = removed_nickname or nickname
        if display_name:
            print(f'[퇴장] {display_name} ({addr[0]}:{addr[1]})')
            broadcast(f'[알림] {display_name}님이 퇴장하셨습니다.\n', exclude_conn=conn)
        conn.close()
