import os
import re

MAPPINGS = {
    r'\bimport llm\b': 'from life_agent.agent import llm',
    r'\bimport quality\b': 'from life_agent.agent import quality',
    r'\bimport research\b': 'from life_agent.agent import research',
    r'\bimport prompt_loader\b': 'from life_agent.agent import prompt_loader',
    r'\bimport event_model\b': 'from life_agent.events import event_model',
    r'\bimport store\b': 'from life_agent.events import store',
    r'\bimport inbound\b': 'from life_agent.notifications import inbound',
    r'\bimport outbound\b': 'from life_agent.notifications import outbound',
    r'\bimport emailer\b': 'from life_agent.notifications import emailer',
    r'\bimport metrics\b': 'from life_agent.metrics import metrics',
    r'\bimport notion_api\b': 'from life_agent.integrations import notion_api',
    r'\bimport calendar_feed\b': 'from life_agent.integrations import calendar_feed',
    r'\bimport config\b': 'from life_agent import config',
    r'\bimport dates\b': 'from life_agent import dates',
}

# Fix task dynamic imports in main.py
# f"tasks.{task}" -> f"life_agent.agent.tasks.{task}"

def refactor():
    for root, dirs, files in os.walk('.'):
        if '.venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            if file == 'refactor_imports.py':
                continue
            
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for old, new in MAPPINGS.items():
                new_content = re.sub(old, new, new_content)
                
            # special case for main.py
            if file == 'main.py':
                new_content = new_content.replace('importlib.import_module(f"tasks.{task}")', 'importlib.import_module(f"life_agent.agent.tasks.{task}")')
                
            if new_content != content:
                print(f"Updated {filepath}")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

if __name__ == '__main__':
    refactor()
