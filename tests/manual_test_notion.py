import sys, os, requests, json
from datetime import datetime, timedelta, timezone

# Manually parse .env
env = {}
try:
    with open('d:/life-agent/.env', 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                env[k] = v.strip('\"\'')
except:
    pass

token = env.get('NOTION_TOKEN')
db_id = env.get('REMINDERS_DB_ID')

if not token or not db_id:
    print('Error: Could not find NOTION_TOKEN or REMINDERS_DB_ID in .env file.')
    exit(1)

# Set time for 5 mins from now in IST
now_utc = datetime.now(timezone.utc)
ist = timezone(timedelta(hours=5, minutes=30))
now_ist = now_utc.astimezone(ist)
start_time = now_ist + timedelta(minutes=5)
start_iso = start_time.strftime('%Y-%m-%dT%H:%M:00+05:30')

print(f'Attempting to set reminder for {start_iso}')

response = requests.post(
    'https://api.notion.com/v1/pages',
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    },
    json={
        'parent': {'database_id': db_id},
        'properties': {
            'Name': {'title': [{'text': {'content': 'API Reminder Test'}}]},
            'When': {
                'date': {
                    'start': start_iso,
                    'reminder': {'unit': 'minute', 'value': 0}
                }
            }
        }
    }
)

print(f'\nStatus Code: {response.status_code}')
try:
    data = response.json()
    if response.status_code == 400:
        print(f'\nERROR: Notion rejected the payload (validation error):\n{json.dumps(data, indent=2)}')
    elif 'properties' in data and 'When' in data['properties']:
        print('\nSUCCESS: Page created! Here is the Date property Notion saved:')
        print(json.dumps(data['properties']['When'], indent=2))
        
        has_reminder = 'reminder' in json.dumps(data['properties']['When'])
        if not has_reminder:
            print('\n🚨 CONCLUSION: The API silently DROPPED the reminder field. It does not work.')
        else:
            print('\n✅ CONCLUSION: The API ACCEPTED the reminder field! It works!')
    else:
        print(json.dumps(data, indent=2))
except Exception as e:
    print(f'Failed to parse response: {e}')
