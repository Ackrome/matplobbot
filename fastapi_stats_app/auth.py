import secrets
import base64
import binascii
from fastapi import Depends, HTTPException, status, WebSocket, WebSocketException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from .config import STATS_USER, STATS_PASS

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверка для обычных HTTP запросов (HTML страницы и API)"""
    correct_username = secrets.compare_digest(credentials.username, STATS_USER)
    correct_password = secrets.compare_digest(credentials.password, STATS_PASS)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def verify_ws_credentials(websocket: WebSocket):
    """Проверка специально для WebSocket соединений"""
    # Получаем заголовок Authorization при установке соединения
    auth_header = websocket.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Basic "):
        # Для сокетов используем WebSocketException со специальным кодом закрытия 1008
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
    
    try:
        # Декодируем логин и пароль из формата base64: "Basic dXNlcjpwYXNz"
        scheme, data = auth_header.split()
        decoded = base64.b64decode(data).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, binascii.Error):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid Auth Header")

    correct_username = secrets.compare_digest(username, STATS_USER)
    correct_password = secrets.compare_digest(password, STATS_PASS)
    
    if not (correct_username and correct_password):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
    
    return username