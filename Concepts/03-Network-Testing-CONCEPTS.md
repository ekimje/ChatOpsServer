# STEP 3 - Network Testing: 개념 정리 및 주석

STEP 2의 채팅 서버에 로깅/타임아웃을 추가하고, 다양한 네트워크 장애 상황을
의도적으로 재현해서 관찰하는 프로젝트. 실제 분석 결과는 `TroubleShooting.md`에
있고, 이 문서는 코드에 담긴 개념을 주석 형태로 풀어 설명한다.

## 1. STEP 2 대비 달라진 점 한눈에 보기

| 항목 | STEP 2 | STEP 3 |
|---|---|---|
| 로그 출력 | `print()` | `logging` 모듈 (파일 + 콘솔 동시 기록) |
| idle 감지 | 없음 | `conn.settimeout(IDLE_TIMEOUT)` + `socket.timeout` 처리 |
| 장애 재현 | 없음 | `run_fault_tests.py`로 5가지 시나리오 자동 재현 |
| 관측 도구 | 없음 | `netstat` 스냅샷 저장 |

## 2. `server.py` 주석 버전 (로깅 부분 중심)

```python
import logging
import os
import socket
import threading

from client_handler import handle_client

HOST = '0.0.0.0'
PORT = 9001  # STEP2(9000)와 포트를 다르게 해서 두 서버를 동시에 띄울 수 있게 함

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)  # exist_ok=True: 폴더가 이미 있어도 에러 없이 통과

logging.basicConfig(
    level=logging.INFO,  # INFO 이상 레벨(INFO, WARNING, ERROR ...)만 기록
    format='%(asctime)s [%(levelname)s] %(message)s',  # "시간 [레벨] 메시지" 형식
    handlers=[
        # 파일로도 남기고
        logging.FileHandler(os.path.join(LOG_DIR, 'server.log'), encoding='utf-8'),
        # 동시에 콘솔에도 출력 (print()를 logging으로 완전히 대체)
        logging.StreamHandler(),
    ],
)
```

`print()` 대신 `logging`을 쓰는 이유:
- 로그 레벨(INFO/WARNING/ERROR)로 심각도를 구분할 수 있다.
- 파일에 자동으로 타임스탬프와 함께 영구 기록되어, 나중에 장애를 재구성(`TroubleShooting.md`처럼)할 수 있다.
- 콘솔 출력과 파일 기록을 동시에, 한 번의 호출로 처리한다.

## 3. `client_handler.py` 주석 버전 (idle timeout + 예외 세분화)

```python
IDLE_TIMEOUT = int(os.environ.get('CHAT_IDLE_TIMEOUT', '60'))
# 환경변수로 타임아웃 값을 주입받는다. run_fault_tests.py는 테스트를 빨리 돌리려고
# 이 값을 3초로 낮춰서 서버를 서브프로세스로 띄운다 (기본값은 운영 상황을 가정한 60초).

def handle_client(conn, addr):
    nickname = None
    try:
        # settimeout(N): 이 소켓의 recv()가 N초 안에 아무 데이터도 못 받으면
        # 예외(socket.timeout)를 던지도록 설정. 이게 없으면 recv()는 무한정 블로킹된다.
        # 즉 "아무 말도 안 하는 유령 연결"을 서버가 영원히 붙들고 있는 상황을 방지.
        conn.settimeout(IDLE_TIMEOUT)

        data = conn.recv(1024)
        if not data:
            return
        nickname = data.decode().strip() or f'Guest-{addr[1]}'
        add_client(conn, nickname)
        ...

        while True:
            data = conn.recv(1024)
            if not data:
                # recv()가 빈 바이트를 반환 = 상대가 FIN을 보내고 정상 종료했다는 뜻
                logging.info(f'[FIN 수신] {nickname} - recv()가 빈 바이트 반환 (정상 종료)')
                break

            message = data.decode().strip()
            if message == 'exit':
                logging.info(f'[정상 종료] {nickname} - exit 메시지 수신')
                break

            broadcast(f'{nickname}> {message}\n', exclude_conn=conn)

    except socket.timeout:
        # settimeout()으로 설정한 시간 동안 recv()에 아무것도 안 들어온 경우
        logging.error(f'[Timeout] {nickname or addr} - {IDLE_TIMEOUT}초간 데이터 없음 (idle timeout)')
    except ConnectionResetError as e:
        # 상대가 FIN이 아니라 RST(강제 리셋)로 연결을 끊었을 때 recv()/send()에서 발생
        logging.error(f'[ConnectionReset] {nickname or addr} - {type(e).__name__}: {e}')
    except OSError as e:
        # ConnectionResetError를 포함해, 소켓 관련 다른 저수준 에러들의 공통 부모 클래스.
        # Windows의 WinError 10054, Unix의 BrokenPipeError 등을 한 번에 포괄해서 잡는다.
        logging.error(f'[OSError] {nickname or addr} - {type(e).__name__}: {e}')
    finally:
        # 정상/비정상 종료 관계없이 반드시 클라이언트 명단에서 제거하고 퇴장 알림 전송
        ...
```

예외를 `socket.timeout` → `ConnectionResetError` → `OSError` 순서로 잡는 이유:
Python은 `except`를 위에서부터 순서대로 검사하므로, **더 구체적인 예외를 먼저,
더 포괄적인 예외를 나중에** 배치해야 한다. `ConnectionResetError`는 사실
`OSError`의 하위 클래스라서, 순서가 바뀌면 `ConnectionResetError`용 로그 메시지가
영원히 실행되지 않는다.

## 4. `run_fault_tests.py` 주석 버전 (장애 재현 스크립트)

```python
def start_server(idle_timeout=3):
    env = os.environ.copy()
    # 서버를 별도 프로세스로 띄우되, 환경변수로 idle timeout을 3초로 짧게 오버라이드
    # -> 실제로는 60초씩 기다릴 필요 없이 테스트를 빠르게 돌리기 위함
    env['CHAT_IDLE_TIMEOUT'] = str(idle_timeout)
    env['PYTHONIOENCODING'] = 'utf-8'  # Windows 콘솔의 인코딩 문제(한글 깨짐) 방지
    proc = subprocess.Popen([sys.executable, 'server.py'], cwd=BASE_DIR, env=env)
    time.sleep(1)  # 서버가 listen() 상태까지 뜨는 시간을 확보하기 위한 대기
    return proc


def netstat_snapshot(label):
    # OS 명령어 netstat을 서브프로세스로 실행해서, 특정 포트(9001)와 관련된
    # 연결 상태(LISTENING, ESTABLISHED, TIME_WAIT 등)를 파일로 저장.
    # 이걸 시나리오 전/후로 찍어서 "그 사이에 연결 상태가 어떻게 바뀌었는지" 비교한다.
    result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if f':{PORT}' in line]
    ...


def rst_close(sock):
    # SO_LINGER on, timeout 0 -> close()가 FIN 대신 RST를 보내도록 강제
    # 정상적으로 close()하면 OS는 FIN(정상 종료 신호)을 보낸다.
    # 하지만 SO_LINGER를 (활성화=1, 유예시간=0)으로 설정하면, close() 시
    # 대기 중인 데이터를 버리고 즉시 RST(강제 리셋)를 보내도록 OS에 지시한다.
    # 이렇게 하면 "kill -9로 프로세스가 죽어서 소켓이 비정상 종료되는 상황"을
    # 코드로 재현할 수 있다.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
    sock.close()
```

## 5. 5가지 장애 시나리오가 검증하는 개념

| 시나리오 | 재현 방법 | 검증하는 개념 |
|---|---|---|
| 1. 정상 종료 | `'exit'` 전송 후 close() | 애플리케이션 프로토콜 기반 정상 종료, FIN |
| 2. RST 강제 종료 | `SO_LINGER(1,0)` 후 close() | FIN vs **RST**의 차이, `ConnectionResetError`, TIME_WAIT 미발생 |
| 3. Idle Timeout | 서버 timeout(3초)보다 오래 침묵 | `socket.settimeout()`, `socket.timeout` 예외 |
| 4. Reconnect | exit 후 동일 닉네임 재접속 | 서버가 `conn`(소켓 객체) 기준으로 클라이언트를 관리 → 세션 개념 부재 |
| 5. 서버 종료 후 send() | 서버 프로세스 kill 후 클라이언트가 전송 시도 | Windows/Unix 간 예외 차이, `OSError`로 포괄 방어 |

## 6. FIN vs RST — 이 STEP에서 가장 중요한 개념

- **FIN**: "더 이상 보낼 데이터가 없다"는 정상 종료 신호. TCP는 이후 연결을
  TIME_WAIT 상태로 잠시 유지한다 (지연된 패킷이 새 연결과 섞이는 것을 방지).
  `recv()`는 이 경우 **빈 바이트(b'')를 반환**하며, 예외를 던지지 않는다.
- **RST**: "연결을 즉시, 비정상적으로 끊는다"는 리셋 신호. TIME_WAIT을 거치지
  않고 바로 연결이 사라진다. 상대방의 `recv()`/`send()`는 이 경우
  **`ConnectionResetError` 예외를 던진다.**

즉, `if not data: break`만으로는 RST 상황을 감지할 수 없고, 반드시
`try/except ConnectionResetError`(또는 더 포괄적으로 `OSError`)가 함께 있어야
서버가 예외로 죽지 않고 정상적으로 클라이언트를 정리할 수 있다.

## 7. TIME_WAIT과 `netstat`

- `TIME_WAIT`은 소켓을 `close()`한 뒤에도 **OS 커널이** 일정 시간 그 연결 정보를
  들고 있는 상태다. 애플리케이션 프로세스가 죽어도 이 상태는 사라지지 않는다
  (`scenario 5` 이후에도 `netstat_after_server_kill.txt`에 TIME_WAIT 항목이
  남아있는 이유).
- RST로 끊긴 연결은 TIME_WAIT을 거치지 않으므로 `netstat` 목록에서 바로 사라진다.

## 8. Windows vs Unix 예외 차이

| 상황 | Windows | Unix/Linux |
|---|---|---|
| 상대가 이미 끊은 소켓에 `send()` | `ConnectionResetError` (WinError 10054) | `BrokenPipeError` (SIGPIPE 기반) |

두 예외 모두 `OSError`의 하위 클래스이므로, `except OSError`로 잡으면 플랫폼에
관계없이 이식성 있게 방어할 수 있다 (`client_handler.py`의 `broadcast()`가 이 방식).

## 9. 핵심 개념 요약

| 개념 | 설명 |
|---|---|
| `socket.settimeout()` | 지정 시간 내 `recv()` 응답이 없으면 `socket.timeout` 예외 발생 |
| `SO_LINGER` | close() 시 FIN 대신 RST를 보내도록 강제하는 소켓 옵션 (테스트 목적) |
| `SO_REUSEADDR` | TIME_WAIT 상태에서도 같은 포트에 재바인딩 허용 |
| `subprocess.Popen` | 서버를 별도 프로세스로 띄워서, 테스트 스크립트가 서버를 강제 종료(`terminate()`)하는 시나리오까지 재현 가능 |
| `logging` | 장애 상황을 타임스탬프와 함께 파일로 영구 기록 → 사후 분석(`TroubleShooting.md`) 가능 |
| `netstat` | OS가 관리하는 TCP 연결 상태(LISTENING/ESTABLISHED/TIME_WAIT)를 확인하는 도구 |

상세한 실행 결과와 로그 분석은 `TroubleShooting.md`를 참고.
