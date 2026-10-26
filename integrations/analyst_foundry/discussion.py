"""Native Foundry transport for the same bounded analyst group chat."""
import asyncio
import json
try:  # Hosted ZIP contains the shared module; local checkout uses the backend.
    from .discussion_core import DiscussionRuntime, VERSION
except ImportError:
    from counterpress.analyst.discussion import DiscussionRuntime, VERSION


def parse_discussion(raw):
    if len(raw.encode('utf-8')) > 180000:
        raise ValueError('packet_too_large')
    packet = json.loads(raw)
    if packet.get('protocol') != VERSION:
        raise ValueError('invalid_protocol')
    for key in ('snapshot_id', 'match_id', 'cutoff', 'through_sequence', 'score', 'metrics', 'evidence'):
        if key not in packet: raise ValueError('invalid_packet')
    if len(packet['metrics']) > 1000 or len(packet['evidence']) > 32:
        raise ValueError('packet_too_large')
    if len({m['id'] for m in packet['metrics']}) != len(packet['metrics']):
        raise ValueError('duplicate_metric')
    return packet


class NativeDiscussion:
    def __init__(self, completions): self.completions = completions

    async def run(self, raw, cancellation_signal):
        packet = parse_discussion(raw)
        async def complete(role, prompt, data, schema, tokens):
            if cancellation_signal.is_set(): raise asyncio.CancelledError
            # Instructions and response schemas live on immutable, pinned native
            # prompt-agent versions. Only data and shared history cross this call.
            result = await self.completions('synthesis' if role == 'footie' else role,
                json.dumps(data, ensure_ascii=False, separators=(',', ':')), tokens)
            return result.text, {'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens}
        return await DiscussionRuntime(complete).run(packet)
