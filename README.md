# 如何在 Trae 中开启或者关闭模型的思考模式，以下是我的方法，明明很简单，官方就是不愿意做一个功能

最近我在 Trae 里接 GLM-5.1 / Coding Plan 的时候，经常遇到一个问题：模型思考时间过长，最后导致断连、超时，或者任务卡住。

本质原因很简单：有些模型默认开启 Thinking / 思考模式，但是 Trae 的自定义模型界面里并没有给我们提供一个地方去传类似：

```json
{
  "thinking": {
    "type": "disabled"
  }
}
```

这种额外参数。

所以我的解决方案是：**在本机启动一个很轻量的本地代理，让 Trae 先请求本地代理，再由本地代理转发到真正的模型 API，并自动帮我们注入开启或关闭思考模式的参数。**

## 一、原理

原本的请求链路是：

```text
Trae → 模型官方 API
```

现在改成：

```text
Trae → 本地代理 → 模型官方 API
```

例如：

```text
Trae
  ↓
http://127.0.0.1:18080/v1/chat/completions
  ↓
本地代理自动添加 thinking 参数
  ↓
https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
  ↓
GLM-5.1
```

这样做的好处是：

1. 不需要修改 Trae 本体；
2. 不需要等官方加功能；
3. 可以自己控制思考模式；
4. 可以顺便限制最大输出，减少超时和断连；
5. Trae 仍然按照 OpenAI Chat Completions 格式调用。

## 二、准备一个本地代理文件

在桌面新建一个文件夹，比如：

```text
glm-proxy
```

然后在里面新建一个文件：

```text
app.py
```

把下面这段代码复制进去：

```python
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse, JSONResponse

app = FastAPI()

# GLM Coding Plan 官方地址
UPSTREAM = os.getenv(
    "GLM_UPSTREAM",
    "https://open.bigmodel.cn/api/coding/paas/v4"
)

# 模型 ID
FORCE_MODEL = os.getenv("GLM_FORCE_MODEL", "glm-5.1")

# 思考模式：disabled = 关闭思考；enabled = 开启思考
THINKING_TYPE = os.getenv("GLM_THINKING", "disabled")

# 最大输出 token，建议先保守一点，避免超时
MAX_TOKENS = int(os.getenv("GLM_MAX_TOKENS", "8000"))


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

    # 强制模型
    body["model"] = FORCE_MODEL

    # 核心：注入思考模式参数
    body["thinking"] = {
        "type": THINKING_TYPE
    }

    # 限制最大输出，减少长时间卡住
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
```

## 三、安装依赖并启动

Windows PowerShell 进入这个文件夹：

```powershell
cd "$env:USERPROFILE\Desktop\glm-proxy"
```

安装依赖：

```powershell
pip install fastapi uvicorn httpx
```

启动本地代理：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 18080
```

如果看到：

```text
Uvicorn running on http://127.0.0.1:18080
```

说明成功了。

注意：这个窗口不要关。关了之后，Trae 就连不上本地代理了。

## 四、Trae 里怎么填

在 Trae 的自定义模型配置里这样填：

| 配置项     | 填写                            |
| ------- | ----------------------------- |
| API 格式  | OpenAI Chat Completions 格式    |
| 自定义请求地址 | `http://127.0.0.1:18080/v1`   |
| 完整 URL  | 关闭                            |
| 模型 ID   | `glm-5.1`                     |
| API 密钥  | 填你的 GLM / Coding Plan API Key |
| 多模态     | 关闭                            |
| 模型展示名称  | GLM-5.1 Fast                  |
| 输出上下文   | 建议 8000                       |
| 工具调用轮次  | 建议 30                         |

这里注意：Trae 里不要再填智谱官方的 URL，而是填本地代理地址：

```text
http://127.0.0.1:18080/v1
```

因为现在是 Trae 先请求本地代理，再由本地代理转发到智谱官方 API。

## 五、如何关闭思考模式

默认代码里这一行就是关闭思考：

```python
THINKING_TYPE = os.getenv("GLM_THINKING", "disabled")
```

也就是说，直接启动：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 18080
```

就是关闭思考模式。

这个模式适合：

* 普通改代码；
* 小 bug 修复；
* 简单解释报错；
* 不想让模型长时间分析；
* 避免 Trae 里断连或超时。

## 六、如何开启思考模式

如果你想开启思考模式，可以在 PowerShell 里这样启动：

```powershell
$env:GLM_THINKING="enabled"
python -m uvicorn app:app --host 127.0.0.1 --port 18080
```

这个模式适合：

* 复杂 bug；
* 架构分析；
* 多文件重构；
* 需要模型认真规划的任务。

如果后面想重新关闭，可以改回：

```powershell
$env:GLM_THINKING="disabled"
python -m uvicorn app:app --host 127.0.0.1 --port 18080
```

## 七、端口被占用怎么办

如果启动时报这个错误：

```text
WinError 10048
通常每个套接字地址只允许使用一次
```

说明端口被占用了。

比如 `10808` 经常是 Clash、v2rayN、sing-box 等代理软件使用的端口。

解决方法：换一个端口，比如 `18080`。

启动：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 18080
```

Trae 里就填：

```text
http://127.0.0.1:18080/v1
```

如果你换成 `19090`，那 Trae 里也要对应改成：

```text
http://127.0.0.1:19090/v1
```

总之，启动端口和 Trae 里填写的端口必须一致。

## 八、一些建议配置

如果你经常因为模型想太久而断连，我建议先这样配：

| 项目     | 建议              |
| ------ | --------------- |
| 思考模式   | disabled        |
| 输出上下文  | 8000            |
| 工具调用轮次 | 30              |
| 输入上下文  | 64000 或 128000  |
| 任务方式   | 分步执行，不要一上来全仓库分析 |

提示词里也可以加一句：

```text
不要长时间思考。每轮只处理必要文件，先定位问题，再做最小修改。如果需要更多上下文，先问我，不要自行长时间全仓库分析。
```

这样可以明显降低模型卡死、超时、断连的概率。

## 九、注意事项

1. 这个方法只是本地转发，不是修改 Trae 本体。
2. API Key 仍然是从 Trae 传到本地代理，再转发给模型官方接口。
3. 建议只监听 `127.0.0.1`，不要改成 `0.0.0.0`，避免局域网其他设备访问。
4. 不同模型的思考参数不一定一样。GLM 是 `thinking.type`，其他模型可能是 `reasoning_effort` 或其他字段。
5. 如果你用的不是 GLM-5.1，需要自己改 `FORCE_MODEL` 和上游 API 地址。

## 十、总结

这个方法的核心就是一句话：

**Trae 没有提供思考模式开关，那就用本地代理在请求转发时自动补上参数。**

关闭思考：

```json
{
  "thinking": {
    "type": "disabled"
  }
}
```

开启思考：

```json
{
  "thinking": {
    "type": "enabled"
  }
}
```

其实功能很简单，官方完全可以在自定义模型界面里加一个“额外请求体 / 自定义参数 / 思考模式开关”。在官方支持之前，这个本地代理方案算是一个比较简单、可控、可复用的临时解决方案。

