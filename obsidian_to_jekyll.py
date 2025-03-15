#!/usr/bin/env python3
"""
Obsidian to Jekyll Converter

This script converts an Obsidian vault to Jekyll-compatible markdown files
while preserving the folder structure and converting folder names to lowercase
with underscore prefixes.
"""

import os
import re
import shutil
import argparse
import yaml
from datetime import datetime
from pathlib import Path


def parse_frontmatter(content):
    """Extract and parse YAML frontmatter from markdown content."""
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    
    if fm_match:
        frontmatter_text = fm_match.group(1)
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
            content_without_fm = content[fm_match.end():]
            return frontmatter, content_without_fm
        except yaml.YAMLError:
            return {}, content
    return {}, content


def create_jekyll_frontmatter(frontmatter, filename, relative_path=None):
    """Create Jekyll frontmatter from Obsidian frontmatter."""
    jekyll_fm = frontmatter.copy() if frontmatter else {}
    
    # Add layout if not present
    if 'layout' not in jekyll_fm:
        jekyll_fm['layout'] = 'page'  # Using 'page' layout for non-posts
    
    # Add title if not present
    if 'title' not in jekyll_fm:
        # Use filename as title, removing date prefix if present
        title = os.path.splitext(filename)[0]
        date_match = re.match(r'^\d{4}-\d{2}-\d{2}-(.+)$', title)
        if date_match:
            title = date_match.group(1)
        jekyll_fm['title'] = title.replace('-', ' ').replace('_', ' ').title()
    
    # Add date if not present
    if 'date' not in jekyll_fm:
        date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', filename)
        if date_match:
            jekyll_fm['date'] = f"{date_match.group(1)} 00:00:00 +0000"
        else:
            jekyll_fm['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S +0000")
    
    # Add permalink if preserving folder structure
    if relative_path:
        # Create permalink based on the relative path without file extension
        permalink_path = os.path.splitext(relative_path)[0]
        # Replace backslashes with forward slashes for URLs
        permalink_path = permalink_path.replace('\\', '/')
        permalink_path = permalink_path.replace(' ', '_')
        permalink_path = '_' + permalink_path.lower()
        jekyll_fm['permalink'] = f"/{permalink_path}.md"
    
    # Convert Obsidian tags to Jekyll tags
    if 'tags' in jekyll_fm and isinstance(jekyll_fm['tags'], str):
        jekyll_fm['tags'] = [tag.strip() for tag in jekyll_fm['tags'].split(',')]
    
    # Format as YAML
    return '---\n' + yaml.dump(jekyll_fm, default_flow_style=False) + '---\n\n'


def convert_wiki_links(content, link_map):
    """Convert Obsidian wiki-links to Jekyll/Markdown links."""
    
    # Handle [[page]] wiki-links
    def replace_wiki_link(match):
        link_text = match.group(1).split('|')[0].strip()
        display_text = match.group(1).split('|')[1].strip() if '|' in match.group(1) else link_text
        
        # Handle anchor links (#heading)
        if link_text.startswith('#'):
            anchor = link_text[1:].lower().replace(' ', '-')
            return f'[{display_text}](#{anchor})'
        
        # Normalize link text to match filenames
        normalized_link = link_text.lower()#.replace(' ', '-')
        
        # Find the corresponding Jekyll file
        target_file = None
        for obs_path, jekyll_path in link_map.items():
            obs_filename = os.path.splitext(os.path.basename(obs_path))[0].lower()
            if obs_filename == normalized_link:
                target_file = jekyll_path
                break
        
        if target_file:
            # Extract permalink from the target file's frontmatter
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    frontmatter, _ = parse_frontmatter(content)
                    if 'permalink' in frontmatter:
                        return f'[{display_text}]({frontmatter["permalink"]})'
            except (FileNotFoundError, IOError):
                pass
            
            # Fallback: Convert to relative URL
            rel_path = os.path.relpath(target_file).replace('\\', '/')
            url_path = os.path.splitext(rel_path)[0]
            return f'[{display_text}](/{url_path}.md)'
        else:
            # If file doesn't exist, keep the display text
            return display_text
    
    # Replace wiki-links
    content = re.sub(r'\[\[(.*?)\]\]', replace_wiki_link, content)
    
    # Handle ![[image.png]] embeds
    def replace_embed(match):
        embed_path = match.group(1).split('|')[0].strip()
        
        # Handle image embeds
        if any(embed_path.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']):
            alt_text = match.group(1).split('|')[1].strip() if '|' in match.group(1) else embed_path
            # Preserve original path structure for images
            image_name = embed_path
            # Strip any folder paths in the image name
            if '/' in image_name:
                image_name = image_name.split('/')[-1]
            return f'![{alt_text}](/assets/images/{image_name})'
        
        # Handle note embeds - convert to a link instead
        return replace_wiki_link(match)
    
    # Replace embeds
    content = re.sub(r'!\[\[(.*?)\]\]', replace_embed, content)
    
    return content


def convert_callouts(content):
    """Convert Obsidian callouts to Jekyll-compatible HTML or Markdown."""
    
    # Define regex for callout blocks
    callout_pattern = re.compile(
        r'> \[!(\w+)\](.*?)\n((?:> .*?\n)+)',
        re.DOTALL
    )
    
    def replace_callout(match):
        callout_type = match.group(1).lower()
        title = match.group(2).strip()
        content_lines = match.group(3)
        
        # Clean up content (remove > prefix from lines)
        clean_content = '\n'.join(line[2:] for line in content_lines.split('\n') if line.startswith('> '))
        
        # Map Obsidian callout types to Bootstrap alert classes
        callout_class_map = {
            'note': 'info',
            'tip': 'success',
            'warning': 'warning',
            'danger': 'danger',
            'info': 'info',
            'success': 'success',
            'error': 'danger',
            'question': 'info',
            'abstract': 'light',
            'example': 'primary',
            'quote': 'secondary'
        }
        
        alert_class = callout_class_map.get(callout_type, 'info')
        
        # Create Bootstrap-style alert that works in most Jekyll themes
        title_html = f'<strong>{title}</strong><br>' if title else ''
        return f'<div class="alert alert-{alert_class}" role="alert">\n{title_html}{clean_content}\n</div>\n\n'
    
    # Replace callouts
    return callout_pattern.sub(replace_callout, content)


def handle_code_blocks(content):
    """Ensure code blocks use Jekyll-compatible format."""
    
    # Convert ```language to ```language
    # (Jekyll is usually OK with Obsidian's format, but this ensures compatibility)
    content = re.sub(r'```(\w+)', r'```\1', content)
    
    return content


def get_relative_path(file_path, base_dir):
    """Get the relative path from base_dir to file_path."""
    return os.path.relpath(file_path, base_dir)


def convert_to_jekyll_path(rel_path):
    """Convert a relative path to Jekyll-style path with lowercase underscore prefixed folders."""
    parts = rel_path.split(os.sep)
    
    # Convert directory names (not the filename)
    for i in range(len(parts) - 1):
        # Skip if already has underscore prefix
        if not parts[i].startswith('_'):
            parts[i] = f"_{parts[i].lower()}"
    
    # Keep the filename as is
    return os.path.join(*parts)


def process_markdown_file(file_path, obsidian_dir, jekyll_dir, link_map):
    """Process a single markdown file from Obsidian vault while preserving folder structure."""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract frontmatter
    frontmatter, content_without_fm = parse_frontmatter(content)
    
    # Get relative path from obsidian dir
    rel_path = get_relative_path(file_path, obsidian_dir)
    
    # Convert to Jekyll path with underscore prefixes
    jekyll_rel_path = convert_to_jekyll_path(rel_path)
    
    # Create output directory structure in Jekyll
    rel_dir = os.path.dirname(jekyll_rel_path)
    output_dir = os.path.join(jekyll_dir, rel_dir).replace(' ', '_')
    # output_dir = output_dir.lower()
    os.makedirs(output_dir, exist_ok=True)
    
    # Preserve original filename
    filename = os.path.basename(file_path)
    jekyll_filename = filename.lower().replace(' ', '_')
    
    # We'll store the original path in frontmatter permalink for consistent URLs
    original_rel_path = rel_path.replace('\\', '/')
    
    # Prepare Jekyll frontmatter with original path for permalink
    jekyll_frontmatter = create_jekyll_frontmatter(frontmatter, jekyll_filename, original_rel_path)
    
    # Convert Obsidian-specific syntax
    content = convert_wiki_links(content_without_fm, link_map)
    content = convert_callouts(content)
    content = handle_code_blocks(content)
    
    # Write the converted file
    output_path = os.path.join(output_dir, jekyll_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(jekyll_frontmatter + content)
    
    return output_path


def process_assets(obsidian_dir, jekyll_dir):
    """Copy image and attachment files to Jekyll assets directory."""
    
    assets_dir = os.path.join(jekyll_dir, 'assets', 'images')
    os.makedirs(assets_dir, exist_ok=True)
    
    # Find all image and attachment files
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf']
    
    for root, _, files in os.walk(obsidian_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in image_extensions):
                src_path = os.path.join(root, file)
                dst_path = os.path.join(assets_dir, file)
                
                # Check for duplicate filenames
                if os.path.exists(dst_path):
                    # Add a timestamp to make the filename unique
                    name, ext = os.path.splitext(file)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    new_filename = f"{name}_{timestamp}{ext}"
                    dst_path = os.path.join(assets_dir, new_filename)
                
                # Copy file
                shutil.copy2(src_path, dst_path)
                print(f"Copied asset: {file}")


def build_link_map(obsidian_dir, jekyll_dir):
    """Build a mapping from Obsidian paths to Jekyll paths."""
    link_map = {}
    
    # Find all markdown files
    for root, _, files in os.walk(obsidian_dir):
        for file in files:
            if file.lower().endswith('.md'):
                obsidian_path = os.path.join(root, file)
                
                # Get relative path from obsidian dir
                rel_path = get_relative_path(obsidian_path, obsidian_dir)
                
                # Convert to Jekyll path with underscore prefixes
                jekyll_rel_path = convert_to_jekyll_path(rel_path)
                
                # Create output path preserving folder structure
                jekyll_path = os.path.join(jekyll_dir, jekyll_rel_path)
                link_map[obsidian_path] = jekyll_path
    
    return link_map


def main():
    """Main function to convert Obsidian vault to Jekyll site."""
    
    parser = argparse.ArgumentParser(description='Convert Obsidian vault to Jekyll site with underscore prefixed folders')
    parser.add_argument('obsidian_dir', help='Path to Obsidian vault directory')
    parser.add_argument('jekyll_dir', help='Path to Jekyll site directory')
    parser.add_argument('--dry-run', action='store_true', help='Dry run without making changes')
    parser.add_argument('--use-posts', action='store_true', help='Use _posts directory for blog-like content')
    args = parser.parse_args()
    
    # Create Jekyll _posts directory if requested
    if args.use_posts:
        posts_dir = os.path.join(args.jekyll_dir, '_posts')
        os.makedirs(posts_dir, exist_ok=True)
    
    # Build link map
    link_map = build_link_map(args.obsidian_dir, args.jekyll_dir)
    
    # Process markdown files
    processed_files = []
    skipped_files = []
    
    for root, _, files in os.walk(args.obsidian_dir):
        for file in files:
            if file.lower().endswith('.md'):
                file_path = os.path.join(root, file)
                
                # Skip files in _posts directory if not using --use-posts
                if '_posts' in file_path.split(os.sep) and not args.use_posts:
                    skipped_files.append(file_path)
                    continue
                
                print(f"Processing: {file}")
                if not args.dry_run:
                    output_path = process_markdown_file(
                        file_path, 
                        args.obsidian_dir, 
                        args.jekyll_dir, 
                        link_map
                    )
                    processed_files.append(output_path)
    
    # Process assets (images, etc.)
    if not args.dry_run:
        process_assets(args.obsidian_dir, args.jekyll_dir)
    
    print(f"\nConversion complete! Processed {len(processed_files)} files.")
    if skipped_files:
        print(f"Skipped {len(skipped_files)} files in _posts directory.")
    print(f"Jekyll files are in: {args.jekyll_dir}")
    
    # Print information about permalinks
    print("\nNOTE: Each file has been assigned a permalink based on its original location.")
    print("This allows internal links to work correctly while preserving the folder structure.")


if __name__ == "__main__":
    main()