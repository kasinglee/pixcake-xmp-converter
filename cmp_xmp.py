import re, sys

def get_attrs(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    attrs = {}
    for m in re.finditer(r'(\w+):(\w+)="([^"]*)"', text):
        key = f'{m.group(1)}:{m.group(2)}'
        attrs[key] = m.group(3)
    return attrs

lr = get_attrs(r'd:\20260620\100EOSR6\LRsave_U8A1872.xmp')
cv = get_attrs(r'd:\20260620\100EOSR6\_U8A1872.xmp')

only_lr = {k:v for k,v in lr.items() if k not in cv}
only_cv = {k:v for k,v in cv.items() if k not in lr}
diff_val = {k: (lr[k], cv[k]) for k in lr if k in cv and lr[k] != cv[k]}

print('=== Only in LR (missing from converter) ===')
for k in sorted(only_lr):
    print(f'  {k}="{only_lr[k]}"')
print(f'\n=== Only in Converter (not in LR) ===')
for k in sorted(only_cv):
    print(f'  {k}="{only_cv[k]}"')
print(f'\n=== Value Differences ===')
for k in sorted(diff_val):
    print(f'  {k}: LR="{diff_val[k][0]}"  CV="{diff_val[k][1]}"')
