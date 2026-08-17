import json
import uuid
import random
from datetime import datetime, timedelta, timezone

def generate():
    events = []
    base_time = datetime.now(timezone.utc) - timedelta(days=14)
    
    for i in range(14):
        current_day = base_time + timedelta(days=i)
        
        # Morning planning email
        m_time = current_day.replace(hour=3, minute=0, second=0) # 8:30 IST
        token = f"LA-{current_day.strftime('%Y%m%d')}-M"
        events.append({
            "id": uuid.uuid4().hex,
            "ts": m_time.isoformat(),
            "kind": "email_sent",
            "slot": "morning",
            "token": token,
            "subject": "Morning Planning",
            "message_id": f"<msg{uuid.uuid4().hex[:8]}@gmail.com>"
        })
        
        # User reply to morning email
        if random.random() > 0.2:
            reply_time = m_time + timedelta(minutes=random.randint(10, 60))
            events.append({
                "id": uuid.uuid4().hex,
                "ts": reply_time.isoformat(),
                "kind": "reply_raw",
                "token": token,
                "from_addr": "user@example.com",
                "gmail_uid": random.randint(1000, 9000),
                "body_raw": "Planned tasks for today: write documentation, fix bugs."
            })
            
            # Tasks planned
            task1_id = uuid.uuid4().hex
            events.append({
                "id": uuid.uuid4().hex,
                "ts": (reply_time + timedelta(minutes=1)).isoformat(),
                "kind": "task_planned",
                "intent_id": task1_id,
                "description": "Write documentation"
            })
            
            task2_id = uuid.uuid4().hex
            events.append({
                "id": uuid.uuid4().hex,
                "ts": (reply_time + timedelta(minutes=1, seconds=1)).isoformat(),
                "kind": "task_planned",
                "intent_id": task2_id,
                "description": "Fix bugs"
            })
            
            # Tasks completed
            if random.random() > 0.1:
                events.append({
                    "id": uuid.uuid4().hex,
                    "ts": (reply_time + timedelta(hours=random.randint(2, 5))).isoformat(),
                    "kind": "task_completed",
                    "intent_id": task1_id
                })
            
            if random.random() > 0.4:
                events.append({
                    "id": uuid.uuid4().hex,
                    "ts": (reply_time + timedelta(hours=random.randint(6, 8))).isoformat(),
                    "kind": "task_completed",
                    "intent_id": task2_id
                })

        # Evening checkin
        e_time = current_day.replace(hour=16, minute=0, second=0) # 21:30 IST
        e_token = f"LA-{current_day.strftime('%Y%m%d')}-E"
        events.append({
            "id": uuid.uuid4().hex,
            "ts": e_time.isoformat(),
            "kind": "email_sent",
            "slot": "evening",
            "token": e_token,
            "subject": "Evening Checkin",
            "message_id": f"<msg{uuid.uuid4().hex[:8]}@gmail.com>"
        })

    with open('data/example_events.jsonl', 'w') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')

if __name__ == '__main__':
    generate()
