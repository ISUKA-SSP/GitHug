"""Small read-only formatter; never interprets HTML or executes links/code."""
import re


def formatted_lines(text):
    fenced=False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            fenced=not fenced
            continue
        if fenced:
            yield [('code',line)]
            continue
        heading=re.match(r'^\s{0,3}#{1,6}\s+(.*)',line)
        if heading:
            yield [('heading',heading.group(1).rstrip('#').rstrip())]
            continue
        line=re.sub(r'^(\s*)[-*+]\s+',r'\1• ',line)
        pieces=[]
        for part in re.split(r'(\*\*[^*\n]+\*\*|`[^`\n]+`)',line):
            if part.startswith('**') and part.endswith('**') and len(part)>4:pieces.append(('bold',part[2:-2]))
            elif part.startswith('`') and part.endswith('`') and len(part)>2:pieces.append(('code',part[1:-1]))
            elif part:pieces.append(('',part))
        yield pieces or [('',line)]


def write_explanation(widget,value):
    widget.configure(state='normal');widget.delete('1.0','end')
    widget.tag_configure('heading',font=('Yu Gothic UI',12,'bold'),spacing1=10,spacing3=5)
    widget.tag_configure('bold',font=('Yu Gothic UI',11,'bold'))
    widget.tag_configure('code',font=('Consolas',11))
    for pieces in formatted_lines(value):
        for tag,text in pieces:widget.insert('end',text,(tag,) if tag else ())
        widget.insert('end','\n')
    widget.configure(state='disabled')
