"""Hard limits at invocation boundaries, independent of framework best effort limits."""

import json
from time import perf_counter

import httpx2
from agent_framework import FunctionMiddleware, MiddlewareFailure

from counterpress.adaptation.azure import ProviderFailure
from counterpress.workflow.contracts import Action


class Budget:
    def __init__(self, seconds: float):
        self.started = perf_counter()
        self.deadline = self.started + seconds
        self.requests = {"analyst": 0, "producer": 0}
        self.tools = 0
        self.actions: list[Action] = []
        self.failure: ProviderFailure | None = None

    def fail(self, status: str, reason: str):
        self.failure = ProviderFailure(status, reason)
        raise self.failure

    def check(self):
        if self.failure:
            raise self.failure
        if perf_counter() >= self.deadline:
            self.fail("timeout", "total_deadline_exceeded")

    def request(self, role: str):
        self.check()
        if self.requests[role] >= (3 if role == "analyst" else 1) or sum(self.requests.values()) >= 4:
            self.fail("budget_exhausted", "provider_request_limit")
        self.requests[role] += 1

    def invoke_tool(self):
        self.check()
        if self.tools >= 3:
            self.fail("budget_exhausted", "tool_invocation_limit")
        self.tools += 1

    def action(self, label: str):
        self.actions.append(Action(label=label, elapsed_ms=max(0, round((perf_counter() - self.started) * 1000))))


class ToolGuard(FunctionMiddleware):
    def __init__(self, budget: Budget):
        self.budget = budget

    async def process(self, context, call_next):
        try:
            self.budget.invoke_tool()
        except ProviderFailure:
            # Ordinary tool exceptions are swallowed by the framework. This signal aborts it.
            raise MiddlewareFailure("CounterPress invocation limit reached") from None
        await call_next()


class GuardedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, budget: Budget, role: str, inner: httpx2.AsyncBaseTransport):
        self.budget, self.role, self.inner = budget, role, inner

    async def handle_async_request(self, request):
        self.budget.request(self.role)
        try:
            response = await self.inner.handle_async_request(request)
            try:
                if response.status_code != 200:
                    self.budget.fail("provider_error", f"http_{response.status_code}")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 65536:
                        self.budget.fail("invalid", "response_too_large")
                body = json.loads(content)
                choice = body["choices"][0]
                message = choice["message"]
                if message.get("refusal"):
                    self.budget.fail("refused", "provider_refusal")
                if choice.get("finish_reason") not in ("stop", "tool_calls"):
                    self.budget.fail("invalid", "incomplete_response")
                self.budget.check()
                # aiter_bytes decoded content encoding; do not ask the SDK to decode it again.
                headers = {key: value for key, value in response.headers.items()
                           if key.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
                return httpx2.Response(200, headers=headers, content=bytes(content))
            finally:
                await response.aclose()
        except httpx2.TimeoutException:
            self.budget.fail("timeout", "provider_timeout")
        except httpx2.HTTPError:
            self.budget.fail("provider_error", "transport_error")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            self.budget.fail("invalid", "malformed_response")

    async def aclose(self):
        await self.inner.aclose()
