
import sys

def fix_indentation(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if 'Critical error in reconciliation' in line or 'Reconciliation Error' in line:
            # Find the indentation of the line before the 'except' block if possible, or just use 26 spaces
            new_lines.append('                          ' + line.lstrip())
        else:
            new_lines.append(line)
            
    with open(filepath, 'w') as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    fix_indentation(r"d:\Workspace\delta-exchange-alog\core\runner.py")
