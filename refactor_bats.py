import re

files = ['.github/workflows/agent.yml', 'run_daily.bat', 'run_task.bat']

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace python main.py <task> with python -m life_agent.agent.main <task>
    # or .venv\Scripts\python.exe main.py %1 -> .venv\Scripts\python.exe -m life_agent.agent.main %1
    new_content = re.sub(r'python main\.py', 'python -m life_agent.agent.main', content)
    new_content = re.sub(r'\.venv\\Scripts\\python\.exe main\.py', r'.venv\\Scripts\\python.exe -m life_agent.agent.main', new_content)
    
    if new_content != content:
        with open(file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {file}")
