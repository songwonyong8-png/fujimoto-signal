const CACHE='fujimoto-v12-levels-macd-20261026';
const SHELL=['./','./index.html','./app.js','./manifest.webmanifest','./icon.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(Promise.all([
  caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))),
  self.clients.claim()
])));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const u=new URL(event.request.url);
  if(u.origin!==self.location.origin)return;
  // A price JSON must never be served as if it were fresh while offline.
  if(u.pathname.includes('/data/')){
    event.respondWith(fetch(event.request,{cache:'no-store'}).catch(()=>new Response('',{status:503,statusText:'Offline price data unavailable'})));
    return;
  }
  event.respondWith(fetch(event.request).catch(()=>caches.match(event.request,{ignoreSearch:true})));
});
