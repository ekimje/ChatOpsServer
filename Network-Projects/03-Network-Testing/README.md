# STEP 3 - Network Testing

STEP 2 채팅 서버를 기반으로 네트워크 장애/예외 상황을 의도적으로 재현하고 분석한다.

## 구성

- `server.py`, `client_handler.py` - STEP 2와 동일한 구조에 `logging` 기반 로그
  기록과 idle timeout(`CHAT_IDLE_TIMEOUT` 환경변수, 기본 60초)을 추가
- `run_fault_tests.py` - 5가지 장애 시나리오(정상 종료, RST 강제 종료, timeout,
  reconnect, 서버 종료 후 send)를 자동으로 재현하고 `logs/`에 증거를 남기는 스크립트
- `logs/` - 실행할 때마다 생성되는 `server.log`, `netstat_*.txt`
- `TroubleShooting.md` - 실제 실행 결과를 바탕으로 작성한 장애 보고서

## 실행 방법

```bash
python run_fault_tests.py
```

서버를 별도로 띄울 필요 없이, 스크립트가 서버를 서브프로세스로 실행하고
모든 시나리오를 순서대로 재현한 뒤 정리한다.

## 학습 내용

Timeout, Broken Pipe, Connection Reset, Reconnect, TCP FIN vs RST, `netstat`을
이용한 연결 상태(TIME_WAIT 등) 확인. 상세 분석은 `TroubleShooting.md` 참고.

## 도구 관련 참고

Wireshark/tcpdump/ss/nmap을 이용한 패킷 레벨 분석은 `TroubleShooting.md`의
"도구 한계" 항목 참고 (Windows 개발 환경 제약, STEP 5/6에서 Rocky Linux 기반으로
보완 예정).
