# STEP 2 - Multi Client Chat: 개념 정리 및 주석

STEP 1(1:1 채팅)에서 다수의 클라이언트를 동시에 처리하는 구조로 확장한 버전이다.
원본 코드(`server.py`, `client.py`, `client_handler.py`)는 그대로 두고, 여기서는
각 부분이 왜 그렇게 설계됐는지 개념과 함께 정리한다.

## 1. STEP 1과의 구조적 차이

STEP 1은 `accept()`를 **한 번만** 호출해서 클라이언트 1명만 받았다.
STEP 2는 `accept()`를 **무한 루프 안에서 반복 호출**하고, 연결이 들어올 때마다
그 연결 전담 스레드를 새로 만든다. 즉 "메인 스레드는 문지기 역할만 하고,
실제 대화는 각 클라이언트마다 배정된 스레드가 담당"하는 구조다.

```
accept() → 클라이언트 A 연결 → Thread-A (handle_client) 생성
accept() → 클라이언트 B 연결 → Thread-B (handle_client) 생성
accept() → 클라이언트 C 연결 → Thread-C (handle_client) 생성
...
```

## 2. `server.py` 주석 버전

```python
import socket
import threading

from client_handler import handle_client  # 연결 처리 로직을 별도 모듈로 분리 (관심사 분리)

HOST = '0.0.0.0'  # 모든 네트워크 인터페이스에서 접속을 받음 (STEP1의 '127.0.0.1'과 대비)
PORT = 9000


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # SO_REUSEADDR: 서버를 재시작할 때 "Address already in use" 에러를 방지.
    # 소켓을 닫아도 OS가 TIME_WAIT 상태로 그 주소를 잠깐 붙들고 있는데,
    # 이 옵션을 켜면 그 상태에서도 같은 포트로 다시 bind할 수 있다.
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))

    # listen()에 인자를 안 주면 시스템 기본 backlog 값 사용 (STEP1은 명시적으로 1을 줬었음)
    server_socket.listen()
    print(f'[서버 시작] {HOST}:{PORT}')

    try:
        while True:
            # accept()를 반복 호출 -> 여러 클라이언트를 순서대로 계속 받아들일 수 있다.
            conn, addr = server_socket.accept()

            # 연결마다 독립된 스레드 생성. daemon=True는 "메인 프로그램이 종료되면
            # 이 스레드도 강제로 함께 종료된다"는 의미. 이게 없으면 클라이언트가
            # 접속해 있는 동안 Ctrl+C를 눌러도 프로세스가 안 끝날 수 있다.
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
            # 주의: join()을 호출하지 않는다. STEP1처럼 join()을 하면
            # 첫 연결이 끝날 때까지 다음 accept()로 못 넘어가서 다중 접속이 불가능해진다.
    except KeyboardInterrupt:
        # Ctrl+C로 서버를 끄면 이 블록이 실행된다.
        print('\n[서버 종료]')
    finally:
        server_socket.close()


if __name__ == '__main__':
    main()
```

## 3. `client_handler.py` 주석 버전 (이 STEP의 핵심 로직)

```python
import threading

# 여러 스레드(각 클라이언트를 처리하는 스레드들)가 동시에 clients 딕셔너리에
# 접근하므로, 데이터 경합(race condition)을 막기 위한 락(lock)이 필요하다.
lock = threading.Lock()
clients = {}  # conn(소켓 객체) -> nickname(str) 매핑. "현재 접속 중인 사람 명단"


def broadcast(message, exclude_conn=None):
    # with lock: 블록 안에서만 clients를 잠깐 읽고, 바로 락을 풀어준다.
    # 락을 잡은 채로 각 클라이언트에 sendall()까지 하면, 전송이 느린 클라이언트
    # 한 명 때문에 다른 스레드들이 전부 대기하게 되므로, 리스트 복사본만 만들고
    # 즉시 락을 반환하는 패턴을 쓴다.
    with lock:
        targets = list(clients.items())

    dead = []
    for conn, nickname in targets:
        if conn is exclude_conn:
            continue  # 메시지를 보낸 본인에게는 다시 보내지 않음 (에코 방지)
        try:
            conn.sendall(message.encode())
        except OSError:
            # 이미 끊긴 연결에 보내려 하면 예외가 난다. 즉시 지우지 않고
            # dead 리스트에 모아뒀다가 루프가 끝난 뒤 한꺼번에 정리한다
            # (반복 중인 컬렉션을 직접 수정하지 않기 위한 안전한 패턴).
            dead.append(conn)

    for conn in dead:
        remove_client(conn)


def add_client(conn, nickname):
    with lock:
        clients[conn] = nickname


def remove_client(conn):
    with lock:
        # pop(conn, None): 이미 지워진 경우에도 KeyError 없이 안전하게 None 반환
        nickname = clients.pop(conn, None)
    return nickname


def handle_client(conn, addr):
    # 이 함수 하나가 "한 명의 클라이언트를 전담하는 스레드"의 전체 생명주기다.
    nickname = None
    try:
        # 접속 직후 첫 메시지는 반드시 닉네임이라는 "약속(프로토콜)"을 전제로 한다.
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
                break  # 상대가 FIN을 보내며 정상 종료

            message = data.decode().strip()
            if message == 'exit':
                break  # 애플리케이션 레벨 프로토콜로 명시적 종료

            # 받은 메시지를 "나를 제외한 모두"에게 뿌린다 -> 이게 채팅방의 핵심 동작
            broadcast(f'{nickname}> {message}\n', exclude_conn=conn)

    except (ConnectionResetError, OSError):
        # 클라이언트가 비정상 종료(강제 종료, 네트워크 끊김 등)했을 때 발생
        pass
    finally:
        # try 블록에서 무슨 일이 있었든(정상 종료/예외) 반드시 정리 작업 수행
        removed_nickname = remove_client(conn)
        display_name = removed_nickname or nickname
        if display_name:
            print(f'[퇴장] {display_name} ({addr[0]}:{addr[1]})')
            broadcast(f'[알림] {display_name}님이 퇴장하셨습니다.\n', exclude_conn=conn)
        conn.close()
```

## 4. `client.py` 주석 버전 (닉네임 프로토콜)

```python
def main():
    # 서버와 "첫 메시지 = 닉네임"이라는 규칙을 맞춰야 하는 부분.
    # 이 규칙이 어긋나면(예: 닉네임 없이 바로 채팅 메시지를 보내면)
    # 서버는 그 첫 메시지를 닉네임으로 착각하게 된다.
    nickname = input('닉네임을 입력하세요: ').strip() or 'Guest'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall(nickname.encode())  # 접속하자마자 닉네임부터 전송

    # 수신 전용 스레드를 daemon으로 띄운다 (메인 스레드가 끝나면 같이 종료되도록)
    receiver = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
    receiver.start()

    try:
        while True:
            message = input()
            sock.sendall(message.encode())
            if message == 'exit':
                break
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C(KeyboardInterrupt) 또는 입력 스트림 종료(EOFError) 시에도
        # 서버에 exit를 보내 정상적으로 퇴장 처리되도록 함
        sock.sendall('exit'.encode())
    finally:
        sock.close()
```

## 5. 핵심 개념 요약

| 개념 | 설명 |
|---|---|
| Thread-per-connection | 클라이언트 하나당 스레드 하나를 배정하는 동시성 모델. 구현이 단순하지만 클라이언트 수가 매우 많아지면 스레드 자원 부담이 커짐 |
| `threading.Lock` | 여러 스레드가 동시에 같은 공유 자원(`clients` dict)을 수정하지 못하도록 상호 배제(mutual exclusion)를 보장 |
| Race Condition | 락 없이 여러 스레드가 동시에 `clients`를 읽고 쓰면, 갱신이 유실되거나 프로그램이 깨질 수 있는 상태 |
| Broadcast 패턴 | 한 명이 보낸 메시지를 접속자 전원(본인 제외)에게 전달 |
| daemon 스레드 | 메인 프로세스 종료 시 함께 종료되는 백그라운드 스레드 |
| 애플리케이션 프로토콜 | "첫 메시지 = 닉네임", "'exit' = 종료 요청" 처럼 TCP 자체에는 없는, 애플리케이션이 정한 약속 |

## 6. STEP 1 대비 개선점 / STEP 3에서 더 다뤄지는 지점

- 예외 처리가 `(ConnectionResetError, OSError)`로 구체화됨 (STEP1의 `except:`보다 개선).
- 다만 `socket.timeout`(idle 상태 감지)은 아직 없음 → STEP 3의 `client_handler.py`에서 `conn.settimeout(IDLE_TIMEOUT)` 추가.
- `print()` 기반 로그는 여전히 실행 기록이 파일로 남지 않음 → STEP 3에서 `logging` 모듈 도입.
