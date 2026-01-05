#!/usr/bin/env python3
import json
import sys

def parse_event_stream(data):
    """解析 AWS event-stream 格式"""
    results = []
    pos = 0
    while pos < len(data):
        if pos + 12 > len(data):
            break
        total_len = int.from_bytes(data[pos:pos+4], 'big')
        headers_len = int.from_bytes(data[pos+4:pos+8], 'big')
        if total_len == 0 or total_len > len(data) - pos:
            break
        payload_start = pos + 12 + headers_len
        payload_end = pos + total_len - 4
        if payload_start < payload_end:
            try:
                payload = json.loads(data[payload_start:payload_end].decode('utf-8'))
                results.append(payload)
            except:
                pass
        pos += total_len
    return results

filename = sys.argv[1] if len(sys.argv) > 1 else '12.json'
with open(filename, 'rb') as f:
    data = f.read()

print(f"File size: {len(data)} bytes")
print()

events = parse_event_stream(data)
print(f"Found {len(events)} events")
print()

for i, event in enumerate(events):
    print(f"=== Event {i} ===")
    print(json.dumps(event, indent=2, ensure_ascii=False)[:2000])
    print()
    if i >= 10:
        print("... (truncated)")
        break
