from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from api import events
from core.exceptions import EventChainBrokenException, TenantNotFoundException

app = FastAPI(title="Timeline", version="1.0.0")

app.include_router(events.router, prefix="/events")


@app.exception_handler(TenantNotFoundException)
async def tenant_not_found_handler(request: Request, exc: TenantNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Tenant not found"}
    )

@app.exception_handler(EventChainBrokenException)
async def chain_broken_handler(request: Request, exc: EventChainBrokenException):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Event chain integrity compromised"}
    )