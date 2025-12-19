
import re

def clean_file(path):
    with open(path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if 'print(f"DEBUG:' in line:
            continue
        new_lines.append(line)
        
    with open(path, 'w') as f:
        f.writelines(new_lines)
    print(f"Cleaned {len(lines) - len(new_lines)} debug lines from {path}")

clean_file("multirig/rig.py")
