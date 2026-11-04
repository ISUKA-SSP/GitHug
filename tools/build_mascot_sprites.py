"""Pack supplied sprite sheets for native Tk playback; Pillow is build-time only.
Usage: python tools/build_mascot_sprites.py PATH_TO_ORIGINAL_SHEETS
Original files are never changed. No artwork is generated or recolored.
"""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
SIZE=(96,80);COLS=9
SPECS={
 'silica':{'idle':'silica_strip(2).png','walk':'silica_walk_trial(1).png','down':'silica_sit_down.png','up':'silica_stand_up.png',
           'carry':'箱を抱えた銀髪少女の歩行スプライト.png','fall':'image(20261104-091332).png',
           'fall_boxes':[(115,0,490,610),(555,40,1030,610),(1030,170,1536,598),(0,740,565,990),(550,650,1065,990),(1070,595,1536,1010)]},
 'stella':{'idle':'stella_strip(2).png','walk':'stella_walk_trial(1).png','down':'stella_sit_down(1).png','up':'stella_stand_up.png',
           'carry':'箱を抱えて歩く紫髪のちびキャラ.png','fall':'image(20261104-091353).png',
           'fall_boxes':[(20,0,520,580),(535,35,1048,585),(1048,150,1536,585),(0,740,590,995),(580,610,1082,995),(1082,595,1536,995)]},
}


def trim(image):
    bounds=image.getchannel('A').point(lambda a:255 if a>40 else 0).getbbox()
    if bounds is None:raise ValueError('Empty sprite')
    return image.crop(bounds)


def build(source):
    dest=ROOT/'githug'/'assets'/'mascots';dest.mkdir(parents=True,exist_ok=True)
    manifest={'frame_size':SIZE,'columns':COLS,'characters':{},'sources':{}}
    for character,spec in SPECS.items():
        frames=[];groups={}
        for group,count,target in [('idle',8,70),('walk',4,70),('carry',4,70),('down',3,66),('up',2,66),('fall',6,70)]:
            path=source/spec[group];original=Image.open(path).convert('RGBA')
            manifest['sources'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            boxes=spec['fall_boxes'] if group=='fall' else [(round(i*original.width/count),0,round((i+1)*original.width/count),original.height) for i in range(count)]
            pieces=[trim(original.crop(box)) for box in boxes]
            reference=max(p.height for p in pieces[:4]) if group=='idle' else pieces[-1].height if group=='up' else pieces[0].height if group in ('down','fall') else max(p.height for p in pieces)
            scale=target/reference
            # Keep a shared scale across a sequence: sitting/falling gets shorter naturally.
            scale=min(scale,min(90/p.width for p in pieces))
            groups[group]=list(range(len(frames),len(frames)+count))
            for piece in pieces:
                width,height=max(1,round(piece.width*scale)),max(1,round(piece.height*scale))
                piece=piece.resize((width,height),Image.Resampling.LANCZOS)
                frame=Image.new('RGBA',SIZE);frame.alpha_composite(piece,((SIZE[0]-width)//2,SIZE[1]-3-height));frames.append(frame)
        atlas=Image.new('RGBA',(COLS*SIZE[0],((len(frames)+COLS-1)//COLS)*SIZE[1]))
        for i,frame in enumerate(frames):atlas.alpha_composite(frame,((i%COLS)*SIZE[0],(i//COLS)*SIZE[1]))
        atlas.save(dest/(character+'.png'),optimize=True)
        manifest['characters'][character]={'file':character+'.png','groups':groups,'count':len(frames)}
    (dest/'sprites.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print({p.name:p.stat().st_size for p in dest.iterdir()})

if __name__=='__main__':build(Path(sys.argv[1]))
