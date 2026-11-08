'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={
 phone:'<path d="M6.3 3H3.8a1 1 0 0 0-1 1.1A18.2 18.2 0 0 0 19.9 21.2a1 1 0 0 0 1.1-1v-2.5a1 1 0 0 0-.7-1l-4-1.3a1 1 0 0 0-1 .2l-1.6 1.6a14.5 14.5 0 0 1-6.9-6.9l1.6-1.6a1 1 0 0 0 .2-1l-1.3-4a1 1 0 0 0-1-.7Z"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
 person:'<circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2H5Z"/>',
 incoming:'<path d="m18 6-12 12m0-9v9h9"/>',
 outgoing:'<path d="M6 18 18 6m-9 0h9v9"/>',
 missed:'<path d="m3 5 6 6a4 4 0 0 0 6 0l6-6m-6 0h6v6"/>',
 bluetooth:'<path d="M12 2v20l6-5L6 7m0 10L18 7l-6-5"/>',
 battery:'<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M23 10v4"/><rect x="4" y="8" width="12" height="8" stroke="none" fill="currentColor"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M19 5l-1.5 1.5m-11 11L5 19"/>',
 moon:'<path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
 star:'<path d="m12 3 3 6 6.5 1-4.7 4.5 1.1 6.5-5.9-3-5.9 3 1.1-6.5L2.5 10 9 9l3-6Z"/>',
 history:'<path d="M3 11a9 9 0 1 1 2 7M3 5v6h6m3-4v5l3 2"/>',
 keypad:'<g fill="currentColor" stroke="none"><circle cx="6" cy="4" r="1.5"/><circle cx="12" cy="4" r="1.5"/><circle cx="18" cy="4" r="1.5"/><circle cx="6" cy="10" r="1.5"/><circle cx="12" cy="10" r="1.5"/><circle cx="18" cy="10" r="1.5"/><circle cx="6" cy="16" r="1.5"/><circle cx="12" cy="16" r="1.5"/><circle cx="18" cy="16" r="1.5"/><circle cx="12" cy="22" r="1.5"/></g>',
 backspace:'<path d="M9 5h12v14H9L2 12l7-7Zm4 4 5 6m0-6-5 6"/>',
 close:'<path d="m6 6 12 12M18 6 6 18"/>',
 back:'<path d="m14 5-7 7 7 7"/>',
 mic:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
 micOff:'<path d="m3 3 18 18M9 9v3a3 3 0 0 0 5 2m1-6V5a3 3 0 0 0-6 0M5 10v2a7 7 0 0 0 12 5m2-7v2a7 7 0 0 1-.6 2.9M12 19v3m-4 0h8"/>',
 speaker:'<path d="M3 9v6h4l5 4V5L7 9H3Zm13-2a7 7 0 0 1 0 10m3-13a11 11 0 0 1 0 16"/>',
 check:'<path d="m5 12 4 4L19 6"/>'
};
const icon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[n]||paths.phone}</svg>`;
