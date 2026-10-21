with open("SWE-rebench-V2/scripts/annotation_script.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("path.read_text()", "path.read_text(encoding='utf-8')")
content = content.replace("prompt_template_path.read_text()", "prompt_template_path.read_text(encoding='utf-8')")
content = content.replace("meta_template_path.read_text()", "meta_template_path.read_text(encoding='utf-8')")
content = content.replace("output_path.write_text(", "output_path.write_text(encoding='utf-8', data=")

with open("SWE-rebench-V2/scripts/annotation_script.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied to SWE-rebench-V2/scripts/annotation_script.py")
