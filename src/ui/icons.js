'use strict';
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
const esc = s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={
 apps:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 messages:'<path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-5 4V6a2 2 0 0 1 2-2Z"/><path d="M7 9h10M7 13h7"/>',
 photos:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
 calls:'<path d="M6 3H3.5a1 1 0 0 0-1 1.1A18.5 18.5 0 0 0 19.9 21.5a1 1 0 0 0 1.1-1V18a1 1 0 0 0-.7-1l-4-1.3a1 1 0 0 0-1 .2l-1.6 1.6a15 15 0 0 1-7.2-7.2l1.6-1.6a1 1 0 0 0 .2-1L7 3.7A1 1 0 0 0 6 3Z"/>',
 notifications:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
 settings:'<path d="m9 3-1 3-3 1-2 4 2 3v3l4 3h3l3 1 3-3 3-2v-4l-2-3-1-3-4-1-2-2H9Z"/><circle cx="12" cy="12" r="3.3"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
 phone:'<rect x="6.5" y="2" width="11" height="20" rx="2"/><path d="M10 5h4M11 19h2"/>',
 sync:'<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
 moon:'<path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M19 5l-1.5 1.5m-11 11L5 19"/>',
 bluetooth:'<path d="M12 2v20l6-5-12-10m0 10L18 7l-6-5"/>',
 volume:'<path d="M4 9v6h4l5 4V5L8 9H4Zm12-2a7 7 0 0 1 0 10m3-13a11 11 0 0 1 0 16"/>',
 music:'<path d="M9 18V5l11-2v13M9 8l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2.5"/><ellipse cx="17" cy="16" rx="3" ry="2.5"/>',
 dnd:'<circle cx="12" cy="12" r="9"/><path d="M7 12h10"/>',
 wifi:'<path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0m-4 4h.01"/>',
 signal:'<path d="M4 18v3m5-7v7m5-12v12m5-17v17"/>',
 battery:'<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M23 10v4"/><rect x="4" y="8" width="13" height="8" fill="currentColor" stroke="none"/>',
 more:'<circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
 send:'<path d="m3 3 19 9-19 9 4-9-4-9Zm4 9h15"/>',
 close:'<path d="m6 6 12 12M18 6 6 18"/>',
 back:'<path d="m14 5-7 7 7 7"/>',
 next:'<path d="m10 5 7 7-7 7"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
 trash:'<path d="M4 6h16m-13 0 1 15h8l1-15M9 6V3h6v3M10 10v7m4-7v7"/>',
 menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
 outgoing:'<path d="M6 18 18 6m-9 0h9v9"/>',
 incoming:'<path d="M18 6 6 18m0-9v9h9"/>',
 mic:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
 keypad:'<g fill="currentColor" stroke="none"><circle cx="6" cy="4" r="1.5"/><circle cx="12" cy="4" r="1.5"/><circle cx="18" cy="4" r="1.5"/><circle cx="6" cy="10" r="1.5"/><circle cx="12" cy="10" r="1.5"/><circle cx="18" cy="10" r="1.5"/><circle cx="6" cy="16" r="1.5"/><circle cx="12" cy="16" r="1.5"/><circle cx="18" cy="16" r="1.5"/><circle cx="12" cy="22" r="1.5"/></g>',
 person:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2H4Z"/>',
 edit:'<path d="m15 4 5 5-12 12H3v-5L15 4Zm-1 1 5 5M13 21h8"/>',
 backspace:'<path d="M9 5h12v14H9L2 12l7-7Zm4 4 5 6m0-6-5 6"/>',
 star:'<path d="m12 3 3 6 6.5 1-4.7 4.5 1.1 6.5-5.9-3-5.9 3 1.1-6.5L2.5 10 9 9l3-6Z"/>'
};
function icon(name,cls=''){return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.apps}</svg>`}
