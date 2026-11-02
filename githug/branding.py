"""Original folder/branch app mark, generated with the standard library."""
import base64
import struct
import zlib
import tkinter as tk


def logo_png(size=64):
    scale = 3
    n = size * scale
    pixels = bytearray(n * n * 4)
    def color(value): return tuple(bytes.fromhex(value.lstrip('#'))) + (255,)
    def dot(x,y,rgba):
        if 0 <= x < n and 0 <= y < n:
            offset=(y*n+x)*4;pixels[offset:offset+4]=bytes(rgba)
    def circle(cx,cy,r,value):
        rgba=color(value)
        for y in range(max(0,int(cy-r)),min(n,int(cy+r)+1)):
            for x in range(max(0,int(cx-r)),min(n,int(cx+r)+1)):
                if (x-cx)**2+(y-cy)**2 <= r*r:dot(x,y,rgba)
    def polygon(points,value):
        points=[(x*n/64,y*n/64) for x,y in points];rgba=color(value)
        for y in range(max(0,int(min(p[1] for p in points))),min(n,int(max(p[1] for p in points))+1)):
            intersections=[]
            for a,b in zip(points,points[1:]+points[:1]):
                if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                    intersections.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
            intersections.sort()
            for start,end in zip(intersections[::2],intersections[1::2]):
                for x in range(max(0,int(start)),min(n,int(end)+1)):dot(x,y,rgba)
    def line(points,width,value):
        points=[(x*n/64,y*n/64) for x,y in points]
        for a,b in zip(points,points[1:]):
            steps=max(1,int(max(abs(b[0]-a[0]),abs(b[1]-a[1]))))
            for i in range(steps+1):
                t=i/steps;circle(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,width*n/128,value)
    # Rounded dark tile with a simple, recognizable folder and branching path.
    radius=13*n/64
    for y in range(n):
        for x in range(n):
            dx=max(radius-x,0,x-(n-1-radius));dy=max(radius-y,0,y-(n-1-radius))
            if dx*dx+dy*dy <= radius*radius:dot(x,y,color('#142b38'))
    polygon([(12,19),(27,19),(32,24),(52,24),(52,48),(12,48)],'#3a6978')
    polygon([(12,28),(54,28),(50,49),(12,49)],'#69c6c8')
    line([(24,42),(24,33),(39,33),(43,24)],3.2,'#10252e')
    for x,y in ((24,42),(24,33),(43,24)):
        circle(x*n/64,y*n/64,3.6*n/64,'#e9fcf8')
        circle(x*n/64,y*n/64,1.8*n/64,'#193b49')
    rows=bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            samples=[pixels[((y*scale+dy)*n+(x*scale+dx))*4:((y*scale+dy)*n+(x*scale+dx))*4+4]
                     for dy in range(scale) for dx in range(scale)]
            alpha=sum(p[3] for p in samples)
            rows.extend([round(sum(p[c]*p[3] for p in samples)/alpha) if alpha else 0 for c in range(3)])
            rows.append(round(alpha/(scale*scale)))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(rows),9))+chunk(b'IEND',b'')


def icon_bytes():
    sizes=(16,32,48,64,128,256)
    images=[logo_png(size) for size in sizes]
    header=struct.pack('<HHH',0,1,len(images));offset=6+16*len(images)
    entries=[]
    for size,data in zip(sizes,images):
        entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset))
        offset+=len(data)
    return header+b''.join(entries)+b''.join(images)


def attach_logo(window):
    images=[tk.PhotoImage(master=window,data=base64.b64encode(logo_png(size))) for size in (32,64)]
    window.iconphoto(True,*images)
    window._githug_logo_images=images
    return images[0]
