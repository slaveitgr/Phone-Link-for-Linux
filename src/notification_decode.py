"""Decode phone-owned notification records without logging their contents."""
import json
SCALARS={1:'uint8_value',2:'int16_value',3:'uint16_value',4:'int32_value',
 5:'uint32_value',6:'int64_value',7:'uint64_value',8:'single_value',9:'double_value',
 10:'char16_value',11:'bool_value',12:'string_value',13:'guid_value',
 36:'datetime_value',37:'timespan_value'}
ARRAYS={18:'uint8_array',19:'int16_array',20:'uint16_array',21:'int32_array',
 22:'uint32_array',23:'int64_array',24:'uint64_array',25:'single_array',
 26:'double_array',27:'char16_array',28:'bool_array',29:'string_array',30:'guid_array'}

def variant_value(variant,depth=0):
    if depth>5:return None
    kind=variant.value_type
    if kind in SCALARS:return getattr(variant,SCALARS[kind])
    if kind==17:return value_map(variant.object_value,depth+1)
    if kind==34:return [value_map(v,depth+1) for v in variant.object_array[:100]]
    if kind in ARRAYS:
        value=getattr(variant,ARRAYS[kind])
        if kind==18:return None # Image bytes stay out of the UI bridge.
        return list(value[:100])
    return None

def value_map(values,depth=0):
    return {key:variant_value(value,depth) for key,value in values.entries.items()}

def notification_records(values):
    if 'notifications' not in values.entries:return None
    notifications=variant_value(values.entries['notifications'])
    if isinstance(notifications,str):
        try:notifications=json.loads(notifications)
        except ValueError:return None
    if isinstance(notifications,dict):notifications=notifications.get('notifications',[notifications])
    if not isinstance(notifications,list):return None
    keys=variant_value(values.entries['notificationKeys']) if 'notificationKeys' in values.entries else []
    records=[]
    for index,item in enumerate(notifications[:100]):
        if isinstance(item,str):
            try:item=json.loads(item)
            except ValueError:continue
        if not isinstance(item,dict):continue
        def pick(*names):
            for name in names:
                v=item.get(name)
                if isinstance(v,(str,int)):return str(v)
            return ''
        identifier=pick('key','notificationKey','id','notificationId')
        if not identifier and isinstance(keys,list) and index<len(keys):identifier=str(keys[index])
        if not identifier:continue
        title=pick('title','notificationTitle')
        body=pick('bigText','big_text','text','notificationText','body')
        if not title and not body:continue
        records.append({'id':identifier,'app':pick('appName','app_name','packageName','package_name'),
                        'title':title,'body':body})
    return records
