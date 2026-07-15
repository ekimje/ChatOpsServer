import os
import socket
import struct
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = '127.0.0.1', 9001
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def start_server(idle_timeout=3):
    env = os.environ.copy()
    env['CHAT_IDLE_TIMEOUT'] = str(idle_timeout)
    env['PYTHONIOENCODING'] = 'utf-8'
    proc = subprocess.Popen([sys.executable, 'server.py'], cwd=BASE_DIR, env=env)
    time.sleep(1)
    return proc


def netstat_snapshot(label):
    result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if f':{PORT}' in line]
    path = os.path.join(LOG_DIR, f'netstat_{label}.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) if lines else '(해당 포트의 연결 없음)')
    return lines


def connect(nickname):
    s = socket.create_connection((HOST, PORT))
    s.sendall(nickname.encode())
    time.sleep(0.2)
    return s


def rst_close(sock):
    # SO_LINGER on, timeout 0 -> close()가 FIN 대신 RST를 보내도록 강제
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
    sock.close()


def scenario_graceful_exit():
    print('\n=== 시나리오 1: 정상 종료 (exit 메시지) ===')
    a = connect('Tester-Graceful')
    a.sendall(b'exit')
    time.sleep(0.5)
    a.close()
    print('완료: exit 메시지를 보내고 정상적으로 연결을 닫음')


def scenario_forced_disconnect_rst():
    print('\n=== 시나리오 2: Client 강제 종료 (RST 유발) ===')
    observer = connect('Observer1')
    victim = connect('Victim-RST')
    time.sleep(0.3)
    observer.recv(4096)  # Victim 입장 알림 비우기
    rst_close(victim)
    time.sleep(0.5)
    try:
        msg = observer.recv(4096).decode()
        print(f'Observer가 받은 퇴장 알림: {msg.strip()!r}')
    except Exception as e:
        print(f'Observer recv 에러: {type(e).__name__}: {e}')
    observer.close()


def scenario_timeout():
    print('\n=== 시나리오 3: Timeout (idle, 서버 타임아웃 3초) ===')
    a = connect('Tester-Timeout')
    print('idle timeout 초과까지 4초 대기...')
    time.sleep(4)
    try:
        data = a.recv(4096)
        print(f'서버 응답: {data!r} (빈 값이면 서버가 timeout으로 연결을 닫은 것)')
    except Exception as e:
        print(f'recv 에러: {type(e).__name__}: {e}')
    a.close()


def scenario_reconnect():
    print('\n=== 시나리오 4: Reconnect (동일 닉네임 재접속) ===')
    a = connect('Tester-Reconnect')
    a.sendall(b'exit')
    time.sleep(0.3)
    a.close()
    time.sleep(0.3)
    b = connect('Tester-Reconnect')
    b.sendall(b'still here?')
    time.sleep(0.3)
    b.close()
    print('완료: 재접속은 서버 입장에서 완전히 새로운 연결로 처리됨 (세션 연속성 없음)')


def scenario_broken_pipe(server_proc):
    print('\n=== 시나리오 5: Server 강제 종료 후 Client send() ===')
    a = connect('Tester-BrokenPipe')
    server_proc.terminate()
    server_proc.wait(timeout=5)
    time.sleep(0.5)
    try:
        a.sendall(b'hello after server died')
        time.sleep(0.3)
        data = a.recv(4096)
        print(f'send 성공, 이후 recv 결과: {data!r} (빈 값이면 FIN/연결 종료 감지)')
    except OSError as e:
        print(f'send/recv 에러: {type(e).__name__}: {e}')
    a.close()


def main():
    server_proc = start_server(idle_timeout=3)
    try:
        netstat_snapshot('initial')
        scenario_graceful_exit()
        scenario_forced_disconnect_rst()
        scenario_timeout()
        scenario_reconnect()
        netstat_snapshot('before_server_kill')
    finally:
        scenario_broken_pipe(server_proc)
        if server_proc.poll() is None:
            server_proc.terminate()
        netstat_snapshot('after_server_kill')


if __name__ == '__main__':
    main()
