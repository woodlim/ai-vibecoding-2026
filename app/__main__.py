"""Run the FastAPI application with: python -m app"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        # Windows에서 reload 프로세스가 반복 생성되는 문제를 방지합니다.
        reload=False,
    )
