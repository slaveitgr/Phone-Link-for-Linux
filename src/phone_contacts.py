"""Native phone contacts resource, decoded only into caller-owned RAM.

No device access, contact reads, persistence or logging happens on import.
Caller must verify the paired sender and request correlation before decoding.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from contacts.v1.contact_pb2 import ContactSearchRequestMessage,ContactSearchResponseMessage
from platform_sdk.v1.device_resource_manager_pb2 import DeviceResourceManagerMessage

# Exact APK getResourcePath: contacts-getResourcePath.json (ev_fb797418...).
RESOURCE_PATH='/contacts'
PAGE_SIZE=100
MAX_CONTACTS=20000
MAX_RESPONSE_BYTES=8*1024*1024


def contacts_request(*,query,last_contact_id='',max_results=PAGE_SIZE,allow_fuzzy=True):
    """Return a PLATFORM plane1 DeviceResourceManagerMessage request."""
    if not isinstance(query,str) or not query.strip() or len(query)>500:raise ValueError('A nonblank contact search query is required')
    query=query.strip()
    if not isinstance(last_contact_id,str) or len(last_contact_id)>300:raise ValueError('Invalid contact cursor')
    if type(max_results) is not int or not 1<=max_results<=PAGE_SIZE:raise ValueError('Invalid contact page size')
    inner=ContactSearchRequestMessage(query=query,max_results=max_results,
        last_contact_id=last_contact_id,allow_fuzzy=bool(allow_fuzzy))
    return DeviceResourceManagerMessage(request_type=1,resource_path=RESOURCE_PATH,
        payload=inner.SerializeToString()).SerializeToString()


def parse_contacts_response(payload):
    """Decode inner ContactSearchResponseMessage; return bounded plain records.

    Keep this result in RAM. It contains user address-book information.
    Cursor is from the last source record even when a contact has no numbers.
    """
    if not isinstance(payload,bytes) or len(payload)>MAX_RESPONSE_BYTES:
        raise ValueError('Invalid contacts response size')
    response=ContactSearchResponseMessage.FromString(payload)
    status={1:'ok',2:'invalid_request',3:'need_permissions',4:'no_contacts',5:'error'}.get(response.status,'unknown')
    if response.status!=1:return {'status':status,'contacts':[],'has_more':False,'cursor':''}
    if len(response.contacts)>MAX_CONTACTS:raise ValueError('Contacts response exceeds record limit')
    contacts=[]
    for item in response.contacts:
        identifier=item.id[:300]
        if not identifier:continue
        name=(item.display_name or ' '.join(filter(None,(item.first_name,item.last_name))) or item.nick_name)[:500]
        numbers=[];seen=set()
        for number in item.phone_numbers[:100]:
            value=(number.value or number.display_value).strip()[:100]
            if not value or value in seen:continue
            seen.add(value)
            numbers.append({'number':value,'label':(number.label or number.type or number.description)[:100]})
        if numbers:contacts.append({'id':identifier,'name':name or numbers[0]['number'],'numbers':numbers})
    cursor=response.contacts[-1].id[:300] if response.contacts else ''
    if response.has_more and not cursor:raise ValueError('Contact page has no next cursor')
    return {'status':'ok','contacts':contacts,'has_more':response.has_more,'cursor':cursor}


class ContactSync:
    """Bounded native contact-search pagination, entirely in RAM."""
    def __init__(self,query):
        if not isinstance(query,str) or not query.strip():raise ValueError('A contact search query is required')
        self.query=query.strip()
        self.contacts={};self.cursor='';self.cursors=set();self.complete=False
    def request(self):
        if self.complete:return None
        return contacts_request(query=self.query,last_contact_id=self.cursor)
    def consume(self,payload):
        page=parse_contacts_response(payload)
        if page['status']!='ok':
            self.complete=True
            return page
        for item in page['contacts']:
            self.contacts[item['id']]=item
            if len(self.contacts)>MAX_CONTACTS:raise ValueError('Contacts sync exceeds record limit')
        cursor=page['cursor']
        if page['has_more'] and (cursor==self.cursor or cursor in self.cursors):
            raise ValueError('Contacts pagination did not advance')
        self.cursors.add(cursor);self.cursor=cursor
        self.complete=not page['has_more']
        return {**page,'complete':self.complete,'total_count':len(self.contacts)}
    def records(self):
        return list(self.contacts.values())
