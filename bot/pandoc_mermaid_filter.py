#!/usr/bin/env python

import sys
import json
import subprocess
import tempfile
import os
import shutil

# --- Configuration ---
# Path to the mmdc executable inside the Docker container.
# We rely on it being in the PATH, which is configured in the Dockerfile.
MMDC_PATH = shutil.which('mmdc') or 'mmdc'
PUPPETEER_CONFIG = '/app/bot/puppeteer-config.json'
# A file to log the paths of generated temporary files for later cleanup.
CLEANUP_LOG_FILE = '/tmp/pandoc_cleanup.log'

generated_files = []

def render_mermaid_to_image_file(mermaid_code: str) -> str | None:
    """
    Renders a Mermaid diagram to a PNG file and returns the file path.
    Returns None if rendering fails.
    """
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.mmd', encoding='utf-8') as infile:
            infile.write(mermaid_code)
            input_path = infile.name
        generated_files.append(input_path)

        # The output path will be in the same directory with a .png extension
        output_path = os.path.splitext(input_path)[0] + '.png'
        generated_files.append(output_path)

        command = [
            MMDC_PATH,
            '-p', PUPPETEER_CONFIG,
            '-i', input_path,
            '-o', output_path,
            '-b', 'transparent'
        ]
        
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')

        if process.returncode != 0 or not os.path.exists(output_path):
            sys.stderr.write(f"Mermaid rendering failed: {process.stderr}\n")
            return None

        return output_path

    except Exception as e:
        sys.stderr.write(f"Exception during Mermaid rendering: {e}\n")
        return None

def apply_filter(doc):
    """
    Walks through the pandoc AST and replaces Mermaid code blocks with rendered images.
    """
    for i, element in enumerate(doc['blocks']):
        if element['t'] == 'CodeBlock':
            [[_id, classes, _kv_pairs], code] = element['c']
            if 'mermaid' in classes:
                image_path = render_mermaid_to_image_file(code)
                if image_path:
                    # Replace the CodeBlock with a Para containing the Image
                    # The image path must be absolute for pandoc to find it.
                    image_node = {
                        't': 'Image',
                        'c': [['', [], []], [], [image_path, '']]
                    }
                    # Wrap the image in a paragraph
                    doc['blocks'][i] = {'t': 'Para', 'c': [image_node]}
    return doc

def main():
    """
    Main function to read from stdin, apply the filter, and write to stdout.
    """
    try:
        doc = json.load(sys.stdin)
        modified_doc = apply_filter(doc)
        json.dump(modified_doc, sys.stdout)
    except Exception as e:
        sys.stderr.write(f"Error in pandoc filter: {e}\n")
        # In case of a JSON loading error, stdin might be consumed.
        # We can't reliably re-read it, so we exit. Pandoc will fail, which is correct.
        sys.exit(1)
    finally:
        # After processing, log the generated file paths for cleanup by the parent process.
        if generated_files:
            try:
                with open(CLEANUP_LOG_FILE, 'a', encoding='utf-8') as f:
                    for path in generated_files:
                        f.write(path + '\n')
            except Exception as e:
                sys.stderr.write(f"Failed to write to cleanup log: {e}\n")

if __name__ == "__main__":
    main()