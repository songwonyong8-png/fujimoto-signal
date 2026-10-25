'use strict';
/* The trading decision arrives from the F9 Python engine in data/*.json.
   This client deliberately DOES NOT recompute a rival RSI/MACD score. */
const WATCHLIST=['DRAM','NVDA','MU','AMD'];
const WEIGHTS={1:'11.1%',2:'22.2%',3:'66.7%'};
const STAGE_NAMES={1:'RSI 반등',2:'MACD 골든크로스',3:'일목 엄격 상승 돌파'};
const EXIT_NAMES={1:'RSI 30 이하',2:'MACD 데드크로스',3:'구름대 하단 종가 이탈'};
const REASONS={RSI_REBOUND:'RSI(14) 과매도 후 반등',MACD_GOLDEN:'MACD 골든크로스',ICHI_STRICT_CROSS:'일목균형표 엄격 상승 돌파',RSI_BACK_BELOW_30:'RSI 30 이하 재하락',MACD_DEATH_CROSS:'MACD 데드크로스',CLOUD_BOTTOM_BREAK:'구름대 하단 종가 이탈'};
const el=id=>document.getElementById(id);
const set=(id,text)=>{el(id).textContent=String(text??'—')};
const fmt=(num,dec=2)=>Number.isFinite(Number(num))&&num!==null&&num!==''?Number(num).toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec}):'—';
const percent=(v)=>Number.isFinite(Number(v))&&v!==null?`${Number(v)>=0?'+':''}${fmt(Number(v)*100,2)}%`:'—';
const money=(v)=>'$'+fmt(v,2);
let current='DRAM';
let cache={};
let csvOverrides={};
function pushText(parent,tag,text,className){const x=document.createElement(tag);if(className)x.className=className;x.textContent=String(text);parent.appendChild(x);return x}
function empty(id){const node=el(id);node.replaceChildren();return node}
function dataValid(d){return d&&Array.isArray(d.rows)&&d.rows.length>=120&&d.rows.every(r=>/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&Number.isFinite(Number(r.close))&&Number(r.close)>0)}
function sourceAge(date){const stamp=Date.parse(String(date)+'T12:00:00Z');return Number.isFinite(stamp)?(Date.now()-stamp)/86400000:Infinity}
function isStale(date){const age=sourceAge(date);return age>7||age< -1}
function priceChart(rows){const node=el('chart');node.replaceChildren();if(!rows?.length){set('chartinfo','—');return}
  const values=rows.slice(-90).map(r=>Number(r.close)).filter(Number.isFinite);
  if(values.length<2){set('chartinfo','—');return}
  const low=Math.min(...values),high=Math.max(...values),span=Math.max(0.01,high-low);
  const axis=document.createElementNS('http://www.w3.org/2000/svg','line');
  Object.entries({x1:'0',y1:'176',x2:'600',y2:'176',stroke:'#2b3d56','stroke-width':'1'}).forEach(([k,v])=>axis.setAttribute(k,v));node.appendChild(axis);
  const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');
  const points=values.map((p,i)=>`${(3+i/(values.length-1)*594).toFixed(1)},${(168-(p-low)/span*149).toFixed(1)}`).join(' ');
  Object.entries({points,stroke:'#70a8ff',fill:'none','stroke-width':'3','stroke-linecap':'round','stroke-linejoin':'round'}).forEach(([k,v])=>line.setAttribute(k,v));node.appendChild(line);
  set('chartinfo',`최근 ${values.length}거래일 · 최저 ${money(low)} · 최고 ${money(high)}`);
}
function renderStage(stage,strat){const item=document.createElement('div');item.className='stage';
  const num=document.createElement('div');num.className='stepnum';pushText(num,'strong',String(stage));pushText(num,'span',WEIGHTS[stage]);item.appendChild(num);
  const body=document.createElement('div');body.className='stepbody';pushText(body,'strong',STAGE_NAMES[stage]);
  const p=strat?.positions?.[String(stage)];let msg='',status='';
  if(p?.held){item.classList.add('ready');status='가상 보유 중';msg=`${p.entry_date} 시가 ${money(p.entry_open)} 진입 · 평가손익(비용 추정) ${percent(p.unrealized_return_net_est)}`;}
  else if(p?.ever_bought_in_campaign){status='이번 주기에서 청산 완료';msg='같은 매매 주기에는 이 단계에 재진입하지 않습니다.';}
  else {status='아직 매수하지 않음';msg=stage===1?'RSI 반등 대기':stage===2?'1차 보유 + MACD 신호 대기':'1·2차 보유 + 일목 신호 대기';
    if(stage===2&&strat?.stage2_days_remaining===0){status='이번 주기 진입 기한 종료';msg='1차 RSI 신호 후 20거래일이 지났습니다.'}
    if(stage===3&&strat?.stage3_days_remaining===0){status='이번 주기 진입 기한 종료';msg='2차 MACD 신호 후 20거래일이 지났습니다.'}
  }
  if(strat?.next_open_orders?.some(x=>x.stage===stage)){item.classList.add('armed');status='다음 시가 주문 후보';}
  pushText(body,'span',status,p?.held?'tag ok':'tag');pushText(body,'div',msg,'stepstatus');pushText(body,'div',`기준 매도: ${EXIT_NAMES[stage]}`,'stepstatus');item.appendChild(body);return item;
}
function renderIndicatorGrid(v){const m=empty('metrics');const data=[['RSI (14)',fmt(v.rsi14,1)],['MACD',fmt(v.macd,4)],['MACD 시그널',fmt(v.macd_signal,4)],['MACD 히스토그램',fmt(v.macd_histogram,4)],['구름대 상단',money(v.cloud_top)],['구름대 하단',money(v.cloud_bottom)]];
  for(const [name,value] of data){const card=document.createElement('div');card.className='metric';pushText(card,'small',name);pushText(card,'div',value,'value');m.appendChild(card)}
}
function renderChecklist(s){const container=empty('checklist');const items=[['1차 RSI 반등','rsi_rebound'],['2차 MACD 골든크로스','macd_golden'],['3차 일목 엄격 돌파','ichimoku_strict'],['전환선·기준선 상승 정렬','tenkan_above_rising_kijun','indicator'],['후행스팬 확인','chikou_confirmation','indicator'],['RSI 30 이하 매도 조건','rsi_back_below_30'],['MACD 데드크로스 매도 조건','macd_death'],['A형 구름대 하단 이탈','cloud_bottom_break']];
  for(const [title,key,src] of items){const line=document.createElement('div');line.className='rule';pushText(line,'span',title);const yes=src==='indicator'?s.indicators?.[key]:s.signals_today?.[key];pushText(line,'span',yes?'발생':'미발생',yes?'yes':'no');container.appendChild(line)}
}
function renderOrders(s){const node=empty('orders');if(!s.next_open_orders?.length){pushText(node,'p','오늘 종가 기준 신규 주문 후보가 없습니다.','note');return}
  for(const order of s.next_open_orders){const p=document.createElement('div');p.className='order'+(order.side==='SELL'?' sell':'');pushText(p,'h3',`${order.side==='SELL'?'매도':'매수'} ${order.stage}차 물량 (${WEIGHTS[order.stage]})`);pushText(p,'div',REASONS[order.reason]||order.reason,'desc');pushText(p,'div','다음 거래일 시가가 확인될 때에만 가상 체결 반영','note');node.appendChild(p)}
}
function renderFills(s){const node=empty('fills');if(!s.recent_fills?.length){pushText(node,'p','가상 체결 기록이 없습니다.','note');return}
  for(const v of [...s.recent_fills].reverse()){const line=document.createElement('div');line.className='rule';pushText(line,'span',`${v.date} · ${v.stage}차 ${v.side==='BUY'?'매수':'매도'}`);pushText(line,'span',money(v.price)+(v.side==='BUY'?'':' · 청산'));node.appendChild(line)}
}
function clearSnapshot(text){set('signal','전략 신호 표시 불가');set('reason',text);set('modeLabel','전략 미확인');set('campaignNote','');set('accountNote','현재 데이터로는 F9 가상 매매 상태를 확인할 수 없습니다.');
 empty('orders');pushText(el('orders'),'p',text,'note');empty('stages');empty('metrics');empty('checklist');empty('fills');['green','yellow','red'].forEach(id=>el(id).classList.remove('on'));
}
function render(){const d=csvOverrides[current]||cache[current];set('ticker',current);document.querySelectorAll('#symbols button').forEach(x=>x.classList.toggle('active',x.textContent===current));
  set('source',csvOverrides[current]?'CSV 시세 미리보기':d?'GitHub 일봉':'데이터 없음');
  if(!dataValid(d)){set('price','—');set('date','데이터 없음');set('change','—');set('updated','—');set('sourceStatus','GitHub Actions의 일봉 데이터 갱신이 필요합니다.');priceChart([]);clearSnapshot('F9 계산용 가격 데이터를 불러오지 못했습니다.');return}
  const rows=d.rows;const last=rows.at(-1),prev=rows.at(-2);set('price',money(last.close));set('date',`기준 종가: ${last.date}`);const ch=(last.close/prev.close-1)*100;set('change',`${ch>=0?'+':''}${fmt(ch,2)}%`);el('change').className='change '+(ch>=0?'positive':'negative');priceChart(rows);
  set('updated',d.updated_at?`갱신: ${String(d.updated_at).replace('T',' ').slice(0,16)} UTC`:'CSV 세션');
  const s=d.strategy;const stale=isStale(last.date);
  if(csvOverrides[current]){clearSnapshot('CSV는 시세 미리보기 전용입니다. F9-A 신호는 GitHub 일봉 자동 갱신을 통해 계산하세요.');set('sourceStatus','CSV를 불러온 세션 동안 자동 전략 신호를 표시하지 않습니다.');return}
  if(!s||s.version!=='F9-A'||s.asof!==last.date){clearSnapshot('이 JSON은 구버전 점수제 데이터이거나 기준일이 다른 자료입니다. GitHub Actions → Daily OHLCV and F9-A iPhone Signals → Run workflow를 실행하세요.');set('sourceStatus','백테스트와 일치하는 F9-A 전략 결과가 아직 없습니다.');return}
  if(stale){clearSnapshot('최신 거래일 시세가 아닙니다. 7일 이상 오래된 데이터로 매수·매도 신호를 표시하지 않습니다.');set('sourceStatus','데이터 오래됨: 자동 갱신 기록을 확인하세요.');return}
  set('sourceStatus','F9 Python 엔진 검증 결과 · 자동 업데이트 · 장중 실시간 신호 아님');
  set('signal',s.headline);set('reason',s.detail);set('modeLabel',s.virtual_campaign_open?'가상 매매 주기 진행 중':'가상 현금 대기');
  set('accountNote','연구용 가상계좌 상태입니다. 실제 보유 종목·수량과 다를 수 있으며 개인 매수가와 손익을 나타내지 않습니다.');
  const status=s.state==='BUY_SIGNAL'?'green':s.state==='SELL_SIGNAL'?'red':'yellow';['green','yellow','red'].forEach(id=>el(id).classList.toggle('on',id===status));
  renderOrders(s);const stageNode=empty('stages');for(const st of [1,2,3])stageNode.appendChild(renderStage(st,s));
  const held=[1,2,3].filter(n=>s.positions?.[String(n)]?.held);const heldtxt=held.length?held.join('·')+'차 가상 보유':'가상 보유 없음';
  const age=s.stage3_days_remaining!==null&&s.stage3_days_remaining!==undefined?` · 3차 기한 잔여 ${s.stage3_days_remaining}거래일`:s.stage2_days_remaining!==null&&s.stage2_days_remaining!==undefined?` · 2차 기한 잔여 ${s.stage2_days_remaining}거래일`:'';
  set('campaignNote',heldtxt+age+'. 매수된 물량이 청산되면 그 단계는 동일 매매 주기에서 재매수하지 않습니다.');renderIndicatorGrid(s.indicators||{});renderChecklist(s);renderFills(s);
}
function parseCsv(raw){const lines=raw.replace(/^\uFEFF/,'').trim().split(/\r?\n/),headers=lines.shift().split(',').map(x=>x.trim().toLowerCase());const index=Object.fromEntries(headers.map((x,i)=>[x,i]));
  if(['date','open','high','low','close','volume'].some(k=>index[k]===undefined))throw Error('CSV 열 이름을 확인하세요.');
  const rows=lines.map(line=>{const vals=line.split(',');return {date:vals[index.date],open:Number(vals[index.open]),high:Number(vals[index.high]),low:Number(vals[index.low]),close:Number(vals[index.close]),volume:Number(vals[index.volume])}}).filter(r=>/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&[r.open,r.high,r.low,r.close,r.volume].every(Number.isFinite)&&r.open>0&&r.close>0&&r.high>=r.low&&r.volume>=0);
  rows.sort((a,b)=>a.date.localeCompare(b.date));const dedup=rows.filter((r,i)=>i===0||r.date!==rows[i-1].date);if(dedup.length<120)throw Error('일봉 120개 이상 필요합니다.');return dedup;
}
async function fetchOne(ticker){const response=await fetch(`data/${ticker}.json?refresh=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw Error(`HTTP ${response.status}`);const d=await response.json();if(!dataValid(d))throw Error('Data invalid');cache[ticker]=d;return d}
async function refresh(){set('sourceStatus','최신 데이터를 확인하고 있습니다.');await Promise.all(WATCHLIST.map(async t=>{try{await fetchOne(t)}catch(e){console.warn('Unable to fetch',t,e)}}));render()}
for(const t of WATCHLIST){const b=document.createElement('button');b.type='button';b.textContent=t;b.onclick=()=>{current=t;render()};el('symbols').appendChild(b)}
el('refresh').onclick=refresh;
el('csv').addEventListener('change',async ev=>{const file=ev.target.files?.[0];if(!file)return;try{const rows=parseCsv(await file.text());csvOverrides[current]={rows};set('csvStatus',`${current}: ${rows.length}개 일봉 미리보기. 전략 신호는 표시하지 않습니다.`);render()}catch(error){set('csvStatus','오류: '+error.message)}});
el('reset').onclick=()=>{delete csvOverrides[current];el('csv').value='';set('csvStatus','자동 데이터 표시로 돌아왔습니다.');render()};
render();refresh();if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(e=>console.warn('Service worker',e));
