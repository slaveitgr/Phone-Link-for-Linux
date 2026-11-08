import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../phoneStatus.js',import.meta.url),'utf8');
const {phoneStatus}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const now=Date.parse('2026-11-07T23:00:00Z');
const status={schema_version:1,state:'connected',updated_at:'2026-11-07T23:00:00Z',
 device:{name:'POCO F8 Ultra',battery_percent:97,charging:true},actions:['open','execute arbitrary command','open']};
assert.equal(phoneStatus(status,now).battery,'97% · Charging');
assert.deepEqual(phoneStatus(status,now).actions,['open']);
assert.equal(phoneStatus(status,now+91000).state,'disconnected');
assert.equal(phoneStatus(status,now+91000).battery,'');
assert.equal(phoneStatus({...status,device:{battery_percent:101}},now).battery,'');
assert.equal(phoneStatus({schema_version:1,state:'paired',actions:['open']},now).label,'Paired · waiting for connection');
assert.equal(phoneStatus(null,now).state,'unavailable');
assert.equal(phoneStatus({...status,updated_at:'invalid'},now).state,'disconnected');
console.log('Phone status: fresh/stale state, battery bounds, missing backend and action allowlist passed');
