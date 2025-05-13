#!/usr/bin/env python3
with open("LMS_batch_word_to_api.py", "r") as f: lines = f.readlines()
if "        except Exception as e:" not in lines[3521]: lines[3521] = "        except Exception as e:\n"
prev_line_indent = len(lines[1136]) - len(lines[1136].lstrip()) if lines[1136].strip()
correct_indent = " " * prev_line_indent
lines[1137] = correct_indent + "except Exception as e:\n"
with open("LMS_batch_word_to_api.py", "w") as f: f.writelines(lines)
print("File updated.")
