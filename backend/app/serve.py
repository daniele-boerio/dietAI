"""`python -m app.serve`: uvicorn su IPv4 e IPv6 insieme, sulla porta 8000.

La rete di Coolify è dual-stack: `backend` risolve anche in IPv6 e nginx prova prima
quello. Con `--host 0.0.0.0` la connessione IPv6 veniva rifiutata ("upstream server
temporarily disabled") e nginx ripiegava sull'IPv4. Con `--host ::` il contrario:
uvicorn apre il socket con `IPV6_V6ONLY` acceso (lo fa asyncio per ogni socket IPv6),
e il controllo di salute del container, che chiama 127.0.0.1, falliva — app su, ma
Coolify la segnava «unhealthy». La riga di comando di uvicorn accetta un host solo,
quindi il socket lo apriamo qui, IPv6 con `IPV6_V6ONLY` spento: un socket solo che
accetta tutti e due.
"""

import socket

import uvicorn

PORTA = 8000


def socket_dual_stack(porta: int = PORTA) -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", porta))
    return sock


def main() -> None:
    config = uvicorn.Config(
        "app.main:app", proxy_headers=True, forwarded_allow_ips="*"
    )
    uvicorn.Server(config).run(sockets=[socket_dual_stack()])


if __name__ == "__main__":
    main()
