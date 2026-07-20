# STEP 1 - Basic TCP Chat: 개념 정리 및 주석

이 파일은 `server.py`, `client.py`의 원본 코드를 건드리지 않고, 각 줄이 왜 필요한지
개념 설명과 함께 정리한 문서다.

## 1. 소켓 통신의 기본 흐름

TCP 소켓 통신은 서버와 클라이언트가 아래 순서로 "연결"을 맺은 뒤에만 데이터를
주고받을 수 있다.

```
[서버]                      [클라이언트]
socket()                    socket()
bind()                      
listen()                    
accept()  <---------------  connect()
   |  (연결 확립, 3-Way Handshake)
recv()/send()  <========>  send()/recv()
close()                     close()
```

- `socket()`: 통신에 사용할 소켓(파일 디스크립터 같은 것) 생성
- `bind()`: 서버가 자신의 IP/포트를 등록 (여기서 대기하겠다고 선언)
- `listen()`: 연결 요청을 받을 준비 완료, 대기열(backlog) 크기 지정
- `accept()`: 실제로 클라이언트의 연결 요청이 올 때까지 **블로킹**되며 대기
- `connect()`: 클라이언트가 서버의 IP/포트로 연결 시도 → 이때 3-Way Handshake 발생
- `send()`/`recv()`: 연결이 확립된 이후 양방향 데이터 송수신
- `close()`: 소켓 종료 (TCP 레벨에서는 FIN 패킷 전송)

## 2. `server.py` 주석 버전

```python
import socket
import threading

# 자기 자신의 주소 등록. (여기서 대기하겠다.)
# '127.0.0.1'은 loopback 주소 - 같은 컴퓨터 안에서만 접속 가능.
# 외부 컴퓨터도 접속받으려면 '0.0.0.0'으로 바꿔야 한다 (모든 인터페이스에서 수신).
server_host = '127.0.0.1'
server_port = 8080

# AF_INET: IPv4 주소 체계 사용
# SOCK_STREAM: TCP(연결 지향, 순서 보장, 신뢰성 있는 스트림) 사용
#   반대로 SOCK_DGRAM을 쓰면 UDP(비연결, 순서/신뢰성 미보장)가 된다.
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# 이 소켓을 (host, port)에 묶는다. 같은 포트를 다른 프로세스가 쓰고 있으면
# "Address already in use" 에러가 발생할 수 있다.
server_socket.bind((server_host, server_port))

# 서버 소켓을 통해 클라이언트의 연결 요청을 기다림.
# 인자 1은 "동시에 대기시킬 수 있는 미처리 연결 요청 수(backlog)".
# 지금은 1:1 채팅이라 1이면 충분하지만, 여러 명을 받으려면 늘려야 한다
# (STEP 2에서 이 구조 자체가 accept()를 반복 호출하는 방식으로 바뀐다).
server_socket.listen(1)
print('waiting.....')

# accept()는 블로킹 함수. 클라이언트가 connect()를 호출하기 전까지 여기서 멈춰있는다.
# 연결이 들어오면 (1) 이 연결 전용의 새 소켓(client_socket)과
# (2) 상대방 주소(client_address)를 튜플로 반환한다.
# 즉 server_socket은 "대문 지키는 소켓", client_socket은 "그 손님과 대화하는 소켓".
client_socket, client_address = server_socket.accept()
print(f'Client connected: {client_address}')

def send_message():
    # input()도 블로킹 함수라서, 만약 send/receive를 스레드로 나누지 않으면
    # 사용자가 뭔가 입력하기 전까지는 상대방 메시지를 받을 수도 없다.
    while True:
        message = input()
        # encode(): 문자열(str) -> 바이트(bytes). 네트워크로는 바이트만 전송 가능.
        client_socket.sendall(message.encode())

def receive_message():
    while True:
        # recv(1024): 최대 1024바이트까지 수신 대기 (블로킹).
        # 상대가 아무것도 안 보내면 여기서 계속 멈춰있는다.
        message = client_socket.recv(1024)

        # 상대방이 정상적으로 연결을 닫으면(close(), 즉 FIN 전송) recv()는
        # 빈 바이트(b'')를 반환한다. 이것이 "연결 종료"를 감지하는 표준적인 방법.
        if not message:
            break

        # 주의(버그): message는 bytes 타입인데 'exit'는 str이라 항상 False다.
        # 실제로 비교하려면 message.decode() == 'exit' 또는 message == b'exit' 이어야 한다.
        if message == 'exit':
            print('채팅 종료')
            client_socket.close()
            break

        # decode(): 바이트(bytes) -> 문자열(str). encode()의 반대 동작.
        print(f'Client >> {message.decode()}')

# 왜 스레드(Thread)가 필요한가?
# send_message()와 receive_message()는 둘 다 내부에서 블로킹 함수(input(), recv())를
# 무한 반복 호출한다. 한 스레드(메인 스레드)에서 순차 실행하면 "보내는 동안 못 받고,
# 받는 동안 못 보내는" 상황이 된다. 두 함수를 별도 스레드로 동시에 돌려야
# 양방향 채팅이 가능하다.
send_thread = threading.Thread(target = send_message)
receive_thread = threading.Thread(target = receive_message)

send_thread.start()
receive_thread.start()

# join(): 해당 스레드가 끝날 때까지 메인 스레드를 대기시킨다.
# 여기서는 두 스레드 모두 while True 무한루프라 사실상 프로그램이 끝날 때까지
# (break로 빠져나오기 전까지) 메인 스레드도 여기서 블록된다.
send_thread.join()
receive_thread.join()

server_socket.close()
```

## 3. `client.py` 주석 버전 (핵심 차이만)

```python
import socket
import threading
import keyboard  # 이 프로젝트에서는 실제로 사용되지 않는 임포트 (미사용 코드)
import sys       # 마찬가지로 미사용

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# connect(): 서버의 (host, port)로 연결 시도. 이 호출이 성공해야 3-Way Handshake가
# 완료되고, 서버 쪽 accept()가 그제서야 반환된다.
client_socket.connect((server_host, server_port))

def send_messages():
    while True:
        message = input()
        client_socket.sendall(message.encode())
        # 여기 str 'exit' 비교는 message가 str이라서 (input()의 반환값) 정상 동작한다.
        # server.py 쪽은 bytes와 비교해서 버그가 있는 것과 대조된다.
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
            # 상대가 소켓을 닫아버리면 recv()가 예외를 던질 수 있어 try/except로 방어.
            # (다만 except: 처럼 예외 타입을 지정하지 않는 것은 모든 에러를 삼켜버려
            # 디버깅이 어려워지는 안티패턴 - STEP 3에서 이 부분이 명시적 예외 처리로 개선된다.)
            break
```

## 4. 이 STEP에서 발견되는 잠재적 문제 (STEP 2/3에서 개선되는 지점)

- `server.py`의 `message == 'exit'` 비교는 `bytes == str`이라 절대 True가 될 수 없는 버그.
- 클라이언트 1명만 처리 가능 (`listen(1)`, `accept()` 1회 호출) → STEP 2에서 `while True: accept()` 반복 구조로 확장.
- 예외 처리가 없거나(`server.py`) 매우 느슨함(`except:`) → STEP 3에서 `ConnectionResetError`, `OSError`, `socket.timeout` 등을 구체적으로 구분해서 처리.
- 로깅이 `print()`뿐이라 실행 후 기록이 남지 않음 → STEP 3에서 `logging` 모듈 도입.

## 5. 스레드 관련 핵심 개념 요약

| 개념 | 설명 |
|---|---|
| 블로킹(Blocking) I/O | `accept()`, `recv()`, `input()`은 데이터/이벤트가 올 때까지 해당 스레드를 멈춘다 |
| 스레드(Thread) | 하나의 프로세스 안에서 동시에 여러 실행 흐름을 만드는 단위. 여기서는 송신/수신을 동시에 처리하기 위해 사용 |
| `start()` | 스레드를 실제로 실행 시작 |
| `join()` | 호출한 스레드가 대상 스레드의 종료를 기다리게 함 |
