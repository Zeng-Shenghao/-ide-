import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse, JSONResponse

app = FastAPI()

UPSTREAM = "https://open.bigmodel.cn/api/coding/paas/v4"
FORCE_MODEL = "glm-5.1"
MAX_TOKENS = 8000


@app.get("/v1/models")
async def models():
    return JSONResponse({
        "object": "list",
        "data": [
            {
                "id": FORCE_MODEL,
                "object": "model",
                "owned_by": "zhipu"
            }
        ]
    })


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()

    body["model"] = FORCE_MODEL

    # 关闭 GLM-5.1 深度思考
    body["thinking"] = {
        "type": "disabled"
    }

    if "max_tokens" not in body or body["max_tokens"] > MAX_TOKENS:
        body["max_tokens"] = MAX_TOKENS

    headers = {
        "Authorization": request.headers.get("authorization", ""),
        "Content-Type": "application/json"
    }

    stream = bool(body.get("stream", False))
    timeout = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)

    if stream:
        async def stream_upstream():
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{UPSTREAM}/chat/completions",
                    headers=headers,
                    json=body
                ) as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            stream_upstream(),
            media_type="text/event-stream"
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{UPSTREAM}/chat/completions",
            headers=headers,
            json=body
        )

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json")
    )