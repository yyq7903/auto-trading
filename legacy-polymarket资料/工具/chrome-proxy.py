#!/usr/bin/env python3
"""
Chrome debugging port proxy for WSL2.
Run this on Windows to forward Chrome debugging port to WSL2.
"""
import socket
import threading
import sys

def forward(source, destination):
    """Forward data between two sockets."""
    while True:
        try:
            data = source.recv(4096)
            if not data:
                break
            destination.send(data)
        except:
            break
    source.close()
    destination.close()

def handle(client):
    """Handle a client connection."""
    try:
        # 连接到本地 Chrome
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.connect(('127.0.0.1', 19825))
        
        # 双向转发
        t1 = threading.Thread(target=forward, args=(client, server), daemon=True)
        t2 = threading.Thread(target=forward, args=(server, client), daemon=True)
        t1.start()
        t2.start()
        
        # 等待线程结束
        t1.join()
        t2.join()
    except Exception as e:
        print(f'Error: {e}')
        client.close()

def main():
    # 监听所有接口，允许 WSL2 连接
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 19826))
    server.listen(5)
    print(f'Chrome proxy listening on 0.0.0.0:19826 -> 127.0.0.1:19825')
    print('WSL2 can connect to this port using Windows IP address')
    sys.stdout.flush()
    
    while True:
        client, addr = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()

if __name__ == '__main__':
    main()
