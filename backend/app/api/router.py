from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.v1 import chat, products

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(products.router)
api_router.include_router(chat.router)
