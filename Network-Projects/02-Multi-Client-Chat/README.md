# STEP 2 - Multi Client Chat

멀티스레드를 이용한 다중 클라이언트 채팅 서버.

## 기능
- 멀티스레드 기반 다중 접속
- 닉네임 설정
- 접속/퇴장 알림 브로드캐스트
- 메시지 브로드캐스트 (Lock으로 클라이언트 목록 보호)

## 실행 방법

```bash
python server.py
python client.py   # 여러 터미널에서 실행 가능
```

## 학습 내용
`Thread`, `Lock`, `Broadcast`, Client List 관리
