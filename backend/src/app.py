from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .routes import challenge, webhooks

app = FastAPI()

# Custom middleware for X-Student-ID header
class StudentIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Student-ID"] = "BSCS23013"
        return response

app.add_middleware(StudentIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


app.include_router(challenge.router, prefix="/api")
app.include_router(webhooks.router, prefix="/webhooks")
