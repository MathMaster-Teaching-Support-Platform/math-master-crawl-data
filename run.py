import sys
import uvicorn
from app.core.config import settings

# Force UTF-8 output so emoji/unicode in log messages work on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=settings.port,
        reload=settings.debug
    )