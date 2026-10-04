"""Personal Undertale / Deltarune faces using optional, local official artwork.

Art remains outside Git. The local sources.json and extraction.json record its
provenance. Percentages and bars always mean quota USED, rather than game HP/TP.
"""
import functools
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageOps
from token_tv import local_art
from token_tv.display import STATUS, overview_rows, pixel_text

WHITE, RED, GOLD = '#ffffff', '#ff2222', '#ffff00'
ORANGE, PURPLE, CYAN = '#ff8c00', '#8e4fdc', '#33e6ff'
FRAMES = 16


@functools.lru_cache(maxsize=64)
def _sprite(root, name):
    with Image.open(root / 'sprites' / (name + '.png')) as image:
        return image.convert('RGBA')


def sprite(name):
    return _sprite(local_art.ART_ROOT, name).copy()


def fit_sprite(image, box):
    """Uniform nearest-neighbour sizing; no independent width/height stretching."""
    result = image.copy()
    result.thumbnail(box, Image.Resampling.NEAREST)
    return result


def put_sprite(canvas, name, box, phase=0, bob=False):
    x, y, width, height = box
    image = fit_sprite(sprite(name), (width, height))
    dy = round(math.sin(phase * 2 * math.pi / FRAMES)) if bob else 0
    canvas.paste(image, (x + (width-image.width)//2, y + height-image.height+dy), image)


def label(draw, xy, value, scale=1, color=WHITE, align='left', width=114):
    value = str(value).upper()
    limit = max(1, (width // scale + 1) // 6)
    if len(value) > limit:
        value = value[:limit-1] + '?'
    x, y = xy
    text_width = (len(value)*6-1)*scale
    if align == 'center':x -= text_width//2
    elif align == 'right':x -= text_width
    marks = {':': '00000/00100/00100/00000/00100/00100/00000',
             '/': '00001/00001/00010/00100/01000/10000/10000',
             '*': '00000/10101/01110/11111/01110/10101/00000'}
    for index, character in enumerate(value):
        xx = x+index*6*scale
        if character not in marks:
            pixel_text(draw,(xx,y),character,scale,color)
            continue
        for row, bits in enumerate(marks[character].split('/')):
            for col, bit in enumerate(bits):
                if bit == '1':draw.rectangle((xx+col*scale,y+row*scale,xx+(col+1)*scale-1,y+(row+1)*scale-1),fill=color)


def heart(draw, x, y, color=RED):
    for row, bits in enumerate(('0110110','1111111','1111111','0111110','0011100','0001000')):
        for col, bit in enumerate(bits):
            if bit == '1':draw.point((x+col,y+row),fill=color)


def star(draw, x, y, phase, color=GOLD):
    radius = 5 if phase % 8 < 4 else 3
    draw.line((x-radius,y,x+radius,y),fill=color)
    draw.line((x,y-radius,x,y+radius),fill=color)
    draw.rectangle((x-1,y-1,x+1,y+1),fill=color)
    angle = phase * 2 * math.pi / FRAMES
    draw.point((x+round(8*math.cos(angle)),y+round(8*math.sin(angle))),fill=color)


def duration(window, now):
    if not window or not window.get('resets_at'):
        return '--'
    minutes = max(0, int((window['resets_at']-now+59)//60))
    return (f'{minutes//1440}D {minutes%1440//60}H' if minutes>=1440
            else f'{minutes//60}H {minutes%60}M')


def used_bar(draw, box, used, color, stale=False):
    x,y,right,bottom = box
    draw.rectangle(box,outline=WHITE)
    if used is not None:
        width = round((right-x-1)*max(0,min(100,used))/100)
        if width:
            draw.rectangle((x+1,y+1,x+width,bottom-1),fill=color)
            if stale:
                for hatch in range(x+1,x+width+1,4):
                    draw.line((hatch,y+1,hatch,bottom-1),fill='#000000')
    else:
        for tick in range(x+3,right-2,7):draw.point((tick,(y+bottom)//2),fill='#555555')


def footer(draw, action, right, deltarune=False):
    color = PURPLE if deltarune else ORANGE
    width = len(action)*6+7
    draw.rectangle((6,109,6+width,123),outline=color)
    label(draw,(10,113),action,color=color)
    label(draw,(120,113),right,color=WHITE,align='right',width=108-width)


def _undertale(panel, snapshot, date, now, phase):
    canvas = Image.new('RGB',(128,128),'#000000');draw=ImageDraw.Draw(canvas)
    draw.rectangle((2,2,125,125),outline=WHITE,width=2)
    kind = panel['kind']
    if kind == 'usage':
        row, window = panel['row'],panel['window']
        label(draw,(8,8),row['alias'])
        label(draw,(8,20),'* '+(window['label'] if window else STATUS.get(row['status'],'NO DATA')),color=WHITE)
        old = row['status']=='stale'
        if old:label(draw,(120,20),'OLD',color=GOLD,align='right')
        draw.rectangle((6,30,121,85),outline=WHITE)
        name = {'claude':'papyrus','codex':'sans','grok':'toriel'}[row['provider']]
        put_sprite(canvas,name,(10,36,37,42))
        used = window['used_percent'] if window else None
        label(draw,(119,43),f'{used:.0f}%' if used is not None else '--',scale=3,align='right',width=71)
        label(draw,(119,74),'USED' if used is not None else 'UNKNOWN',align='right',color=WHITE,width=67)
        # The SOUL moves below the portrait, clear of quota text.
        heart(draw,14+phase%8,76+phase//8)
        used_bar(draw,(7,90,120,96),used,GOLD,old)
        label(draw,(8,100),'RESET IN')
        footer(draw,'ACT',duration(window,now))
    elif kind == 'clock':
        label(draw,(64,9),'SAVE POINT',align='center')
        star(draw,64,33,phase)
        draw.rectangle((6,47,121,78),outline=WHITE)
        clock(draw,date,(64,53),3)
        label(draw,(64,86),date.strftime('%a %d %b'),align='center')
        put_sprite(canvas,'dog-bark' if phase//4%2 else 'dog',(8,95,23,22))
        label(draw,(120,101),'STAY',align='right')
        label(draw,(120,113),'DETERMINED',align='right',color=GOLD,width=82)
    elif kind == 'status':
        label(draw,(64,9),'PARTY STATUS',align='center')
        put_sprite(canvas,'toriel',(42,23,44,34))
        star(draw,20,40,phase)
        rows = list(snapshot['accounts'].values())
        label(draw,(64,65),f"{sum(r['status']=='ok' for r in rows)}/{len(rows)}",scale=3,align='center')
        label(draw,(64,93),'ACCOUNTS LIVE',align='center')
        updated = snapshot.get('updated_at')
        footer(draw,'SAVE',datetime.fromtimestamp(updated,date.tzinfo).strftime('%H:%M') if updated else '--')
    else:
        label(draw,(64,9),'UNDERTALE',align='center')
        put_sprite(canvas,'blook',(41,30,46,46),phase,True)
        star(draw,20,43,phase)
        label(draw,(64,88),'NO ACCOUNT',align='center')
        footer(draw,'ACT','CONNECT')
    return canvas


def clock(draw,date,xy,scale):
    # The project's 5x7 alphabet has no colon. Draw it explicitly, on the same grid.
    x,y=xy;value=date.strftime('%H%M');width=29*scale
    left=x-width//2
    label(draw,(left,y),value[:2],scale=scale)
    label(draw,(left+18*scale,y),value[2:],scale=scale)
    for top in (y+scale,y+5*scale):
        draw.rectangle((left+14*scale,top,left+15*scale-1,top+scale-1),fill=WHITE)


def _deltarune(panel,snapshot,date,now,phase):
    canvas=Image.new('RGB',(128,128),'#050008');draw=ImageDraw.Draw(canvas)
    for pos in range(-16,145,16):
        draw.line((pos+phase,26,pos+phase,104),fill='#240024')
        if 26 <= pos+phase <= 104:
            draw.line((4,pos+phase,123,pos+phase),fill='#240024')
    draw.rectangle((2,2,125,125),outline=PURPLE,width=2)
    kind=panel['kind']
    if kind=='usage':
        row,window=panel['row'],panel['window']
        heart(draw,8,8)
        label(draw,(20,8),row['alias'],width=100)
        label(draw,(8,20),window['label'] if window else STATUS.get(row['status'],'NO DATA'))
        old=row['status']=='stale'
        if old:label(draw,(120,20),'OLD',color=GOLD,align='right')
        name={'claude':'susie','codex':'kris','grok':'ralsei'}[row['provider']]
        color={'claude':'#ff4fdc','codex':CYAN,'grok':'#7cff8b'}[row['provider']]
        put_sprite(canvas,name,(15,31,35,51),phase,True)
        label(draw,(32,86),name,align='center',color=color,width=55)
        used=window['used_percent'] if window else None
        label(draw,(120,47),f'{used:.0f}%' if used is not None else '--',scale=3,align='right',width=71)
        label(draw,(120,76),'USED' if used is not None else 'UNKNOWN',align='right',width=67)
        # A TP-shaped vertical meter, explicitly measuring quota USED.
        used_bar(draw,(6,34,11,82),None,GOLD)
        if used is not None:
            height=round(46*max(0,min(100,used))/100)
            if height:draw.rectangle((7,82-height,10,81),fill=color)
        label(draw,(120,88),'RESET IN',align='right',width=62)
        used_bar(draw,(7,97,120,103),used,color,old)
        footer(draw,'ACT',duration(window,now),True)
    elif kind=='clock':
        image=ImageOps.fit(sprite('fountain-'+str(phase*5//FRAMES)),(118,118),method=Image.Resampling.NEAREST,centering=(.5,.6))
        canvas.paste(image,(5,5));draw=ImageDraw.Draw(canvas)
        for box in ((5,5,122,22),(7,49,120,78),(7,87,120,98),(7,106,120,120)):
            draw.rectangle(box,fill='#000000')
        label(draw,(64,10),'DARK FOUNTAIN',align='center')
        clock(draw,date,(64,53),3)
        label(draw,(64,89),date.strftime('%a %d %b'),align='center')
        star(draw,16,112,phase,WHITE)
        label(draw,(112,110),date.tzname() or 'LOCAL',align='right',color=CYAN)
    elif kind=='status':
        label(draw,(64,9),'PARTY STATUS',align='center')
        put_sprite(canvas,'ralsei',(45,25,38,50),phase,True)
        rows=list(snapshot['accounts'].values())
        draw.rectangle((7,77,120,104),fill='#000000',outline=WHITE)
        label(draw,(64,80),f"{sum(r['status']=='ok' for r in rows)}/{len(rows)}",scale=2,align='center')
        label(draw,(64,96),'ACCOUNTS LIVE',align='center',color='#7cff8b')
        updated=snapshot.get('updated_at')
        footer(draw,'SAVE',datetime.fromtimestamp(updated,date.tzinfo).strftime('%H:%M') if updated else '--',True)
    else:
        label(draw,(64,9),'DELTARUNE',align='center')
        put_sprite(canvas,'ralsei',(43,28,42,55),phase,True)
        label(draw,(64,93),'NO ACCOUNT',align='center')
        footer(draw,'ACT','CONNECT',True)
    return canvas


def render_panel(panel,snapshot,style,now,phase=0,timezone='Europe/London'):
    date=datetime.fromtimestamp(now,ZoneInfo(timezone))
    return (_undertale if style=='undertale' else _deltarune)(panel,snapshot,date,now,phase)


def render_stock(snapshot,style):
    """Keep the 240px photo-display contract for the optional local styles, too."""
    now=time.time();rows=overview_rows(snapshot)
    canvas=Image.new('RGB',(240,240),'#000000');draw=ImageDraw.Draw(canvas)
    draw.rectangle((2,2,237,237),outline=WHITE if style=='undertale' else PURPLE,width=2)
    for index,row in enumerate(rows):
        y=6+index*77+(3-len(rows))*77//2
        label(draw,(10,y),row['alias'],width=210)
        name=({'claude':'papyrus','codex':'sans','grok':'toriel'} if style=='undertale'
              else {'claude':'susie','codex':'kris','grok':'ralsei'})[row['provider']]
        put_sprite(canvas,name,(12,y+13,38,43))
        window=max(row['windows'],key=lambda w:w['used_percent'],default=None) if row['status'] in ('ok','stale') else None
        used=window['used_percent'] if window else None
        label(draw,(220,y+24),f'{used:.0f}%' if used is not None else '--',3,align='right',width=157)
        label(draw,(56,y+53),('OLD ' if row['status']=='stale' else '')+(window['label'] if window else STATUS.get(row['status'],'NO DATA')),color=GOLD)
        used_bar(draw,(10,y+65,229,y+70),used,GOLD if style=='undertale' else PURPLE,row['status']=='stale')
    return canvas
