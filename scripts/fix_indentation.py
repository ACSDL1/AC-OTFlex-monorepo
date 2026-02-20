#!/usr/bin/env python3
"""
Script to fix indentation in OTFLEX_WORKFLOW_Iliya.py
"""

def fix_indentation():
    file_path = "OTFLEX_WORKFLOW_Iliya.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the start and end of the section that needs indentation
    start_line = None
    end_line = None
    
    for i, line in enumerate(lines):
        if "# load custom labware in slot 11" in line:
            start_line = i
        elif "else:" in line and "When imported as module" in lines[i+1] if i+1 < len(lines) else False:
            end_line = i
            break
    
    if start_line is None or end_line is None:
        print(f"Could not find section boundaries. start_line={start_line}, end_line={end_line}")
        return
    
    print(f"Indenting lines {start_line+1} to {end_line}")
    
    # Add 4 spaces of indentation to each line in the section
    for i in range(start_line, end_line):
        if lines[i].strip():  # Only indent non-empty lines
            lines[i] = "    " + lines[i]
    
    # Write the modified content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("Indentation fixed!")

if __name__ == "__main__":
    fix_indentation()
