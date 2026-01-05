#!/usr/bin/env python3
import json
import sys

har_file = sys.argv[1] if len(sys.argv) > 1 else '9.har'

with open(har_file, 'r') as f:
    har = json.load(f)

print(f"Total entries: {len(har['log']['entries'])}")

for i, entry in enumerate(har['log']['entries']):
    url = entry['request']['url']
    if 'generateAssistantResponse' in url:
        print(f"\n{'='*60}")
        print(f"Entry {i}: generateAssistantResponse")
        print('='*60)
        
        # Request
        req = entry['request']
        if req.get('postData'):
            try:
                body = json.loads(req['postData']['text'])
                print("\n>>> REQUEST BODY:")
                print(json.dumps(body, indent=2, ensure_ascii=False))
            except:
                print("\n>>> REQUEST (raw):")
                print(req['postData']['text'][:2000])
        
        # Response
        print("\n>>> RESPONSE:")
        resp_text = entry['response']['content'].get('text', '')
        if resp_text:
            print(resp_text[:10000])
        else:
            print("(empty or binary)")
        print()
