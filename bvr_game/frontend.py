"""Reference-inspired hangar, settings and battle preparation, using actual catalog data.

Coordinates use a1920x1080 design canvas; hit testing follows the same transform.
The frontend owns navigation/drafts only. FlightGame starts the actual core sortie.
"""
from pathlib import Path
from . import loadouts
import copy, math
from .client_settings import ClientSettings,DEFAULTS,CHOICES
from .aircraft_tree import history,countries,ordered,decade_label,layout as tree_layout,ROLES

def rgba(value,alpha=255):
    r,g,b=bytes.fromhex(value);return alpha<<24|b<<16|g<<8|r
INK=rgba('172028',230);PANEL=rgba('28343d',225);CONTROL=rgba('10171d',245)
LINE=rgba('6a7880',110);TEXT=rgba('dfe4e5');MUTED=rgba('a4afb4');ACCENT=rgba('c25b31');GOLD=rgba('dbad6c');GREEN=rgba('9db89d')
MISSIONS={'air':'空中作战','strike':'对地打击','combined':'联合打击','training':'自由试飞',
          'intercept_patrol':'巡逻拦截','convoy':'车队打击'}
LOADOUTS={'mixed':'多用途挂载','intercept':'空中拦截','strike':'对地挂载','unarmed':'无武装','clean':'无武装','custom':'自定义挂载'}
CONTROLS=[('鼠标移动','指向飞行方向'),('W / S','压低 / 拉起机头'),('A / D','向左 / 向右滚转'),
          ('C','自由观察'),('鼠标右键','缩放视野'),('鼠标滚轮','调整油门'),('R / Tab','锁定 / 切换目标'),
          ('Space / B','发射所选武器 / 投弹'),('V','切换武器'),('P / .','暂停 / 精确步进'),
          ('F5 / F6','切换辅助 / 暂停时重载参数'),('F9 / F12','打开出击记录 / 截图'),('Esc','返回机库')]

class Frontend:
    def __init__(self,game,path=None):
        self.game=game;self.settings=ClientSettings(path);self.page='hangar';self.menu=False
        self.tab='general';self.section='general';self.country=history(game.current_aircraft())['country'];self.offset=0
        self.tree_open=False;self.tree_scroll=0.;self.expanded_families=set();self.country_offset=0
        self.typing=None;self.dropdown=None;self.hover=(-1,-1);self.notice=''
        self.orbit=0.;self.zoom=1.;self.draft={};self.preparation={}
        self.regions=[];self.texts=[];self.lines=[];self.images=[]
        self.selection_changed(game.current_aircraft())
    def home(self):self.page='hangar';self.dropdown=None;self.typing=None;self.menu=False;self.tree_open=False
    def rows(self):
        return ordered(self.game.filtered_aircraft(),self.country)
    def selection_changed(self,row):
        self.country=history(row)['country'];self.tree_open=False
        rows=self.rows();index=next((i for i,r in enumerate(rows) if r['id']==row['id']),None)
        if index is not None and not self.offset<=index<self.offset+8:self.offset=index//8*8
    def missions(self):
        row=self.game.current_aircraft()
        convoy=bool(self.game.map.get('mission',{}).get('ground_units'))
        if self.page=='prepare' and self.preparation.get('map_version'):
            version=next((r for r in self.game.map_versions() if r['id']==self.preparation['map_version']),None)
            if version and version.get('quality')!='external':convoy=version.get('supports_convoy',False)
        return [m for m in MISSIONS if m in row['missions'] and (m!='convoy' or convoy) and (m not in ('strike','combined','convoy') or any('Mk-82' in s.weapons for s in loadouts.stations(row).stations))]
    def select(self,id):
        try:
            self.game.select_aircraft(id);self.notice=''
            self.country=history(id)['country'];self.tree_open=False
            rows=self.rows();index=next((i for i,r in enumerate(rows) if r['id']==id),None)
            if index is not None and not self.offset<=index<self.offset+8:self.offset=index//8*8
        except (ValueError,FileNotFoundError) as error:self.notice=str(error)
    def open_settings(self):
        self.page='settings';self.menu=False;self.dropdown=None;self.typing=None;self.tree_open=False
        self.draft=dict(self.settings.values)
    def open_preparation(self,training=False):
        self.page='prepare';self.menu=False;self.dropdown=None;self.typing=None;self.tree_open=False
        g=self.game;row=g.current_aircraft()
        preset=next((p['id'] for p in row['legal_loadouts'] if (p['missiles'],p['bombs'])==(g.config.missiles,g.config.bombs)),row['default_loadout'])
        self.preparation={'mission':'training' if training else g.config.mission,'loadout':preset,
                          'enemy_attacks':bool(g.config.enemy_attacks),'seed':str(g.config.seed),
                          'map_version':next(r['id'] for r in g.map_versions() if Path(r['map'])==g.map_path)}
        if self.preparation['mission'] not in self.missions():self.preparation['mission']=self.missions()[0]
        definition=loadouts.stations(row)
        mounts=dict(g.config.loadout) if g.config.use_station_loadout else loadouts.preset(row,preset)
        self.preparation['mounts']=mounts
        self.preparation['loadout']=next((id for id,m in definition.presets.items() if dict(m)==mounts),'custom')
        self.station=definition.stations[0].id if definition.stations else ''
        self.normalize_preparation()
    def normalize_preparation(self):
        if self.game.current_aircraft().get('library_aircraft') or self.preparation['mission']=='training':self.preparation['enemy_attacks']=False
        if self.preparation['mission']=='intercept_patrol':
            self.preparation['enemy_attacks']=True
    def apply_preferences(self):
        g=self.game;p=self.settings.values;g.quality=p['quality'];g.show_hud=p['show_hud']
        if g.player_input:
            g.player_input.profile=copy.deepcopy(g.player_profile)
            g.player_input.profile['input']['sensitivity']*=p['mouse_sensitivity']
            g.player_input.mode=p['control_mode']
        if g.renderer:
            g.renderer.set_quality(g.quality)
            if hasattr(g.renderer,'set_audio_volume'):g.renderer.set_audio_volume(p['master_volume'])
    def launch(self):
        g=self.game;row=g.current_aircraft();self.normalize_preparation()
        if not row['available']:self.notice=row['unavailable_reason'];return
        try:
            if self.preparation['mission'] not in self.missions():raise ValueError('unsupported mission')
            seed=int(self.preparation['seed'])
            if not 0<=seed<=2147483647:raise ValueError('invalid seed')
            mounts=self.preparation['mounts']
            errors=loadouts.native.validate_loadout(row['simulation_model'],mounts)
            if errors:raise ValueError('; '.join(errors))
            g.load_map_version(self.preparation['map_version'])
            g.config.mission=self.preparation['mission'];g.config.seed=seed
            loadouts.configure(g.config,row,mounts)
            g.config.enemy_attacks=self.preparation['enemy_attacks']
            g.weapon=loadouts.initial_weapon(mounts)
            self.home();g.start()
        except (ValueError,StopIteration,OSError,RuntimeError) as error:self.notice='出击未开始：'+str(error)
    def rect(self,x,y,w,h,color=PANEL):self.lines.append((x,y,w,h,color,0))
    def text(self,x,y,value,size=18,color=TEXT):self.texts.append((x,y,str(value),size,color))
    def mask_text(self,x,y,w,h):
        # Native HUD submits shapes before text; remove obscured lower text.
        self.texts=[t for t in self.texts if not (x<=t[0]<x+w and y-10<=t[1]<y+h)]
    def border(self,x,y,w,h,color=LINE):
        for a,b,c,d in [(x,y,w,1),(x,y+h,w,1),(x,y,1,h),(x+w,y,1,h)]:self.rect(a,b,c,d,color)
    def button(self,id,x,y,w,h,label,action,primary=False,selected=False,enabled=True):
        hover=x<=self.hover[0]<=x+w and y<=self.hover[1]<=y+h
        color=rgba('53616a') if hover else rgba('3d4c56') if selected else PANEL
        if not enabled:color=rgba('293137')
        self.rect(x,y,w,h,color)
        if primary:
            self.rect(x,y,w,h,rgba('652d1c'));self.border(x,y,w,h,rgba('d58a4d'))
            for i in range(12):self.rect(x+2,y+2+i*(h-4)/12,w-4,(h-4)/12,rgba(f'{126+i*3:02x}{55+i:02x}{29+i//2:02x}'))
        if selected:self.rect(x,y+h-3,w,3,ACCENT)
        self.text(x+12,y+(h-24)/2,label,21 if primary else 18,TEXT if enabled else MUTED)
        if enabled:self.regions.append((id,(x,y,w,h),action))
    def field(self,id,y,label,value,options=None,enabled=True):
        self.field_label(y+7,label)
        self.button(id,960,y,475,37,str(value)+('     ˅' if options else ''),('dropdown',id,options) if options else (id,),enabled=enabled)
    def field_label(self,y,label):
        width=sum(1 if ord(c)>255 else .55 for c in label)*19*.85
        self.text(938-width,y,label,19,MUTED)
    def card_strip(self,y=914,interactive=True):
        g=self.game;rows=self.rows();self.offset=max(0,min(max(0,len(rows)-8),self.offset))
        self.rect(0,y-(80 if interactive else 39),1920,207 if interactive else 166,rgba('152027',245))
        if interactive:
            tabs=countries(g.aircraft_rows)
            # Reference hangar: one fixed toggle precedes the nation row.
            self.button('tree_toggle',24,y-78,188,33,'',('tree',),selected=self.tree_open)
            self.text(81,y-73,'科技树',19)
            direction='v' if self.tree_open else '^'
            for x in (36,188):
                self.text(x,y-78,direction,17,MUTED);self.text(x,y-73,direction,17,MUTED)
            self.text(35,y-33,'点击展开 / 收起',14,MUTED)
            for i,c in enumerate(tabs[self.country_offset:self.country_offset+20]):
                self.button('country_'+c['id'],224+(i%10)*128,y-78+(i//10)*36,124,33,
                            c['label']+' '+str(c['count']),('country',c['id']),selected=self.country==c['id'])
            self.button('search',1520,y-77,375,33,'搜索型号 / '+g.aircraft_search+('|' if self.typing=='search' else ''),('search',))
            self.text(1532,y-31,f'{len(rows)} 架 · 滚轮浏览 · Esc 收起',15,MUTED)
            if len(tabs)>20:self.button('countries_more',1820,y-113,75,29,'更多',('countries_more',))
        else:
            label=next((c['label'] for c in countries(g.aircraft_rows) if c['id']==self.country),self.country)
            self.text(35,y-29,label+'  /  年代顺序',17,MUTED)
            self.text(1450,y-29,f'{len(rows)} 架    {self.offset+1 if rows else 0}–{min(self.offset+8,len(rows))}',15,MUTED)
        for i,row in enumerate(rows[self.offset:self.offset+8]):
            x=67+i*221;selected=row['simulation_model']==g.config.player_model
            self.button('aircraft_'+row['id'],x,y,212,103,'',('select',row['id']),selected=selected,enabled=interactive)
            self.rect(x,y,212,22,rgba('334754'))
            self.text(x+8,y+2,history(row)['family'][:23],15)
            path=Path(__file__).resolve().parents[1]/'game/assets/ui/aircraft'/f'{row["id"]}.png'
            if path.exists():self.images.append((x+12,y+22,188,60,str(path)))
            else:
                self.text(x+14,y+39,row['display_name'][:20],14,MUTED)
            self.text(x+8,y+81,'试飞' if row.get('library_aircraft') else '作战',14,GREEN)
            self.text(x+138,y+81,'就绪' if row['available'] else '不可用',14,MUTED)
        self.button('previous',20,y,35,103,'‹',('scroll',-8),enabled=interactive and self.offset>0)
        self.button('next',1846,y,49,103,'›',('scroll',8),enabled=interactive and self.offset+8<len(rows))
    def top(self):
        self.rect(0,0,1920,48,rgba('162023',250));self.rect(0,0,1920,2,rgba('b46442',180))
        self.button('menu',22,6,56,35,'',('menu',))
        for y in (15,22,29):self.rect(39,y,22,2,TEXT)
        self.text(103,14,'机库',19);self.text(198,15,'BVR SIM',17,MUTED)
        self.text(553,15,'本地飞行员',17)
        self.button('battle',820,5,280,51,'加入战斗  !',('prepare',),primary=True)
        self.rect(790,57,340,38,INK);self.text(830,64,MISSIONS.get(self.game.config.mission,'空中作战'),19)
        self.text(1285,16,f'{len(self.game.aircraft_rows)} 架飞机',16,MUTED)
        self.button('logs',1450,7,153,33,'战斗记录  F9',('logs',))
        self.button('settings',1620,7,132,33,'设置  F2',('settings',))
        self.button('controls',1768,7,128,33,'操作指南',('controls',))
    def hangar(self):
        g=self.game;r=g.current_aircraft();self.top()
        self.rect(16,119,397,513,rgba('28333b',190));self.rect(16,119,397,40,rgba('17232e',240))
        self.text(35,127,r['display_name'][:32],23)
        self.text(36,178,'载具资料',18)
        info=[('型号',r['id']),('动力学',r['fdm']['type'].upper()),('用途','无武装试飞' if r.get('library_aircraft') else '空战 / 对地任务'),
              ('雷达','无战斗传感器' if r.get('library_aircraft') else f'{r.get("radar",{}).get("range_m",0)/1000:g} km  /  共有参数'),
              ('空空导弹',f'{g.config.missiles} 枚'),
              ('航弹',f'{g.config.bombs} × Mk-82' if g.config.bombs else '无')]
        bounds=r['appearance'].get('bounds')
        if bounds:
            info.extend([('源模型翼展',f'{bounds["span"][0]:.1f} m'),('源模型机长',f'{bounds["span"][1]:.1f} m')])
        for i,(label,value) in enumerate(info):
            y=219+i*33;self.text(35,y,label,16,MUTED);self.text(185,y,value,16)
            self.rect(35,y+28,355,1,rgba('87949a',35))
        self.text(35,510,'资源模型 · 当前挂载',15,MUTED)
        self.button('loadout',32,546,364,35,'装备与战斗准备',('prepare',))
        self.button('testflight',32,589,364,33,'试飞',('testflight',))
        self.rect(1595,159,301,150,rgba('27343d',210))
        self.text(1612,173,'飞行任务',21);self.rect(1610,207,270,1,LINE)
        self.text(1612,221,MISSIONS.get(g.config.mission,g.config.mission),18)
        self.text(1612,256,'选择挂载，确认后出击。',16,MUTED)
        self.text(1612,281,'核心战果 · ACMI 出击记录',14,MUTED)
        self.text(455,813,'拖动右键旋转预览    点击国家展开科技树    / 搜索',15,MUTED)
        self.card_strip()
        self.rect(0,1028,1920,52,rgba('111b22',250));self.text(34,1043,'BVR SIM  /  飞行基地',16,MUTED)
        self.text(1320,1043,'FlightGear  ·  Wicked Engine',15,MUTED)
        if self.tree_open:self.technology_tree()
        if self.notice:self.text(450,112,self.notice[:90],16,GOLD)
        if self.menu:
            self.mask_text(22,47,240,156)
            for i,(label,action) in enumerate([('游戏设置',('settings',)),('按键与操作',('controls',)),('出击记录',('logs',)),('退出游戏',('quit',))]):
                self.button('menu_'+str(i),22,47+i*39,240,39,label,action)
    def technology_tree(self):
        """All cards use pre-rendered PNGs; no per-card 3D scenes are created."""
        self.mask_text(15,102,1890,730)
        # Obscured hangar controls must not remain clickable through the panel.
        self.regions=[r for r in self.regions if r[1][1]<100 or r[1][1]>=834]
        self.rect(15,102,1890,730,rgba('17242e',250));self.border(15,102,1890,730)
        label=next((c['label'] for c in countries(self.game.aircraft_rows) if c['id']==self.country),self.country)
        rows=self.rows();tree=tree_layout(rows,self.expanded_families)
        self.tree_scroll=max(0,min(max(0,tree['height']-560),self.tree_scroll))
        self.text(34,115,label+'  /  航空科技树',25)
        self.text(365,121,f'{len(rows)} 架 · 按机型家族年代粗排 · 点击机型预览',17,MUTED)
        for lane,(_,name) in enumerate(ROLES):
            self.rect(137+lane*340,158,325,35,rgba('354653'));self.text(150+lane*340,164,name,19)
        self.text(35,165,'研发年代',18,MUTED)
        top,bottom=204,764
        for band in tree['bands']:
            y=top+band['top']-self.tree_scroll
            if top<=y<bottom:
                self.rect(30,y,1850,1,LINE);self.text(35,y+8,decade_label(band['decade']),17,MUTED)
            elif y<top<y+band['height']:self.text(35,top+8,decade_label(band['decade']),17,MUTED)
        # Each of the two role tracks joins actual card centres across decades.
        for lane in range(len(ROLES)):
            for column in range(2):
                track=[n for n in tree['nodes'] if n['lane']==lane and n['x']==145+lane*340+column*158]
                for previous,current in zip(track,track[1:]):
                    lo=max(top,top+previous['y']+82-self.tree_scroll)
                    target=top+current['y']-self.tree_scroll;hi=min(bottom,target if target+82<=bottom else bottom);x=current['x']+75
                    if hi>lo:
                        self.rect(x,lo,2,hi-lo,rgba('70909e',190))
                        if top+12<=target and target+82<=bottom:self.text(x-5,target-14,'▼',10,rgba('70909e'))
        for n in tree['nodes']:
            y=top+n['y']-self.tree_scroll
            if not top<=y or y+82>bottom:continue
            r=n['row'];h=history(r);x=n['x'];selected=r['simulation_model']==self.game.config.player_model
            family=n['kind']=='family';action=('family',n['group']) if family else ('select',r['id'])
            id='family_'+n['group'] if family else 'tree_aircraft_'+r['id']
            self.button(id,x,y,150,82,'',action,selected=selected)
            self.rect(x,y,150,20,rgba('405563') if selected else rgba('334754'))
            title=n['family']+f' [{len(n["members"])}] '+('−' if n['group'] in self.expanded_families else '+') if family else h['family']
            self.text(x+5,y+2,title[:21],14)
            p=Path(__file__).resolve().parents[1]/'game/assets/ui/aircraft'/f'{r["id"]}.png'
            if p.is_file():self.images.append((x+4,y+20,142,45,str(p)))
            else:self.text(x+7,y+34,'缩略图待生成',13,MUTED)
            state={'paper':'方案','fictional':'虚构','unknown':'待核实','experimental':'试验'}
            caption=f'{len(n["members"])} 个资源 · 点击'+('收起' if n['group'] in self.expanded_families else '展开') if family else state.get(h['status'],'试飞' if r.get('library_aircraft') else '作战')
            if not r['available']:caption+=' / 不可用'
            self.text(x+5,y+64,caption,12,GREEN if h['status']=='historical' else GOLD)
            if x<=self.hover[0]<=x+150 and y<=self.hover[1]<=y+82:
                self.tree_hover={**h,'note':r['display_name'][:42]+' | '+h['note']}
        self.rect(30,774,1850,46,CONTROL)
        hovered=getattr(self,'tree_hover',None)
        message=hovered['note'] if hovered else '年代参考机型家族首飞；未首飞方案按设计年代。连线仅表示同用途时间序列，不是解锁或真实衍生关系。'
        self.text(42,785,message[:98],16,MUTED);self.tree_hover=None
        self.button('tree_up',1844,205,35,32,'↑',('tree_scroll',-350),enabled=self.tree_scroll>0)
        self.button('tree_down',1844,727,35,32,'↓',('tree_scroll',350),enabled=self.tree_scroll<max(0,tree['height']-560))
        if tree['height']>560:
            track=478;thumb=max(28,track*560/tree['height']);position=(track-thumb)*self.tree_scroll/(tree['height']-560)
            self.rect(1888,242,3,track,LINE);self.rect(1886,242+position,7,thumb,ACCENT)
        if not rows:self.text(650,380,'当前国家没有匹配型号；可清空搜索或切换国家。',23,MUTED)
    def settings_page(self):
        self.rect(0,0,1920,1080,rgba('17212a',155));self.text(28,22,'‹ 基地  |  游戏设置',30)
        for i,(id,label) in enumerate([('general','主要参数'),('graphics','画面设置'),('audio','声音'),('controls','控制')]):
            self.button('tab_'+id,25+i*155,76,147,36,label,('tab',id),selected=self.tab==id)
        self.rect(25,125,1870,1,LINE);self.rect(357,150,1,786,LINE)
        self.text(151,151,'导航',22)
        sections=[('general','主要参数'),('flight','空战设置'),('interface','战斗界面'),('controls','按键与操作')]
        for i,(id,label) in enumerate(sections):self.button('nav_'+id,25,195+i*44,318,40,label,('section',id),selected=self.section==id)
        self.rect(425,151,1440,35,CONTROL);self.text(439,158,'当前可用的游戏选项',16,MUTED)
        rows=[]
        if self.tab=='graphics':rows=[('quality','画面质量'),('font_scale','界面字体大小')]
        elif self.tab=='audio':rows=[('master_volume','主音量')]
        elif self.tab=='controls' or self.section=='controls':
            for i,(key,meaning) in enumerate(CONTROLS):
                y=215+i*46;self.text(565,y,key,19,MUTED);self.text(960,y,meaning,19);self.rect(540,y+34,1000,1,LINE)
        elif self.section=='flight':rows=[('mouse_sensitivity','鼠标指向灵敏度'),('control_mode','默认控制模式')]
        elif self.section=='interface':rows=[('show_hud','显示战斗 HUD'),('font_scale','界面字体大小')]
        else:rows=[('font_scale','界面字体大小'),('quality','画面质量'),('show_hud','显示战斗 HUD')]
        def label(key,v):
            return {'quality':{'low':'低','medium':'中','high':'高'},'control_mode':{'assisted':'鼠标辅助','raw_manual':'原始手动'},'show_hud':{True:'是',False:'否'}}.get(key,{}).get(v,f'{v*100:.0f}%' if isinstance(v,float) else str(v))
        for i,(key,name) in enumerate(rows):self.field('pref_'+key,218+i*53,name,label(key,self.draft[key]),[(label(key,v),v) for v in CHOICES[key]])
        if self.tab=='audio':self.text(960,300,'设置立即应用于确认后的游戏音效。',16,MUTED)
        self.rect(24,955,1872,1,LINE)
        self.button('defaults',30,982,188,40,'恢复默认',('defaults',))
        self.button('cancel',1460,982,180,40,'取消 / 返回',('cancel',))
        self.button('apply',1660,982,222,40,'应用设置',('apply',),primary=True)
        self.text(425,892,'修改将在应用后保存。关闭或取消保留原设置。',16,MUTED)
        if self.notice:self.text(425,922,self.notice[:90],16,GOLD)
    def preparation_page(self):
        g=self.game;r=g.current_aircraft();d=self.preparation;definition=loadouts.stations(r)
        self.rect(0,0,1920,1080,rgba('12202b',160))
        self.rect(80,62,1760,811,rgba('18242f',244));self.rect(80,62,1760,43,rgba('35434e'))
        self.text(99,70,'战斗准备  —  '+r['display_name'],25)
        self.text(111,130,'点击挂点选择弹药',23)
        self.text(111,169,loadouts.summary(d['mounts']),17,GREEN)
        self.rect(110,215,660,490,rgba('111c27'));self.border(110,215,660,490)
        # A schematic, deliberately separate from unverified physical mesh coordinates.
        self.rect(427,258,28,369,rgba('607985',100));self.rect(329,567,224,22,rgba('607985',100))
        self.rect(215,442,450,26,rgba('607985',100));self.text(410,232,'机头 ↑',15,MUTED)
        for station in definition.stations:
            x=160+station.diagram[0]*560;y=250+station.diagram[1]*420
            weapon=d['mounts'].get(station.id,'')
            self.button('station_'+station.id,x-53,y-25,108,55,'',('station',station.id),selected=self.station==station.id)
            self.text(x-44,y-20,station.name,14,MUTED)
            self.text(x-44,y+3,weapon or '空挂点',14,GREEN if weapon else TEXT)
        if not definition.stations:self.text(220,440,'此机型尚无可用武器挂点',22,MUTED)
        self.text(111,722,'挂点为简化示意；当前仅支持单挂弹药。',16,MUTED)
        self.text(111,750,'V 切换已挂载武器  /  Space 发射  /  B 投弹',16,MUTED)
        y=133
        self.field('mission',y,'任务类型',MISSIONS[d['mission']],[(MISSIONS[m],m) for m in self.missions()])
        presets=[(LOADOUTS.get(id,id),id) for id,mounts in definition.presets.items()
                 if (id!='unarmed' or 'clean' not in definition.presets) and (mounts or id in ('clean','unarmed'))]
        self.field('loadout',y+52,'挂载预设',LOADOUTS.get(d['loadout'],d['loadout']),presets)
        self.field('enemy',y+104,'敌方武器','实弹' if d['enemy_attacks'] else '训练',[('训练',False),('实弹',True)],enabled=not r.get('library_aircraft') and d['mission'] not in ('training','intercept_patrol'))
        self.field('seed',y+156,'仿真随机种子',d['seed']+('|' if self.typing=='seed' else ''))
        versions=g.map_versions();selected=next((v for v in versions if v['id']==d['map_version']),None)
        marker={'candidate':' [候选]','baseline':' [基线]','reference_matched':' [已对齐]','external':''}
        label=lambda v:v['label']+marker[v['quality']]
        self.field('map_version',y+208,'地图版本',label(selected) if selected else '版本不可用',[(label(v),v['id']) for v in versions])
        current=next((s for s in definition.stations if s.id==self.station),None)
        self.rect(850,420,930,280,PANEL)
        self.text(875,433,('当前挂点：'+current.name) if current else '无武装试飞',22)
        if current:
            options=['']+list(current.weapons);catalog=loadouts.weapons()
            for i,weapon in enumerate(options):
                x=875+(i%2)*440;yy=480+(i//2)*58
                self.button('mount_'+(weapon or 'empty'),x,yy,420,46,weapon or '不挂载',('mount',weapon),selected=d['mounts'].get(current.id,'')==weapon)
                self.border(x,yy,420,46,LINE)
            if current.mirror:self.button('mirror',875,706,420,38,'应用到对称挂点',('mirror',))
        self.text(875,760,'配置将在确认出击后生效；返回机库会放弃修改。',16,MUTED)
        if self.notice:self.text(875,795,self.notice[:65],16,GOLD)
        self.rect(95,810,1730,1,LINE)
        self.button('back',100,822,195,40,'返回机库',('cancel',))
        self.button('launch',1580,819,243,43,'确认出击',('launch',),primary=True,enabled=r['available'])
        self.card_strip(928,interactive=False)
        self.text(35,1053,'BVR SIM  /  出击准备',15,MUTED)
    def layout(self):
        self.regions=[];self.texts=[];self.lines=[];self.images=[]
        if self.page=='hangar':self.hangar()
        elif self.page=='settings':self.settings_page()
        else:self.preparation_page()
        if self.dropdown:
            id,options=self.dropdown
            region=next((r for r in self.regions if r[0]==id),None)
            if region:
                x,y,w,h=region[1];height=len(options)*36
                top=y+h if y+h+height<786 else y-height
                self.mask_text(x,top,w,height)
                for i,(label,value) in enumerate(options):self.button('option_'+str(i),x,top+i*36,w,36,label,('option',id,value))
        return self.texts,self.lines,self.images
    def hud(self):
        self.layout();g=self.game;sx=g.width/1920;sy=g.height/1080;texts=[];lines=[];images=[]
        for x,y,value,size,color in self.texts:
            t=g.r.HudText();t.x=x*sx;t.y=y*sy;t.text=value;t.size=max(10,int(size*sy*self.settings.values['font_scale']*1.15));t.color=color;texts.append(t)
        for x,y,w,h,color,rotation in self.lines:
            l=g.r.HudLine();l.x=x*sx;l.y=y*sy;l.w=w*sx;l.h=h*sy;l.color=color;l.rotation=rotation;lines.append(l)
        if hasattr(g.r,'HudImage'):
            for x,y,w,h,file in self.images:
                image=g.r.HudImage();image.x=x*sx;image.y=y*sy;image.w=w*sx;image.h=h*sy;image.file=file;images.append(image)
        if hasattr(g.renderer,'set_menu_overlay'):g.renderer.set_menu_overlay(self.page!='hangar' or self.tree_open,images)
        return texts,lines
    def action(self,a):
        key=a[0];g=self.game
        if key=='quit':return False
        if key=='menu':self.menu=not self.menu
        elif key=='settings':self.open_settings()
        elif key=='controls':self.open_settings();self.tab='controls';self.section='controls'
        elif key=='prepare':self.open_preparation()
        elif key=='testflight':self.open_preparation(True)
        elif key=='logs':
            from .sortie_logs import open_logs_directory
            try:g.last_log_opened=open_logs_directory(g.log_paths())
            except OSError as error:self.notice=str(error)
        elif key=='select':self.select(a[1])
        elif key=='country':self.country=a[1];self.offset=0;self.tree_scroll=0.;self.tree_open=True;self.menu=False
        elif key=='tree':self.tree_open=not self.tree_open;self.menu=False
        elif key=='tree_scroll':self.tree_scroll=max(0,self.tree_scroll+a[1])
        elif key=='family':
            if a[1] in self.expanded_families:self.expanded_families.remove(a[1])
            else:self.expanded_families.add(a[1])
        elif key=='countries_more':self.country_offset=0 if self.country_offset else 20
        elif key=='scroll':self.offset=max(0,min(max(0,len(self.rows())-8),self.offset+a[1]))
        elif key=='search':self.typing='search'
        elif key=='cancel':self.home();self.notice=''
        elif key=='defaults':self.draft=dict(DEFAULTS)
        elif key=='apply':
            try:self.settings.save(self.draft);self.apply_preferences();self.home();self.notice='设置已保存'
            except (ValueError,OSError) as error:self.notice='设置未保存：'+str(error)
        elif key=='tab':self.tab=a[1];self.dropdown=None
        elif key=='section':self.section=a[1];self.tab='controls' if a[1]=='controls' else 'general';self.dropdown=None
        elif key=='dropdown':self.dropdown=None if self.dropdown and self.dropdown[0]==a[1] else (a[1],a[2])
        elif key=='option':
            id,value=a[1:]
            if id.startswith('pref_'):self.draft[id[5:]]=value
            else:
                self.preparation[{'enemy':'enemy_attacks'}.get(id,id)]=value
                if id=='loadout':self.preparation['mounts']=loadouts.preset(g.current_aircraft(),value)
                if id=='map_version' and self.preparation['mission'] not in self.missions():self.preparation['mission']=self.missions()[0]
                self.normalize_preparation()
            self.dropdown=None
        elif key=='station':self.station=a[1];self.dropdown=None
        elif key=='mount':
            self.preparation['mounts'][self.station]=a[1];self.preparation['loadout']='custom'
        elif key=='mirror':
            definition=loadouts.stations(g.current_aircraft());current=next(s for s in definition.stations if s.id==self.station)
            weapon=self.preparation['mounts'].get(current.id,'')
            mirrored=next((s for s in definition.stations if s.id==current.mirror),None)
            if mirrored and (not weapon or weapon in mirrored.weapons):
                self.preparation['mounts'][mirrored.id]=weapon;self.preparation['loadout']='custom'
        elif key=='seed':self.typing='seed'
        elif key=='launch':self.launch()
        return True
    def input(self,event,dt):
        pressed=set(event.pressed);held=set(event.held);g=self.game
        x=event.x/g.width*1920;y=event.y/g.height*1080;self.hover=x,y
        if self.typing:
            if self.typing=='search':
                if 27 in pressed:g.aircraft_search='';self.typing=None
                elif 13 in pressed:self.typing=None
                else:
                    if 8 in pressed:g.aircraft_search=g.aircraft_search[:-1]
                    for key in sorted(pressed):
                        if 65<=key<=90 or 48<=key<=57:g.aircraft_search+=chr(key)
                        elif key==32:g.aircraft_search+=' '
                        elif key in (189,109):g.aircraft_search+='-'
                    g.aircraft_search=g.aircraft_search[:48];self.offset=0;self.tree_scroll=0.;self.tree_open=True
                    if not self.rows() and g.filtered_aircraft():self.country=history(g.filtered_aircraft()[0])['country']
            else:
                if 27 in pressed or 13 in pressed:self.typing=None
                else:
                    if 8 in pressed:self.preparation['seed']=self.preparation['seed'][:-1]
                    for key in sorted(pressed):
                        if 48<=key<=57:self.preparation['seed']=(self.preparation['seed']+chr(key))[-10:]
            if 1 not in pressed:return True
            self.typing=None
        if 113 in pressed:self.open_settings();return True
        if 27 in pressed:
            if self.dropdown:self.dropdown=None
            elif self.tree_open:self.tree_open=False
            elif self.page!='hangar':self.home()
            else:self.menu=not self.menu
            return True
        if 13 in pressed:
            if self.dropdown:self.dropdown=None;return True
            if self.page=='prepare':self.launch()
            elif self.page=='hangar':self.open_preparation()
            return True
        if self.page=='hangar':
            if 191 in pressed:self.typing='search';return True
            for i,row in enumerate(g.aircraft_rows[:5]):
                if 49+i in pressed:self.select(row['id'])
            wheel=getattr(event,'wheel',0)
            if wheel:self.action(('tree_scroll',-int(math.copysign(96,wheel))) if self.tree_open else ('scroll',-int(math.copysign(1,wheel))))
            if pressed.intersection({37,38,33}):self.action(('tree_scroll',-450) if self.tree_open else ('scroll',-8))
            if pressed.intersection({39,40,34}):self.action(('tree_scroll',450) if self.tree_open else ('scroll',8))
            if 36 in pressed:self.offset=0;self.tree_scroll=0.
            if 35 in pressed:
                if self.tree_open:self.tree_scroll=10**6
                else:self.offset=max(0,len(self.rows())-8)
            if 2 in held and not self.tree_open:
                previous=getattr(self,'last_drag',None)
                if previous:self.orbit+=(x-previous[0])*.004
                self.last_drag=x,y
            else:self.last_drag=None
            if 77 in pressed or 76 in pressed or 71 in pressed:self.open_preparation()
        if 1 in pressed:
            self.layout()
            for id,(rx,ry,rw,rh),a in reversed(self.regions):
                if rx<=x<=rx+rw and ry<=y<=ry+rh:return self.action(a)
            self.dropdown=None
        return True
