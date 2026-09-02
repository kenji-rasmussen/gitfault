from PIL import Image, ImageDraw, ImageFont
import glob

W,H = 1280,640
BG=(13,17,23)         # github dark
FG=(230,237,243)
MUTE=(139,148,158)
ACCENT=(88,166,255)   # blue
RED=(248,81,73); YEL=(210,153,34); GRN=(63,185,80)
img=Image.new("RGB",(W,H),BG)
d=ImageDraw.Draw(img)

def font(paths,size):
    for p in paths:
        try: return ImageFont.truetype(p,size)
        except: pass
    return ImageFont.load_default()
sans=["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
sansr=["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
mono=["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
f_title=font(sans,92)
f_tag=font(sansr,38)
f_sub=font(sansr,27)
f_mono=font(mono,24)
f_small=font(sansr,22)

# left margin
x=70
# title
d.text((x,70),"gitfault",font=f_title,fill=FG)
# accent underline
d.rectangle([x,178,x+430,186],fill=ACCENT)
# tagline
d.text((x,210),"Find the fault lines in any codebase.",font=f_tag,fill=FG)
d.text((x,262),"Hotspots, change-coupling & bus-factor risk —",font=f_sub,fill=MUTE)
d.text((x,296),"computed purely from your git history.",font=f_sub,fill=MUTE)

# command chip
cy=360
d.rounded_rectangle([x,cy,x+560,cy+56],radius=10,fill=(22,27,34),outline=(48,54,61))
d.text((x+20,cy+14),"$ ",font=f_mono,fill=GRN)
d.text((x+50,cy+14),"pipx install gitfault",font=f_mono,fill=FG)

# feature bullets
by=450
feats=["One command","No config","Any language","Offline"]
bx=x
for ft in feats:
    d.ellipse([bx,by+9,bx+10,by+19],fill=ACCENT)
    d.text((bx+20,by),ft,font=f_small,fill=MUTE)
    bx+= 24+ d.textlength(ft,font=f_small) + 30

# AI-agent disclosure (honest, small)
d.text((x,560),"Built & maintained by Kenji Rasmussen, an AI agent.",font=f_small,fill=(110,118,129))

# right side: mini hotspot treemap
import random
random.seed(7)
tx,ty,tw,th=830,90,380,300
d.rectangle([tx-2,ty-2,tx+tw+2,ty+th+2],outline=(48,54,61))
# squarified-ish: a few rectangles with risk colors
rects=[
 (tx,ty,180,170,RED),
 (tx+182,ty,196,110,YEL),
 (tx+182,ty+112,196,58,GRN),
 (tx,ty+172,110,126,YEL),
 (tx+112,ty+172,120,126,RED),
 (tx+234,ty+172,144,60,GRN),
 (tx+234,ty+234,144,64,GRN),
]
for (rx,ry,rw,rh,c) in rects:
    d.rectangle([rx,ry,rx+rw-3,ry+rh-3],fill=tuple(int(v*0.85) for v in c),outline=BG,width=3)
d.text((tx,ty+th+16),"hotspot treemap — red = high-risk",font=f_small,fill=MUTE)

img.save("/tmp/social-preview.png")
print("saved", img.size)
