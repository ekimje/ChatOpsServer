# STEP 3 - 네트워크 장애 보고서

STEP 2 채팅 서버(`server.py` + `client_handler.py`)를 대상으로 `run_fault_tests.py`를
이용해 5가지 장애 시나리오를 실제로 재현하고, 서버 로그(`logs/server.log`)와
`netstat` 스냅샷(`logs/netstat_*.txt`)으로 관측한 결과를 정리한다.

환경: Windows 11, Python 3.13, 서버 idle timeout = 3초(테스트용, 기본값은 60초)

## 시나리오 1. 정상 종료 (exit 메시지)

- **재현 방법**: 클라이언트가 `'exit'`를 보내고 소켓을 닫음
- **관측 결과**: 서버가 `recv()`로 `'exit'`를 수신 → 정상 루프 종료 → `close()`
- **로그**: `[정상 종료] Tester-Graceful - exit 메시지 수신`
- **분석**: 예외 없이 정상 흐름으로 처리됨. 애플리케이션 레벨 프로토콜(`exit` 문자열)로
  종료를 명시하는 것이 TCP의 FIN만 보고 판단하는 것보다 의도 파악이 명확함.

## 시나리오 2. Client 강제 종료 (RST 유발)

- **재현 방법**: `SO_LINGER(on, timeout=0)` 옵션을 설정한 뒤 `close()` 호출 → OS가
  FIN 대신 **RST**를 전송하도록 강제 (kill -9로 죽인 프로세스와 유사한 상황을 재현)
- **관측 결과**:
  ```
  [ERROR] [ConnectionReset] Victim-RST - ConnectionResetError: [WinError 10054]
  현재 연결은 원격 호스트에 의해 강제로 끊겼습니다
  ```
- **분석**: 정상 종료(FIN, `recv()`가 빈 바이트 반환)와 달리, RST는 `recv()`에서
  **예외(`ConnectionResetError`)** 를 발생시킨다. 따라서 서버 코드는 `recv()`의
  빈 반환값 체크만으로는 부족하고, 반드시 `try/except ConnectionResetError`로도
  방어해야 한다 (본 프로젝트의 `client_handler.py`는 이를 처리하고 있음).
- **부가 관측**: `netstat` 스냅샷에서 RST로 끊긴 연결(포트 58740)은 **TIME_WAIT
  목록에 나타나지 않는다.** FIN 기반 정상 종료(58737, 58741, 58742, 58743)는
  전부 TIME_WAIT에 남아있는 것과 대조적 — RST는 TCP 상태 머신에서 TIME_WAIT을
  거치지 않고 즉시 연결을 끊기 때문.

## 시나리오 3. Timeout (idle)

- **재현 방법**: 서버 idle timeout(3초)보다 오래 아무 데이터도 보내지 않고 대기
- **관측 결과**: `[ERROR] [Timeout] Tester-Timeout - 3초간 데이터 없음 (idle timeout)`
  → 서버가 `socket.timeout` 예외로 감지하고 연결을 정리함
- **흥미로운 발견 (레이스 컨디션)**: 테스트 클라이언트가 마지막에 `recv()`를 호출했을 때
  받은 데이터가 빈 값이 아니라 `Observer1님이 퇴장하셨습니다` 브로드캐스트 메시지였다.
  원인은 타이밍: `Tester-Timeout`이 접속한 시점과 `Observer1`이 퇴장 처리된 시점이
  거의 동시(`23:20:59,215`)여서, `Observer1` 퇴장 브로드캐스트가 이미 클라이언트
  목록에 추가된 `Tester-Timeout`의 수신 버퍼에 먼저 쌓였다. 즉 클라이언트가 recv()로
  읽는 데이터는 "자신과 관련된 이벤트"만이 아니라 "그 시점까지 쌓인 모든 브로드캐스트"
  일 수 있다는 것을 실제로 확인했다. 실무에서는 메시지에 타입/시퀀스를 넣어
  파싱해야 하는 이유를 보여주는 사례.

## 시나리오 4. Reconnect (동일 닉네임 재접속)

- **재현 방법**: `exit`로 정상 종료 후 동일 닉네임으로 즉시 재접속
- **관측 결과**: 서버는 완전히 새로운 소켓 연결로 처리 (로그에 포트 번호가
  58742 → 58743으로 바뀌며 별개의 `[접속]`/`[퇴장]` 이벤트로 기록됨)
- **분석**: 현재 구조는 `conn`(소켓 객체) 자체를 키로 클라이언트를 관리하므로
  세션/사용자 개념이 없다. 로드맵상 STEP 4 이후(로그인 기능, DB 저장)에서
  닉네임 중복 방지, 세션 유지 같은 요구사항이 왜 필요한지 보여주는 근거가 된다.

## 시나리오 5. Server 강제 종료 후 Client의 send()

- **재현 방법**: 클라이언트 접속 후 `server_proc.terminate()`로 서버 프로세스를 종료,
  그 직후 클라이언트가 `sendall()` 시도
- **관측 결과**:
  ```
  send/recv 에러: ConnectionResetError: [WinError 10054]
  현재 연결은 원격 호스트에 의해 강제로 끊겼습니다
  ```
- **분석**: Unix의 `BrokenPipeError`(SIGPIPE 기반)와 달리, **Windows는 이런 상황도
  WinError 10054(Connection Reset)로 통일해서 보고**한다. Unix/Linux 배포
  환경(STEP 5, Rocky Linux)에서 같은 테스트를 하면 `BrokenPipeError`가 나올 수
  있으므로, 두 플랫폼 모두 `OSError`(두 예외의 공통 부모 클래스)로 잡는 것이
  이식성 있는 방어 코드다. 실제로 `client_handler.py`의 `broadcast()`는
  `except OSError`로 두 경우를 모두 포괄한다.

## netstat 관측 요약

| 스냅샷 | 특이사항 |
|---|---|
| `netstat_initial.txt` | `LISTENING` 상태만 존재 (연결 전) |
| `netstat_before_server_kill.txt` | FIN으로 정상/timeout 종료된 5개 연결이 `TIME_WAIT`. RST로 끊은 `Victim-RST`(58740)는 목록에 없음 |
| `netstat_after_server_kill.txt` | 서버 프로세스를 죽인 뒤에도 기존 `TIME_WAIT` 항목이 그대로 남아있음 → TIME_WAIT은 프로세스가 아니라 OS 커널이 관리하는 상태라는 것을 보여줌 |

## 도구 한계 (Windows 개발 환경)

- `tcpdump`, `ss`, `nmap`은 Linux 도구로 현재 Windows 개발 PC에는 없음. 동일한
  패킷 레벨 분석은 STEP 5(Rocky Linux 배포) 단계에서 수행 예정.
- `Wireshark`는 GUI 기반 캡처 도구라 이 자동화 스크립트로는 캡처할 수 없음.
  수동으로 Wireshark를 켜고 `tcp.port == 9001` 필터로 `run_fault_tests.py`를
  재실행하면 3-Way Handshake, RST 패킷, FIN 패킷을 직접 확인할 수 있다
  (STEP 6에서 본격적으로 다룰 예정).
- Packet Loss는 Windows에 표준 도구가 없어 이번 STEP에서는 재현하지 않음.
  Rocky Linux 배포 후 `tc netem loss`로 재현 예정.

## 재현 방법

```bash
cd Network-Projects/03-Network-Testing
python run_fault_tests.py
```

실행 시 `server.py`가 서브프로세스로 자동 기동되고, 5개 시나리오가 순차 실행되며
`logs/server.log`, `logs/netstat_*.txt`가 생성/갱신된다.
