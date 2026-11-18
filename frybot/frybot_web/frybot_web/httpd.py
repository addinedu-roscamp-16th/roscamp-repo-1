"""Tiny JSON-over-HTTP helper (standard library only) shared by the web service and the guest simulator UI."""
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


# [수정 2026-11-17] 신규 (D6): 요청이 이 서버가 낸 화면에서 왔는지 확인
def same_origin(origin: str, host: str) -> bool:
    """Origin 헤더가 이 서버 자신(http://<Host 헤더>)을 가리키는지 본다.

    Args:
        origin: 요청의 Origin 헤더 값.
        host: 요청의 Host 헤더 값(host:port).

    Returns:
        같은 출처면 True. 'null' 이나 다른 scheme·host·port 는 False.
    """
    parsed = urlparse(origin)
    return parsed.scheme == 'http' and bool(host) and parsed.netloc == host


# [수정 2026-11-17] D6: post_guard 인자 추가
def serve(port, static_dir, get_routes, post_routes, pages=None,
          post_guard=None):
    """get_routes/post_routes: {path: fn(query|body) -> dict}. pages: {'/': 'index.html'}.
    post_guard: fn(path, headers, client_ip) -> 거부할 때의 응답(dict), 허용이면 None. POST 마다 부른다."""
    pages = pages or {}

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            # [수정 2026-11-17] D6: CORS 허용 헤더(Access-Control-Allow-Origin:
            # *)와 OPTIONS 응답을 삭제. 화면은 모두 이 서버가 직접 내므로
            # 필요 없고, 다른 웹 페이지가 관리자 명령을 부를 수 있었음
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            try:
                if u.path in get_routes:
                    return self._send(200, get_routes[u.path]({k: v[0] for k, v in parse_qs(u.query).items()}))
                name = pages.get(u.path) or (u.path[len('/static/'):] if u.path.startswith('/static/') else None)
                if name and '/' not in name and '..' not in name:
                    path = os.path.join(static_dir, name)
                    if os.path.isfile(path):
                        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                        if ctype.startswith('text/') or ctype.endswith('javascript'):
                            ctype += '; charset=utf-8'
                        return self._send(200, open(path, 'rb').read(), ctype)
                self._send(404, {'ok': False, 'message': 'not found'})
            except Exception as e:  # noqa
                self._send(500, {'ok': False, 'message': str(e)})

        def do_POST(self):
            u = urlparse(self.path)
            try:
                # [수정 2026-11-17] D6: JSON 요청만 받고(다른 사이트의 단순
                # 폼 전송 차단), 브라우저가 Origin 을 붙였으면 이 서버의
                # 화면에서 온 것만 받음. 그 뒤 호출부의 검사(post_guard)
                ctype = self.headers.get('Content-Type', '')
                if ctype.split(';')[0].strip().lower() != 'application/json':
                    return self._send(415, {
                        'ok': False,
                        'message': 'Content-Type must be application/json'})
                origin = self.headers.get('Origin')
                if origin is not None and not same_origin(
                        origin, self.headers.get('Host', '')):
                    return self._send(403, {
                        'ok': False, 'message': 'cross-origin request'})
                if post_guard is not None:
                    denied = post_guard(u.path, self.headers,
                                        self.client_address[0])
                    if denied:
                        return self._send(403, denied)
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                if u.path in post_routes:
                    return self._send(200, post_routes[u.path](body))
                self._send(404, {'ok': False, 'message': 'not found'})
            except Exception as e:  # noqa
                self._send(500, {'ok': False, 'message': str(e)})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(('0.0.0.0', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
