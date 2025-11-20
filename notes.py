#!/usr/bin/env python3
"""
General-Purpose Note-Taking CLI Tool with Anki Integration
Capture, enrich with AI, and sync notes to Anki for spaced repetition learning.
"""

import os
import sys
import argparse
import json
import datetime
import logging
import requests
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# AnkiConnect integration
try:
    from anki import AnkiConnect
except ImportError:
    AnkiConnect = None

# --- Configuration ---
SCRIPT_DIR = Path(__file__).resolve().parent
COURSES_DIR = SCRIPT_DIR / 'courses'
COURSES_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = SCRIPT_DIR / '.notes_config.json'

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class Colors:
    GREEN, BLUE, YELLOW, RED, BOLD, END = '\033[92m', '\033[94m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'

# --- Core Configuration Functions ---

def load_global_config():
    """Load global config (current course, etc.)"""
    if not CONFIG_FILE.exists():
        return {"current_course": None}

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"current_course": None}

def save_global_config(config):
    """Save global config"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_course_config(course_name):
    """Load course-specific configuration"""
    course_file = COURSES_DIR / f"{sanitize_filename(course_name)}.json"
    if not course_file.exists():
        return None

    with open(course_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_course_config(course_name, config):
    """Save course configuration"""
    course_file = COURSES_DIR / f"{sanitize_filename(course_name)}.json"
    with open(course_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def sanitize_filename(name):
    """Convert course name to safe filename"""
    return name.lower().replace(" ", "_").replace("/", "_")

def get_default_ai_prompt():
    """Default AI prompt template for general note-taking"""
    return """You are an expert tutor helping a student learn about {course}.

The student has given you a concept/term to learn: "{phrase}"

Current level/topic: {level}
{context_section}
{grammar_section}

Please provide:
1. A clear, concise explanation of this concept
2. A practical example showing how it's used
3. Any important details or nuances to remember

Format your response as JSON with these fields:
{{
  "term": "the term/concept (cleaned up if needed)",
  "explanation": "clear explanation",
  "example": "practical example",
  "example_explanation": "what the example demonstrates",
  "notes": "additional important details"
}}"""

def get_language_ai_prompt():
    """AI prompt template specifically for language learning"""
    return """You are an expert language teacher for {course}.

The student (at level: {level}) has given you a word/phrase to learn: "{phrase}"
{context_section}
{grammar_section}

Please provide:
1. The word/phrase in the target language (if not already)
2. Pronunciation guide (if applicable, e.g., pinyin for Chinese, IPA for complex words)
3. English translation
4. An example sentence in the target language
5. Translation of the example sentence
6. Grammar notes or usage tips

Format your response as JSON with these fields:
{{
  "term": "word/phrase in target language",
  "pronunciation": "pronunciation guide (if applicable)",
  "translation": "English translation",
  "example": "example sentence in target language",
  "example_translation": "example translation",
  "notes": "grammar notes and usage tips"
}}"""

# --- Course Management Commands ---

def cmd_course(args):
    """Set or create a new course"""
    course_name = args.name
    global_config = load_global_config()
    course_config = load_course_config(course_name)

    # If course doesn't exist, create it
    if course_config is None:
        print(f"{Colors.BLUE}Creating new course: {Colors.BOLD}{course_name}{Colors.END}")
        print()

        # Ask if this is a language course
        is_language = input("Is this a language learning course? (y/n) [n]: ").strip().lower() == 'y'

        # Get AI prompt
        default_prompt = get_language_ai_prompt() if is_language else get_default_ai_prompt()
        print()
        print(f"{Colors.YELLOW}AI Prompt Template{Colors.END}")
        print("This template will be used to generate note content with AI.")
        print(f"Default template will be used. You can customize it anytime in:")
        print(f"  {COURSES_DIR / f'{sanitize_filename(course_name)}.json'}")
        print()

        custom_prompt = input("Enter custom AI prompt (or press Enter to use default): ").strip()
        ai_prompt = custom_prompt if custom_prompt else default_prompt

        # Create course config
        course_config = {
            "course_name": course_name,
            "created": datetime.datetime.now().isoformat(),
            "is_language": is_language,
            "current_level": None,
            "ai_prompt": ai_prompt,
            "anki": {
                "deck_name": course_name,
                "model_name": f"{course_name} (Notes)",
                "use_sub_decks": True
            },
            "fields": {
                "term": "Term",
                "translation": "Translation" if is_language else "Explanation",
                "example": "Example",
                "example_translation": "Example Explanation",
                "notes": "Notes",
                "pronunciation": "Pronunciation" if is_language else None
            }
        }

        save_course_config(course_name, course_config)
        print(f"{Colors.GREEN}✓ Course '{course_name}' created successfully!{Colors.END}")
        print()

    # Set as current course
    global_config['current_course'] = course_name
    save_global_config(global_config)

    print(f"{Colors.GREEN}✓ Current course set to: {Colors.BOLD}{course_name}{Colors.END}")
    if course_config.get('current_level'):
        print(f"  Current level: {course_config['current_level']}")

def cmd_level(args):
    """Set the current level/topic within a course"""
    global_config = load_global_config()
    current_course = global_config.get('current_course')

    if not current_course:
        print(f"{Colors.RED}Error: No course selected. Run 'notes course <name>' first.{Colors.END}")
        return

    course_config = load_course_config(current_course)
    course_config['current_level'] = args.level
    save_course_config(current_course, course_config)

    print(f"{Colors.GREEN}✓ Level set to: {Colors.BOLD}{args.level}{Colors.END}")
    print(f"  Course: {current_course}")

def cmd_new(args):
    """Add a new note"""
    global_config = load_global_config()
    current_course = global_config.get('current_course')

    if not current_course:
        print(f"{Colors.RED}Error: No course selected. Run 'notes course <name>' first.{Colors.END}")
        return

    course_config = load_course_config(current_course)

    # Load existing notes
    notes_file = COURSES_DIR / f"{sanitize_filename(current_course)}_notes.json"
    if notes_file.exists():
        with open(notes_file, 'r', encoding='utf-8') as f:
            try:
                notes_data = json.load(f)
            except json.JSONDecodeError:
                notes_data = {}
    else:
        notes_data = {}

    # Build AI prompt
    level = course_config.get('current_level', 'general')
    context_section = f"\nContext/Example: {args.context}" if args.context else ""
    grammar_section = f"\nAdditional info: {args.grammar}" if args.grammar else ""

    prompt = course_config['ai_prompt'].format(
        course=course_config['course_name'],
        phrase=args.phrase,
        level=level,
        context_section=context_section,
        grammar_section=grammar_section
    )

    print(f"{Colors.BLUE}Adding new note to {Colors.BOLD}{current_course}{Colors.END} (Level: {level})...")

    # Call OpenAI API
    if not OPENAI_API_KEY:
        print(f"{Colors.RED}Error: OPENAI_API_KEY not set in .env file{Colors.END}")
        return

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
        )
        response.raise_for_status()

        ai_response = response.json()['choices'][0]['message']['content']

        # Parse JSON from AI response
        # Remove markdown code blocks if present
        if "```json" in ai_response:
            ai_response = ai_response.split("```json")[1].split("```")[0].strip()
        elif "```" in ai_response:
            ai_response = ai_response.split("```")[1].split("```")[0].strip()

        note_data = json.loads(ai_response)

        # Add metadata
        note_data['added'] = datetime.datetime.now().isoformat()
        note_data['level'] = level
        note_data['synced'] = False

        # Add context and grammar if provided
        if args.context:
            note_data['context'] = args.context
        if args.grammar:
            note_data['grammar'] = args.grammar

        # Store note
        term_key = note_data.get('term', args.phrase)
        notes_data[term_key] = note_data

        # Save notes
        with open(notes_file, 'w', encoding='utf-8') as f:
            json.dump(notes_data, f, indent=2, ensure_ascii=False)

        # Display summary
        print(f"{Colors.GREEN}✓ Successfully added:{Colors.END}")
        for key, value in note_data.items():
            if key not in ['added', 'synced', 'level'] and value:
                print(f"  {key.capitalize()}: {value}")
        print()
        print(f"Run {Colors.BOLD}notes sync{Colors.END} to add it to Anki.")

    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()

def cmd_sync(args):
    """Sync notes to Anki"""
    global_config = load_global_config()
    current_course = global_config.get('current_course')

    if not current_course:
        print(f"{Colors.RED}Error: No course selected. Run 'notes course <name>' first.{Colors.END}")
        return

    print(f"{Colors.BLUE}Syncing notes from {Colors.BOLD}{current_course}{Colors.END} to Anki...")

    # Load notes
    notes_file = COURSES_DIR / f"{sanitize_filename(current_course)}_notes.json"
    if not notes_file.exists():
        print(f"{Colors.YELLOW}No notes found to sync.{Colors.END}")
        return

    with open(notes_file, 'r', encoding='utf-8') as f:
        notes_data = json.load(f)

    # Filter unsynced notes
    unsynced = {k: v for k, v in notes_data.items() if not v.get('synced', False)}

    if not unsynced:
        print(f"{Colors.YELLOW}All notes are already synced!{Colors.END}")
        return

    print(f"Found {len(unsynced)} new note(s) to sync...")

    # Initialize Anki
    if AnkiConnect is None:
        print(f"{Colors.RED}Error: Could not import AnkiConnect module{Colors.END}")
        return

    anki = AnkiConnect()
    course_config = load_course_config(current_course)

    # Ensure deck exists
    deck_name = course_config['anki']['deck_name']
    anki.create_deck(deck_name)

    # TODO: Setup card model if needed

    synced_count = 0
    for i, (term, note) in enumerate(unsynced.items(), 1):
        try:
            # Determine deck (with sub-deck if level is set)
            if course_config['anki']['use_sub_decks'] and note.get('level'):
                target_deck = f"{deck_name}::{note['level']}"
            else:
                target_deck = deck_name

            anki.create_deck(target_deck)

            # Build fields
            fields = {
                course_config['fields']['term']: note.get('term', term),
                course_config['fields']['example']: note.get('example', ''),
                course_config['fields']['notes']: note.get('notes', ''),
            }

            # Add translation/explanation
            if course_config['fields']['translation']:
                trans_key = 'translation' if 'translation' in note else 'explanation'
                fields[course_config['fields']['translation']] = note.get(trans_key, '')

            # Add example translation
            if course_config['fields']['example_translation']:
                fields[course_config['fields']['example_translation']] = note.get('example_translation', '')

            # Add pronunciation if available
            if course_config['fields'].get('pronunciation') and note.get('pronunciation'):
                fields[course_config['fields']['pronunciation']] = note['pronunciation']

            # Add note to Anki
            anki.add_note(
                deck_name=target_deck,
                model_name=course_config['anki']['model_name'],
                fields=fields,
                tags=[sanitize_filename(current_course)]
            )

            # Mark as synced
            notes_data[term]['synced'] = True
            print(f"  [{i}/{len(unsynced)}] {Colors.GREEN}✓{Colors.END} Synced '{term}'")
            synced_count += 1

        except Exception as e:
            print(f"  [{i}/{len(unsynced)}] {Colors.RED}✗{Colors.END} Failed to sync '{term}': {e}")

    # Save updated notes data
    with open(notes_file, 'w', encoding='utf-8') as f:
        json.dump(notes_data, f, indent=2, ensure_ascii=False)

    print()
    print(f"{Colors.GREEN}Sync complete! {synced_count}/{len(unsynced)} notes synced successfully.{Colors.END}")

def cmd_list(args):
    """List recent notes"""
    global_config = load_global_config()
    current_course = global_config.get('current_course')

    if not current_course:
        print(f"{Colors.RED}Error: No course selected. Run 'notes course <name>' first.{Colors.END}")
        return

    notes_file = COURSES_DIR / f"{sanitize_filename(current_course)}_notes.json"
    if not notes_file.exists():
        print(f"{Colors.YELLOW}No notes found for {current_course}.{Colors.END}")
        return

    with open(notes_file, 'r', encoding='utf-8') as f:
        notes_data = json.load(f)

    # Sort by date added (most recent first)
    sorted_notes = sorted(notes_data.items(), key=lambda x: x[1].get('added', ''), reverse=True)

    limit = args.number if hasattr(args, 'number') and args.number else 5
    recent = sorted_notes[:limit]

    print(f"{Colors.BOLD}Recent notes from {current_course}:{Colors.END}")
    print()
    for term, note in recent:
        synced_marker = f"{Colors.GREEN}✓{Colors.END}" if note.get('synced') else f"{Colors.YELLOW}○{Colors.END}"
        print(f"{synced_marker} {Colors.BOLD}{term}{Colors.END}")
        if note.get('translation'):
            print(f"  → {note['translation']}")
        elif note.get('explanation'):
            print(f"  → {note['explanation']}")
        if note.get('level'):
            print(f"  Level: {note['level']}")
        print()

# --- Main CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="General-purpose note-taking CLI with Anki integration and AI enrichment"
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # course command
    parser_course = subparsers.add_parser('course', help='Set or create a course')
    parser_course.add_argument('name', help='Course name (e.g., "French", "Biology", "Python")')

    # level command
    parser_level = subparsers.add_parser('level', help='Set current level/topic within course')
    parser_level.add_argument('level', help='Level or topic name (e.g., "Beginner", "HSK 3", "Chapter 5")')

    # new command
    parser_new = subparsers.add_parser('new', help='Add a new note')
    parser_new.add_argument('phrase', help='The term/concept/phrase to learn')
    parser_new.add_argument('-c', '--context', help='Context or example sentence')
    parser_new.add_argument('-g', '--grammar', help='Grammar points or additional info')

    # sync command
    parser_sync = subparsers.add_parser('sync', help='Sync notes to Anki')

    # list command
    parser_list = subparsers.add_parser('list', help='List recent notes')
    parser_list.add_argument('-n', '--number', type=int, default=5, help='Number of notes to show')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Route to appropriate command
    if args.command == 'course':
        cmd_course(args)
    elif args.command == 'level':
        cmd_level(args)
    elif args.command == 'new':
        cmd_new(args)
    elif args.command == 'sync':
        cmd_sync(args)
    elif args.command == 'list':
        cmd_list(args)

if __name__ == '__main__':
    main()
