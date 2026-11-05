"""Small, local-only mascot animation. It never drives application operations."""
from dataclasses import dataclass
import json
from pathlib import Path
import random
import time
import tkinter as tk


def operation_pose(description):
    return 'carry' if any(word in description for word in ('コピーしています','更新しています','送っています','ごみ箱へ')) else 'think'


@dataclass
class Actor:
    name:str
    home:float
    left:float
    right:float
    x:float
    direction:int=1
    facing:int|None=None
    sitting:bool=False
    state:str='idle'
    since:float=0
    next_action:float=8
    next_blink:float=4
    blink_until:float=0
    fall_started:float|None=None


    def __post_init__(self):
        if self.facing is None:self.facing=self.direction


class MascotModel:
    def __init__(self,now=0,seed=None):
        self.now=now;self.previous=now;self.rng=random.Random(seed);self.enabled=True;self.activities={}
        self.actors=[Actor('silica',60,48,82,60,since=now,next_action=now+9,next_blink=now+3),
                     Actor('stella',200,178,212,200,direction=-1,sitting=True,since=now,next_action=now+13,next_blink=now+5)]
        self.error_index=0

    @property
    def activity(self):
        return 'carry' if 'carry' in self.activities.values() else 'think' if self.activities else 'idle'

    def begin(self,source,pose='think'):self.activities[source]=pose

    def end(self,source,error=False,now=None):
        self.activities.pop(source,None)
        if error and self.enabled:
            actor=self.actors[self.error_index%len(self.actors)];self.error_index+=1
            actor.fall_started=self.now if now is None else now

    def _move(self,actor,delta):
        previous=actor.x
        actor.x+=actor.direction*18*delta
        if actor.x!=previous:actor.facing=actor.direction
        if actor.x>=actor.right:actor.x=actor.right;actor.direction=-1;return True
        if actor.x<=actor.left:actor.x=actor.left;actor.direction=1;return True
        return False

    def advance(self,now):
        delta=max(0,min(.15,now-self.previous));self.previous=now;self.now=now
        output=[]
        for actor in self.actors:
            if not self.enabled:
                output.append((actor.name,'idle',4,actor.home,1));continue
            if actor.fall_started is not None:
                elapsed=now-actor.fall_started
                ends=(.12,.26,.44,.94,1.19,1.44)
                if elapsed<1.44:
                    frame=next(i for i,end in enumerate(ends) if elapsed<end)
                    output.append((actor.name,'fall',frame,actor.x,actor.facing));continue
                if elapsed<1.70:
                    output.append((actor.name,'up',min(1,int((elapsed-1.44)/.13)),actor.x,actor.facing));continue
                actor.fall_started=None;actor.sitting=False;actor.state='idle';actor.next_action=now+8
            if now>=actor.next_blink:
                actor.blink_until=now+.15;actor.next_blink=now+self.rng.uniform(3,7)
            blink=int(now<actor.blink_until)
            activity=self.activity
            if activity!='idle':
                actor.next_action=now+self.rng.uniform(5,12)
                if activity=='carry':
                    if actor.sitting:
                        if actor.state!='busy_up':actor.state='busy_up';actor.since=now
                        elapsed=now-actor.since
                        if elapsed<.26:
                            output.append((actor.name,'up',min(1,int(elapsed/.13)),actor.x,actor.facing));continue
                    actor.state='idle';actor.sitting=False;self._move(actor,delta)
                    output.append((actor.name,'carry',int(now/.17)%4,actor.x,actor.facing))
                else:
                    actor.state='idle';output.append((actor.name,'idle',(6 if actor.sitting else 2)+blink,actor.x,actor.facing))
                continue
            if actor.state in ('down','up'):
                duration=.13*(3 if actor.state=='down' else 2)
                if now-actor.since<duration:
                    output.append((actor.name,actor.state,int((now-actor.since)/.13),actor.x,actor.facing));continue
                actor.sitting=actor.state=='down';actor.state='idle';actor.next_action=now+self.rng.uniform(6,14)
            if actor.state=='walk':
                ended=self._move(actor,delta)
                output.append((actor.name,'walk',int((now-actor.since)/.16)%4,actor.x,actor.facing))
                if ended:actor.state='idle';actor.next_action=now+self.rng.uniform(6,14)
                continue
            if now>=actor.next_action:
                actor.since=now
                if actor.sitting:actor.state='up'
                elif self.rng.random()<.5:actor.state='down'
                else:actor.state='walk'
                actor.next_action=now+self.rng.uniform(6,14)
            output.append((actor.name,'idle',(4 if actor.sitting else 0)+blink,actor.x,actor.facing))
        return output


class MascotView:
    def __init__(self,parent,on_click,fallback,enabled=True,clock=time.monotonic):
        self.clock=clock;self.model=MascotModel(now=clock());self.timer=None;self.frames={};self.items={};self.last={}
        self.loaded=False;self.error=None;self.closed=False
        self.canvas=tk.Canvas(parent,width=260,height=83,background='#202020',borderwidth=0,highlightthickness=0,cursor='hand2',takefocus=True)
        self.canvas.bind('<Button-1>',lambda e:on_click())
        self.canvas.bind('<Return>',lambda e:on_click());self.canvas.bind('<space>',lambda e:on_click())
        self.canvas.bind('<Destroy>',lambda e:self.close() if e.widget is self.canvas else None)
        self.static_item=self.canvas.create_image(130,83,image=fallback,anchor='s')
        try:
            self.load(Path(__file__).parent/'assets'/'mascots')
            for actor in self.model.actors:
                self.items[actor.name]=self.canvas.create_image(actor.home,83,anchor='s',tags=('actor',))
            self.loaded=True
        except (OSError,ValueError,KeyError,TypeError,tk.TclError) as exc:
            self.error=str(exc)
        self.set_enabled(enabled)

    def load(self,base):
        manifest=json.loads((base/'sprites.json').read_text(encoding='utf-8'))
        width,height=manifest['frame_size'];columns=manifest['columns']
        if (width,height)!=(96,80) or columns!=9:raise ValueError('Unsupported sprite dimensions')
        for name,character in manifest['characters'].items():
            file=character['file']
            if Path(file).name!=file or not 0<character['count']<=64:raise ValueError('Invalid sprite atlas')
            sheet=tk.PhotoImage(master=self.canvas,file=str(base/file))
            for group,indices in character['groups'].items():
                for frame,index in enumerate(indices):
                    x=(index%columns)*width;y=(index//columns)*height
                    image=tk.PhotoImage(master=self.canvas,width=width,height=height)
                    image.tk.call(str(image),'copy',str(sheet),'-from',x,y,x+width,y+height,'-to',0,0)
                    mirror=tk.PhotoImage(master=self.canvas,width=width,height=height)
                    mirror.tk.call(str(mirror),'copy',str(image),'-subsample',-1,1)
                    self.frames[(name,group,frame,1)]=image;self.frames[(name,group,frame,-1)]=mirror

    def begin(self,source,pose='think'):self.model.begin(source,pose)
    def end(self,source,error=False):self.model.end(source,error,self.clock())

    def set_enabled(self,value):
        if self.timer is not None:
            try:self.canvas.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer=None
        self.model.enabled=bool(value)
        if self.loaded and not self.closed:
            self.canvas.itemconfigure(self.static_item,state='hidden' if value else 'normal')
            for item in self.items.values():self.canvas.itemconfigure(item,state='normal' if value else 'hidden')
            if value:self.tick()

    def tick(self):
        self.timer=None
        if self.closed or not self.canvas.winfo_exists():return
        for name,group,frame,x,direction in self.model.advance(self.clock()):
            state=(group,frame,round(x),direction)
            if self.last.get(name)==state:continue
            self.last[name]=state
            self.canvas.itemconfigure(self.items[name],image=self.frames[(name,group,frame,direction)])
            self.canvas.coords(self.items[name],x,83)
        if self.model.enabled:self.timer=self.canvas.after(100,self.tick)

    def close(self):
        self.closed=True
        if self.timer is not None:
            try:self.canvas.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer=None
