import config
from datetime import datetime, date
import requests
from w2m import generate_slack_thread_content
import time
import re

PREFIX_LEN = 2

def post_to_slack(additional_data):
    """Trigger the actual post to Slack"""
    data = {
        "channel": config.channel_id
    }
    data.update(additional_data)

    headers = {
        "Authorization": f"Bearer {config.slack_bot_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(config.post_message_endpoint, headers=headers, json=data)
    response_json = response.json()

    if not response_json.get('ok'):
        raise RuntimeError(f"Failed: {response_json}")

    return response_json

def get_conversation_history():
    """Get messages sent today in the channel. Checks in UTC time"""
    t = date.today()
    dt = datetime(t.year, t.month, t.day)

    headers = {
        "Authorization": f"Bearer {config.slack_bot_token}"
    }

    data = {
        "channel": config.channel_id,
        "oldest": dt.timestamp()
    }

    response = requests.get(config.get_history_endpoint, headers=headers, params=data)
    response_json = response.json()

    if not response_json.get('ok'):
        raise RuntimeError(f"Failed: {response_json}")
    
    return response_json['messages']

def get_assessment_course_num(course_num):
    """Generate assessment course number"""
    if course_num in ['101', '110', '120', '130', '225', '230', '240', '250']:
        # Assessment number ends in 9
        return course_num[:-1] + '9'
    elif course_num in ['170', '180', '210']:
        return course_num[:-1] + '1'
    elif course_num == '215':
        return '216'
    else:
        return ""

def parse_course_from_message(message_text):
    """Extract course code from a parent post message text.
    
    Args:
        message_text: The text content of a Slack message
        
    Returns:
        str or None: Course code (e.g., 'RB101') if found, None otherwise
    """
    # Message format: "{icon} {prefix} {number} Study Session: Sign Up Here!"
    # or "{icon} {prefix} {number}-{assessment} Study Session: Sign Up Here!"
    # Example: ":ruby: RB 101 Study Session: Sign Up Here!"

    # Special-case: PEDAC has no prefix/number split.
    if re.search(r'\bPEDAC\b\s+Study Session', message_text):
        return 'PEDAC' if 'PEDAC' in config.courses else None

    # Standard pattern: emoji + space + 2-letter prefix + space + 3-digit number
    # + optional "-" + digits + " Study Session"
    pattern = r':\w+:\s+([A-Z]{2})\s+(\d{3})(?:-\d+)?\s+Study Session'
    match = re.search(pattern, message_text)

    if match:
        prefix = match.group(1)
        number = match.group(2)
        course_code = prefix + number
        # Verify it's a valid course code
        if course_code in config.courses:
            return course_code

    return None

def get_posted_status():
    """Check what has already been posted today by parsing messages.
    
    Returns:
        tuple: (posted_courses_set, intro_posted_boolean)
            - posted_courses_set: Set of course codes (e.g., {'RB101', 'JS110'}) that have parent posts today
            - intro_posted_boolean: True if the intro message has been posted today, False otherwise
    """
    messages_today = get_conversation_history()
    posted_courses = set()
    intro_posted = False
    
    # Parse each message from the app today
    for message in messages_today:
        if message.get('app_id') != config.slack_app_id:
            continue
        
        message_text = message.get('text', '')
        if not message_text:
            continue
        
        # Check for intro message
        if 'WEEKLY STUDY SESSION SIGN-UPS' in message_text:
            intro_posted = True
            continue
        
        # Check for course posts
        course_code = parse_course_from_message(message_text)
        if course_code:
            posted_courses.add(course_code)
    
    return posted_courses, intro_posted

def generate_slack_parent_content(courses):
    """Generate content for parent posts on Slack for specified courses.
    
    Args:
        courses: List of course codes to generate content for
        
    Returns:
        dict: Dictionary mapping course codes to their parent post text
    """
    posts = {}

    for course in courses:
        if course == 'PEDAC':
            icon = config.icons['PEDAC']
            posts[course] = f"{icon} PEDAC Study Session: Sign Up Here!"
            continue

        prefix = course[:PREFIX_LEN]
        number = course[PREFIX_LEN:]

        assessment_number = get_assessment_course_num(number)
        icon = config.icons[prefix]

        if not assessment_number:
            posts[course] = f"{icon} {prefix} {number} Study Session: Sign Up Here!"
        else:
            posts[course] = f"{icon} {prefix} {number}-{assessment_number} Study Session: Sign Up Here!"

    return posts

def posts_all_courses():
    """Post all Slack content, skipping courses or other messagesthat have already been posted today."""
    # First, check what's already been posted
    posted_courses, intro_posted = get_posted_status()
    
    # Determine which courses need to be posted
    courses_to_post = [course for course in config.courses if course not in posted_courses]
    
    # If everything is already posted, we're done
    if not courses_to_post and intro_posted:
        return
    
    # Only generate content for courses that need posting
    if courses_to_post:
        parent_content = generate_slack_parent_content(courses_to_post)
        thread_content = generate_slack_thread_content(courses_to_post)
    
    # Post intro message if it hasn't been posted yet
    if not intro_posted:
        post_to_slack({
            "blocks": config.intro_message
        })
    
    # Post courses that haven't been posted yet
    for course in courses_to_post:
        parent = post_to_slack({
            "text": parent_content[course]
        })

        thread_ts = parent['ts']

        post_to_slack({
            "text": thread_content[course],
            "thread_ts": thread_ts
        })

        time.sleep(2)
