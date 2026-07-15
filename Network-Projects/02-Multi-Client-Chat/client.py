import socket
import threading

HOST = '127.0.0.1'
PORT = 9000


def receive_messages(sock):
    while True:
        try:
            data = sock.recv(1024)
        except OSError:
            break
        if not data:
            print('[서버와의 연결이 종료되었습니다]')
            break
        print(data.decode(), end='')


def main():
    nickname = input('닉네임을 입력하세요: ').strip() or 'Guest'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall(nickname.encode())

    receiver = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
    receiver.start()

    try:
        while True:
            message = input()
            sock.sendall(message.encode())
            if message == 'exit':
                break
    except (KeyboardInterrupt, EOFError):
        sock.sendall('exit'.encode())
    finally:
        sock.close()


if __name__ == '__main__':
    main()
