import re
import requests
from datetime import datetime, date, timedelta
import time
import config

def get_form_dates(start_date):
    """Get all dates from Sunday to Saturday, representing one complete week"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    date_range = [start + timedelta(days=x) for x in range(0, 7)]

    return "|".join([d.strftime("%Y-%m-%d")for d in date_range])

def post_form(title, dates_str):
    """Trigger w2m creation"""
    data = {
        'NewEventName': title,
        'DateTypes': 'SpecificDates',
        'PossibleDates': dates_str,
        'NoEarlierThan': '4',
        'NoLaterThan': '0',
        'TimeZone': 'America/New_York',
    }

    # response = requests.post(config.new_event_endpoint, cookies=cookies, headers=headers, data=data)
    response = requests.post(config.new_event_endpoint, headers=config.headers, data=data)
    
    try:
        # Tag looks like this in response: <body onload="window.location='./?34071889-83eWy'">, ID is 34071889-83eWy
        w2m_id = re.search(r'window\.location=\'\.\/\?([a-zA-Z0-9-]+)', response.text).group(1) # Get parenthesized subgroup
    except Exception as e:
        print(response.text)
        raise e

    return w2m_id

def format_and_log(links, courses):
    """Format thread content for Slack.
    
    Args:
        links: Dictionary mapping course codes to their w2m links
        courses: List of course codes to be posted
    """

    for title in courses:
        if title == config.last_course_key:
            links[title] = config.last_desc + links[title]
        else:
            links[title] = config.bulk_desc + links[title]

    for key, value in links.items():
        print(key)
        print(value)

    return links

def create_events(start_date, courses):
    """Create the w2m links for specified courses.
    
    Args:
        start_date: Start date string in YYYY-MM-DD format
        courses: List of course codes to create events for
    """
    links = {}
    dates_str = get_form_dates(start_date)

    for title in courses:
        w2m_id = post_form(title, dates_str)
        links[title] = f"{title}: https://www.when2meet.com/?{w2m_id}"
        time.sleep(2)

    return links

def get_next_sunday():
    """Get the next Sunday based on today's date"""
    today = date.today()

    # Sunday is 6 in weekday(): Monday is 0, Sunday is 6
    days_ahead = 6 - today.weekday()
    next_sunday = today + timedelta(days=days_ahead)
    return next_sunday.strftime("%Y-%m-%d")

def generate_slack_thread_content(courses=config.courses):
    """Generate thread content for specified courses.
    
    Args:
        courses: List of course codes to generate thread content for
    """
    sunday = get_next_sunday()
    links = create_events(sunday, courses)
    return format_and_log(links, courses)
