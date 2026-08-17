import os
import re

MAPPINGS = {
    r'patch\("store\.': 'patch("life_agent.events.store.',
    r'patch\("event_model\.': 'patch("life_agent.events.event_model.',
    r'patch\("metrics\.': 'patch("life_agent.metrics.metrics.',
    r'patch\("outbound\.': 'patch("life_agent.notifications.outbound.',
    r'patch\("inbound\.': 'patch("life_agent.notifications.inbound.',
    r'patch\("emailer\.': 'patch("life_agent.notifications.emailer.',
    r'patch\("notion_api\.': 'patch("life_agent.integrations.notion_api.',
    r'patch\("calendar_feed\.': 'patch("life_agent.integrations.calendar_feed.',
    r'patch\("config\.': 'patch("life_agent.config.',
    r'patch\("dates\.': 'patch("life_agent.dates.',
    r'patch\("llm\.': 'patch("life_agent.agent.llm.',
    r'patch\("prompt_loader\.': 'patch("life_agent.agent.prompt_loader.',
}

def fix_mocks():
    for root, _, files in os.walk('tests'):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content
                for old, new in MAPPINGS.items():
                    new_content = re.sub(old, new, new_content)
                
                if new_content != content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated mock patches in {filepath}")

if __name__ == '__main__':
    fix_mocks()
