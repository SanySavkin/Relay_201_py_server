import http.server
import socketserver
import json
import time
import logging
from urllib.parse import urlparse, parse_qs

# === НАСТРОЙКИ ===
# Настройка логирования для systemd
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

WEB_PORT = 80  

# Глобальные переменные
current_relay_command = "A"
last_seen_time = 0  # Время последнего POST-запроса от реле (в секундах UNIX)

# Храним состояние реле.
relay_states = {
    "1": "0",  # Реле 1
    "2": "0"   # Реле 2
}

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Управление реле (Облачный режим)</title>
    <style>
        body { font-family: sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; width: 340px; }
        
        /* Стили для статуса устройства */
        .device-status { font-size: 14px; font-weight: bold; margin-bottom: 20px; padding: 8px; border-radius: 6px; transition: all 0.3s; }
        .status-online { background-color: #e8f8f5; color: #2ecc71; border: 1px solid #2ecc71; }
        .status-offline { background-color: #fdedec; color: #e74c3c; border: 1px solid #e74c3c; }
        
        .relay-block { margin-bottom: 25px; padding: 15px; border: 1px solid #eef2f5; border-radius: 8px; background-color: #fafbfc; position: relative; }
        .relay-title { font-weight: bold; margin-bottom: 10px; font-size: 18px; }
        .indicator { width: 12px; height: 12px; border-radius: 50%; display: inline-block; position: absolute; top: 15px; right: 15px; background-color: #bdc3c7; }
        .indicator.active { background-color: #2ecc71; box-shadow: 0 0 8px #2ecc71; }
        .btn { border: none; padding: 12px 20px; font-size: 14px; font-weight: bold; border-radius: 6px; cursor: pointer; margin: 0 5px; color: white; transition: background 0.2s; }
        .btn-on { background-color: #2ecc71; }
        .btn-on:hover { background-color: #27ae60; }
        .btn-off { background-color: #e74c3c; }
        .btn-off:hover { background-color: #c0392b; }
        .btn:disabled { background-color: #e2e8f0; color: #a0aec0; cursor: not-allowed; }
        .status-text { font-size: 12px; color: #7f8c8d; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Облачное Реле (POST)</h1>
        
        <!-- Блок общего статуса модуля -->
        <div id="dev-status-block" class="device-status status-offline">Модуль: ОФФЛАЙН</div>
        
        <div class="relay-block" id="block-1">
            <div class="relay-title">Реле 1</div>
            <div class="indicator" id="ind-1"></div>
            <button class="btn btn-on" id="btn-on-1" onclick="sendCmd('11:2')">ВКЛ</button>
            <button class="btn btn-off" id="id-off-1" onclick="sendCmd('21:2')">ВЫКЛ</button>
        </div>
        
        <div class="relay-block" id="block-2">
            <div class="relay-title">Реле 2</div>
            <div class="indicator" id="ind-2"></div>
            <button class="btn btn-on" id="btn-on-2" onclick="sendCmd('12:2')">ВКЛ</button>
            <button class="btn btn-off" id="id-off-2" onclick="sendCmd('22:2')">ВЫКЛ</button>
        </div>
        
        <div class="status-text" id="sync-time">Синхронизация...</div>
    </div>

    <script>
        function sendCmd(code) {
            fetch('/cmd?code=' + code)
                .catch(err => console.error('Ошибка сети:', err));
        }

        function updateUI() {
            fetch('/status-data')
                .then(res => res.json())
                .then(data => {
                    const statusBlock = document.getElementById('dev-status-block');
                    
                    // Обновляем общий статус модуля (онлайн/офлайн)
                    if (data.online) {
                        statusBlock.innerText = "Статус: ОНЛАЙН";
                        statusBlock.className = "device-status status-online";
                        
                        // Если онлайн — делаем кнопки доступными (в зависимости от состояния реле)
                        document.getElementById('btn-on-1').disabled = (data["1"] === "1");
                        document.getElementById('id-off-1').disabled = (data["1"] === "0");
                        document.getElementById('btn-on-2').disabled = (data["2"] === "1");
                        document.getElementById('id-off-2').disabled = (data["2"] === "0");
                    } else {
                        statusBlock.innerText = "Статус: ОФФЛАЙН";
                        statusBlock.className = "device-status status-offline";
                        
                        // Если модуль ушел в офлайн — блокируем все кнопки управления
                        document.getElementById('btn-on-1').disabled = true;
                        document.getElementById('id-off-1').disabled = true;
                        document.getElementById('btn-on-2').disabled = true;
                        document.getElementById('id-off-2').disabled = true;
                    }

                    // Лампочки-индикаторы каналов реле
                    const ind1 = document.getElementById('ind-1');
                    if (data["1"] === "1") ind1.classList.add('active'); else ind1.classList.remove('active');

                    const ind2 = document.getElementById('ind-2');
                    if (data["2"] === "1") ind2.classList.add('active'); else ind2.classList.remove('active');

                    document.getElementById('sync-time').innerText = 'Связь с сервером активна.';
                })
                .catch(err => {
                    document.getElementById('sync-time').innerText = 'Ошибка связи с сервером';
                });
        }

        // Опрашиваем API сервера раз в секунду
        setInterval(updateUI, 1000);
        updateUI();
    </script>
</body>
</html>
"""

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
            code = query.get('code', [None])
            if code:
                current_relay_command = f"A{code}"
                self.send_response(200)
            else:
                self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
            return

        # API endpoint, отдающий состояние в браузер
        if self.path == '/status-data':
            # Считаем устройство Онлайн, если от него был запрос в течение последних 5 секунд
            is_online = (time.time() - last_seen_time) < 5
            
            # Собираем JSON для отправки в UI
            response_data = {
                "online": is_online,
                "1": relay_states["1"],
                "2": relay_states["2"]
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        if self.path == '/nrk/zmiy/relay' or self.path == '/nrk/zmiy/relay/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
            return
            
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        global current_relay_command, relay_states, last_seen_time

        if self.path == '/SyncServiceImpl.svc/ReportStatus':
            # Фиксируем точное время получения POST-запроса
            last_seen_time = time.time()
            
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            raw_body = post_data.strip('"')

            # ЛОГ 1: Логируем факт получения POST-запроса и входящее тело
            logging.info(f"Получен POST-запрос на {self.path} | Тело: {raw_body}")
            
            if len(raw_body) >= 28:
                state_part = raw_body[-8:]
                relay_states["1"] = state_part[0]  # Индекс 0 — первое реле
                relay_states["2"] = state_part[1]  # Индекс 1 — второе реле

            response_body = f'"{current_relay_command}"'
            response_bytes = response_body.encode('utf-8')

            # ЛОГ 2: Логируем данные, подготовленные к отправке в ответ
            logging.info(f"Отправка ответа на реле: {response_body}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)
            
            current_relay_command = "A"
            return

        # Логируем некорректные POST-запросы
        logging.warning(f"Некорректный POST-запрос на путь: {self.path}")
        self.send_response(400)
        self.end_headers()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    with ThreadedHTTPServer(("0.0.0.0", WEB_PORT), CloudRelayHTTPHandler) as httpd:
        print(f"[УСПЕХ] Сервер со статусом Онлайн/Офлайн запущен на порту {WEB_PORT}!")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nСервер остановлен.")
