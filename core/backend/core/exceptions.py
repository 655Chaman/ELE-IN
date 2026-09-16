import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger()

class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(self.message)

def setup_exception_handlers(app: FastAPI):
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        logger.warning("api_error", code=exc.code, message=exc.message, status=exc.status_code, details=exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning("validation_error", errors=exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid input data",
                    "details": exc.errors()
                }
            }
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning("http_exception", status=exc.status_code, detail=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail)
                }
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback
        import sys
        print("====== UNHANDLED EXCEPTION ======", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("=================================", file=sys.stderr)
        logger.error("unhandled_exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred."
                }
            }
        )
