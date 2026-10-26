'use strict';
/* Full 200-name public screener + exclusively device-local REAL holdings.
   Signals are produced by the same Python v6/F9 indicator routines used in F9.
   Never infer a brokerage position from the historical virtual strategy account.
*/
const SCREENER_PATH='data/screener_f9a.json';
const STORAGE_KEY='fujimoto-user-holdings-v1';
const DEFAULT_STOCKS=[];
// Names are client-fallbacks until the next GitHub Actions price refresh.
const KOREAN_NAMES={"005930.KS":"삼성전자","000660.KS":"SK하이닉스","005380.KS":"현대자동차","009150.KS":"삼성전기","373220.KS":"LG에너지솔루션","207940.KS":"삼성바이오로직스","105560.KS":"KB금융","012450.KS":"한화에어로스페이스","000270.KS":"기아","034020.KS":"두산에너빌리티","055550.KS":"신한지주","032830.KS":"삼성생명","068270.KS":"셀트리온","012330.KS":"현대모비스","006400.KS":"삼성SDI","066570.KS":"LG전자","035420.KS":"NAVER","010120.KS":"LS ELECTRIC","042660.KS":"한화오션","009540.KS":"HD한국조선해양","034730.KS":"SK","000810.KS":"삼성화재","005490.KS":"POSCO홀딩스","015760.KS":"한국전력","051910.KS":"LG화학","096770.KS":"SK이노베이션","033780.KS":"KT&G","035720.KS":"카카오","086790.KS":"하나금융지주","018260.KS":"삼성에스디에스","000150.KS":"두산","003550.KS":"LG","003670.KS":"포스코퓨처엠","259960.KS":"크래프톤","323410.KS":"카카오뱅크","005940.KS":"NH투자증권","005830.KS":"DB손해보험","003490.KS":"대한항공","028050.KS":"삼성E&A","024110.KS":"기업은행","039490.KS":"키움증권","316140.KS":"우리금융지주","000100.KS":"유한양행","047050.KS":"포스코인터내셔널","402340.KS":"SK스퀘어","329180.KS":"HD현대중공업","028260.KS":"삼성물산","267260.KS":"HD현대일렉트릭","298040.KS":"효성중공업","010130.KS":"고려아연","011200.KS":"HMM","138040.KS":"메리츠금융지주","042700.KS":"한미반도체","010140.KS":"삼성중공업","017670.KS":"SK텔레콤","079550.KS":"LIG넥스원","064350.KS":"현대로템","006800.KS":"미래에셋증권","267250.KS":"HD현대","010950.KS":"S-Oil","086280.KS":"현대글로비스","047810.KS":"한국항공우주","278470.KS":"에이피알","272210.KS":"한화시스템","011070.KS":"LG이노텍","030200.KS":"KT","000720.KS":"현대건설","307950.KS":"현대오토에버","071050.KS":"한국금융지주","0126Z0.KS":"삼성에피스홀딩스","003230.KS":"삼양식품","443060.KS":"HD현대마린솔루션","078930.KS":"GS","006260.KS":"LS","161390.KS":"한국타이어앤테크놀로지","090430.KS":"아모레퍼시픽","016360.KS":"삼성증권","180640.KS":"한진칼","352820.KS":"하이브","064400.KS":"LG씨엔에스","326030.KS":"SK바이오팜","047040.KS":"대우건설","267270.KS":"HD건설기계","007660.KS":"이수페타시스","021240.KS":"코웨이","032640.KS":"LG유플러스","241560.KS":"두산밥캣","377300.KS":"카카오페이","009830.KS":"한화솔루션","001440.KS":"대한전선","062040.KS":"산일전기","000880.KS":"한화","271560.KS":"오리온","353200.KS":"대덕전자","175330.KS":"JB금융지주","128940.KS":"한미약품","010060.KS":"OCI홀딩스","029780.KS":"삼성카드","034220.KS":"LG디스플레이","051900.KS":"LG생활건강"};
const el=id=>document.getElementById(id);
const safeText=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const fmt=(n,d=2)=>Number.isFinite(Number(n)) && n!=='' && n!==null ? Number(n).toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const currency=(v,c)=> Number.isFinite(Number(v)) && v!==null ? (c==='KRW'?'₩':'$')+fmt(v,c==='KRW'?0:2):'—';
const pct=v=> Number.isFinite(v)?`${v>=0?'+':''}${fmt(v,2)}%`:'—';
let universe=[],holdings={},filter='all',market='all',query='',selected=null,editMode='edit',statusMessage='';
const flags={1:'sell1',2:'sell2',3:'sell3'};
const buyReason={buy1:'RSI(14) 과매도 반등',buy2:'MACD(12,26,9) 골든크로스',buy3:'일목균형표 엄격 상승 돌파'};
const sellReason={sell1:'1차 · RSI 30 이하',sell2:'2차 · MACD 데드크로스',sell3:'3차 · 구름대 하단 종가 이탈'};
function loadHoldings(){try {const raw=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');let items=raw.holdings||{};for(const [symbol,item] of Object.entries(items)){const clean=validHolding(item);if(clean)holdings[symbol]=clean;}}catch(e){statusMessage='보유내역을 읽지 못했습니다. 브라우저 저장 공간을 확인하세요.';}}
function validHolding(item){if(!item||typeof item!=='object')return null;const qty=Number(item.qty),avg=Number(item.avg);if(!Number.isFinite(qty)||!Number.isFinite(avg)||qty<=0||avg<=0)return null;
 const stages=Array.isArray(item.stages)?[...new Set(item.stages.map(Number).filter(n=>n>=1&&n<=3&&Number.isInteger(n)))].sort():[];
 return stages.length?{qty,avg,stages,updated_at:String(item.updated_at||'')}:null;}
function persist(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify({version:1,holdings}));return true}catch(e){notice('기기에 저장할 수 없습니다. Safari 개인 정보 보호 설정·저장 용량을 확인하세요.');return false;}}
function notice(msg){const t=el('toast');t.textContent=msg;t.classList.remove('hidden');clearTimeout(notice.timer);notice.timer=setTimeout(()=>t.classList.add('hidden'),3500);}
function stale(s){if(!s||s.status!=='OK'||!s.asof)return true;const stamp=Date.parse(s.asof+'T12:00:00Z');const age=(Date.now()-stamp)/86400000;return !Number.isFinite(age)||age>7||age< -1.5;}
function isHeld(symbol){return !!holdings[symbol]}
function sellTriggers(s){const h=holdings[s.symbol];if(!h||stale(s))return [];return h.stages.map(n=>flags[n]).filter(k=>s.signals?.[k]);}
function decision(s){const held=isHeld(s.symbol);if(stale(s))return {kind:'warn',label:'신호 보류',detail:s.status==='STALE_CACHED'?'데이터 갱신 실패':s.status==='UNAVAILABLE'?'데이터 미확보':'최신 일봉 확인 필요'};
 if(held){const tr=sellTriggers(s);if(tr.length)return {kind:'sell',label:'매도 확인',detail:tr.map(k=>sellReason[k]).join(' · ')};return {kind:'hold',label:'보유 · 유지',detail:'선택한 단계의 매도 조건 없음'};}
 if(s.signals?.buy1)return {kind:'buy',label:'1차 매수 후보',detail:'RSI 반등 · 다음 거래일 시가'};
 return {kind:'neutral',label:'관망',detail:'1차 RSI 반등 조건 대기'};}
function listView(){const q=query.trim().toLowerCase();return universe.filter(s=>{
 if(market!=='all'&&s.market!==market)return false;
 if(q&&!`${s.symbol} ${s.name}`.toLowerCase().includes(q))return false;
 const held=isHeld(s.symbol),kind=decision(s).kind;
 return filter==='all'||(filter==='unheld'&&!held)||(filter==='held'&&held)||(filter==='buy'&&kind==='buy')||(filter==='sell'&&kind==='sell');
 });}
function fmtPrice(s){return s.close===null||s.close===undefined?'—':currency(s.close,s.currency)}
function render(){const held=universe.filter(s=>isHeld(s.symbol));const buys=universe.filter(s=>decision(s).kind==='buy');const sells=universe.filter(s=>decision(s).kind==='sell');
 el('totalCount').textContent=universe.length;el('heldCount').textContent=held.length;el('buyCount').textContent=buys.length;el('sellCount').textContent=sells.length;
 const kr=totals('KRW'),us=totals('USD');el('portfolioPnl').classList.toggle('visible',held.length>0);
 for(const [group,id,basisid] of [[kr,'krwPnl','krwBasis'],[us,'usdPnl','usdBasis']]){
   el(id).textContent=group.count?`${currency(group.pnl,group.currency)} (${pct(group.valuedBasis?group.pnl/group.valuedBasis*100:NaN)})`:'미보유';
   el(id).style.color=group.pnl<0?'#ffabb7':group.pnl>0?'#7beabd':'';
   el(basisid).textContent=group.count?`투자원금 ${currency(group.basis,group.currency)} · 평가가능 ${group.valued}/${group.count}종목`:'등록 내역 없음';
 }
 for(const s of universe){if(s.market==='KOSPI'&&KOREAN_NAMES[s.symbol])s.name=KOREAN_NAMES[s.symbol];}
 const rows=listView();el('visibleCount').textContent=`${rows.length}개 표시`;el('missingHint').textContent=`미확인 ${universe.filter(s=>stale(s)).length}종목`;
 const container=el('stockList');const fragment=document.createDocumentFragment();
 for(const s of rows){const d=decision(s),h=holdings[s.symbol],node=document.createElement('button');node.type='button';node.className='stock';node.dataset.symbol=s.symbol;
    node.setAttribute('aria-label',`${s.name} ${s.symbol}, ${d.label}, 상세 보기`);
    node.style.width='100%';node.style.textAlign='left';node.style.color='inherit';node.style.font='inherit';
    const pos=h?`보유 ${fmt(h.qty,4).replace(/0+$/,'').replace(/\.$/,'')}주 · 평단 ${currency(h.avg,s.currency)}`:s.market==='KOSPI'?'코스피 시총 상위':s.market==='ETF'?'관심 ETF':'나스닥100 구성종목';
    const change=stale(s)?'':`<div class="change ${s.change_pct>=0?'positive':'negative'}">${pct(s.change_pct)}</div>`;
    const pnl=h&&!stale(s)&&s.close!=null?`<div class="tagline ${s.close>=h.avg?'positive':'negative'}">내 수익률 ${pct((s.close/h.avg-1)*100)}</div>`:`<div class="tagline">${safeText(d.detail)}</div>`;
    node.innerHTML=`<div><div class="name">${safeText(s.name)}</div><div class="symbol">${safeText(s.symbol)} · ${safeText(s.market)} #${s.rank}</div><div class="secondary">${safeText(pos)}</div></div><div class="right"><div class="price">${safeText(fmtPrice(s))}</div>${change}<span class="chip ${d.kind}">${safeText(d.label)}</span>${pnl}</div>`;
    node.addEventListener('click',()=>showDetail(s.symbol));fragment.appendChild(node);
 }
 if(rows.length===0){const x=document.createElement('div');x.className='empty';x.textContent='조건에 맞는 종목이 없습니다. 검색어나 필터를 변경해 보세요.';fragment.appendChild(x)}
 container.replaceChildren(fragment);
}
function totals(cur){let basis=0,valuedBasis=0,pnl=0,count=0,valued=0;for(const s of universe){const h=holdings[s.symbol];if(!h||s.currency!==cur)continue;count++;basis+=h.qty*h.avg;if(!stale(s)&&s.close!=null){valued++;valuedBasis+=h.qty*h.avg;pnl+=(s.close-h.avg)*h.qty;}}return {basis,pnl,count,valued,valuedBasis,currency:cur};}
function setMode(mode){editMode=mode;document.querySelectorAll('#editModes button').forEach(b=>{b.classList.toggle('primary',b.dataset.mode===mode);b.classList.toggle('secondarybtn',b.dataset.mode!==mode)});
 el('editFields').classList.toggle('hidden',mode!=='edit');el('tradeFields').classList.toggle('hidden',mode==='edit');
 el('tradeQtyLabel').textContent=mode==='buy'?'추가 매수 수량 (주)':'매도 수량 (주)';
 el('saveHolding').textContent=mode==='edit'?'보유정보 저장':mode==='buy'?'매수 내역 반영':'매도 내역 반영';
 el('tradePriceLabel').firstChild.textContent=mode==='buy'?'매수 체결 단가 (':'매도 체결 단가 (';
 el('formInfo').textContent=mode==='buy'?'추가 매수 시 평균단가를 가중평균으로 자동 갱신합니다.':mode==='sell'?'일부 매도하면 평균단가는 유지되고 수량만 감소합니다.':'실제 보유 수량과 평균단가를 직접 수정할 수 있습니다.';
}
function showDetail(symbol){selected=universe.find(s=>s.symbol===symbol);if(!selected)return;const s=selected,h=holdings[s.symbol],d=decision(s);
 el('detailTitle').textContent=`${s.name} · ${s.symbol}`;el('detailMarket').textContent=`${s.market} · ${s.currency}`;el('detailAsOf').textContent=s.asof?`기준 종가: ${s.asof}`:'시세 미확보';
 el('detailPrice').textContent=fmtPrice(s);el('detailPnl').textContent=h&&!stale(s)&&s.close!=null?`${currency((s.close-h.avg)*h.qty,s.currency)} (${pct((s.close/h.avg-1)*100)})`:h?'시세 확인 필요':'미보유';
 el('detailPnl').style.color=h&&!stale(s)&&s.close<h.avg?'#ff9cae':'#94e4ba';
 const rules=el('detailRules');const sg=s.signals||{};const triggers=sellTriggers(s);const label=(!stale(s)?d.label:'신호 보류');
 const out=[`<strong class="${d.kind==='sell'?'active-sell':d.kind==='buy'?'active-buy':''}">${safeText(label)}</strong>`, `<div>${safeText(d.detail)}</div>`];
 if(!stale(s)){
  out.push(`<div style="margin-top:8px">1차 RSI 반등: ${sg.buy1?'● 충족':'— 미충족'}</div>`,
  `<div>2차 MACD 골든: ${sg.buy2?'● 충족':'— 미충족'}</div>`,
  `<div>3차 일목 엄격돌파: ${sg.buy3?'● 충족':'— 미충족'}</div>`);
  if(h){out.push('<hr style="border-color:#2e4155">',
  ...[1,2,3].filter(k=>h.stages.includes(k)).map(k=>`<div class="${triggers.includes(flags[k])?'active-sell':''}">${safeText(sellReason[flags[k]])}: ${triggers.includes(flags[k])?'● 매도 조건 충족':'— 아직 미충족'}</div>`));}
 }
 out.push('<div class="hint">종가 확정 이후 판단. 신호가 발생해도 아직 주문 또는 체결된 것은 아닙니다.</div>');rules.innerHTML=out.join('');
 el('detailRsi').textContent=fmt(s.rsi14,1);
 renderMacdSummary(s);
 el('detailCloudTop').textContent=currency(s.cloud_top,s.currency);el('detailCloudBottom').textContent=currency(s.cloud_bottom,s.currency);
 drawChart(s,h);
 drawMacdChart(s);
 el('heldQty').value=h?h.qty:'';el('averageCost').value=h?h.avg:'';
 for(const n of [1,2,3])el('lot'+n).checked=h?h.stages.includes(n):n===1;
 document.querySelectorAll('.currencyLabel').forEach(x=>x.textContent=s.currency);
 el('tradeQty').value='';el('tradePrice').value='';el('clearHolding').disabled=!h;
 setMode(h?'edit':'buy');
 el('detailDialog').showModal();}
// SVG is created with DOM APIs; ticker names and downloaded text are never executed.
const SVG_NS='http://www.w3.org/2000/svg';
function svgAdd(parent,tag,attrs={},content){const node=document.createElementNS(SVG_NS,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(content!==undefined)node.textContent=String(content);parent.appendChild(node);return node;}
function safeLevel(v){return v!==null&&v!==undefined&&Number.isFinite(Number(v))&&Number(v)>0?Number(v):null;}
function drawChart(s,holding){
 const svg=el('detailChart');svg.replaceChildren();
 const panel=el('profileLevels');panel.replaceChildren();
 const interpretation=el('profileInterpretation');
 const closes=(Array.isArray(s.recent_closes)?s.recent_closes:[]).map(Number).filter(v=>Number.isFinite(v)&&v>0);
 const vp=s.volume_profile;
 if(closes.length<2){interpretation.textContent='표시할 종가 데이터가 없습니다.';return;}
 const labels=[{key:'vah',name:'VAH 상단',color:'#ff95a3'},
               {key:'poc',name:'POC 최다',color:'#facc72'},
               {key:'val',name:'VAL 하단',color:'#68dfa4'}];
 const levels=vp?labels.map(x=>({...x,price:safeLevel(vp[x.key])})).filter(x=>x.price!==null):[];
 const price=safeLevel(s.close)||closes.at(-1);
 const extra=holding?safeLevel(holding.avg):null;
 const all=[...closes,price,...levels.map(x=>x.price),...(extra!==null?[extra]:[])];
 const rawMin=Math.min(...all),rawMax=Math.max(...all);
 const padding=Math.max((rawMax-rawMin)*0.09,rawMax*0.006,0.0001);
 const min=rawMin-padding,max=rawMax+padding,scale=v=>205-(v-min)/(max-min)*183;
 const n=closes.length;
 const xOf=i=>12+i/Math.max(n-1,1)*277;
 // Actual 70% value-area region behind price movement.
 if(vp&&safeLevel(vp.val)!==null&&safeLevel(vp.vah)!==null){
   const top=scale(Number(vp.vah)),bottom=scale(Number(vp.val));
   svgAdd(svg,'rect',{x:9,y:Math.min(top,bottom),width:327,height:Math.max(1,Math.abs(bottom-top)),fill:'#facc72','fill-opacity':'0.055'});
 }
 for(let i=0;i<4;i++){const y=26+i*56;svgAdd(svg,'line',{x1:10,y1:y,x2:337,y2:y,stroke:'#23364a','stroke-width':1});}
 // Volume histogram on the same price axis. Width = relative concentration.
 if(vp&&Array.isArray(vp.histogram)&&vp.histogram.length===32){
   const start=Number(vp.range_low),end=Number(vp.range_high);
   vp.histogram.forEach((weight,i)=>{if(!Number.isFinite(Number(weight))||Number(weight)<=0)return;
     const level=start+(end-start)*(i+0.5)/32;
     const yy=scale(level);const width=32*Math.max(0,Math.min(1,Number(weight)));
     svgAdd(svg,'rect',{x:336-width,y:yy-1.65,width:width.toFixed(2),height:3.3,
       fill:Math.abs(level-Number(vp.poc))<=Math.max(Number(vp.width)/2,1e-9)?'#facc72':'#7e9bae','fill-opacity':'0.60'});
   });
 }
 const points=closes.map((v,i)=>`${xOf(i).toFixed(1)},${scale(v).toFixed(1)}`).join(' ');
 svgAdd(svg,'polyline',{points,stroke:'#66bffd','stroke-width':2.5,fill:'none','stroke-linecap':'round','stroke-linejoin':'round'});
 const annotations=[...levels,{key:'close',name:'현재',price,color:'#eef8ff'}];
 if(extra!==null)annotations.push({key:'avg',name:'평단',price:extra,color:'#7df0d5'});
 annotations.forEach(p=>svgAdd(svg,'line',{x1:10,y1:scale(p.price),x2:337,y2:scale(p.price),stroke:p.color,'stroke-width':p.key==='poc'?2:1.2,'stroke-dasharray':p.key==='close'?'3 4':'6 5','stroke-opacity':p.key==='close'?'0.9':'0.8'}));
 // Avoid text collisions: put floating price labels in separate right gutter.
 const sorted=annotations.map(p=>({...p,actualY:scale(p.price),labelY:scale(p.price)})).sort((a,b)=>a.actualY-b.actualY);
 for(let i=1;i<sorted.length;i++)sorted[i].labelY=Math.max(sorted[i].labelY,sorted[i-1].labelY+16);
 const overflow=Math.max(0,sorted.at(-1).labelY-218);if(overflow>0)sorted.forEach(x=>x.labelY-=overflow);
 if(sorted[0].labelY<15){const delta=15-sorted[0].labelY;sorted.forEach(x=>x.labelY+=delta);}
 sorted.forEach(p=>{
   svgAdd(svg,'line',{x1:338,y1:p.actualY,x2:346,y2:p.labelY,stroke:p.color,'stroke-width':0.85,'stroke-opacity':0.65});
   svgAdd(svg,'text',{x:350,y:p.labelY+3.8,fill:p.color,'font-size':10.2,'font-weight':p.key==='poc'?800:600},p.name);
   svgAdd(svg,'text',{x:350,y:p.labelY+14,fill:p.color,'font-size':10.2},s.currency==='KRW'?`${fmt(p.price,0)}원`:`$${fmt(p.price,2)}`);
 });
 svgAdd(svg,'text',{x:12,y:232,fill:'#91abc0','font-size':10},`최근 ${closes.length}거래일 · 종가`);
 svgAdd(svg,'text',{x:294,y:232,fill:'#91abc0','font-size':9.5},'매물 분포 →');
 if(levels.length!==3){interpretation.textContent='매물대는 다음 일봉 스캔이 완료된 후 표시됩니다. 최신 데이터가 없어 가격을 임의로 만들지 않습니다.';return;}
 labels.forEach(info=>{
   const level=Number(vp[info.key]);const relative=(level/price-1)*100;
   const box=document.createElement('div');box.className='profile-item';
   const name=document.createElement('span');name.textContent=info.name;
   const val=document.createElement('strong');val.style.color=info.color;val.textContent=currency(level,s.currency);
   const distance=document.createElement('em');distance.textContent=`현재가 대비 ${pct(relative)}`;
   box.append(name,val,distance);panel.appendChild(box);
 });
 const closestBelow=levels.filter(x=>x.price<=price&&x.price!==null).sort((a,b)=>b.price-a.price)[0];
 const closestAbove=levels.filter(x=>x.price>price&&x.price!==null).sort((a,b)=>a.price-b.price)[0];
 const nearText=closestBelow?`현재가 아래에서 가장 가까운 참고 구간은 ${closestBelow.name} ${currency(closestBelow.price,s.currency)} (${pct((closestBelow.price/price-1)*100)})입니다.`:'현재가 아래에 표시할 120일 핵심 매물대가 없습니다.';
 const upperText=closestAbove?` 위쪽에는 ${closestAbove.name} ${currency(closestAbove.price,s.currency)}가 있습니다.`:'';
 interpretation.textContent=nearText+upperText+' 아래 매물대가 반드시 지지선이 되는 것은 아닙니다. 실제 매수는 RSI·MACD·일목 신호 확인 후 판단하세요.';
}
function renderMacdSummary(s){
 const area=el('macdSummary'),value=el('detailMacd'),badge=el('macdCrossBadge');
 const m=s.macd!=null?Number(s.macd):NaN,k=s.macd_signal!=null?Number(s.macd_signal):NaN;
 const mc=s.macd_chart,series=mc?.histogram||[];
 const h=series.length?Number(series.at(-1)):(Number.isFinite(m)&&Number.isFinite(k)?m-k:NaN);
 const prev=series.length>1?Number(series.at(-2)):NaN;
 if(!Number.isFinite(m)||!Number.isFinite(k)){
   area.textContent='MACD 최신 데이터가 없습니다.';area.className='momentum-summary neutral';value.textContent='데이터 없음';badge.textContent='확인 대기';return;
 }
 const up=m>k,down=m<k;
 const phase=h>0?(h>(Number.isFinite(prev)?prev:h)?'상승 힘 확대':'상승 힘 둔화'):(h<0?(h>(Number.isFinite(prev)?prev:h)?'하락 압력 감소':'하락 압력 확대'):'중립');
 const direction=up?'상승 모멘텀 우위':down?'하락 모멘텀 우위':'모멘텀 중립';
 const zeroContext=(m<0&&k<0)?' · 두 선 모두 0 아래':(m>0&&k>0)?' · 두 선 모두 0 위':'';
 area.textContent=`${up?'↗':down?'↘':'→'} ${direction} · ${phase}${zeroContext}`;
 area.className=`momentum-summary ${up?'up':down?'down':'neutral'}`;
 value.textContent=direction;
 const buy=Boolean(s.signals?.buy2),sell=Boolean(s.signals?.sell2);
 badge.textContent=buy?'오늘 골든크로스':sell?'오늘 데드크로스':up?'MACD > 시그널':down?'MACD < 시그널':'두 선 비슷';
 badge.style.borderColor=buy?'#59d5ad':sell?'#ff95a3':'#365269';
 el('macdGuide').textContent=`파랑 MACD ${fmt(m,3)} / 노랑 시그널 ${fmt(k,3)} / 차이 ${fmt(h,3)}. `+
 (buy?'오늘 두 선이 아래→위로 교차했습니다. 단, 2차 매수는 1차 RSI 보유와 20일 이내 조건도 필요합니다.':
 sell?'오늘 두 선이 위→아래로 교차했습니다. 보유한 2차 물량의 매도 신호입니다.':
 '파란선이 노란선보다 위면 상승 모멘텀이 상대적으로 강하고, 아래면 하락 모멘텀이 상대적으로 강합니다. 현재 위치만으로 신규 매수 신호가 확정되는 것은 아닙니다.');
}
function drawMacdChart(s){
 const svg=el('macdChart');svg.replaceChildren();
 const m=s.macd_chart;
 if(!m||!Array.isArray(m.macd)||!Array.isArray(m.signal)||!Array.isArray(m.histogram)||m.macd.length<2){
   svgAdd(svg,'text',{x:16,y:85,fill:'#b3c9d9','font-size':13},'다음 일봉 갱신 이후 MACD 차트가 표시됩니다.');return;
 }
 const n=Math.min(m.macd.length,m.signal.length,m.histogram.length),mac=m.macd.slice(-n).map(Number),signal=m.signal.slice(-n).map(Number),hist=m.histogram.slice(-n).map(Number);
 if([mac,signal,hist].some(arr=>arr.some(v=>!Number.isFinite(v))))return;
 const values=[...mac,...signal,...hist,0],lo=Math.min(...values),hi=Math.max(...values);
 const padding=Math.max((hi-lo)*0.18,Math.abs(hi)*0.08,0.0001),lower=lo-padding,upper=hi+padding;
 const y=v=>148-(v-lower)/(upper-lower)*127,x=i=>12+(i/Math.max(1,n-1))*416,zero=y(0);
 for(let i=0;i<4;i++){const yy=14+i*43;svgAdd(svg,'line',{x1:12,y1:yy,x2:429,y2:yy,stroke:'#26394d','stroke-width':0.8});}
 svgAdd(svg,'line',{x1:12,y1:zero,x2:429,y2:zero,stroke:'#8ba5bc','stroke-width':1,'stroke-dasharray':'4 5','stroke-opacity':0.7});
 const width=Math.min(8,375/n*0.65);
 hist.forEach((v,i)=>{
  const yy=y(v);
  svgAdd(svg,'rect',{x:x(i)-width/2,y:Math.min(yy,zero),width:width,height:Math.max(0.9,Math.abs(zero-yy)),
    fill:v>=0?'#56daa5':'#f58da5','fill-opacity':'0.54'});
 });
 for(const [values,color] of [[mac,'#54baff'],[signal,'#ffce66']]){
   const points=values.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
   svgAdd(svg,'polyline',{points,fill:'none',stroke:color,'stroke-width':2.3,'stroke-linecap':'round','stroke-linejoin':'round'});
 }
 svgAdd(svg,'circle',{cx:x(n-1),cy:y(mac.at(-1)),r:3.7,fill:'#54baff'});
 svgAdd(svg,'circle',{cx:x(n-1),cy:y(signal.at(-1)),r:3.7,fill:'#ffce66'});
 svgAdd(svg,'text',{x:13,y:169,fill:'#89a8bf','font-size':10},`최근 ${n}거래일 · 종가 확정`);
}

function stagesForm(){return [1,2,3].filter(n=>el('lot'+n).checked)}
function updateHolding(evt){evt.preventDefault();if(!selected)return;const key=selected.symbol,h=holdings[key]||null,stages=stagesForm();
 if(!stages.length){notice('보유 물량에 해당하는 1·2·3차 단계를 하나 이상 선택해 주세요.');return;}
 if(editMode==='edit'){
   if(el('heldQty').value.trim()===''||el('averageCost').value.trim()===''){notice('보유 수량과 평균 매수가를 모두 입력해 주세요.');return;}
   const qty=Number(el('heldQty').value),avg=Number(el('averageCost').value);
   if(!Number.isFinite(qty)||qty<0){notice('유효한 보유 수량을 입력해 주세요.');return;}
   if(qty===0){notice('보유 삭제는 별도의 보유 삭제 버튼을 사용해 주세요.');return;}
   else if(!Number.isFinite(avg)||avg<=0){notice('유효한 평균 매수가를 입력해 주세요.');return;}
   else holdings[key]={qty,avg,stages,updated_at:new Date().toISOString()};
 }else{
   if(el('tradeQty').value.trim()===''||el('tradePrice').value.trim()===''){notice('매매 수량과 단가를 모두 입력해 주세요.');return;}
   const qty=Number(el('tradeQty').value),price=Number(el('tradePrice').value);
   if(!Number.isFinite(qty)||qty<=0||!Number.isFinite(price)||price<=0){notice('매매 수량과 체결 단가를 올바르게 입력해 주세요.');return;}
   if(editMode==='buy'){
     const old=h||{qty:0,avg:0,stages:[]};const newQty=old.qty+qty;
     holdings[key]={qty:newQty,avg:(old.avg*old.qty+price*qty)/newQty,stages,updated_at:new Date().toISOString()};
   }else if(editMode==='sell'){
     if(!h||qty>h.qty+1e-9){notice('현재 보유 수량보다 많이 매도할 수 없습니다.');return;}
     const remain=Math.max(0,h.qty-qty);
     if(remain<=1e-9){delete holdings[key]}
     else holdings[key]={qty:remain,avg:h.avg,stages,updated_at:new Date().toISOString()};
   }
 }
 const message=editMode==='sell'&&h?`매도 반영 · 실현손익 ${currency((Number(el('tradePrice').value)-h.avg)*Number(el('tradeQty').value),selected.currency)} (수수료·세금 제외)`:'보유정보가 이 기기에 저장됐습니다.';
 const success=persist();render();el('detailDialog').close();notice(success?message:'저장 실패 · 화면에서만 변경됐습니다.');}
function downloadBackup(){const d={format:'F9-A-LOCAL-HOLDINGS',version:1,exported_at:new Date().toISOString(),holdings};const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='f9a-holdings-backup-'+new Date().toISOString().slice(0,10)+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);notice('보유정보 백업 파일을 만들었습니다.');}
async function importBackup(file){try{if(file.size>1e6)throw Error('백업 파일이 너무 큽니다.');const content=JSON.parse(await file.text());if(content.format!=='F9-A-LOCAL-HOLDINGS'||!content.holdings||typeof content.holdings!=='object')throw Error('지원하지 않는 백업 형식입니다.');const next={};for(const [ticker,item] of Object.entries(content.holdings)){const h=validHolding(item);if(!universe.some(s=>s.symbol===ticker))continue;if(h)next[ticker]=h;}if(!confirm(`현재 보유정보를 ${Object.keys(next).length}종목의 백업으로 교체할까요?`))return;holdings=next;persist();render();el('backupDialog').close();notice('보유정보 백업을 복원했습니다.');}catch(e){el('backupInfo').textContent=e.message||'백업을 읽지 못했습니다.'}}
async function fetchScreener(){try{const resp=await fetch(SCREENER_PATH+'?v='+Date.now(),{cache:'no-store'});if(!resp.ok)throw Error('시세 목록 HTTP '+resp.status);const info=await resp.json();if(!Array.isArray(info.stocks)||info.stocks.length!==201)throw Error('200종목과 DRAM ETF 목록이 완전하지 않습니다.');const set=new Set(info.stocks.map(s=>s.symbol));if(set.size!==201)throw Error('중복된 종목코드가 있습니다.');universe=info.stocks;
 const valid=universe.filter(s=>!stale(s)).length;
 el('scanStatus').textContent=`201종목 표시 · 신호 확인 ${valid}개`;
 el('freshDot').classList.toggle('warn',valid<170);
 el('scanDate').textContent=info.updated_at?`갱신 ${info.updated_at.replace('T',' ').slice(0,16)} UTC`:'첫 스캔 전';
 if(statusMessage)notice(statusMessage);
 }catch(e){universe=DEFAULT_STOCKS;el('scanStatus').textContent='시세 목록을 불러오지 못했습니다.';el('scanDate').textContent='페이지 새로고침 필요';notice(String(e.message||e));}
 render();}
function init(){loadHoldings();document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});render();}));
 document.querySelectorAll('[data-market]').forEach(b=>b.addEventListener('click',()=>{market=b.dataset.market;document.querySelectorAll('[data-market]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});render();}));
 el('search').addEventListener('input',e=>{query=e.target.value;render();});
 el('closeDialog').onclick=()=>el('detailDialog').close();el('closeBackup').onclick=()=>el('backupDialog').close();el('positionForm').addEventListener('submit',updateHolding);
 el('clearHolding').addEventListener('click',()=>{if(!selected||!holdings[selected.symbol])return;if(confirm(`${selected.name} 보유정보를 삭제할까요?`)){delete holdings[selected.symbol];persist();el('detailDialog').close();render();notice('보유정보를 삭제했습니다.');}});
 document.querySelectorAll('#editModes [data-mode]').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));
 el('backupButton').onclick=()=>el('backupDialog').showModal();el('exportHoldings').onclick=downloadBackup;
 el('importHoldings').addEventListener('change',async e=>{if(e.target.files?.[0])await importBackup(e.target.files[0]);e.target.value='';});
 fetchScreener();if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
}
init();
