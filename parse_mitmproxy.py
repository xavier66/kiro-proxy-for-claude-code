#!/usr/bin/env python3
import json
import re
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else '12.json'

with open(filename, 'rb') as f:
    data = f.read()

print(f"File size: {len(data)} bytes")
print()

# 查找所有 JSON 对象
# 匹配 {"content":...} 或 {"toolUseId":...} 等模式
text = data.decode('utf-8', errors='ignore')

# 查找 toolUseEvent 相关内容
tool_matches = re.findall(r'toolUseEvent.*?\{[^}]+\}', text)
print(f"Found {len(tool_matches)} toolUseEvent mentions")

# 查找所有 JSON 对象
json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
all_jsons = re.findall(json_pattern, text)

print(f"Found {len(all_jsons)} JSON-like objects")
print()

# 过滤出有意义的 JSON
interesting = []
for j in all_jsons:
    if 'toolUseId' in j or 'toolUse' in j:
        interesting.append(j)

print(f"Found {len(interesting)} tool-related JSONs:")
for i, j in enumerate(interesting[:20]):
    print(f"\n=== Tool JSON {i} ===")
    try:
        parsed = json.loads(j)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except:
        print(j[:500])
