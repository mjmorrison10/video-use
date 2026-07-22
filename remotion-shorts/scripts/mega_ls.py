#!/usr/bin/env python3
"""List a public MEGA FOLDER tree (metadata only — no file downloads).
Fetches the encrypted node tree via the MEGA API and decrypts names locally.
Usage: mega_ls.py "https://mega.nz/folder/<H>#<KEY>" > listing.tsv
Outputs TSV: type<TAB>size<TAB>handle<TAB>path
"""
import sys, json, base64, struct, urllib.request
from Crypto.Cipher import AES

def b64d(s):
    s+='='*((4-len(s)%4)%4); return base64.b64decode(s.replace('-','+').replace('_','/'))
def b64e(b):
    return base64.b64encode(b).replace(b'+',b'-').replace(b'/',b'_').rstrip(b'=').decode()
def a32(b): return struct.unpack('>%dI'%(len(b)//4), b)
def str2a32(b):
    if len(b)%4: b+=b'\0'*(4-len(b)%4)
    return a32(b)
def a2b(a): return struct.pack('>%dI'%len(a), *a)

link=sys.argv[1]
frag=link.split('/folder/')[1]
handle,key=frag.split('#'); key=key.split('/')[0]
master=str2a32(b64d(key))  # 4 words

def api(data):
    url=f"https://g.api.mega.co.nz/cs?id=0&n={handle}"
    req=urllib.request.Request(url, json.dumps(data).encode(), {'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def dec_key(ek, mk):
    c=AES.new(a2b(mk), AES.MODE_ECB)
    out=[]
    for i in range(0,len(ek),4):
        out+=a32(c.decrypt(a2b(ek[i:i+4])))
    return tuple(out)
def dec_attr(attr, k):
    c=AES.new(a2b(k[:4]), AES.MODE_CBC, b'\0'*16)
    d=c.decrypt(attr).rstrip(b'\0')
    if d[:4]==b'MEGA': 
        try: return json.loads(d[4:].decode('utf-8','ignore').rstrip('\0'))
        except: return {}
    return {}

res=api([{"a":"f","c":1,"r":1,"ca":1}])[0]
nodes=res['f']
# map handle->(name,parent,type,size)
info={}
for n in nodes:
    h=n['h']; p=n.get('p'); t=n['t']  # t:0 file,1 folder,2 root
    name='?'; size=n.get('s',0)
    if t in (0,1) and 'k' in n and ':' in n['k']:
        try:
            ek=str2a32(b64d(n['k'].split(':')[1]))
            k=dec_key(ek, master)
            if t==0 and len(k)>=8:  # file key = first4 XOR last4
                fk=(k[0]^k[4],k[1]^k[5],k[2]^k[6],k[3]^k[7])
            else: fk=k[:4]
            at=dec_attr(b64d(n['a']), fk if t==0 else k)
            name=at.get('n','?')
        except Exception as e:
            name=f'?err'
    info[h]={'name':name,'p':p,'t':t,'s':size}
def path(h):
    parts=[]; seen=set()
    while h in info and h not in seen:
        seen.add(h); parts.append(info[h]['name']); h=info[h]['p']
    return '/'.join(reversed([p for p in parts if p and p!='?']))
files=folders=0
for h,v in info.items():
    if v['t']==0: files+=1
    elif v['t']==1: folders+=1
    typ='D' if v['t']==1 else ('F' if v['t']==0 else 'R')
    if v['t'] in (0,1):
        print(f"{typ}\t{v['s']}\t{h}\t{path(h)}")
print(f"# {files} files, {folders} folders", file=sys.stderr)
