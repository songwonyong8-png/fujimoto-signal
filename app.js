'use strict';
/* Full 200-name public screener + exclusively device-local REAL holdings.
   Signals are produced by the same Python v6/F9 indicator routines used in F9.
   Never infer a brokerage position from the historical virtual strategy account.
*/
const SCREENER_PATH='data/screener_f9a.json';
const STORAGE_KEY='fujimoto-user-holdings-v1';
const DEFAULT_STOCKS=[];
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
 el('detailRsi').textContent=fmt(s.rsi14,1);el('detailMacd').textContent=`${fmt(s.macd,3)} / ${fmt(s.macd_signal,3)}`;
 el('detailCloudTop').textContent=currency(s.cloud_top,s.currency);el('detailCloudBottom').textContent=currency(s.cloud_bottom,s.currency);
 drawChart(s.recent_closes||[]);
 el('heldQty').value=h?h.qty:'';el('averageCost').value=h?h.avg:'';
 for(const n of [1,2,3])el('lot'+n).checked=h?h.stages.includes(n):n===1;
 document.querySelectorAll('.currencyLabel').forEach(x=>x.textContent=s.currency);
 el('tradeQty').value='';el('tradePrice').value='';el('clearHolding').disabled=!h;
 setMode(h?'edit':'buy');
 el('detailDialog').showModal();}
function drawChart(values){const svg=el('detailChart');svg.replaceChildren();const a=values.map(Number).filter(Number.isFinite);if(a.length<2)return;const lo=Math.min(...a),hi=Math.max(...a),span=Math.max(1e-9,hi-lo);const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');const points=a.map((n,i)=>`${(10+i/(a.length-1)*400).toFixed(1)},${(98-(n-lo)/span*75).toFixed(1)}`).join(' ');line.setAttribute('points',points);line.setAttribute('fill','none');line.setAttribute('stroke','#5ebee9');line.setAttribute('stroke-width','2.5');line.setAttribute('stroke-linecap','round');line.setAttribute('stroke-linejoin','round');svg.appendChild(line);}
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
