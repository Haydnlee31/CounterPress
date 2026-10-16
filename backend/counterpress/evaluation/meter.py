"""Numeric-only benchmark metering and conservative request admission.

This is a per-process evaluation allowance, not a production quota or Azure
billing cap. Missing usage (including cancellation) remains explicitly unknown.
"""

from dataclasses import dataclass, field
from decimal import Decimal
import json

import httpx2

from counterpress.adaptation.azure import ProviderFailure


@dataclass
class Meter:
    max_requests: int = 96
    allowance_usd: Decimal = Decimal('1.00')
    input_usd_per_million: Decimal = Decimal('0.44')
    output_usd_per_million: Decimal = Decimal('1.76')
    receipts: list[dict] = field(default_factory=list)
    reserved_usd: Decimal = Decimal(0)

    def cost(self, input_tokens, output_tokens):
        return (input_tokens * self.input_usd_per_million
                + output_tokens * self.output_usd_per_million) / Decimal(1_000_000)

    def admit(self, request):
        payload = json.loads(request.content)
        output_limit = payload.get('max_completion_tokens', payload.get('max_tokens'))
        if (payload.get('stream') or type(output_limit) is not int or not 0 < output_limit <= 650
                or len(request.content) > 65536):
            raise ProviderFailure('budget_exhausted', 'evaluation_payload_limit')
        # UTF-8 bytes plus overhead deliberately overestimate ordinary text input;
        # actual provider accounting, tariffs and taxes can differ.
        estimate = self.cost(len(request.content) + 4096, output_limit)
        if len(self.receipts) >= self.max_requests or self.reserved_usd + estimate > self.allowance_usd:
            raise ProviderFailure('budget_exhausted', 'evaluation_allowance_exhausted')
        self.reserved_usd += estimate  # Never release on error or missing usage.
        record = {'input_tokens': None, 'output_tokens': None, 'estimated_usd': None,
                  'admission_estimate_usd': float(estimate)}
        self.receipts.append(record)
        return record


class MeteredTransport(httpx2.AsyncBaseTransport):
    def __init__(self, meter, inner):
        self.meter, self.inner = meter, inner

    async def handle_async_request(self, request):
        receipt = self.meter.admit(request)
        response = await self.inner.handle_async_request(request)
        try:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 65536:
                    raise ProviderFailure('invalid', 'response_too_large')
            try:
                usage = json.loads(data).get('usage') or {}
                inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
                if type(inp) is int and type(out) is int and 0 <= inp <= 2_000_000 and 0 <= out <= 65536:
                    receipt.update(input_tokens=inp, output_tokens=out,
                                   estimated_usd=float(self.meter.cost(inp, out)))
            except (ValueError, TypeError, AttributeError):
                pass  # The guarded transport validates content; unknown usage is not zero.
            headers = {k: v for k, v in response.headers.items()
                       if k.lower() not in ('content-length', 'content-encoding', 'transfer-encoding')}
            return httpx2.Response(response.status_code, headers=headers, content=bytes(data))
        finally:
            await response.aclose()

    async def aclose(self):
        await self.inner.aclose()
