'use strict';
let tab='notifications',snapshot={},lastView='',dial='',clipboardDraft='';
const bridge=(action,extra={})=>window.webkit.messageHandlers.phoneLink.postMessage(JSON.stringify({action,...extra}));
const header=(title,subtitle,actions='')=>`<div class="page-header"><div><h1 class="page-title">${title}</h1><p class="page-subtitle">${subtitle}</p></div><div class="header-actions">${actions}</div></div>`;
const empty=(name,text)=>`<div class="empty-state">${icon(name)}<b>${esc(text)}</b></div>`;
function render(){
 const d=snapshot.device||{},connected=snapshot.state==='connected',notes=snapshot.notifications||[];
 $('.device-name').textContent=d.name||'POCO F8 Ultra';
 $('#device-indicators').innerHTML=(typeof d.wifi_enabled==='boolean'?`<span title="Wi-Fi ${d.wifi_enabled?'On':'Off'}" style="opacity:${d.wifi_enabled?1:.35}">${icon('wifi')}</span>`:'')+(typeof d.bluetooth_enabled==='boolean'?`<span title="Bluetooth ${d.bluetooth_enabled?'On':'Off'}" style="opacity:${d.bluetooth_enabled?1:.35}">${icon('bluetooth')}</span>`:'')+icon('battery')+`<span>${Number.isInteger(d.battery_percent)?d.battery_percent+'%':'—'}${d.charging?' ⚡':''}</span>`;
 $('#connection').innerHTML=`<span class="status-dot" style="background:${connected?'#6abf91':'#8b9099'}"></span>${connected?'Connected':'Connecting…'}`;
 if(snapshot.wallpaper)$('.phone-wallpaper').style.backgroundImage=`url("${snapshot.wallpaper}")`;
 $('#quick-controls').innerHTML=[['dnd','Do not disturb'],['bluetooth','Bluetooth'],['volume','Phone audio'],['music','Music']].map(([id,title])=>`<button disabled class="quick-toggle ${id==='bluetooth'&&d.bluetooth_enabled?'active':''}" title="${title}">${icon(id)}</button>`).join('');
 $('#navigation').innerHTML=[['notifications','Notifications'],['messages','Messages'],['photos','Photos'],['apps','Apps'],['calls','Calls'],['clipboard','Clipboard']].map(([id,label])=>`<button class="nav-item ${tab===id?'active':''}" data-tab="${id}">${icon(id==='clipboard'?'phone':id)}<span>${label}</span>${id==='notifications'&&notes.length?`<span class="nav-badge">${notes.length}</span>`:''}</button>`).join('');
 $('#settings-nav').innerHTML=icon('settings')+'<span>Settings</span>';$('#settings-nav').classList.toggle('active',tab==='settings');
 $('#sync-state').innerHTML=icon('sync')+`<span>${connected?'Connected to your phone':'Waiting for connection'}<small>${connected?'Live device updates':''}</small></span>`;
 $('#footer-state').textContent=(d.name||'POCO')+(connected?' connected':' disconnected');
 const dialer=$('#native-dialer');if(dialer?.contentWindow)dialer.contentWindow.postMessage({type:'phone-link-snapshot',snapshot},'*');
 const fingerprint=tab==='calls'?JSON.stringify([tab]):JSON.stringify([tab,notes,snapshot.clipboard,snapshot.state,tab==='settings'?d:null]);
 if(lastView===fingerprint)return;lastView=fingerprint;
 if(tab==='notifications')$('#view').innerHTML=header('Notifications','A quieter way to stay in the loop.')+`<div class="notifications-list">${notes.length?notes.map(n=>`<article class="notification-card"><div class="notification-card-top">${icon('notifications')} ${esc(n.app)}</div><h3>${esc(n.title)}</h3><p>${esc(n.body)}</p></article>`).join(''):empty('notifications',"You're all caught up")}</div>`;
 else if(tab==='calls')$('#view').innerHTML='<iframe id="native-dialer" title="Phone Link dialer" src="dialer/index.html" style="width:100%;height:100%;border:0;display:block"></iframe>';
 else if(tab==='clipboard')$('#view').innerHTML=header('Clipboard','Copy and paste between your phone and PC.')+`<div class="content-panel" style="padding:24px"><textarea id="clipboard-text" class="native-clipboard" placeholder="Text to send to your phone">${esc(clipboardDraft)}</textarea><div class="native-actions"><button class="primary-button" data-action="send_clipboard">${icon('send')} Send to phone</button><button class="secondary-button" data-action="copy_clipboard">Copy from phone</button></div><p class="native-status">${esc(snapshot.clipboard||'Waiting for text from your phone.')}</p></div>`;
 else if(tab==='settings')$('#view').innerHTML=header('Settings','Make Phone Link feel like you.')+`<div class="settings-list"><div class="section-heading"><h2>Your device</h2></div><div class="settings-row">${icon('phone')}<div><b>${esc(d.name||'POCO F8 Ultra')}</b><p>${esc(snapshot.message||'')}</p></div></div><div class="settings-row">${icon('battery')}<div><b>Battery</b><p>${d.battery_percent??'—'}% ${d.charging?'· Charging':''}</p></div></div><div class="settings-row">${icon('wifi')}<div><b>Connection</b><p>${connected?'Connected':'Disconnected'}</p></div></div></div>`;
 else {const name={apps:'Apps',messages:'Messages',photos:'Photos'}[tab];$('#view').innerHTML=header(name,{apps:'Your favorite apps, now on your PC.',messages:'Your conversations, together in one place.',photos:'Your recent memories, within reach.'}[tab],`<button class="screen-button" disabled>${icon('phone')} Open phone screen</button>`)+`<div class="section-heading"><h2>${tab==='apps'?'All apps':name}</h2></div>`+empty(tab,`${name} sync is not connected yet`);}
}
window.phoneLinkUpdate=value=>{snapshot=value;render()};
document.addEventListener('click',e=>{const nav=e.target.closest('[data-tab]');if(nav){tab=nav.dataset.tab;lastView='';render();return}const key=e.target.closest('[data-key]');if(key){dial=($('#dial-number')?.value||'')+key.dataset.key;$('#dial-number').value=dial;return}const a=e.target.closest('[data-action]')?.dataset.action;if(!a)return;if(a==='backspace'){$('#dial-number').value=$('#dial-number').value.slice(0,-1);return}if(a==='dial')bridge('dial',{number:$('#dial-number').value});else if(a==='send_clipboard')bridge(a,{text:$('#clipboard-text').value});else bridge(a)});
window.phoneLinkToast=text=>{$('#toast').textContent=text;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),3500)};
render();
document.addEventListener('input',e=>{if(e.target.id==='dial-number')dial=e.target.value;if(e.target.id==='clipboard-text')clipboardDraft=e.target.value});

window.phoneLinkNavigate=value=>{if(['notifications','messages','photos','apps','calls','clipboard','settings'].includes(value)){tab=value;lastView='';render()}};

setInterval(()=>{const frame=$('#native-dialer');if(frame?.contentWindow)frame.contentWindow.postMessage({type:'phone-link-snapshot',snapshot},'*')},500);

window.phoneLinkPhoto=value=>{const frame=$('#native-dialer');if(frame?.contentWindow)frame.contentWindow.postMessage({type:'phone-link-photo',photo:value},'*')};
