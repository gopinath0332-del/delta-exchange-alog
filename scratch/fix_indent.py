import sys

file_path = 'core/runner.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# We want to fix the indentation in the main loop block.
# Line 445 is 'if live_pos_data:'
# We will find the indentation of that line and apply it to the rest of the block.

target_indent = None
for i, line in enumerate(lines):
    if 'if live_pos_data:' in line and i > 440:
        target_indent = len(line) - len(line.lstrip())
        print(f"Found target indent: {target_indent} at line {i+1}")
        break

if target_indent is not None:
    # Re-align lines from 452 up to where the next block starts (around 580)
    for i in range(451, 580): # 0-indexed
        line = lines[i]
        if line.strip():
            current_indent = len(line) - len(line.lstrip())
            # If the line is at 26 spaces (one too many), move it to 25
            if current_indent == target_indent + 1:
                lines[i] = ' ' * target_indent + line.lstrip()
            elif current_indent == target_indent + 5: # Nested 4 spaces in
                lines[i] = ' ' * (target_indent + 4) + line.lstrip()
            # Add more cases as needed, or just standardizing
            
    with open(file_path, 'w') as f:
        f.writelines(lines)
    print("Indentation fixed.")
else:
    print("Could not find anchor line.")
