from fastapi import FastAPI

app = FastAPI(title="의도-엔티티 분류기 백엔드")


@app.get("/health")
def health():
    return {"status": "ok"}
