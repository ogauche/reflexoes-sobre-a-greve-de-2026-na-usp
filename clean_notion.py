import os
import re
import urllib.parse
import shutil
import unicodedata

RAW_DIR = 'notion_raw'
DOCS_DIR = 'docs'

def clean_string(text):
    text = re.sub(r'\s+[a-f0-9]{32}', '', text)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = text.lower()
    text = text.replace(' ', '-').replace('_', '-')
    text = re.sub(r'[^a-z0-9\-./]', '', text)
    return text

# --- WORKSPACE CLEANUP ---
if os.path.exists(DOCS_DIR):
    for item in os.listdir(DOCS_DIR):
        if item in ['stylesheets', 'javascripts']:
            continue 
        item_path = os.path.join(DOCS_DIR, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    
    for item in os.listdir(RAW_DIR):
        s = os.path.join(RAW_DIR, item)
        d = os.path.join(DOCS_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
else:
    shutil.copytree(RAW_DIR, DOCS_DIR)

# 1. Renaming Files and Folders
for root, dirs, files in os.walk(DOCS_DIR, topdown=False):
    for name in files + dirs:
        base, ext = os.path.splitext(name)
        clean_name = clean_string(base) + ext
        
        old_path = os.path.join(root, name)
        new_path = os.path.join(root, clean_name)
        if old_path != new_path:
            os.rename(old_path, new_path)

# 2. Flattening ONLY the Root
main_md_clean = None
root_items = os.listdir(DOCS_DIR)
root_mds = [f for f in root_items if f.endswith('.md')]
root_dirs = [d for d in root_items if os.path.isdir(os.path.join(DOCS_DIR, d)) and d not in ['stylesheets', 'javascripts']]

if len(root_mds) == 1 and len(root_dirs) == 1:
    root_md = root_mds[0]
    root_dir = root_dirs[0]
    if root_md[:-3] == root_dir:
        main_md_clean = root_md  
        os.rename(os.path.join(DOCS_DIR, root_md), os.path.join(DOCS_DIR, 'index.md'))
        for item in os.listdir(os.path.join(DOCS_DIR, root_dir)):
            shutil.move(os.path.join(DOCS_DIR, root_dir, item), DOCS_DIR)
        os.rmdir(os.path.join(DOCS_DIR, root_dir))

# 2a. Merging Subfolders
for root, dirs, files in os.walk(DOCS_DIR, topdown=False):
    if 'stylesheets' in dirs: dirs.remove('stylesheets') 
    if 'javascripts' in dirs: dirs.remove('javascripts')
    for file in files:
        if file.endswith('.md') and file != 'index.md':
            base = file[:-3]
            if base in dirs:
                os.rename(os.path.join(root, file), os.path.join(root, base, 'index.md'))

# 3. Resolve Links in Content
file_map = {}
for root, dirs, files in os.walk(DOCS_DIR):
    if 'stylesheets' in dirs: dirs.remove('stylesheets')
    if 'javascripts' in dirs: dirs.remove('javascripts')
    for file in files:
        rel_path = os.path.relpath(os.path.join(root, file), DOCS_DIR).replace('\\', '/')
        if file == 'index.md':
            if root == DOCS_DIR and main_md_clean:
                file_map[main_md_clean] = rel_path
            else:
                folder_name = os.path.basename(root)
                file_map[folder_name + '.md'] = rel_path
        else:
            file_map[file] = rel_path

for root, dirs, files in os.walk(DOCS_DIR):
    if 'stylesheets' in dirs: dirs.remove('stylesheets')
    if 'javascripts' in dirs: dirs.remove('javascripts')
    for file in files:
        if file.endswith('.md'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # --- EXACT, SAFE LINK PROCESSING ---

            code_blocks = []
            def repl_code(m):
                code_blocks.append(m.group(0))
                return f"__CODE_{len(code_blocks)-1}__"
            content = re.sub(r'```.*?```', repl_code, content, flags=re.DOTALL)
            content = re.sub(r'`[^`]+`', repl_code, content)

            math_blocks = []
            def repl_math(m):
                math_blocks.append(m.group(0))
                return f"__MATH_{len(math_blocks)-1}__"
            
            content = re.sub(r'\$\$.*?\$\$', repl_math, content, flags=re.DOTALL)
            content = re.sub(r'\$(?!\s)[^$\n]+?(?<!\s)\$', repl_math, content)

            md_links = []
            def repl_md(m):
                md_links.append(m.group(0))
                return f"__MDLINK_{len(md_links)-1}__"
            content = re.sub(r'\[([^\]]+)\]\(((?:[^)(]+|\([^)(]*\))*)\)', repl_md, content)

            html_tags = []
            def repl_html(m):
                html_tags.append(m.group(0))
                return f"__HTML_{len(html_tags)-1}__"
            content = re.sub(r'<[^>]+>', repl_html, content)

            def repl_bare(m):
                url = m.group(0)
                trailing = ""
                while url and url[-1] in ".,;!?()":
                    trailing = url[-1] + trailing
                    url = url[:-1]
                return f"[{url}]({url}){{: target=\"_blank\" }}" + trailing

            content = re.sub(r'https?://[^\s<>]+', repl_bare, content)

            for i in range(len(html_tags)-1, -1, -1):
                content = content.replace(f"__HTML_{i}__", html_tags[i])

            lines = content.split('\n')
            first_header_seen = False
            for i, line in enumerate(lines):
                if re.match(r'^#+\s', line):
                    if not first_header_seen:
                        first_header_seen = True
                        if line.startswith('# '):
                            continue
                    lines[i] = '#' + line
            content = '\n'.join(lines)

            for i in range(len(md_links)-1, -1, -1):
                original_link = md_links[i]
                match = re.match(r'\[([^\]]+)\]\(((?:[^)(]+|\([^)(]*\))*)\)', original_link)
                if match:
                    text, url = match.group(1), match.group(2)
                    if url.startswith('http'):
                        resolved_link = f'[{text}]({url}){{: target="_blank" }}'
                    else:
                        raw_url = urllib.parse.unquote(url)
                        basename = os.path.basename(raw_url)
                        base_no_ext, ext = os.path.splitext(basename)
                        clean_target = clean_string(base_no_ext) + ext

                        if clean_target in file_map:
                            target_rel = file_map[clean_target]
                            current_dir_rel = os.path.relpath(root, DOCS_DIR)

                            if current_dir_rel == '.':
                                final_url = target_rel
                            else:
                                final_url = os.path.relpath(target_rel, current_dir_rel)

                            final_url = final_url.replace('\\', '/')
                            clean_url = urllib.parse.quote(final_url, safe='/?#')

                            if clean_url.lower().endswith('.pdf'):
                                resolved_link = f'<iframe src="{clean_url}" width="100%" height="600px" style="border: 1px solid #ccc; border-radius: 8px;"></iframe>\n<br>[🔗 Abrir {text} em nova guia]({clean_url}){{: target="_blank" }}'
                            else:
                                resolved_link = f"[{text}]({clean_url})"
                        else:
                            resolved_link = original_link
                else:
                    resolved_link = original_link

                content = content.replace(f"__MDLINK_{i}__", resolved_link)

            for i in range(len(math_blocks)-1, -1, -1):
                content = content.replace(f"__MATH_{i}__", math_blocks[i])

            for i in range(len(code_blocks)-1, -1, -1):
                content = content.replace(f"__CODE_{i}__", code_blocks[i])

            # --- NESTED CALLOUT REPLACER SIMPLIFICADO ---
            innermost_pattern = re.compile(r'([ \t]*)<aside>((?:(?!<aside>).)*?)</aside>', re.DOTALL | re.IGNORECASE)
            
            while True:
                match = innermost_pattern.search(content)
                if not match:
                    break
                
                indent = match.group(1) 
                inner_html = match.group(2)
                
                if 'push-pin_red' in inner_html:
                    admonition_type = 'important'
                    title = 'Importante'
                elif 'thought' in inner_html or 'green' in inner_html:
                    admonition_type = 'observation'
                    title = 'Observação'
                else:
                    admonition_type = 'info'
                    title = 'Nota'
                
                text_content = re.sub(r'^[ \t]*<img[^>]*>\n?', '', inner_html, flags=re.MULTILINE)
                
                lines = text_content.split('\n')
                processed_lines = []
                for line in lines:
                    line = line.rstrip() 
                    
                    if line.startswith(indent):
                        line = line[len(indent):]
                    
                    if line:
                        processed_lines.append(f"{indent}    {line}")
                    else:
                        processed_lines.append(f"{indent}    ")
                
                while processed_lines and processed_lines[0].strip() == '':
                    processed_lines.pop(0)
                while processed_lines and processed_lines[-1].strip() == '':
                    processed_lines.pop()
                    
                joined_text = '\n'.join(processed_lines)
                
                # Substituição exata e direta, sem injetar quebras de linha artificiais
                replacement = f'{indent}!!! {admonition_type} "{title}"\n{joined_text}'
                content = content[:match.start()] + replacement + content[match.end():]

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

# 4. Generate the nav: tree dynamically for mkdocs.yml
def build_nav_tree(md_filepath, base_dir):
    tree = []
    if not os.path.exists(md_filepath): return tree
    
    with open(md_filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md)\)', content)
    
    seen_paths = set()
    for title, url in links:
        if url.startswith('http'): continue
        url = url.split(')')[0] 
        
        current_dir = os.path.dirname(md_filepath)
        abs_target = os.path.normpath(os.path.join(current_dir, urllib.parse.unquote(url)))
        rel_to_docs = os.path.relpath(abs_target, base_dir).replace('\\', '/')
        
        if rel_to_docs in seen_paths: continue
        seen_paths.add(rel_to_docs)
        
        if rel_to_docs.endswith('/index.md') and rel_to_docs != 'index.md':
            children = build_nav_tree(abs_target, base_dir)
            tree.append({
                'title': title,
                'path': rel_to_docs,
                'children': children
            })
        else:
            tree.append({
                'title': title,
                'path': rel_to_docs
            })
    return tree

def tree_to_yaml(tree, indent_level=2):
    yaml_lines = []
    indent = ' ' * indent_level
    for item in tree:
        if 'children' in item and item['children']:
            yaml_lines.append(f"{indent}- \"{item['title']}\":")
            yaml_lines.append(f"{indent}  - {item['path']}")
            yaml_lines.extend(tree_to_yaml(item['children'], indent_level + 2))
        else:
            yaml_lines.append(f"{indent}- \"{item['title']}\": {item['path']}")
    return yaml_lines

root_tree = build_nav_tree(os.path.join(DOCS_DIR, 'index.md'), DOCS_DIR)

nav_yaml = ["nav:", "  - Home: index.md"]
nav_yaml.extend(tree_to_yaml(root_tree, 2))
nav_string = "\n".join(nav_yaml)

mkdocs_yml_path = 'mkdocs.yml'
if os.path.exists(mkdocs_yml_path):
    with open(mkdocs_yml_path, 'r', encoding='utf-8') as f:
        mkdocs_content = f.read()
    
    if '\nnav:' in mkdocs_content or mkdocs_content.startswith('nav:'):
        mkdocs_content = re.sub(r'\nnav:[\s\S]*', '', mkdocs_content)
        
    with open(mkdocs_yml_path, 'w', encoding='utf-8') as f:
        f.write(mkdocs_content.strip() + '\n\n' + nav_string + '\n')