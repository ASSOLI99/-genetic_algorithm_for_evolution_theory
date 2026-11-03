"""Loopback-only local dashboard; no remote services or runtime web dependencies."""
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .artifacts import ROOT
from .gui_session import LabSession, SessionError, Settings

WEB = Path(__file__).parent/'web'


class LabServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address=('127.0.0.1', 8765), output_root=None):
        if address[0] != '127.0.0.1':
            raise ValueError('The live laboratory binds to loopback only')
        self.lab = LabSession(output_root or ROOT/'runs')
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, status, content, kind='application/json; charset=utf-8', attachment=None):
        raw = content.encode('utf-8') if isinstance(content, str) else content
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(raw)

    def json_response(self, status, value):
        self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False))

    def host_allowed(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        try:
            if not self.host_allowed():
                raise SessionError('invalid_host', 'عنوان الخادم غير مسموح.', 403)
            url = urlsplit(self.path)
            if url.path == '/':
                document = (WEB/'index.html').read_text(encoding='utf-8').replace('__TOKEN__', html.escape(self.server.token, quote=True))
                self.send(200, document, 'text/html; charset=utf-8')
            elif url.path in ('/app.js', '/style.css'):
                self.send(200, (WEB/url.path[1:]).read_bytes(), 'text/javascript; charset=utf-8' if url.path.endswith('.js') else 'text/css; charset=utf-8')
            elif url.path == '/api/state':
                try:
                    after = int(parse_qs(url.query).get('after', ['-1'])[0])
                except ValueError:
                    raise SessionError('invalid_cursor', 'مؤشر تحديث غير صالح.') from None
                if not -1 <= after <= 5000:
                    raise SessionError('invalid_cursor', 'مؤشر تحديث خارج الحدود.')
                self.json_response(200, self.server.lab.snapshot(after))
            elif re.fullmatch(r'/api/(download|report)/[0-9a-f]{32}', url.path):
                mode, identity = url.path.split('/')[2:]
                with self.server.lab.lock:
                    archive = self.server.lab.exports.get(identity)
                if archive is None:
                    raise SessionError('not_found', 'ملف غير موجود.', 404)
                if mode == 'download':
                    self.send(200, archive.read_bytes(), 'application/zip', 'evolution-lab-session.zip')
                else:
                    self.send(200, (archive.with_suffix('')/'REPORT.html').read_bytes(), 'text/html; charset=utf-8')
            else:
                raise SessionError('not_found', 'صفحة غير موجودة.', 404)
        except SessionError as exc:
            self.json_response(exc.status, {'error': exc.code, 'message': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.host_allowed() or self.headers.get('Origin', origins[0]) not in origins:
                raise SessionError('invalid_origin', 'طلب من مصدر غير مسموح.', 403)
            if not secrets.compare_digest(self.headers.get('X-Evolution-Token', ''), self.server.token):
                raise SessionError('invalid_token', 'أعد تحميل الصفحة قبل التحكم بالمحاكاة.', 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise SessionError('invalid_content', 'يلزم إرسال JSON.')
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 32768:
                    raise ValueError
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                raise SessionError('invalid_body', 'بيانات الطلب غير صالحة.') from None
            route = urlsplit(self.path).path
            lab = self.server.lab
            if route == '/api/estimate':
                result = Settings.parse(body).estimate()
            elif route == '/api/start':
                result = lab.configure(body.get('settings', {}), body.get('acknowledge_resources'), background=True)
            elif route == '/api/control':
                lab.control(body.get('action'), body.get('speed'))
                result = {'ok': True}
            elif route == '/api/catastrophe':
                result = lab.catastrophe(body)
            elif route == '/api/remove-program':
                result = lab.remove_program(body)
            elif route == '/api/export':
                result = lab.export()
            else:
                raise SessionError('not_found', 'أمر غير موجود.', 404)
            self.json_response(200, result)
        except SessionError as exc:
            self.json_response(exc.status, {'error': exc.code, 'message': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.json_response(500, {'error': 'internal_error', 'message': 'تعذر تنفيذ الطلب. أوقف التجربة وراجع سجل الخادم.'})


def serve(port=8765, open_browser=True):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Invalid GUI port')
    server = LabServer(('127.0.0.1', port))
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Evolution Lab GUI: {url}', flush=True)
    print('Local-only dashboard. Ctrl+C stops the server. Outputs remain in runs/.', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server.lab.status in ('running', 'paused'):
            server.lab.control('stop')
        server.server_close()
