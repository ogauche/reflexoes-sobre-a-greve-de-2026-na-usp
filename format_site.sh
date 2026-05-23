#!/bin/bash

echo "🧹 Cleaning up Notion export (removing UUIDs, fixing links, formatting callouts & PDFs)..."
python3 clean_notion.py

echo "🚀 Building and deploying it locally..."
# This command automatically reads docs/, builds the HTML, and pushes it to your github repository!
mkdocs serve

echo "✅ Done!"