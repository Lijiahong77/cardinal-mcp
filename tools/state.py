# -*- coding: utf-8 -*-
"""临时诊断：机架文件 vs Cardinal 实时存档 vs OSC 状态。"""
import sys, os, glob, time, socket
sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

TEMP = os.environ.get('TEMP', '')
F = r'D:\Cardinal\patches\helm_full.vcv'
print('=== 现在 %s ===' % time.strftime('%H:%M:%S'))


def rows_of(d):
    r = {}
    for m in d.get('modules', []):
        r.setdefault(m['pos'][1], []).append(m)
    return r


def show(tag, p):
    if not os.path.exists(p):
        print(tag, p, '不存在')
        return None
    st = os.stat(p)
    d = patchio.read_patch(p)
    ms = d.get('modules', [])
    r = rows_of(d)
    print('%s %s' % (tag, p.replace(TEMP, '%%TEMP%%')))
    print('   mtime %s  size %d  模块 %d  线缆 %d  zoom=%s gridOffset=%s' % (
        time.strftime('%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
        st.st_size, len(ms), len(d.get('cables', [])), d.get('zoom'), d.get('gridOffset')))
    for y in sorted(r):
        mm = sorted(r[y], key=lambda m: m['pos'][0])
        print('   y=%-6s %2d个  %s' % (y, len(mm),
              ' '.join('%s@%s' % (m.get('model'), m['pos'][0]) for m in mm)))
    print()
    return d


print('--- 机架文件 ---')
df = show('[文件]', F)
print('--- 实时存档 ---')
dl = None
for p in sorted(glob.glob(os.path.join(TEMP, 'Cardinal*', 'patch.json'))):
    dl = show('[实时]', p)

if df and dl:
    a = {str(m['id']): m for m in df['modules']}
    b = {str(m['id']): m for m in dl['modules']}
    diff = []
    for k in sorted(set(a) | set(b)):
        pa = a.get(k, {}).get('pos')
        pb = b.get(k, {}).get('pos')
        if pa != pb:
            diff.append((k, a.get(k, {}).get('model') or b.get(k, {}).get('model'), pa, pb))
    print('--- 文件 vs 最近实时存档 ---')
    if diff:
        print('   %-24s %-14s %-14s' % ('id/model', '文件', '实时'))
        for k, mdl, pa, pb in diff:
            print('   %-24s %-14s %-14s' % ((k[:16] + '/' + str(mdl)[:12]), pa, pb))
    else:
        print('   坐标完全一致（没有未保存的改动）')

print('--- OSC 探活 ---')
for port in (2228, 7000, 7001):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.6)
    try:
        s.sendto(b'/hello', ('127.0.0.1', port))
        dta, _ = s.recvfrom(2048)
        print('   端口 %d 有回应: %r' % (port, dta[:60]))
    except Exception as e:
        print('   端口 %d 无回应 (%s)' % (port, type(e).__name__))
    s.close()

print('--- 找 Cardinal 配置文件（用于确认 OSC 开关）---')
cands = []
for pat in [os.path.join(os.environ.get('APPDATA', ''), 'Cardinal*'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Cardinal*'),
            os.path.join(os.path.expanduser('~'), 'Documents', 'Cardinal*'),
            os.path.join(os.path.expanduser('~'), '.Cardinal*')]:
    for c in glob.glob(pat):
        if os.path.isdir(c):
            for f in os.listdir(c):
                fp = os.path.join(c, f)
                if os.path.isfile(fp) and 'patch' not in f.lower():
                    cands.append(fp)
for c in cands[:20]:
    print('   ', c, os.path.getsize(c))
if not cands:
    print('    (没找到)')
