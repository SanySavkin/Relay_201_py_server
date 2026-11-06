import http.server
import socketserver
import json
import time
import logging
import sys
import os
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

WEB_PORT = 80  
current_relay_command = "A"
last_seen_time = 0  

relay_states = {
    "1": "0",  
    "2": "0"   
}

class CloudRelayHTTPHandler(http.server.SimpleHTTPRequestHandler):
    global current_relay_command, relay_states, last_seen_time

    def do_GET(self):
        global current_relay_command, relay_states, last_seen_time

        if self.path == '/favicon.ico':
            self.send_response(404)
            self.end_headers()
            return

        if self.path.startswith('/cmd'):
            query = parse_qs(urlparse(self.path).query)
            code_list = query.get('code', [None])
            
            full_code = code_list.pop(0) if code_list else None
            
            if full_code:
                if current_relay_command != "A":
                    logging.warning("Блокировка: Ожидание ответа на предыдущую команду")
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.end_headers()
                    self.wfile.write("Ошибка: Предыдущая команда еще не обработана".encode('utf-8'))
                    return

                full_code = full_code.strip()
                current_relay_command = f"A{full_code}"
                logging.info(f"Сформирована команда для отправки: {current_relay_command}")
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(400)
                self.end_headers()
            return

        if self.path == '/status-data':
            is_online = (time.time() - last_seen_time) < 5
            response_data = {
                "online": is_online,
                "1": relay_states.get("1", "0"),
                "2": relay_states.get("2", "0")
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        if self.path in ['/nrk/zmiy/relay', '/nrk/zmiy/relay/']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            if os.path.exists('index.html'):
                with open('index.html', 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            else:
                self.wfile.write(b"<h1>index.html not found</h1>")
            return
            
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        global current_relay_command, relay_states, last_seen_time

        if self.path == '/SyncServiceImpl.svc/ReportStatus':
            last_seen_time = time.time()
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            raw_body = post_data.strip('"')
            logging.info(f"Получен POST-запрос на {self.path} | Тело: {raw_body}")
            
            if len(raw_body) >= 28:
                state_part = raw_body[-8:]
                
                chars = list(state_part)
                relay_states["1"] = chars.pop(0) if chars else "0"
                relay_states["2"] = chars.pop(0) if chars else "0"

                # Очищаем от спецсимволов и разделяем по двоеточию для интерлока
                clean_cmd = current_relay_command.replace("*", "").split(":")
                base_cmd = clean_cmd.pop(0) if clean_cmd else ""

                if base_cmd == "A11" and relay_states.get("2") == "1":
                    logging.warning("Блокировка: Сброс команды ВКЛ 1, так как Реле 2 активно")
                    current_relay_command = "A"
                
                if base_cmd == "A12" and relay_states.get("1") == "1":
                    logging.warning("Блокировка: Сброс команды ВКЛ 2, так как Реле 1 активно")
                    current_relay_command = "A"

                response_body = f'"{current_relay_command}"'
                response_bytes = response_body.encode('utf-8')
                logging.info(f"Отправка ответа на реле: {response_body}")

            raw_response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(response_bytes)}\r\n"
                "\r\n"
            ).encode('utf-8') + response_bytes
            self.wfile.write(raw_response)
            current_relay_command = "A"
            return
        
        logging.warning(f"Некорректный POST-запрос на путь: {self.path}")
        self.send_response(400)
        self.end_headers()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    with ThreadedHTTPServer(("0.0.0.0", WEB_PORT), CloudRelayHTTPHandler) as httpd:
        logging.info(f"Сервер запущен на порту {WEB_PORT}!")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info("Сервер остановлен.")