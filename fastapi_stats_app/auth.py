import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from .config import STATS_USER, STATS_PASS

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверяет логин и пароль из заголовка Basic Auth."""
    # Используем secrets.compare_digest для защиты от timing-атак
    correct_username = secrets.compare_digest(credentials.username, STATS_USER)
    correct_password = secrets.compare_digest(credentials.password, STATS_PASS)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username