"""Native Tk checks for sprite loading, flipping, bounded movement and click actions."""
import time


def verify_mascot(app):
    view=app.mascot_view;root=app.window;report={}
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:root.update();time.sleep(.02)
    report['mascot_assets_loaded']=view.loaded
    report['mascot_frame_count']=len(view.frames)
    if not view.loaded:raise RuntimeError('キャラクター素材を読み込めません: '+str(view.error))
    normal=view.frames[('silica','walk',0,1)];mirror=view.frames[('silica','walk',0,-1)]
    report['mascot_mirror_correct']=all(normal.get(x,y)==mirror.get(95-x,y) for x,y in ((35,20),(48,40),(50,60)))
    view.set_enabled(True);view.begin('smoke','carry');wait(.6)
    report['mascot_carry']=all(state[0]=='carry' for state in view.last.values())
    report['mascot_stays_in_bounds']=all(actor.left<=actor.x<=actor.right for actor in view.model.actors)
    view.end('smoke');view.begin('smoke','think');wait(.2)
    report['mascot_thinking']=all(state[0]=='idle' and state[1] in (2,3,6,7) for state in view.last.values())
    view.end('smoke',True);wait(.2)
    report['mascot_falls_once']=any(state[0]=='fall' for state in view.last.values())
    wait(1.7)
    report['mascot_recovers']=all(state[0]!='fall' for state in view.last.values())
    view.set_enabled(False)
    report['mascot_off_stops_timer']=view.timer is None and view.canvas.itemcget(view.static_item,'state')=='normal'
    view.canvas.event_generate('<Button-1>',x=60,y=40);root.update_idletasks()
    report['mascot_click_opens_guide']=bool(app.guide_window.winfo_exists())
    def descendants(widget):return [item for child in widget.winfo_children() for item in [child]+descendants(child)]
    report['living_agent_link_visible']=any('LivingAgent' in str(w.cget('text')) for w in descendants(app.guide_window) if w.winfo_class()=='TButton')
    app.guide_window.destroy();view.set_enabled(True)
    if not all(v for k,v in report.items() if k!='mascot_frame_count') or report['mascot_frame_count']!=108:
        raise RuntimeError('キャラクターの確認に失敗しました: '+str(report))
    return report
