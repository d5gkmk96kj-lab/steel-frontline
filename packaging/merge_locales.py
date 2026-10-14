#!/usr/bin/env python3
"""把 en_*.json 分片合并成 locales/en.json。"""
import json, os, glob
loc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'locales')
zh = json.load(open(os.path.join(loc,'zh.json'), encoding='utf-8'))
en = {}
for p in sorted(glob.glob(os.path.join(loc,'en_*.json'))):
    try: en.update(json.load(open(p, encoding='utf-8')))
    except Exception as e: print('跳过', p, e)
# 并集：既包含 zh.json 索引里的原文，也保留分片里手动补的零散 key
# （有些运行时拼接的片段不在源码字面量里，只能手工加）
keys = set(zh) | set(en)
out = {k: en.get(k, '') for k in sorted(keys)}
json.dump(out, open(os.path.join(loc,'en.json'),'w',encoding='utf-8'),
          ensure_ascii=False, indent=1, sort_keys=True)
filled = sum(1 for v in out.values() if v)
print('合并: %d/%d 已翻译 (%.1f%%)' % (filled, len(out), 100*filled/max(1,len(out))))
